#!/bin/bash
# Opt-in host slimming for headless VPS. Run manually:
#   bash /opt/hiddify-manager/common/optimize_host.sh
source "$(dirname "$0")/utils.sh"
for svc in multipathd ModemManager fwupd fwupd-refresh.timer udisks2; do
    if systemctl list-unit-files 2>/dev/null | grep -q "^${svc%.timer}"; then
        systemctl disable --now "$svc" >/dev/null 2>&1 \
            && success "disabled $svc" || warning "could not disable $svc"
    fi
done
warning "Left 'unattended-upgrades' ENABLED (security updates). Disable it only if you patch manually."
