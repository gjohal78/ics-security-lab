#!/usr/bin/env python3
"""recon.py — discover live hosts on the lab network and enumerate the PLC.

Two stages:
  1. ARP sweep of the lab subnet (scapy) to find live hosts at layer 2.
  2. For the openplc target, read each Modbus table (coils, discrete inputs,
     holding registers, input registers) and print whatever responds.

Read-only: recon only READS. It changes nothing on the PLC. Lab use only.
"""

from __future__ import annotations

import socket

from pymodbus.client import ModbusTcpClient

from lab_target import (LAB_SUBNET, LEVEL_REG, MODBUS_UNIT, PLC_PORT, log,
                        resolve_plc)


def arp_sweep() -> list[tuple[str, str]]:
    """Find live hosts on the lab subnet with an ARP broadcast sweep."""
    log(f"ARP sweep of {LAB_SUBNET} ...")
    try:
        from scapy.all import ARP, Ether, srp
        ans, _ = srp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=str(LAB_SUBNET)),
                     timeout=3, verbose=0)
    except (OSError, PermissionError) as exc:
        log(f"  ARP sweep needs raw-socket privileges (NET_RAW): {exc}")
        return []
    hosts = sorted(((r.psrc, r.hwsrc) for _, r in ans),
                   key=lambda t: tuple(int(x) for x in t[0].split(".")))
    for ip, mac in hosts:
        log(f"  host up: {ip:<15} {mac}")
    return hosts


def port_open(ip: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex((ip, port)) == 0


def enumerate_modbus(ip: str) -> None:
    """Read each Modbus table on the PLC and print what comes back."""
    log(f"enumerating Modbus on {ip}:{PLC_PORT} ...")
    c = ModbusTcpClient(ip, port=PLC_PORT, timeout=2)
    if not c.connect():
        log("  could not open Modbus connection")
        return
    try:
        # (label, read fn, start address, count)
        reads = [
            ("coils          FC1  0-15  ", c.read_coils, 0, 16),
            ("discrete inputs FC2  0-15 ", c.read_discrete_inputs, 0, 16),
            ("holding regs   FC3  1024-34", c.read_holding_registers, LEVEL_REG, 11),
            ("input regs     FC4  0-10  ", c.read_input_registers, 0, 11),
        ]
        for label, fn, addr, count in reads:
            rr = fn(addr, count=count, device_id=MODBUS_UNIT)
            if rr.isError():
                log(f"  {label}: no/err ({rr})")
            elif hasattr(rr, "bits"):
                log(f"  {label}: {[int(b) for b in rr.bits[:count]]}")
            else:
                log(f"  {label}: {rr.registers}")
        log(f"  note: holding reg {LEVEL_REG} (%MW0) is the tank level, "
            "coil 0 (%QX0.0) is the pump — both writable, no auth")
    finally:
        c.close()


def main() -> None:
    ip = resolve_plc()
    log(f"recon start — sanctioned target {ip}")
    hosts = arp_sweep()
    live = [h for h, _ in hosts]
    modbus_hosts = [h for h in live if port_open(h, PLC_PORT)]
    log(f"hosts with Modbus/{PLC_PORT} open: {modbus_hosts or '(none found via sweep)'}")
    # Only ever enumerate the sanctioned lab PLC, whatever the sweep saw.
    enumerate_modbus(ip)
    log("recon done")


if __name__ == "__main__":
    main()
