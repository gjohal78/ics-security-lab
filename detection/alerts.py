#!/usr/bin/env python3
"""alerts.py — tail Suricata's eve.json and print lab alerts as a clean table.

Suricata writes one JSON object per line to eve.json; many are flow/stats
records. This keeps only `event_type == "alert"` and prints:

    time | attack type | source | destination | rule (sid + signature)

Usage (on the host, from the repo root):
    python3 detection/alerts.py              # follow new alerts as they arrive
    python3 detection/alerts.py --history    # also show alerts already in the file
    python3 detection/alerts.py --no-follow  # print what's there and exit

No dependencies beyond the standard library.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

# Map our rule SIDs (see suricata/rules/local.rules) to short attack labels.
ATTACK_BY_SID = {
    1000001: "Unauthorized write",
    1000002: "Level-sensor spoof",
    1000003: "Write burst/flood",
    1000004: "Register scan",
}

DEFAULT_EVE = Path(__file__).resolve().parent / "suricata" / "logs" / "eve.json"

HEADER = f"{'TIME':<8}  {'ATTACK':<18}  {'SOURCE':<21}  {'DESTINATION':<21}  RULE"


def attack_label(alert: dict) -> str:
    sid = alert.get("signature_id")
    if sid in ATTACK_BY_SID:
        return ATTACK_BY_SID[sid]
    # Unknown rule: fall back to the signature text, trimmed.
    sig = alert.get("signature", "alert")
    return (sig[:17] + "…") if len(sig) > 18 else sig


def format_row(evt: dict) -> str | None:
    if evt.get("event_type") != "alert":
        return None
    alert = evt.get("alert", {})
    # eve timestamp looks like 2026-11-10T20:28:37.123456-0500; keep HH:MM:SS.
    t = evt.get("timestamp", "")
    clock = t[11:19] if len(t) >= 19 else t
    src = f"{evt.get('src_ip', '?')}:{evt.get('src_port', '?')}"
    dst = f"{evt.get('dest_ip', '?')}:{evt.get('dest_port', '?')}"
    sid = alert.get("signature_id", "?")
    return (f"{clock:<8}  {attack_label(alert):<18}  {src:<21}  {dst:<21}  "
            f"sid {sid}")


def follow(path: Path, from_start: bool, keep_following: bool):
    """Yield lines from `path`, optionally from the start, then tail the file."""
    # Wait for the file to appear (Suricata may still be starting).
    waited = False
    while not path.exists():
        if not keep_following:
            print(f"(no eve.json at {path} yet)")
            return
        if not waited:
            print(f"waiting for {path} ...")
            waited = True
        time.sleep(1)

    with path.open("r") as f:
        if not from_start:
            f.seek(0, 2)  # jump to end: only new alerts
        while True:
            line = f.readline()
            if line:
                yield line
                continue
            if not keep_following:
                return
            time.sleep(0.5)


def main() -> None:
    ap = argparse.ArgumentParser(description="Tail Suricata eve.json for lab alerts.")
    ap.add_argument("--eve", type=Path, default=DEFAULT_EVE,
                    help=f"path to eve.json (default: {DEFAULT_EVE})")
    ap.add_argument("--history", action="store_true",
                    help="also print alerts already in the file")
    ap.add_argument("--no-follow", action="store_true",
                    help="print existing alerts and exit instead of tailing")
    args = ap.parse_args()

    keep_following = not args.no_follow
    from_start = args.history or args.no_follow

    print(f"reading alerts from {args.eve}")
    print(HEADER)
    print("-" * len(HEADER))

    count = 0
    try:
        for line in follow(args.eve, from_start, keep_following):
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue  # partial line mid-write; skip it
            row = format_row(evt)
            if row:
                print(row, flush=True)
                count += 1
    except KeyboardInterrupt:
        pass
    if not keep_following:
        print("-" * len(HEADER))
        print(f"{count} alert(s)")


if __name__ == "__main__":
    main()
