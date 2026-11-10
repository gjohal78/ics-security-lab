#!/bin/sh
# ics-security-lab — zone firewall / router.
#
# This container has an interface in all three zones and routes between them.
# Policy (IEC 62443 "conduit"): the ONLY inter-zone flow allowed is the HMI in
# the supervisory zone reading Modbus from the PLC in the control zone. Modbus
# WRITES from the HMI are dropped, the corporate zone (attacker) is dropped
# entirely, and every blocked packet is logged. The simulator writes the PLC
# directly inside the control zone, so it never crosses this firewall.
#
# No `set -e`: if an optional feature (u32 write-filtering) is unavailable in
# the host kernel, the script logs a warning and still enforces zone isolation.

PLC=172.30.1.10          # control
HMI=172.30.2.30          # supervisory
MODBUS_PORT=502

echo "[firewall] enabling IPv4 forwarding"
sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || echo 1 > /proc/sys/net/ipv4/ip_forward

echo "[firewall] resetting tables"
iptables -F
iptables -t nat -F
iptables -X ZONE-DROP 2>/dev/null

# Inter-zone traffic is denied by default; traffic to/from the firewall itself
# (and its own forwarding decisions) is governed by the rules below.
iptables -P FORWARD DROP
iptables -P INPUT ACCEPT
iptables -P OUTPUT ACCEPT

# A chain that logs a packet and then drops it, for visibility.
iptables -N ZONE-DROP
iptables -A ZONE-DROP -j LOG --log-prefix "ZONE-DROP " --log-level 4
iptables -A ZONE-DROP -j DROP

# 1. Let established/return traffic flow (e.g. the PLC's replies to the HMI).
iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# 2. Conduit: supervisory HMI -> control PLC on Modbus/502, READ ONLY.
#    Drop Modbus write function codes (5/6 single, 15/16 multiple, 22/23
#    mask & read-write-multiple) by inspecting the function-code byte at TCP
#    payload offset 7 with the u32 match. Best-effort: if xt_u32 is missing the
#    rule fails to load, we warn, and zone isolation below still holds.
U32_OK=1
for fc in "5:6" "15:16" "22:23"; do
    if ! iptables -A FORWARD -s "$HMI" -d "$PLC" -p tcp --dport "$MODBUS_PORT" \
            -m u32 --u32 "0>>22&0x3C@12>>26&0x3C@4&0xFF=$fc" -j ZONE-DROP 2>/dev/null; then
        U32_OK=0
    fi
done
[ "$U32_OK" = 1 ] \
    && echo "[firewall] Modbus write-filtering active (HMI may read, not write)" \
    || echo "[firewall] WARN: xt_u32 unavailable — HMI write-filtering disabled; zone isolation still enforced"

# 3. Allow the rest of HMI -> PLC:502 (the TCP handshake and read requests).
iptables -A FORWARD -s "$HMI" -d "$PLC" -p tcp --dport "$MODBUS_PORT" -j ACCEPT

# 4. SNAT that conduit so the PLC sees the firewall (a control-zone address) as
#    the source and can reply without needing a route back to the supervisory
#    zone. The firewall un-NATs the replies from conntrack.
iptables -t nat -A POSTROUTING -s "$HMI" -d "$PLC" -p tcp --dport "$MODBUS_PORT" -j MASQUERADE

# 5. Everything else between zones (the attacker, HMI non-Modbus, etc.): drop + log.
iptables -A FORWARD -j ZONE-DROP

echo "[firewall] FORWARD policy:"
iptables -S FORWARD
echo "[firewall] NAT POSTROUTING:"
iptables -t nat -S POSTROUTING

echo "[firewall] up. Reporting blocked-packet counts every 15s (also see 'ZONE-DROP' in host dmesg)."
while true; do
    sleep 15
    DROPPED=$(iptables -nvxL ZONE-DROP 2>/dev/null | awk '/DROP/{print $1; exit}')
    echo "[firewall $(date -u +%H:%M:%S)] packets blocked by zone policy: ${DROPPED:-0}"
done
