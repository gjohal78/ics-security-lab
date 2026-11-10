#!/usr/bin/env python3
"""run_experiments.py — detection vs. prevention across both topologies.

Each attack is run twice:
  * FLAT networking (docker-compose.yml) — one segment, so Suricata sees all
    the traffic. This run measures whether the attack is DETECTED and how long
    detection takes.
  * ZONED networking (docker-compose.segmented.yml) — three zones with the
    firewall conduit. This run measures whether the attack is BLOCKED.

It then writes a results table to docs/results.md.

Columns:
  * detected        — did Suricata raise the attack's rule (flat run)?
  * blocked w/zones — did the firewall drop it (zoned run)?
  * time to detect  — seconds from attack start to the first alert (flat run).

Preconditions:
  * Docker Desktop running; images built once:
      docker compose build
      docker compose -f docker-compose.segmented.yml build
  * The OpenPLC program loaded in each topology. The script tries to start the
    PLC over HTTP; if it can't, it prints what to do. Enabling "Start OpenPLC in
    RUN mode" in each instance makes every reset fully automatic.

The two topologies share host ports 8080/8000, so the script brings one down
before bringing the other up.

NOTE: this harness has not been run end-to-end from here — validate it on your
machine. It only reads results; it never weakens the firewall or the rules.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVE = ROOT / "detection" / "suricata" / "logs" / "eve.json"
RESULTS = ROOT / "docs" / "results.md"

FLAT = ["docker", "compose"]
SEG = ["docker", "compose", "-f", "docker-compose.segmented.yml"]
PLC_IP = {"flat": "172.28.0.10", "seg": "172.30.1.10"}

# attack script -> (primary Suricata sid, human label)
ATTACKS = [
    ("recon.py", 1000004, "recon (register scan)"),
    ("pump_override.py", 1000001, "pump override (unauthorized write)"),
    ("sensor_spoof.py", 1000002, "sensor spoof (level register)"),
    ("replay.py", 1000004, "replay (captured reads)"),
]

DETECT_WINDOW = 20      # seconds to wait for an alert after an attack
ATTACK_TIMEOUT = 40     # seconds cap per attack run


def run(cmd, timeout=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def compose(topo):
    return FLAT if topo == "flat" else SEG


def up(topo):
    """Bring the OTHER topology down (shared ports) then this one up."""
    other = "seg" if topo == "flat" else "flat"
    print(f"[{topo}] stopping the {other} stack, then starting {topo} ...")
    run(compose(other) + ["down"])
    run(compose(topo) + ["up", "-d"])
    time.sleep(8)


def plc_listening(topo) -> bool:
    # Check from the HMI container, which may reach the PLC in both topologies.
    chk = (
        "import socket\n"
        "try:\n"
        f"    socket.create_connection(('{PLC_IP[topo]}', 502), 2).close()\n"
        "    print('UP')\n"
        "except Exception:\n"
        "    print('DOWN')\n"
    )
    r = run(compose(topo) + ["exec", "-T", "hmi", "python", "-c", chk])
    return "UP" in r.stdout


def try_start_plc():
    """Best-effort: log in to OpenPLC and start the PLC over HTTP."""
    base = "http://127.0.0.1:8080"
    jar = "/tmp/oplc.cookies"
    run(["curl", "-s", "-c", jar, "--data",
         "username=openplc&password=openplc", base + "/login"])
    run(["curl", "-s", "-b", jar, base + "/start_plc"])
    time.sleep(3)


def ensure_plc(topo) -> bool:
    for _ in range(6):
        if plc_listening(topo):
            print(f"[{topo}] PLC is serving Modbus on 502")
            return True
        time.sleep(3)
    print(f"[{topo}] PLC not up yet; trying to start it over HTTP ...")
    try_start_plc()
    for _ in range(6):
        if plc_listening(topo):
            print(f"[{topo}] PLC started")
            return True
        time.sleep(3)
    print(f"[{topo}] ERROR: PLC isn't serving Modbus on 502.\n"
          "  Open http://127.0.0.1:8080, upload plc/tank_control.st, click Start\n"
          "  PLC (ideally tick 'Start OpenPLC in RUN mode'), then re-run.")
    return False


def eve_len() -> int:
    if not EVE.exists():
        return 0
    with EVE.open() as f:
        return sum(1 for _ in f)


def firewall_drops() -> int:
    """Packet count on the firewall's ZONE-DROP rule (zoned topology only)."""
    r = run(SEG + ["exec", "-T", "firewall", "iptables", "-nvxL", "ZONE-DROP"])
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "DROP":
            try:
                return int(parts[0])
            except ValueError:
                return 0
    return 0


def run_attack(topo, script):
    try:
        run(compose(topo) + ["exec", "-T", "attacker", "python", script],
            timeout=ATTACK_TIMEOUT)
    except subprocess.TimeoutExpired:
        pass


def detect(sid, since_epoch, baseline_len):
    """First alert with this sid appearing after baseline_len; return latency."""
    deadline = time.time() + DETECT_WINDOW
    while time.time() < deadline:
        if EVE.exists():
            with EVE.open() as f:
                for i, line in enumerate(f):
                    if i < baseline_len:
                        continue
                    line = line.strip()
                    if '"event_type":"alert"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if e.get("alert", {}).get("signature_id") == sid:
                        ts = e.get("timestamp", "")
                        try:
                            at = datetime.strptime(
                                ts, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()
                        except ValueError:
                            at = since_epoch
                        return max(0.0, at - since_epoch)
        time.sleep(0.5)
    return None


def main():
    results = {}

    # ---- FLAT: detection + time-to-detect ----
    up("flat")
    if not ensure_plc("flat"):
        sys.exit(1)
    for script, sid, label in ATTACKS:
        print(f"[flat] {script} ...")
        base = eve_len()
        start = time.time()
        run_attack("flat", script)
        ttd = detect(sid, start, base)
        results[label] = {"detected": ttd is not None, "ttd": ttd, "blocked": None}
        print(f"[flat] {label}: detected={ttd is not None} ttd={ttd}")

    # ---- ZONES: firewall blocking ----
    up("seg")
    ensure_plc("seg")  # attacker is blocked regardless; don't abort if PLC idle
    for script, sid, label in ATTACKS:
        print(f"[seg] {script} ...")
        before = firewall_drops()
        run_attack("seg", script)
        time.sleep(2)
        after = firewall_drops()
        results[label]["blocked"] = after > before
        print(f"[seg] {label}: firewall drops {before} -> {after}")

    write_results(results)
    print(f"\nwrote {RESULTS.relative_to(ROOT)}")


def yn(b):
    return "—" if b is None else ("yes" if b else "no")


def fmt_ttd(t):
    return "—" if t is None else f"{t:.2f} s"


def write_results(results):
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    out = [
        "# Experiment results",
        "",
        f"_Generated by `run_experiments.py` on {now}._",
        "",
        "Each attack ran twice: once on the **flat** network (one segment, so "
        "Suricata sees every packet) and once on the **zoned** lab (three zones "
        "with the firewall conduit). *Detected* and *time to detect* come from "
        "the flat run; *blocked with zones* from the zoned run.",
        "",
        "| Attack | Detected (Suricata) | Blocked with zones | Time to detect |",
        "|---|---|---|---|",
    ]
    for _, _, label in ATTACKS:
        r = results.get(label, {})
        out.append(f"| {label} | {yn(r.get('detected'))} | "
                   f"{yn(r.get('blocked'))} | {fmt_ttd(r.get('ttd'))} |")
    out += [
        "",
        "## How to read this",
        "",
        "- **Detected** is the IDS doing its job on the flat network: Suricata "
        "raises the matching rule for each attack.",
        "- **Blocked with zones** is the firewall conduit doing prevention: the "
        "corporate attacker cannot reach the PLC, so its packets are dropped at "
        "the zone boundary.",
        "- Because the zoned attacker is dropped *before* its packets reach the "
        "supervisory sensor, the zoned IDS does not see it — the firewall log is "
        "the record instead. That is the defence-in-depth split this lab "
        "demonstrates: **detect** on the flat net, **prevent** with zones.",
        "",
    ]
    RESULTS.write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
