# Attacker workstation.
# Idle box you exec into to run the attack scripts against the lab PLC.
FROM python:3.12-slim

# Network tools + libpcap for scapy; iproute2 for the zone-route entrypoint.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iputils-ping netcat-openbsd tcpdump libpcap0.8 iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Pinned to match the rest of the lab (3.x `device_id=` keyword).
RUN pip install --no-cache-dir "pymodbus==3.16.2" "scapy==2.5.0"

WORKDIR /attacks
COPY . .
RUN chmod +x zone-route.sh

# Runs as root (an attacker box) so scapy can open raw sockets; the compose
# file grants only NET_RAW/NET_ADMIN. zone-route.sh sets routing (no-op in the
# flat lab) then runs the idle command.
ENTRYPOINT ["/attacks/zone-route.sh"]
CMD ["sleep", "infinity"]
