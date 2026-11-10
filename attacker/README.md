# attacker/

Attack scripts that demonstrate how unauthenticated Modbus/TCP lets any host
on the control network read and manipulate the PLC.

> ## ⚠️ SAFETY — ISOLATED LAB USE ONLY
>
> **These scripts attack a PLC. Run them only against this lab's own
> `openplc` container, on the isolated `ics-net` Docker network
> (172.28.0.0/24), on your own machine.**
>
> - **Never** point them at a real PLC, a device on a real network, or any
>   system you do not own. Doing so is almost certainly illegal (e.g. the
>   US Computer Fraud and Abuse Act and equivalents elsewhere) and can cause
>   real physical damage or endanger people.
> - Modbus has no authentication, so these techniques "work" on real
>   equipment. That is exactly why they must stay in the lab.
> - As a guard rail, every script calls `resolve_plc()`, which **refuses to
>   run** unless the target resolves to an address inside `LAB_SUBNET`
>   (172.28.0.0/24). Do not remove that check.
> - The lab network is created by `docker compose` with no route to the
>   outside world. Keep it that way.

## The scripts

Run them from inside the attacker container, which sits on the lab network:

```bash
docker compose exec attacker python recon.py
docker compose exec attacker python pump_override.py
docker compose exec attacker python sensor_spoof.py
docker compose exec attacker python replay.py
```

Each prints what it did, with timestamps. `recon.py` is read-only; the other
three write to the PLC and are detected by the Suricata rule and logged by
Zeek.

| Script | Technique | Effect in the lab |
|---|---|---|
| `recon.py` | ARP sweep + Modbus enumeration | Lists live hosts and dumps the PLC's coils/registers. Read-only. |
| `pump_override.py` | Unauthorized coil write | Forces the pump coil OFF. The PLC re-drives its outputs every scan, so you watch the write get fought. |
| `sensor_spoof.py` | False data injection | Pins the level register at a fake 50 % while the real tank keeps filling. |
| `replay.py` | Capture + replay | Sniffs Modbus to a pcap, then replays the request PDUs — accepted, because Modbus has no session/nonce. |

## What each attack would mean in a real plant

- **recon** — Reconnaissance. On a real network this is the quiet first step:
  find the controllers and learn the register map (which address is a pump,
  a valve, a level) with no credentials and no alarms. Everything after it
  depends on this map. The real-world lesson is that flat, unsegmented OT
  networks hand an attacker the whole process on a plate.

- **pump_override** — Direct command injection to an actuator. In a plant
  the equivalent is forcing a pump, valve, or breaker to a state the operator
  did not choose. The lab shows an important subtlety: writing an *output*
  that the PLC program drives every scan gets overwritten, so a crude write
  often doesn't "stick". Real attacks therefore tend to stop or reprogram the
  PLC, or manipulate *inputs/setpoints* instead — which is what the next
  script does.

- **sensor_spoof** — False data injection, the most dangerous of the four.
  The controller and every operator screen show a safe 50 % while the real
  tank overflows (or a reactor overheats, or a pipeline over-pressures). This
  is the class of attack behind Stuxnet: let the physical process run to a
  damaging state while the humans and the safety logic are told everything is
  fine. It defeats the operator's ability to respond, because they cannot
  trust what they see.

- **replay** — Shows that captured control traffic can simply be resent;
  Modbus has no authentication, timestamps, or nonces to stop it. In a plant,
  replaying a captured *write* (e.g. an "open valve" command) lets an attacker
  issue valid-looking commands without even understanding the protocol, and
  replaying old sensor readings can mask a live change. It underlines why OT
  protocols need authentication or, failing that, strict network segmentation
  and monitoring.

The common thread: Modbus trusts anyone who can reach it. Defense is about
keeping attackers off the control network (segmentation, firewalls), watching
it when they get on (the Suricata/Zeek sensors in `detection/`), and, where
possible, moving to authenticated protocols.
