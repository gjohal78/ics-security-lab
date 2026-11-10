# detection/

Network monitoring for the lab. Both sensors run in the **host** network
namespace and sniff the lab bridge `br-ics` directly, because a container on a
Docker bridge only sees its own traffic.

- **Suricata** — Modbus app-layer parser on, custom rules in
  `suricata/rules/local.rules`, alerts written to `suricata/logs/eve.json`.
- **Zeek** — built-in Modbus analyzer (`zeek/scripts/lab.zeek`) writing a full
  transaction record to `zeek/logs/modbus.log`.
- **alerts.py** — tails `eve.json` and prints a clean table of attacks.

```bash
python3 detection/alerts.py --history     # show past + live alerts
docker compose exec attacker python recon.py   # (in another terminal) trigger some
```

## How Suricata is configured

`docker-compose.yml` runs Suricata with:

```
-i br-ics                                        sniff the lab bridge
-S /etc/suricata/rules/local.rules               load ONLY our rules (no noise)
--set app-layer.protocols.modbus.enabled=yes     turn on the Modbus parser
```

The Modbus parser is what lets rules match on `modbus:` fields (function,
read/write, register address) instead of raw bytes. `eve.json` output is on by
default in the image's `suricata.yaml`.

## The rules, line by line

Lab addresses: PLC `172.28.0.10:502`, simulator `172.28.0.20` (the only
legitimate writer), HMI `172.28.0.30` (reads only), attacker `172.28.0.66`.

Every rule has the same shape:

```
alert modbus <src> any -> 172.28.0.10 502 ( ...options... )
```

- `alert modbus` — action `alert`, and match only flows the parser has
  identified as **Modbus** (so the `modbus:` keyword below is available).
- `<src> any -> 172.28.0.10 502` — from this source (any source port), to the
  PLC on 502. `->` is one-directional (client → PLC).

### Rule 1 — unauthorized write (sid 1000001)
```
alert modbus !172.28.0.20 any -> 172.28.0.10 502 ( \
  msg:"... Unauthorized Modbus write ..."; \
  flow:to_server,established; \
  modbus:access write; \
  classtype:attempted-admin; sid:1000001; rev:1; \
  metadata:attack unauthorized_write;)
```
- `!172.28.0.20` — source is **not** the simulator. Only the simulator should
  write, so anyone else writing is unauthorized.
- `flow:to_server,established` — only the request direction on an established
  TCP session (ignores the PLC's replies).
- `modbus:access write` — any write function (FC5 coil, FC6 register, FC15/16
  multiple). Catches both `pump_override` (coil) and `sensor_spoof` (register).
- `classtype` / `sid` / `rev` — alert category, unique rule id, revision.
- `metadata:attack …` — a label surfaced in `eve.json`.

### Rule 2 — level-register spoof (sid 1000002)
Same header as rule 1, but:
- `modbus:access write holding, address 1024` — a write specifically to
  **holding register 1024** (`%MW0`, the tank level). This is the sensor-spoof
  signature. It is a stricter subset of rule 1, so a level spoof trips both — a
  generic "unauthorized write" and the specific "someone is faking the level",
  which is the one an operator cares about.

### Rule 3 — write burst / flood (sid 1000003)
Same as rule 1 (`modbus:access write` from non-simulator) plus:
- `detection_filter:track by_src, count 15, seconds 2` — stay silent until the
  same source sends **more than 15 writes in 2 seconds**, then alert. Separates
  a rapid override/flood (`sensor_spoof` at ~10/s) from an occasional write.

### Rule 4 — register scan / recon (sid 1000004)
```
alert modbus ![172.28.0.20,172.28.0.30] any -> 172.28.0.10 502 ( \
  ... modbus:access read; ... sid:1000004; ...)
```
- `![172.28.0.20,172.28.0.30]` — source is neither the simulator nor the HMI,
  the only two hosts that legitimately read the PLC.
- `modbus:access read` — any read function. A read from anyone else is
  reconnaissance; this catches `recon.py` enumerating the Modbus tables.

## Zeek

`zeek/scripts/lab.zeek` loads the built-in Modbus analyzer, which writes
`modbus.log`: one row per transaction with the function code, unit id and PDU
type. Suricata answers "is this an attack?"; Zeek keeps the complete, neutral
record for investigating what happened.
