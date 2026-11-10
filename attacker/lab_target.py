"""Shared target config and helpers for the ics-security-lab attacker scripts.

SAFETY: every script in this folder is hard-scoped to the lab's own isolated
Docker network. The sanctioned target is the `openplc` container only, which
lives on 172.28.0.0/24 inside `docker compose` and is never routed to a real
network. `resolve_plc()` refuses to run if the target does not resolve to an
address inside that lab subnet, so a copy-pasted script cannot be aimed at a
real device by accident.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from datetime import datetime

# --- Target (overridable by env, but still checked against LAB_SUBNET) --------
PLC_HOST = os.getenv("PLC_HOST", "openplc")
PLC_PORT = int(os.getenv("PLC_PORT", "502"))
LAB_SUBNET = ipaddress.ip_network(os.getenv("LAB_SUBNET", "172.28.0.0/24"))
MODBUS_UNIT = int(os.getenv("MODBUS_UNIT", "1"))

# --- Modbus address map (see docs/architecture.md) ----------------------------
PUMP_COIL = 0        # %QX0.0  pump run command
ALARM_HI_COIL = 1    # %QX0.1
ALARM_LO_COIL = 2    # %QX0.2
TRIP_COIL = 3        # %QX0.3  HIHI trip (latched)
RESET_COIL = 4       # %QX0.4  operator reset
LEVEL_REG = 1024     # %MW0    tank level, 0..1000 = 0.0..100.0 %


def ts() -> str:
    """Local timestamp for log lines."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def log(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)


def resolve_plc() -> str:
    """Resolve the PLC host to an IP and refuse anything outside the lab subnet."""
    try:
        ip = socket.gethostbyname(PLC_HOST)
    except socket.gaierror as exc:
        raise SystemExit(f"cannot resolve PLC host {PLC_HOST!r}: {exc}")
    if ipaddress.ip_address(ip) not in LAB_SUBNET:
        raise SystemExit(
            f"REFUSING TO RUN: target {PLC_HOST} ({ip}) is not inside the lab "
            f"subnet {LAB_SUBNET}. These scripts only run against the isolated lab."
        )
    return ip
