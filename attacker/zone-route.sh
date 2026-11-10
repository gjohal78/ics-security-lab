#!/bin/sh
# zone-route.sh — in the segmented lab, route to peer zones via the firewall.
#
# ZONE_GW        = the firewall's address in THIS container's zone
# ZONE_PEER_NETS = space-separated subnets to reach through it
#
# Both are set only by docker-compose.segmented.yml. In the flat single-network
# lab they are unset and this is a no-op, so the same image works in both.
if [ -n "$ZONE_GW" ] && [ -n "$ZONE_PEER_NETS" ]; then
    for net in $ZONE_PEER_NETS; do
        if ip route replace "$net" via "$ZONE_GW" 2>/dev/null; then
            echo "[zone-route] $net via $ZONE_GW"
        else
            echo "[zone-route] WARN: could not route $net via $ZONE_GW (need NET_ADMIN)" >&2
        fi
    done
fi
exec "$@"
