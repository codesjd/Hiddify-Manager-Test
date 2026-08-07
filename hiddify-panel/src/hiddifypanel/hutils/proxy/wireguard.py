def _conf_value(value) -> str:
    """WireGuard's .conf format is line-oriented - a newline inside any
    interpolated field would let it inject an entirely new directive
    (e.g. PostUp/PostDown, which wg-quick runs as shell commands on
    whoever's machine imports this profile). Strip CR/LF so a value can
    never span past the single line it belongs on."""
    return str(value).replace("\r", "").replace("\n", "")


def generate_wireguard_config(proxy: dict) -> str:
    """
    Generates a WireGuard configuration from a given proxy dictionary.

    Args:
        proxy (dict): Dictionary containing WireGuard and proxy details.

    Returns:
        str: A WireGuard configuration string.
    """
    name = _conf_value(f'{proxy["extra_info"]} {proxy["name"]}')
    addrs = _conf_value(f"{proxy['wg_ipv4']}/32")
    if proxy["wg_ipv6"]:
        addrs += f", {_conf_value(proxy['wg_ipv6'])}/128"
    config = f"""[Interface]
# Name = {name}
Address= {addrs}
PrivateKey = {_conf_value(proxy["wg_pk"])}
MTU = {_conf_value(proxy.get("mtu", 1380))}
DNS = {_conf_value(proxy.get("dns", "1.1.1.1"))}

[Peer]
# Name = Public Peer for {name}
Endpoint = {_conf_value(proxy["server"])}:{_conf_value(proxy["port"])}
PublicKey = {_conf_value(proxy["wg_server_pub"])}
PresharedKey = {_conf_value(proxy['wg_psk'])}
AllowedIPs = {_conf_value(proxy.get("allowed_ips", "0.0.0.0/0, ::/0"))}
PersistentKeepalive = {_conf_value(proxy.get("keep_alive", 25))}
"""

    return config
