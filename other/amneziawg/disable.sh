# Runs when there are no enabled Outbounds with Protocol=amneziawg AND the
# client-facing interface is off (see hiddify.py's has_amneziawg_outbound,
# which now covers both) - tear down every awg-quick interface this module
# ever brought up, whatever it's named, including the shared client-facing
# hiddifyawg interface.
for unit in $(systemctl list-units --all --plain --no-legend 'awg-quick@awg*.service' 2>/dev/null | awk '{print $1}'); do
    systemctl stop --now "$unit" >/dev/null 2>&1
    systemctl disable "$unit" >/dev/null 2>&1
done
rm -f /etc/amnezia/amneziawg/awg*.conf

systemctl stop --now awg-quick@hiddifyawg >/dev/null 2>&1
systemctl disable awg-quick@hiddifyawg >/dev/null 2>&1
rm -f /etc/amnezia/amneziawg/hiddifyawg.conf
