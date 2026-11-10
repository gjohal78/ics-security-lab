# plc/

PLC logic for the water tank, in IEC 61131-3 Structured Text.

- `tank_control.st`: hysteresis pump control (ON > 70 %, OFF < 30 %),
  HI/LO alarms (85 % / 15 %), and a latched HIHI trip at 95 % that forces
  the pump on until an operator reset.
- `tests/`: compiles the program with matiec (OpenPLC's ST compiler) and
  runs it scan-by-scan through test scenarios: `./tests/run_tests.sh`

The OpenPLC runtime is built from the official
[OpenPLC_v3](https://github.com/thiagoralves/OpenPLC_v3) repo by `docker-compose.yml`.
Upload the program through the web UI at http://127.0.0.1:8080 (default login
`openplc` / `openplc`; change it).

Addresses are listed in [docs/architecture.md](../docs/architecture.md#modbus-address-map).
