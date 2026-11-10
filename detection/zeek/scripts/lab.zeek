# ics-security-lab — Zeek customization.
#
# Zeek's Modbus analyzer is built in. Loading it here makes the setup explicit:
# it dissects Modbus/TCP on port 502 and writes modbus.log (one row per
# request/response, with function code, unit id and PDU type) into Zeek's
# working directory, which docker-compose.yml mounts to detection/zeek/logs.
#
# Zeek and Suricata are complementary here: Suricata alerts on the attacks
# (alerts.py reads those), while Zeek keeps the full, neutral record of every
# Modbus transaction for after-the-fact investigation.
@load base/protocols/modbus
