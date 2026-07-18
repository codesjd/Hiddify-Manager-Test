import datetime
import json
from flask import request, g
from hiddifypanel import hutils
from hiddifypanel.models import ProxyTransport, ProxyL3, ProxyProto, Domain, User, ConfigEnum, hconfig
from flask_babel import gettext as _
from urllib.parse import urlencode, quote
OUTBOUND_LEVEL = 8


def is_muxable_agent(proxy: dict) -> bool:
    if not proxy.get('mux_enable'):
        return False
    if proxy.get('mux_enable') == "xray" and g.user_agent.get('is_singbox'):
        return False
    if proxy.get('mux_enable') == "singbox" and not g.user_agent.get('is_singbox'):
        return False
    return True


def to_link(proxy: dict) -> str | dict:
    if 'error' in proxy:
        return proxy

    orig_name_link = (proxy['extra_info'] + " " + proxy["name"]).strip()
    name_link = hutils.encode.url_encode(orig_name_link)
    if proxy['proto']=="dnstt":
        resolvers="&".join([f"resolver={r}" for r in proxy['resolvers']])
        params={**{
            s.replace("_","-"):proxy[s]
            for s in ["tunnel_per_resolver","keepalive","idle_timeout","clientid_size","dnstt_compat","record_type","max_qname_len","open_stream_timeout"]
            if  (v:=proxy.get(s))
        },
        "domain":proxy["sni"],
        "pubkey":proxy["public_key"]
        }
        dnstt=f'dnstt://?{urlencode(params, quote_via=quote)}&{resolvers}'
        return f'socks://{proxy["uuid"]}:{proxy["password"]}@localhost:0#{name_link} -> {dnstt}'
    if proxy['proto'] in ("xdns", "xicmp"):
        # Unlike dnstt (its own dnstt:// scheme, needs an external client),
        # these are real vless connections a finalmask-aware Xray-core
        # client can dial directly - so they get a genuine vless:// link,
        # mkcp transport, with the finalmask settings under &fm= per
        # XTLS/Xray-core#5560/#5633's updated link-format note.
        # proxy['server']/['port'] are already the right dial target (see
        # make_proxy()'s xdns/xicmp branches - the first public resolver for
        # xdns, this server's own IP for xicmp). Reuses
        # add_mask_finalmask_stream() rather than re-declaring the same
        # finalmask JSON here - single source of truth with the "Full Xray
        # json" outbound builder.
        from .xrayjson import add_mask_finalmask_stream
        ss = {}
        add_mask_finalmask_stream(ss, proxy)
        fm_q = quote(json.dumps(ss['finalmask'], separators=(',', ':')))
        return f'vless://{proxy["uuid"]}@{proxy["server"]}:{proxy["port"]}?type=kcp&headerType=none&security=none&fm={fm_q}#{name_link}'
    if proxy['proto'] == "naive":
        naive = f'naive://{proxy["uuid"]}:{proxy["password"]}@{proxy["server"]}:{proxy["port"]}/?security=tls&sni={proxy["sni"]}&uot=1'
        if proxy.get('mode') == 'Fake' or proxy.get('allow_insecure'):
            naive += "&allow_insecure=1"
        if proxy.get('quic'):
            naive += "&quic=1"
        else:
            naive += f'&header=hiddify-naive-secret:{proxy["path"]}'
        return f'{naive}#{name_link}'

    if proxy['proto'] == "mieru":
        mieru = f'mieru://{proxy["uuid"]}:{proxy["password"]}@{proxy["server"]}/?handshake-mode={proxy["handshake"]}&mtu=1400&multiplexing={proxy["multiplexing"]}'
        for port in proxy["tcp_ports"]:
            if port:
                mieru += f"&port={port}&protocol=TCP"
        for port in proxy["udp_ports"]:
            if port:
                mieru += f"&port={port}&protocol=UDP"

        return f'{mieru}#{name_link}'

    if proxy['proto'] == 'vmess':
        # print(proxy)
        vmess_type = None
        if proxy["transport"] == 'tcp':
            vmess_type = 'http'
        if 'grpc_mode' in proxy:
            vmess_type = proxy['grpc_mode']
        vmess_data = {"v": "2",
                      "ps": orig_name_link,
                      "add": proxy['server'],
                      "port": proxy['port'],
                      "id": proxy["uuid"],
                      "aid": 0,
                      "scy": proxy['cipher'],
                      "net": proxy["transport"],
                      "type": vmess_type or "none",
                      "host": proxy.get("host", ""),
                      "alpn": proxy.get("alpn", "h2,http/1.1"),
                      "path": proxy["path"] if "path" in proxy else "",
                      "tls": "tls" if "tls" in proxy["l3"] or "quic" in proxy['l3'] else "",
                      "sni": proxy["sni"],
                      "fp": proxy["fingerprint"]
                      }
        if proxy.get('ech'):
            vmess_data['ech'] = proxy['ech']
        if 'reality' in proxy["l3"]:
            vmess_data['tls'] = "reality"
            vmess_data['pbk'] = proxy['reality_pbk']
            vmess_data['sid'] = proxy['reality_short_id']
        if proxy.get('transport') in {ProxyTransport.xhttp}:
            vmess_data['core'] = 'xray'
            _add_xhttp_extra(vmess_data, proxy)
        if vmess_data.get('tls') == 'tls':
            if proxy.get('ech'):
                vmess_data['ech'] = proxy['ech']
            if proxy.get('mode') == 'Fake' or proxy.get('allow_insecure'):
                # Xray-core >= 26.2.6 hard-rejects allowInsecure in its own
                # JSON schema (see xrayjson.py's _add_security for the full
                # story) - only emit it here if we don't have a
                # pinnedPeerCertSha256 pin to prefer instead, same fallback
                # order as the raw-JSON path.
                if proxy.get('pinned_cert_sha256'):
                    vmess_data['pcs'] = proxy['pinned_cert_sha256']
                else:
                    vmess_data['allowInsecure'] = True
        add_tls_tricks_to_dict(vmess_data, proxy)
        add_mux_to_dict(vmess_data, proxy)

        return "vmess://" + hutils.encode.do_base_64(f'{json.dumps(vmess_data, cls=hutils.proxy.ProxyJsonEncoder)}')
    if proxy['proto'] == 'ssh':
        # baseurl = 'ssh://'
        # if g.user_agent.get('is_streisand'):
        #     streisand_ssh = hutils.encode.do_base_64(f'{proxy["uuid"]}:0:{proxy["private_key"]}::@{proxy["server"]}:{proxy["port"]}')
        #     baseurl += f'{streisand_ssh}#{name_link}'
        # else:
        hk = ",".join(proxy["host_keys"])
        pk = proxy["private_key"]
        q = {
            'file': 'ssh',
            'hk': hk,
            'pk': pk,
            'private_key': pk,
            'authentication': 0,
            'passphrase': '',
        }
        return f"ssh://{proxy['uuid']}@{proxy['server']}:{proxy['port']}/?{urlencode(q, quote_via=quote)}#{name_link}"
        # baseurl += f'{proxy["uuid"]}@{proxy["server"]}:{proxy["port"]}/?file=ssh&pk={pk}&hk={hk}&private_key={pk}&authentication=0&passphrase#{name_link}'

        # return baseurl
    if proxy['proto'] == "ssr":
        baseurl = f'ssr://{proxy["cipher"]}:{proxy["uuid"]}@{proxy["server"]}:{proxy["port"]}'
        return baseurl
    if proxy['proto'] in ['ss', 'v2ray']:
        baseurl = f'ss://{hutils.encode.do_base_64(proxy["cipher"] + ":" + proxy["password"])}@{proxy["server"]}:{proxy["port"]}'

        if proxy['transport'] == 'shadowsocks':
            return f'{baseurl}#{name_link}'
        if proxy['transport'] == 'faketls':
            return f'{baseurl}?plugin=obfs-local&obfs-host={proxy["fakedomain"]}&obfs=http&udp-over-tcp=true#{name_link}'
        if proxy['transport'] == 'shadowtls':
            return "ShadowTLS is Not Supported for this platform"
            # return f'{baseurl}?plugin=v2ray-plugin&path={proxy["proxy_path"]}&host={proxy["fakedomain"]}&udp-over-tcp=true#{name_link}'
        if proxy['proto'] == 'v2ray':
            return f'{baseurl}?plugin=v2ray-plugin&mode=websocket&path={proxy["proxy_path"]}&host={proxy["sni"]}&tls&udp-over-tcp=true#{name_link}'

    if proxy['proto'] == 'tuic':
        # congestion_control must reflect the admin's actual
        # tuic_congestion_control setting (see shared.py/singbox.py) - a
        # hardcoded "cubic" here silently ignored the setting for anyone
        # importing this link instead of the full subscription.
        cc = proxy.get('tuic_congestion_control') or 'cubic'
        baseurl = f'tuic://{proxy["uuid"]}:{proxy["uuid"]}@{proxy["server"]}:{proxy["port"]}?congestion_control={cc}&udp_relay_mode=native&sni={proxy["sni"]}&alpn=h3'
        if proxy['mode'] == 'Fake' or proxy['allow_insecure']:
            # Same allowInsecure removal as xrayjson.py/_add_security() -
            # prefer pcs, only fall back to the deprecated field when we
            # don't have a pin yet (see the vmess/generic-link fixes above).
            if proxy.get('pinned_cert_sha256'):
                baseurl += f"&pcs={proxy['pinned_cert_sha256']}"
            else:
                baseurl += "&allow_insecure=1"
        return f"{baseurl}#{name_link}"
    if proxy['proto'] == 'anytls':
        # AnyTLS auth is a bare password - make_proxy() never sets a
        # separate 'password' key for this proto, so proxy['uuid'] (also
        # what singbox.py's add_anytls() uses as the password) is the
        # actual auth token here.
        baseurl = f'anytls://{proxy["uuid"]}@{proxy["server"]}:{proxy["port"]}?sni={proxy["sni"]}&alpn={proxy["alpn"]}'
        if proxy.get('fingerprint', 'none') != 'none':
            baseurl += f'&fp={proxy["fingerprint"]}'
        if proxy['mode'] == 'Fake' or proxy['allow_insecure']:
            # Same allowInsecure removal as xrayjson.py/_add_security() -
            # prefer pcs, only fall back to the deprecated fields when we
            # don't have a pin yet (see the vmess/generic-link fixes above).
            if proxy.get('pinned_cert_sha256'):
                baseurl += f"&pcs={proxy['pinned_cert_sha256']}"
            else:
                baseurl += "&insecure=1&allow_insecure=1"
        return f"{baseurl}#{name_link}"
    if proxy['proto'] == 'hysteria2':
        baseurl = f'hysteria2://{proxy["uuid"]}@{proxy["server"]}:{proxy["port"]}?hiddify=1&sni={proxy["sni"]}'
        # obfs is only configured on the server when hysteria_obfs_enable is
        # on (see singbox/configs/05_inbounds_4100_hysteria.json.j2). Adding
        # obfs=salamander unconditionally made xray-style clients (e.g.
        # v2rayN) fail the handshake whenever obfs was disabled server-side;
        # singbox.py already gates it on the same flag.
        if proxy.get('hysteria_obfs_enable'):
            baseurl += f'&obfs=salamander&obfs-password={proxy["hysteria_obfs_password"]}'
        if proxy['mode'] == 'Fake' or proxy['allow_insecure']:
            # Same allowInsecure removal as xrayjson.py/_add_security() -
            # prefer pcs, only fall back to the deprecated fields when we
            # don't have a pin yet (see the vmess/generic-link fixes above).
            if proxy.get('pinned_cert_sha256'):
                baseurl += f"&pcs={proxy['pinned_cert_sha256']}"
            else:
                baseurl += "&insecure=1&allow_insecure=1"
        return f"{baseurl}#{name_link}"
    if proxy['proto'] == ProxyProto.wireguard:
        if g.user_agent.get('is_streisand'):
            query = {
                "private_key": proxy["wg_pk"],
                "peer_public_key": proxy["wg_server_pub"],
                "pre_shared_key":   proxy["wg_psk"],
                "reserved": "0,0,0"
            }
            return f'wireguard://{proxy["server"]}:{proxy["port"]}?{urlencode(query)}#{name_link}'
        else:
            # hiddify_format =
            # f'wg://{proxy["server"]}:{proxy["port"]}/?pk={proxy["wg_pk"]}&local_address={proxy["wg_ipv4"]}/32&peer_pk={proxy["wg_server_pub"]}&pre_shared_key={proxy["wg_psk"]}&workers=4&mtu=1380&reserved=0,0,0&ifp={proxy["wg_noise_trick"]}#{name_link}'

            query = {
                "privateKey": proxy["wg_pk"],
                "publicKey": proxy["wg_server_pub"],
                "presharedKey":   proxy["wg_psk"],
                "reserved": "0,0,0",
                "ip":f'{proxy["wg_ipv4"]}/32',
                "mtu":"1380",
                "keepalive":"30",
                "udp":1,
                "ifp":proxy["wg_noise_trick"]
            }
            return f'wg://{proxy["server"]}:{proxy["port"]}?{urlencode(query)}#{name_link}'
    if proxy['proto'] == ProxyProto.amneziawg:
        # Same wg:// hiddify-format link as plain wireguard above (a
        # WireGuard-unaware client would ignore the extra jc/jmin/jmax
        # params, though it would then fail the handshake since the server
        # requires them) - a client that knows to look for these gets full
        # AmneziaWG obfuscation. No established "amneziawg://" URI scheme
        # exists in this codebase or elsewhere to mirror, so this extends
        # the existing convention rather than inventing a new one; the
        # downloadable .conf (see hutils/proxy/amneziawg.py) is the
        # authoritative, format-native way to import this connection.
        query = {
            "privateKey": proxy["wg_pk"],
            "publicKey": proxy["wg_server_pub"],
            "presharedKey": proxy["wg_psk"],
            "reserved": "0,0,0",
            "ip": f'{proxy["wg_ipv4"]}/32',
            "mtu": "1280",
            "keepalive": "30",
            "udp": 1,
        }
        if proxy.get("awg_jc"):
            query["jc"] = proxy["awg_jc"]
        if proxy.get("awg_jmin"):
            query["jmin"] = proxy["awg_jmin"]
        if proxy.get("awg_jmax"):
            query["jmax"] = proxy["awg_jmax"]
        if proxy.get("awg_h1"):
            query["h1"] = proxy["awg_h1"]
        if proxy.get("awg_h2"):
            query["h2"] = proxy["awg_h2"]
        if proxy.get("awg_h3"):
            query["h3"] = proxy["awg_h3"]
        if proxy.get("awg_h4"):
            query["h4"] = proxy["awg_h4"]
        return f'wg://{proxy["server"]}:{proxy["port"]}?{urlencode(query)}#{name_link}'

    baseurl = f'{proxy["proto"]}://{proxy["uuid"]}@{proxy["server"]}:{proxy["port"]}'

    q = {
        'hiddify': 1,
        'sni': proxy['sni'],
        'type': proxy['transport'],
        'alpn': proxy['alpn']
    }

    # the ray2sing supports vless, vmess and trojan tls tricks and mux
    # the vmess handled already

    add_mux_to_dict(q, proxy)
    add_tls_tricks_to_dict(q, proxy)
    if "path" in proxy:
        q['path'] = proxy["path"]
    if "host" in proxy:
        q['host'] = proxy["host"]
    # infos+=f'&alpn={proxy["alpn"]}'

    if "grpc" == proxy["transport"]:
        q['serviceName'] = proxy["grpc_service_name"]
        q['mode'] = proxy["grpc_mode"]
    # print(proxy['cdn'],proxy["transport"])
    if request.args.get("fragment"):
        q['fragment'] = request.args.get("fragment")  # type: ignore
    if "ws" == proxy["transport"] and proxy['cdn'] and request.args.get("fragment_v1"):
        q['fragment_v1'] = request.args.get("fragment_v1")  # type: ignore
    if 'vless' == proxy['proto']:
        q['encryption'] = 'none'

    if proxy.get('fingerprint', 'none') != 'none':
        q['fp'] = proxy['fingerprint']
    if proxy.get('transport') in {ProxyTransport.xhttp}:
        q['core'] = 'xray'
        _add_xhttp_extra(q, proxy)
    if proxy['l3'] != 'quic':
        if proxy.get('params', {}).get('headers', {}).get("type", '') == 'none' or proxy['l3'] != ProxyL3.http:
            q['headerType'] = 'none'
        else:
            # if proxy.get('l3') != ProxyL3.reality and (proxy.get('transport') in {ProxyTransport.tcp, ProxyTransport.httpupgrade, ProxyTransport.xhttp}) and proxy['proto'] in [ProxyProto.vless, ProxyProto.trojan]:
            q['headerType'] = 'http'

    if proxy['mode'] == 'Fake' or proxy['allow_insecure']:
        # Same allowInsecure removal as xrayjson.py/_add_security() and the
        # vmess branch above - some clients (confirmed: v2rayN) forward this
        # query param straight into their embedded Xray-core's deprecated
        # JSON field with no pcs/vcn migration of their own, so this can't
        # be set unconditionally alongside pcs like before. Prefer pcs; only
        # fall back to the deprecated fields when we don't have a pin yet.
        if proxy.get('pinned_cert_sha256'):
            q['pcs'] = proxy['pinned_cert_sha256']
        else:
            q['allowInsecure'] = 'true'
            q['insecure'] = 'true'
    if proxy.get('flow'):
        q['flow'] = proxy["flow"]

    if 'reality' in proxy["l3"]:
        q['security'] = 'reality'
        q['pbk'] = proxy['reality_pbk']
        q['sid'] = proxy['reality_short_id']

    elif 'tls' in proxy['l3'] or "quic" in proxy['l3']:
        q['security'] = 'tls'

    elif proxy['l3'] == 'http':
        q['security'] = 'none'
    if proxy.get('ech'):
        q['ech'] = proxy['ech']
    if proxy.get('transport') not in {ProxyTransport.xhttp}:
        for k, v in proxy.get('params', {}).items():
            if k not in q and k != "download":
                q[k] = v
    return f"{baseurl}?{urlencode(q, quote_via=quote)}#{name_link}"


def make_v2ray_configs(domains: list[Domain], user: User, expire_days: int, ip_debug=None) -> str:
    res = []

    if hconfig(ConfigEnum.show_usage_in_sublink) and not g.user_agent.get('is_hiddify'):

        fake_ip_for_sub_link = datetime.datetime.now().strftime(f"%H.%M--%Y.%m.%d.time:%H%M")
        # if ua['app'] == "Fair1":
        #     res.append(f'trojan://1@{fake_ip_for_sub_link}?sni=fake_ip_for_sub_link&security=tls#{round(user.current_usage_GB,3)}/{user.usage_limit_GB}GB_Remain:{expire_days}days')
        # else:

        # res.append(f'trojan://1@{fake_ip_for_sub_link}?sni=fake_ip_for_sub_link&security=tls#{hutils.encode.url_encode(profile_title)}')

        name = '⏳ ' if user.is_active else '✖ '
        if user.usage_limit_GB < 1000:
            name += f'{round(user.current_usage_GB, 3)}/{str(user.usage_limit_GB).replace(".0", "")}GB'
        elif user.usage_limit_GB < 100000:
            name += f'{round(user.current_usage_GB/1000, 3)}/{str(round(user.usage_limit_GB/1000, 1)).replace(".0", "")}TB'
        else:
            res.append("#No Usage Limit")
        name += " 📅 "
        if expire_days < 1000:
            name += _(f'%(expire_days)s days', expire_days=expire_days)
        else:
            res.append("#No Time Limit")

        name = name.strip()
        if len(name) > 3:
            res.append(f'trojan://1@{fake_ip_for_sub_link}?sni=fake_ip_for_sub_link&security=tls#{hutils.encode.url_encode(name)}')

    if g.user_agent.get('is_browser') and ip_debug:
        res.append(f'#Hiddify auto ip: {ip_debug}')

    if not user.is_active:

        if hconfig(ConfigEnum.lang) == 'fa':
            res.append('trojan://1@1.1.1.1#' + hutils.encode.url_encode('✖ بسته شما به پایان رسید'))
        else:
            res.append('trojan://1@1.1.1.1#' + hutils.encode.url_encode('✖ Package Ended'))
        return "\n".join(res)

    core_is_singbox = hconfig(ConfigEnum.core_type) == 'singbox'

    for pinfo in hutils.proxy.get_valid_proxies(domains):
        # sing-box now always runs alongside xray (see install.sh - it used
        # to be disabled whenever core_type=='xray', which killed every
        # singbox-only inbound's server side entirely) so these protocols'
        # servers are always up regardless of the primary core. The only
        # remaining reason to skip one here is a client-recognizability
        # problem, not a server-availability one: ssh/amneziawg/dnstt have
        # no standard URI scheme plain-link clients (v2rayN, NekoBox, etc)
        # know how to parse. anytls/tuic/naive/mieru all have working
        # schemes built below in to_link(), so they stay.
        if pinfo['proto'] in {ProxyProto.ssh, ProxyProto.amneziawg, ProxyProto.dnstt}:
            continue

        # xhttp is xray-specific; singbox has no xhttp inbound so these links
        # always time out when core_type == singbox.
        if core_is_singbox and pinfo.get('transport') == 'xhttp':
            continue
        link = to_link(pinfo)
        if 'msg' not in link:
            res.append(link)
    return "\n".join(res)


def add_tls_tricks_to_dict(d: dict, proxy: dict):
    if proxy.get('tls_fragment_enable'):
        # if g.user_agent.get('is_shadowrocket'):
        #     d['fragment'] = f'1,{proxy["tls_fragment_size"]},{proxy["tls_fragment_sleep"]}'
        # else:

        d['fragment'] = f'{proxy["tls_fragment_size"]},{proxy["tls_fragment_sleep"]},{proxy.get("tls_fragment_packets", "tlshello")}'
        # if g.user_agent.get('is_streisand'):
        # else:
        #     d['fragment'] = f'tlshello,{proxy["tls_fragment_size"]},{proxy["tls_fragment_sleep"]}'

    if proxy.get("tls_mixed_case"):
        d['mc'] = 1
    if proxy.get("tls_padding_enable"):
        d['padsize'] = proxy["tls_padding_length"]


def add_mux_to_dict(d: dict, proxy):
    if not is_muxable_agent(proxy):
        return

    # according to github.com/hiddify/ray2sing/
    d['muxtype'] = proxy["mux_protocol"]
    d['muxmaxc'] = proxy["mux_max_connections"]
    d['mux'] = proxy['mux_min_streams']
    d['muxsmax'] = proxy["mux_max_streams"]
    d['muxpad'] = proxy["mux_padding_enable"]

    if proxy.get('mux_brutal_enable'):
        d['muxup'] = proxy["mux_brutal_up_mbps"]
        d['muxdown'] = proxy["mux_brutal_down_mbps"]


def _add_xhttp_extra(d: dict, proxy):
    from .xrayjson import _add_xhttp_details
    xhttp_dict = {}
    _add_xhttp_details(xhttp_dict, proxy)
    d['extra'] = json.dumps(xhttp_dict['xhttpSettings']['extra'], separators=(',', ':'))


