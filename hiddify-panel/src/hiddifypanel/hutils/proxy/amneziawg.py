def _conf_value(value) -> str:
    """AmneziaWG/WireGuard's .conf format is line-oriented - a newline
    inside any interpolated field would let it inject an entirely new
    directive (e.g. PostUp/PostDown, which wg-quick runs as shell commands
    on whoever's machine imports this profile). Strip CR/LF so a value can
    never span past the single line it belongs on."""
    return str(value).replace('\r', '').replace('\n', '')


def generate_amneziawg_config(proxy: dict) -> str:
    """
    Generates an AmneziaWG configuration from a given proxy dictionary.

    Mirrors generate_wireguard_config() (same [Interface]/[Peer] shape,
    since AmneziaWG is wire-compatible WireGuard plus the Jc/Jmin/Jmax
    obfuscation lines), for a genuine AmneziaWG-capable client - a plain
    WireGuard client can still load this file but will fail the handshake
    unless the server's Jc/Jmin/Jmax are all left unset.

    Args:
        proxy (dict): Dictionary containing AmneziaWG and proxy details.

    Returns:
        str: An AmneziaWG configuration string.
    """
    name = _conf_value(f'{proxy["extra_info"]} {proxy["name"]}')
    addrs = _conf_value(f"{proxy['wg_ipv4']}/32")
    if proxy['wg_ipv6']:
        addrs += f", {_conf_value(proxy['wg_ipv6'])}/128"
    obfuscation_lines = ""
    for key, label in [
        ("awg_jc", "Jc"), ("awg_jmin", "Jmin"), ("awg_jmax", "Jmax"),
        ("awg_h1", "H1"), ("awg_h2", "H2"), ("awg_h3", "H3"), ("awg_h4", "H4"),
        ("awg_s1", "S1"), ("awg_s2", "S2"), ("awg_s3", "S3"), ("awg_s4", "S4"),
        ("awg_i1", "I1"), ("awg_i2", "I2"), ("awg_i3", "I3"), ("awg_i4", "I4"), ("awg_i5", "I5"),
    ]:
        if proxy.get(key):
            obfuscation_lines += f"{label} = {_conf_value(proxy[key])}\n"
    config = f"""[Interface]
# Name = {name}
Address= {addrs}
PrivateKey = {_conf_value(proxy["wg_pk"])}
MTU = {_conf_value(proxy.get("mtu", 1380))}
DNS = {_conf_value(proxy.get("dns", "1.1.1.1"))}
{obfuscation_lines}
[Peer]
# Name = Public Peer for {name}
Endpoint = {_conf_value(proxy["server"])}:{_conf_value(proxy["port"])}
PublicKey = {_conf_value(proxy["wg_server_pub"])}
PresharedKey = {_conf_value(proxy['wg_psk'])}
AllowedIPs = {_conf_value(proxy.get("allowed_ips", "0.0.0.0/0, ::/0"))}
PersistentKeepalive = {_conf_value(proxy.get("keep_alive", 25))}
"""

    return config
