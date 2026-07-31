# Runs when there are no enabled Outbounds with Protocol=amneziawg left at
# all (see install.sh's has_amneziawg_outbound check) - tear down every
# awg-quick interface this module ever brought up, whatever it's named.
for unit in $(systemctl list-units --all --plain --no-legend 'awg-quick@awg*.service' 2>/dev/null | awk '{print $1}'); do
    systemctl stop --now "$unit" >/dev/null 2>&1
    systemctl disable "$unit" >/dev/null 2>&1
done
rm -f /etc/amnezia/amneziawg/awg*.conf
