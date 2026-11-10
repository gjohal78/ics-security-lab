# Experiment results

_This table is produced by `run_experiments.py`. The values below are the
outcomes verified during development; run the harness to regenerate it with
measured time-to-detect on your machine._

Each attack is run twice: once on the **flat** network (one segment, so Suricata
sees every packet) and once on the **zoned** lab (three zones with the firewall
conduit). *Detected* and *time to detect* come from the flat run; *blocked with
zones* from the zoned run.

| Attack | Detected (Suricata) | Blocked with zones | Time to detect |
|---|---|---|---|
| recon (register scan) | yes | yes | _run harness_ |
| pump override (unauthorized write) | yes | yes | _run harness_ |
| sensor spoof (level register) | yes | yes | _run harness_ |
| replay (captured reads) | yes | yes | _run harness_ |

Detection was confirmed by the Suricata alerts in `eve.json` (sids 1000001–1000004
all fired on the flat network); blocking was confirmed by the firewall's
ZONE-DROP counter rising while the attacker could not reach the PLC. Run
`python3 run_experiments.py` to repopulate the table — including the measured
time-to-detect for each attack.

## How to read this

- **Detected** is the IDS doing its job on the flat network: Suricata raises the
  matching rule for each attack.
- **Blocked with zones** is the firewall conduit doing prevention: the corporate
  attacker cannot reach the PLC, so its packets are dropped at the zone boundary.
- Because the zoned attacker is dropped *before* its packets reach the
  supervisory sensor, the zoned IDS does not see it — the firewall log is the
  record instead. That is the defence-in-depth split this lab demonstrates:
  **detect** on the flat net, **prevent** with zones.

## Running it

```bash
# one-time: build both topologies' images
docker compose build
docker compose -f docker-compose.segmented.yml build

# then run the experiment (brings each topology up in turn; a few minutes)
python3 run_experiments.py
```

The two topologies share host ports 8080/8000, so the harness brings one down
before the other up. It needs the OpenPLC program loaded in each instance; it
tries to start the PLC over HTTP and tells you what to do if it can't.
