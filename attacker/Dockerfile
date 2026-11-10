# Attacker workstation.
# Idle box you exec into to run the attack scripts against the lab PLC.
FROM python:3.12-slim

# Network tools + libpcap for scapy's sniffing/ARP.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iputils-ping netcat-openbsd tcpdump libpcap0.8 \
    && rm -rf /var/lib/apt/lists/*

# Pinned to match the rest of the lab (3.x `device_id=` keyword).
RUN pip install --no-cache-dir "pymodbus==3.16.2" "scapy==2.5.0"

WORKDIR /attacks
COPY . .

# Runs as root (an attacker box) so scapy can open raw sockets; the compose
# file still grants only NET_RAW/NET_ADMIN, nothing more.
CMD ["sleep", "infinity"]
