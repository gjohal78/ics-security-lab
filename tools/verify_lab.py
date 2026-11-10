"""End-to-end health check for ics-security-lab (read-only).

Runs inside the attacker container (it has pymodbus and sits on ics-net):
    make verify
It only READS from the PLC: it never writes coils or registers.

Watches the PLC for up to WATCH_SECONDS and checks that:
  1. OpenPLC answers Modbus/TCP on port 502
  2. the level register (%MW0) is changing, i.e. the simulator is feeding it
  3. pump, alarms and trip coils agree with the control rules
  4. the pump completes an ON -> OFF cycle at the 70 % / 30 % setpoints
"""

import os
import sys
import time

from pymodbus.client import ModbusTcpClient

PLC_HOST = os.getenv("PLC_HOST", "openplc")
PLC_PORT = int(os.getenv("PLC_PORT", "502"))
LEVEL_REG = 1024          # %MW0
COILS = 5                 # %QX0.0 .. %QX0.4
WATCH_SECONDS = 60        # one full pump cycle is ~33 s with default rates
SAMPLE_PERIOD = 0.25
# The register and coils are read in two requests, and the level moves a
# little between them; ignore rule checks this close to a threshold.
MARGIN = 10               # raw units = 1.0 %

results = []


def report(ok, msg):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {msg}")


def read(client):
    rr = client.read_holding_registers(LEVEL_REG, count=1)
    rc = client.read_coils(0, count=COILS)
    if rr.isError() or rc.isError():
        raise RuntimeError(f"Modbus error: {rr if rr.isError() else rc}")
    pump, hi, lo, trip, reset = (bool(b) for b in rc.bits[:COILS])
    return rr.registers[0], pump, hi, lo, trip


def near(level, threshold):
    return abs(level - threshold) <= MARGIN


def main():
    client = ModbusTcpClient(PLC_HOST, port=PLC_PORT, timeout=2)
    if not client.connect():
        report(False, f"cannot connect to {PLC_HOST}:{PLC_PORT}; is OpenPLC up and the program started (Start PLC)?")
        return
    report(True, f"connected to OpenPLC Modbus at {PLC_HOST}:{PLC_PORT}")

    rule_errors, levels = [], []
    pump_on_levels, pump_off_levels = [], []
    trip_seen = False
    prev_pump = None
    deadline = time.monotonic() + WATCH_SECONDS
    print(f"watching for up to {WATCH_SECONDS}s (stops early after a full pump cycle)...")

    while time.monotonic() < deadline:
        level, pump, hi, lo, trip = read(client)
        levels.append(level)
        trip_seen |= trip

        # Rule checks (skipped right at a threshold, see MARGIN).
        if not near(level, 850) and hi != (level >= 850):
            rule_errors.append(f"HI alarm={hi:d} at level {level / 10:.1f}%")
        if not near(level, 150) and lo != (level <= 150):
            rule_errors.append(f"LO alarm={lo:d} at level {level / 10:.1f}%")
        if not trip:
            if level > 700 + MARGIN and not pump:
                rule_errors.append(f"pump OFF at {level / 10:.1f}% (should be ON above 70%)")
            if level < 300 - MARGIN and pump:
                rule_errors.append(f"pump ON at {level / 10:.1f}% (should be OFF below 30%)")

        # Record where the pump switches.
        if prev_pump is not None and pump != prev_pump:
            (pump_on_levels if pump else pump_off_levels).append(level)
            print(f"  pump -> {'ON ' if pump else 'OFF'} at level {level / 10:.1f}%")
        prev_pump = pump

        if pump_on_levels and pump_off_levels:
            break
        time.sleep(SAMPLE_PERIOD)

    client.close()

    span = max(levels) - min(levels)
    report(span >= 20, f"level is changing ({min(levels) / 10:.1f}% .. {max(levels) / 10:.1f}%), simulator is feeding %MW0"
           if span >= 20 else "level is not changing; is the simulator running and is the PLC started?")
    report(not rule_errors, "pump/alarm coils follow the control rules" if not rule_errors
           else f"{len(rule_errors)} rule violation(s), first: {rule_errors[0]}")
    report(not trip_seen, "no HIHI trip latched" if not trip_seen
           else "HIHI trip is latched (coil 3); write coil 4 to reset once level < 95%")

    on_ok = bool(pump_on_levels) and all(near(lv, 700) for lv in pump_on_levels)
    off_ok = bool(pump_off_levels) and all(near(lv, 300) for lv in pump_off_levels)
    report(on_ok, f"pump switched ON at ~70% ({', '.join(f'{v/10:.1f}%' for v in pump_on_levels) or 'not seen'})")
    report(off_ok, f"pump switched OFF at ~30% ({', '.join(f'{v/10:.1f}%' for v in pump_off_levels) or 'not seen'})")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # report, don't traceback, for a readable summary
        report(False, f"check aborted: {exc}")
    print(f"\n{'ALL CHECKS PASSED' if results and all(results) else 'SOME CHECKS FAILED'}")
    sys.exit(0 if results and all(results) else 1)
