source /opt/hiddify-manager/common/utils.sh

# L2TP/IPsec = strongSwan (IPsec transport-mode encryption, PSK auth) +
# xl2tpd (the L2TP tunnel that runs inside it) + pppd (per-user CHAP auth,
# pulled in as an xl2tpd dependency). strongswan-starter is the legacy
# stroke/ipsec.conf daemon - modern strongSwan split it out from the
# swanctl-based `strongswan` package, and the whole L2TP/IPsec ecosystem
# (and every client-side how-to) is written against the classic
# /etc/ipsec.conf + `ipsec` CLI that strongswan-starter provides.
#
# NOTE: PPTP is deliberately NOT offered - its MS-CHAPv2 auth has been
# publicly breakable since 2012, so shipping it in a censorship-circumvention
# tool would be actively harmful. L2TP/IPsec with a strong PSK is dated but
# not cryptographically broken, and every stock OS (Windows/macOS/iOS/
# Android) has a built-in client for it.
install_package strongswan strongswan-starter xl2tpd

# L2TP clients get an internal 10.x address and reach the internet NAT'd out
# the server's public NIC - same forwarding requirement WireGuard has.
echo "net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1" >/etc/sysctl.d/l2tp.conf
if [ "$MODE" != "docker" ]; then
    sysctl --system >/dev/null
fi

# xl2tpd hands every session off to pppd, which needs the kernel's
# ppp_generic module and /dev/ppp. Some container-based VPS products
# (OpenVZ, some restricted LXC profiles) don't allow loading kernel modules
# and never expose /dev/ppp - on those hosts xl2tpd installs fine but can
# never actually start a tunnel. Try to load the module now and warn clearly
# here (install time) instead of failing silently/looking like an unrelated
# install error later when run.sh starts the service.
modprobe ppp_generic >/dev/null 2>&1 || true
modprobe pppol2tp >/dev/null 2>&1 || true
if [ ! -e /dev/ppp ]; then
    warning "L2TP/IPsec: /dev/ppp is not available in this environment (common on some container-based VPS). xl2tpd will be installed but left stopped - L2TP/IPsec will not work on this server."
fi
