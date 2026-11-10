# Attacker workstation (stub).
# Kept idle; you exec into it to run tools against the lab network.
FROM python:3.12-slim

# Basic network tools; more (e.g. nmap) can be added when attacks are written.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "pymodbus>=3.6,<4"

WORKDIR /attacks
CMD ["sleep", "infinity"]
