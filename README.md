# ics-security-lab

A Docker-based industrial control system (ICS) security lab: an OpenPLC
controller runs a simulated water tank, an HMI displays it, an attacker
container goes after it over Modbus/TCP, and Suricata + Zeek watch the traffic.

> **Lab use only.** Everything runs on isolated Docker networks on your own
> machine. Never point the attacker tooling at real networks or devices.

## Layout

```
plc/         PLC program (Structured Text)
simulator/   Python water-tank simulator (Modbus client)
hmi/         Web HMI
attacker/    Attack scripts (recon, pump override, sensor spoof, replay) - see attacker/README.md SAFETY note
detection/   Suricata rules/logs, Zeek logs
docs/        Architecture and write-ups
```

## Quick start

```bash
make up      # build and start everything
make logs    # follow logs (make logs S=simulator for one service)
make down    # stop
make reset   # stop, delete volumes and detection logs
make verify  # check the PLC/simulator loop end to end (~30-60 s)
```

- OpenPLC UI: http://127.0.0.1:8080
- HMI: http://127.0.0.1:8000

Requires Docker with Compose v2. Suricata and Zeek sniff the `br-ics` bridge
from the host network namespace (works on Linux and Docker Desktop).

## Status

Working lab: PLC, simulator, HMI, attacker scripts, and Suricata/Zeek detection.

## License

MIT, see [LICENSE](LICENSE).
