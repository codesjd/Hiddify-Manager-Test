
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
    name = f'{proxy["extra_info"]} {proxy["name"]}'
    addrs = f"{proxy['wg_ipv4']}/32"
    if proxy['wg_ipv6']:
        addrs += f", {proxy['wg_ipv6']}/128"
    obfuscation_lines = ""
    if proxy.get("awg_jc"):
        obfuscation_lines += f"Jc = {proxy['awg_jc']}\n"
    if proxy.get("awg_jmin"):
        obfuscation_lines += f"Jmin = {proxy['awg_jmin']}\n"
    if proxy.get("awg_jmax"):
        obfuscation_lines += f"Jmax = {proxy['awg_jmax']}\n"
    config = f"""[Interface]
# Name = {name}
Address= {addrs}
PrivateKey = {proxy["wg_pk"]}
MTU = {proxy.get("mtu", 1380)}
DNS = {proxy.get("dns", "1.1.1.1")}
{obfuscation_lines}
[Peer]
# Name = Public Peer for {name}
Endpoint = {proxy["server"]}:{proxy["port"]}
PublicKey = {proxy["wg_server_pub"]}
PresharedKey = {proxy['wg_psk']}
#PersistentKeepalive = {proxy.get("keep_alive", 25)}
"""

    return config
