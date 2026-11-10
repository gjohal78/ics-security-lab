# Architecture

| Service   | IP           | Role                                   |
|-----------|--------------|----------------------------------------|
| openplc   | 172.28.0.10  | PLC, Modbus/TCP server on 502          |
| simulator | 172.28.0.20  | Water tank physics, Modbus client      |
| hmi       | 172.28.0.30  | Operator web view, Modbus client       |
| attacker  | 172.28.0.66  | Attack tooling                         |
| suricata  | host netns   | IDS, sniffs bridge `br-ics`            |
| zeek      | host netns   | Network logging, sniffs bridge `br-ics`|

All lab containers share one bridge network (`ics-net`, 172.28.0.0/24) for now.

## Modbus address map

OpenPLC_v3 uses a fixed mapping from IEC addresses to Modbus data addresses
(0-based). The values the lab uses:

| Signal        | IEC address | Modbus table      | Address | Written by | Notes                    |
|---------------|-------------|-------------------|---------|------------|--------------------------|
| Pump command  | `%QX0.0`    | Coil              | 0       | PLC        | 1 = pump running         |
| Tank level    | `%MW0`      | Holding register  | 1024    | simulator  | 0-1000 = 0.0-100.0 %     |
| HI alarm      | `%QX0.1`    | Coil              | 1       | PLC        | level >= 85 %            |
| LO alarm      | `%QX0.2`    | Coil              | 2       | PLC        | level <= 15 %            |
| HIHI trip     | `%QX0.3`    | Coil              | 3       | PLC        | latched at >= 95 %       |
| Operator reset| `%QX0.4`    | Coil              | 4       | HMI        | write 1; PLC clears it   |

Why `%MW0` and not an input register (`%IW`): Modbus input registers are
read-only for clients, so the simulator couldn't write one. `%MW` is a
read/write holding register the PLC program can read like a sensor value.
All `%QX` coils are writable by any Modbus client; the PLC recomputes
outputs every scan, so only `op_reset` is meant to be written externally.
Coil address = byte × 8 + bit, so `%QX0.1` would be coil 1, `%QX1.0` coil 8.
