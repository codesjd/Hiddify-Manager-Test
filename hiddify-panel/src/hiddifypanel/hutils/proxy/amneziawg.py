
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
    if proxy.get("awg_h1"):
        obfuscation_lines += f"H1 = {proxy['awg_h1']}\n"
    if proxy.get("awg_h2"):
        obfuscation_lines += f"H2 = {proxy['awg_h2']}\n"
    if proxy.get("awg_h3"):
        obfuscation_lines += f"H3 = {proxy['awg_h3']}\n"
    if proxy.get("awg_h4"):
        obfuscation_lines += f"H4 = {proxy['awg_h4']}\n"
    if proxy.get("awg_s1"):
        obfuscation_lines += f"S1 = {proxy['awg_s1']}\n"
    if proxy.get("awg_s2"):
        obfuscation_lines += f"S2 = {proxy['awg_s2']}\n"
    if proxy.get("awg_s3"):
        obfuscation_lines += f"S3 = {proxy['awg_s3']}\n"
    if proxy.get("awg_s4"):
        obfuscation_lines += f"S4 = {proxy['awg_s4']}\n"
    if proxy.get("awg_i1"):
        obfuscation_lines += f"I1 = {proxy['awg_i1']}\n"
    if proxy.get("awg_i2"):
        obfuscation_lines += f"I2 = {proxy['awg_i2']}\n"
    if proxy.get("awg_i3"):
        obfuscation_lines += f"I3 = {proxy['awg_i3']}\n"
    if proxy.get("awg_i4"):
        obfuscation_lines += f"I4 = {proxy['awg_i4']}\n"
    if proxy.get("awg_i5"):
        obfuscation_lines += f"I5 = {proxy['awg_i5']}\n"
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
AllowedIPs = {proxy.get("allowed_ips", "0.0.0.0/0, ::/0")}
PersistentKeepalive = {proxy.get("keep_alive", 25)}
"""

    return config
