source /opt/hiddify-manager/common/utils.sh

cd "$(dirname -- "$0")" || exit 1

# The .j2 templates in this dir were already rendered to their plain
# counterparts by common/jinja.py before run.sh is called; copy each config
# into the location its daemon actually reads.
mkdir -p /etc/xl2tpd /etc/ppp
install -m 600 ipsec.conf     /etc/ipsec.conf
install -m 600 ipsec.secrets  /etc/ipsec.secrets
install -m 644 xl2tpd.conf     /etc/xl2tpd/xl2tpd.conf
install -m 644 options.xl2tpd  /etc/ppp/options.xl2tpd
# chap-secrets holds every user's secret in plaintext - keep it 600.
install -m 600 chap-secrets     /etc/ppp/chap-secrets

# NAT the L2TP pool out the public NIC so tunnelled clients reach the
# internet, same masquerade WireGuard sets up for its own pool. -C checks
# first so re-running Apply Configs doesn't stack duplicate rules.
SERVER_PUB_NIC="$(ip -4 route ls | grep default | grep -Po '(?<=dev )(\S+)' | head -1)"
L2TP_POOL="10.92.0.0/24"
if [ -n "$SERVER_PUB_NIC" ]; then
    iptables -t nat -C POSTROUTING -s "$L2TP_POOL" -o "$SERVER_PUB_NIC" -j MASQUERADE 2>/dev/null \
        || iptables -t nat -A POSTROUTING -s "$L2TP_POOL" -o "$SERVER_PUB_NIC" -j MASQUERADE
fi
iptables -C FORWARD -s "$L2TP_POOL" -j ACCEPT 2>/dev/null || iptables -A FORWARD -s "$L2TP_POOL" -j ACCEPT
iptables -C FORWARD -d "$L2TP_POOL" -j ACCEPT 2>/dev/null || iptables -A FORWARD -d "$L2TP_POOL" -j ACCEPT

# strongSwan's systemd unit is "strongswan-starter" on modern Debian/Ubuntu
# (the legacy stroke/ipsec.conf daemon) and plain "strongswan" on older
# ones - enable/restart whichever exists. The `ipsec` CLI shipped by
# strongswan-starter reloads the SAs from the config we just wrote.
systemctl enable strongswan-starter >/dev/null 2>&1 || systemctl enable strongswan >/dev/null 2>&1
systemctl restart strongswan-starter >/dev/null 2>&1 || systemctl restart strongswan >/dev/null 2>&1
ipsec reload >/dev/null 2>&1 || true

systemctl enable xl2tpd >/dev/null 2>&1
systemctl restart xl2tpd
