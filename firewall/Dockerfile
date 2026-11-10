# Zone firewall / router for ics-security-lab.
FROM alpine:3.20

# iptables userspace (incl. the u32 and conntrack extensions).
RUN apk add --no-cache iptables ip6tables

COPY firewall.sh /firewall.sh
RUN chmod +x /firewall.sh

# Needs NET_ADMIN (granted in docker-compose) to program iptables and forward.
ENTRYPOINT ["/firewall.sh"]
