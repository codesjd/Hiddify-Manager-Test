# Called by install_run when l2tp_enable is 0/false. Stop and disable both
# daemons; leave the rendered config files and NAT rules in place (harmless
# when the services are down, and re-enabling shouldn't need a full
# reinstall to restore them).
systemctl stop xl2tpd strongswan-starter strongswan >/dev/null 2>&1
systemctl disable xl2tpd strongswan-starter strongswan >/dev/null 2>&1
ipsec stop >/dev/null 2>&1 || true
