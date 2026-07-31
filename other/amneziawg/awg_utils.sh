
SERVER_AWG_NIC=hiddifyawg

# Duplicated from other/wireguard/wg_utils.sh rather than sourced from there -
# install_run() pushd's into this subsystem's own directory (see install.sh's
# runsh()), so a relative source across sibling other/ directories would be
# fragile, and the two subsystems are meant to be independently
# enable/disable-able.
add_number_to_ipv4() {
    local ip="$1"
    local number="$2"

    IFS='.' read -r -a octets <<<"$ip"

    octets[2]=$(((${octets[2]} + (${octets[3]} + number) / 256)))
    octets[3]=$(((${octets[3]} + number) % 256))

    echo "${octets[0]}.${octets[1]}.${octets[2]}.$((octets[3]))"
}

add_number_to_ipv6() {
    local ip="$1"
    local number="$2"

    IFS=':' read -r -a segments <<<"$ip"

    segments[${#segments[@]} - 1]=$((0x${segments[${#segments[@]} - 1]} + number))

    local modified_ipv6=$(
        IFS=:
        echo "${segments[*]}"
    )
    echo "$modified_ipv6"
}
