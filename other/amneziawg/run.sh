source /opt/hiddify-manager/common/utils.sh

# Deliberately reading amneziawg_config via hconfig at runtime (not baked
# into a .j2 template) so the pasted conf content is never interpolated
# into a shell command - it's only ever written straight to a file.
CONFIG_CONTENT=$(hconfig "amneziawg_config")

mkdir -p /etc/amnezia/amneziawg

if [ -z "$CONFIG_CONTENT" ]; then
    echo "AmneziaWG is enabled but no config has been pasted into Settings > AmneziaWG yet - not bringing up the interface."
    systemctl disable --now awg-quick@hiddify0 >/dev/null 2>&1
    exit 0
fi

echo "$CONFIG_CONTENT" >/etc/amnezia/amneziawg/hiddify0.conf
chmod 600 /etc/amnezia/amneziawg/hiddify0.conf

systemctl enable awg-quick@hiddify0 >/dev/null 2>&1
systemctl restart awg-quick@hiddify0
sleep .5
if systemctl is-active --quiet awg-quick@hiddify0; then
    success "AmneziaWG interface hiddify0 is up."
else
    warning "AmneziaWG interface hiddify0 failed to start - check: journalctl -u awg-quick@hiddify0"
fi
