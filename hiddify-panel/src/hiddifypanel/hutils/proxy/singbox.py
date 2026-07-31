from flask import render_template, request, g
import json

from hiddifypanel import hutils
from hiddifypanel.hutils.proxy.xrayjson import to_xray
from hiddifypanel.models import ProxyProto, ProxyTransport, Domain, ConfigEnum


def configs_as_json(domains: list[Domain], **kwargs) -> dict:
    ua = hutils.flask.get_user_agent()
    base_config = json.loads(render_template('base_singbox_config.json.j2'))
    allphttp = [p for p in request.args.get("phttp", "").split(',') if p]
    allptls = [p for p in request.args.get("ptls", "").split(',') if p]

    allp = []
    for d in domains:
        base_config['dns']['rules'][0]['domain'].append(d.domain)
    endpoints=[]
    for pinfo in hutils.proxy.get_valid_proxies(domains):
        # xhttp is an Xray-core transport with no sing-box equivalent -
        # to_singbox()/_add_xhttp_details() below still emitted a
        # "transport":{"type":"xhttp",...} block for it regardless, which
        # sing-box's JSON parser rejects outright ("unknown transport type:
        # xhttp") - a single unparseable outbound made the ENTIRE config
        # fail to load, not just this one proxy. is_xray_proxy() was meant
        # to route these through a raw-embedding fallback for Hiddify Next
        # specifically, but its actual check is commented out (always
        # False), so nothing currently protects generic sing-box clients
        # (v2rayN, etc) from this - skip xhttp here the same way the
        # plain-link subscription already does in make_v2ray_configs().
        if pinfo.get('transport') == ProxyTransport.xhttp:
            continue
        # SSH, Mieru, Naive, AmneziaWG and DNSTT outbounds aren't compiled
        # into every sing-box build (mieru needs CGO, ssh/naive/wireguard/
        # dnstt are optional modules some minimal/mobile builds leave out) -
        # unlike xhttp above this doesn't fail the whole config, but it does
        # leave dead, unusable proxy group entries in the client's Select/
        # Auto lists. Excluded from the sing-box JSON specifically; these
        # protocols are untouched in every other subscription format (they
        # still get their own independent links, see to_link()).
        if pinfo.get('proto') in (ProxyProto.ssh, ProxyProto.mieru, ProxyProto.naive, ProxyProto.amneziawg, ProxyProto.dnstt):
            continue
        # xdns/xicmp are Xray-core's finalmask DNS/ICMP-tunneled vless
        # (xray/configs/05_inbounds_0{5,6}_x{dns,icmp}.json.j2) - Xray-core-
        # exclusive concepts sing-box has no matching outbound type for, and
        # to_singbox() below has no branch for either - without this, they
        # fell through to the generic tail of to_singbox() and got emitted
        # as literal `"type": "xdns"/"xicmp"` outbounds, which aren't real
        # sing-box outbound types at all.
        if pinfo.get('proto') in (ProxyProto.xdns, ProxyProto.xicmp):
            continue
        sing = to_singbox(pinfo)
        if 'msg' not in sing:
            if hutils.flask.is_client_version(hutils.flask.ClientVersion.hiddify_next, 4, 0, 0) and sing[0]['type']=="wireguard":
                endpoints+=sing
            else:
                allp += sing
    base_config['outbounds'] += allp
    base_config['endpoints'] = endpoints

    select = {
        "type": "selector",
        "tag": "Select",
        "outbounds": [p['tag'] for p in allp if 'shadowtls-out' not in p['tag']],
        "default": "Auto"
    }
    select['outbounds'].insert(0, "Auto")
    base_config['outbounds'].insert(0, select)
    smart = {
        "type": "urltest",
        "tag": "Auto",
        # Match the Select group above: filter on the tag string, not the
        # dict itself ('shadowtls-out' not in p checked dict keys and always
        # passed, leaking the internal shadowtls detour outbound into the
        # Auto url-test group).
        "outbounds": [p['tag'] for p in allp if 'shadowtls-out' not in p['tag']],
        "url": "https://www.gstatic.com/generate_204",
        "interval": "10m",
        "tolerance": 200
    }
    base_config['outbounds'].insert(1, smart)
    
    # if ua['is_hiddify']:
    #     res = res[:-1]+',"experimental": {}}'
    return base_config


def is_xray_proxy(proxy: dict):
    # if g.user_agent.get('is_hiddify_prefere_xray'):
    #     return True
    # if proxy['transport'] == ProxyTransport.xhttp:
    #     return True
    return False


def to_singbox(proxy: dict) -> list[dict] | dict:
    name = proxy['name']

    all_base = []
    if proxy['l3'] == "kcp":
        return {'name': name, 'msg': "clash does not support kcp", 'type': 'debug'}

    base = {}
    all_base.append(base)
    # vmess ws
    base["tag"] = f"""{proxy['extra_info']} {proxy["name"]} § {proxy['port']} {proxy["dbdomain"].id}"""
    if is_xray_proxy(proxy):
        if hutils.flask.is_client_version(hutils.flask.ClientVersion.hiddify_next, 1, 9, 0):
            base['type'] = "xray"
            xp = to_xray(proxy)
            xp['streamSettings']['sockopt'] = {}
            base['xray_outbound_raw'] = xp
            if proxy.get('tls_fragment_enable'):
                base['xray_fragment'] = {
                    'packets': proxy.get("tls_fragment_packets", "tlshello"),
                    'length': proxy["tls_fragment_size"],
                    'interval': proxy["tls_fragment_sleep"]
                }
            return all_base
        return {'name': name, 'msg': "xray proxy does not support in this client version", 'type': 'debug'}
    base["type"] = str(proxy["proto"])
    if proxy['proto']==ProxyProto.dnstt:
        add_dnstt(all_base, proxy)
        return all_base
    
    base["server"] = proxy["server"]
    base["server_port"] = int(proxy["port"])
    # base['alpn'] = proxy['alpn'].split(',')
    if proxy["proto"] == "ssr":
        add_ssr(base, proxy)
        return all_base
    if proxy["proto"] == ProxyProto.wireguard:
        add_wireguard(base, proxy)
        return all_base
    if proxy["proto"] == ProxyProto.amneziawg:
        # sing-box has no native "amneziawg" outbound type; the wireguard
        # type is the closest real schema it understands.
        base["type"] = "wireguard"
        add_amneziawg(base, proxy)
        return all_base


    if proxy['proto']==ProxyProto.mieru:
        add_mieru(base, proxy)
        return all_base
    if proxy['proto']==ProxyProto.naive:
        add_naive(base, proxy)
        return all_base
    if proxy["proto"] in ["ss", "v2ray"]:
        add_shadowsocks_base(all_base, proxy)
        return all_base
    if proxy["proto"] == "ssh":
        add_ssh(all_base, proxy)
        return all_base

    if proxy["proto"] == "trojan":
        base["password"] = proxy["password"]

    if proxy['proto'] in ['vmess', 'vless']:
        base["uuid"] = proxy["uuid"]

    if proxy['proto'] in ['vmess', 'vless', 'trojan']:
        add_multiplex(base, proxy)

    add_tls(base, proxy)

    if g.user_agent.get('is_hiddify'):
        add_tls_tricks(base, proxy)

    if proxy.get('flow'):
        base["flow"] = proxy['flow']
        # base["flow-show"] = True

    if proxy["proto"] == "vmess":
        base["alter_id"] = 0
        base["security"] = proxy["cipher"]

    # base["udp"] = True
    if proxy["proto"] in ["vmess", "vless"]:
        base["packet_encoding"] = "xudp"  # udp packet encoding

    if proxy["proto"] == "tuic":
        add_tuic(base, proxy)
    elif proxy["proto"] == "anytls":
        add_anytls(base, proxy)
    elif proxy["proto"] == "hysteria2":
        add_hysteria(base, proxy)
    else:
        add_transport(base, proxy)

    return all_base


def add_multiplex(base: dict, proxy: dict):
    if proxy.get('mux_enable') != "singbox":
        return
    base['multiplex'] = {
        "enabled": True,
        "protocol": proxy['mux_protocol'],
        "padding": proxy['mux_padding_enable']
    }
    # Conflicts: max_streams with max_connections and min_streams
    mux_max_streams = proxy.get('mux_max_streams', 0)
    if mux_max_streams and mux_max_streams != 0:
        base['multiplex']['max_streams'] = mux_max_streams
    else:
        base['multiplex']['max_connections'] = proxy.get('mux_max_connections', 0)
        base['multiplex']['min_streams'] = proxy.get('mux_min_streams', 0)

    add_tcp_brutal(base, proxy)


def add_tcp_brutal(base: dict, proxy: dict):
    if 'multiplex' in base:
        if proxy.get('mux_brutal_enable'):
            base['multiplex']['brutal'] = {
                "enabled": proxy.get('mux_brutal_enable', False),
                "up_mbps": proxy.get('mux_brutal_up_mbps', 10),
                "down_mbps": proxy.get('mux_brutal_down_mbps', 10)
            }


def add_udp_over_tcp(base: dict):
    base['udp_over_tcp'] = {
        "enabled": True,
        "version": 2
    }


def add_tls(base: dict, proxy: dict):
    if not ("tls" in proxy["l3"] or "reality" in proxy["l3"] or "quic" in proxy["l3"]):
        return
    base["tls"] = {
        "enabled": True,
        "server_name": proxy["sni"]
    }
    if proxy.get("ech"):
        base["tls"]['ech'] = {
            "enabled": True,
            "config":f"-----BEGIN ECH CONFIGS-----\n{proxy.get('ech')}\n-----END ECH CONFIGS-----"
        }
    if proxy['proto']=="naive":
        base["tls"]['insecure'] = proxy['allow_insecure'] or (proxy["mode"] == "Fake")
        return
    if proxy['proto'] not in ["tuic", "hysteria2"] and proxy['transport']!="xhttp":
        base["tls"]["utls"] = {
            "enabled": True,
            "fingerprint": proxy.get('fingerprint', 'none')
        }

    if "reality" in proxy["l3"]:
        base["tls"]["utls"] = {
            "enabled": True,
            "fingerprint": proxy.get('fingerprint', 'none')
        }
        base["tls"]["reality"] = {
            "enabled": True,
            "public_key": proxy['reality_pbk'],
            "short_id": proxy['reality_short_id']
        }
    base["tls"]['insecure'] = proxy['allow_insecure'] or (proxy["mode"] == "Fake")
    
    base["tls"]["alpn"] = proxy['alpn'].split(',')
    


def add_tls_tricks(base: dict, proxy: dict):
    if proxy.get('tls_fragment_enable'):
        base['tls_fragment'] = {
            'enabled': True,
            'size': proxy["tls_fragment_size"],
            'sleep': proxy["tls_fragment_sleep"]
        }

    if 'tls' in base:
        if proxy.get("tls_padding_enable") or proxy.get("tls_mixed_case"):
            base['tls']['tls_tricks'] = {}
        if proxy.get("tls_padding_enable"):
            base['tls']['tls_tricks']['padding_size'] = proxy["tls_padding_length"]

        if proxy.get("tls_mixed_case"):
            base['tls']['tls_tricks']['mixedcase_sni'] = True


def add_transport(base: dict, proxy: dict):
    if proxy['l3'] == 'reality' and proxy['transport'] not in ["grpc"]:
        return
    base["transport"] = {}
    if proxy['transport'] in ["ws", "WS"]:
        base["transport"] = {
            "type": "ws",
            "path": proxy["path"],
            "early_data_header_name": "Sec-WebSocket-Protocol"
        }
        if "host" in proxy:
            base["transport"]["headers"] = {"Host": proxy["host"]}

    if proxy['transport'] in ["xhttp"]:
        _add_xhttp_details(base,proxy)
        

    if proxy['transport'] in [ProxyTransport.httpupgrade]:
        base["transport"] = {
            "type": "httpupgrade",
            "path": proxy["path"]
        }
        if "host" in proxy:
            base["transport"]["headers"] = {"Host": proxy["host"]}

    if proxy["transport"] in ["tcp", "h2"]:
        base["transport"] = {
            "type": "http",
            "path": proxy.get("path", ""),
            "idle_timeout": "15s",
            "ping_timeout": "15s"
            # "method": "",
            # "headers": {},
        }

        if 'host' in proxy:
            base["transport"]["host"] = [proxy["host"]]

    if proxy["transport"] == "grpc":
        base["transport"] = {
            "type": "grpc",
            "service_name": proxy["grpc_service_name"],
            "idle_timeout": "115s",
            "ping_timeout": "15s",
            # "permit_without_stream": false
        }

def _add_xhttp_details(base: dict, proxy: dict):
    
    base["transport"] = {
            "type": "xhttp",
            "path": proxy["path"],
            'host': proxy['host'],
            'mode':proxy['xhttp_mode'],
            "headers": proxy['params'].get('headers', {})
        }
    
    
    if pdl:=proxy.get("download"):
        base['transport']['downloadSettings']={
            "path": proxy["path"],
            'host': pdl.get("server"),
            "headers":pdl.get("headers")            
        }
        dls = {**proxy, **proxy['download']}
        add_tls(base['transport']['downloadSettings'],dls)
        

def add_dnstt(all_base:list,proxy:dict):
    all_base[0]['domain']=proxy["sni"]
    all_base[0]['publicKey']=proxy["public_key"]
    all_base[0]['resolvers']=proxy['resolvers']
    for s in ["tunnel_per_resolver","keepalive","idle_timeout","clientid_size","dnstt_compat","record_type","max_qname_len","open_stream_timeout"]:
        if v:= proxy.get(s):
            all_base[0][s.replace("_","-")]=v
    tag=all_base[0]["tag"]
    all_base[0]["tag"]+="§hide§"
    all_base.append({
        "type":"socks",
        "username":proxy['uuid'],
        "password":proxy['password'],
        "tag":tag,
        "detour":all_base[0]["tag"]
    })
    
 

def add_ssr(base: dict, proxy: dict):

    base["method"] = proxy["cipher"]
    base["password"] = proxy["uuid"]
    # base["udp"] = True
    base["obfs"] = proxy["ssr-obfs"]
    base["protocol"] = proxy["ssr-protocol"]
    base["protocol-param"] = proxy["fakedomain"]


def add_naive(base: dict, proxy: dict):
    base['type']="naive"
    base['username']=proxy['uuid']
    base["password"]=proxy["password"]
    base["udp_over_tcp"]=True
    base["quic"]=proxy["quic"]
    base["extra_headers"]={
        "hiddify-naive-secret":proxy["path"]
    }

    add_tls(base,proxy)

def add_mieru(base: dict, proxy: dict):
    base['type']="mieru"
    base['multiplexing']=proxy['multiplexing']
    base['handshake_mode']=proxy['handshake']
    base['username']=proxy['uuid']
    base['password']=proxy['password']
    base['portBindings']=[]
    
    for port in proxy["tcp_ports"]:
        if port:
            base['portBindings'].append({
                'protocol':"TCP",
                "port":0 if "-" in port else int(port),
                "portRange":port if "-" in port else ""
            })
    for port in proxy["udp_ports"]:
        if port:
            base['portBindings'].append({
                'protocol':"UDP",
                "port":0 if "-" in port else int(port),
                "portRange":port if "-" in port else ""
            })
            
                
    
def add_wireguard(base: dict, proxy: dict):
    if hutils.flask.is_client_version(hutils.flask.ClientVersion.singbox, 1, 13, 0):
        
        base["private_key"] = proxy["wg_pk"]
        base["mtu"] = 1380
        base["address"] = [f'{proxy["wg_ipv4"]}/32']
        base['peers']=[{
            "public_key":proxy["wg_server_pub"],
            "pre_shared_key":proxy["wg_psk"],
            "address":base['server'],
            "port":base['server_port'],
            "allowed_ips": [
                "0.0.0.0/0","::/0"
            ]
        }]
        del base["server_port"]
        del base["server"]
        if g.user_agent.get('is_hiddify'):
            base["noise"] ={
                "fake_packet":{
                    "enabled":True,
                    "count":proxy["wg_noise_trick"]
                } 
            }

    else:
        base["local_address"] = f'{proxy["wg_ipv4"]}/32'
        base["private_key"] = proxy["wg_pk"]
        base["peer_public_key"] = proxy["wg_server_pub"]

        base["pre_shared_key"] = proxy["wg_psk"]

        base["mtu"] = 1380
        if g.user_agent.get('is_hiddify') and hutils.flask.is_client_version(hutils.flask.ClientVersion.hiddify_next, 0, 15, 0):
                base["fake_packets"] = proxy["wg_noise_trick"]


def add_amneziawg(base: dict, proxy: dict):
    # sing-box's wireguard outbound has no official Jc/Jmin/Jmax
    # (AmneziaWG obfuscation) fields. This mirrors the wg_noise_trick
    # precedent above: an undocumented, best-effort extension gated to
    # Hiddify's own client, since no verified public client is known to
    # read these fields on a "wireguard"-typed outbound.
    if hutils.flask.is_client_version(hutils.flask.ClientVersion.singbox, 1, 13, 0):
        base["private_key"] = proxy["wg_pk"]
        base["mtu"] = 1380
        base["address"] = [f'{proxy["wg_ipv4"]}/32']
        base['peers'] = [{
            "public_key": proxy["wg_server_pub"],
            "pre_shared_key": proxy["wg_psk"],
            "address": base['server'],
            "port": base['server_port'],
            "allowed_ips": [
                "0.0.0.0/0", "::/0"
            ]
        }]
        del base["server_port"]
        del base["server"]
        if g.user_agent.get('is_hiddify'):
            amnezia_params = {}
            if proxy.get("awg_jc"):
                amnezia_params["jc"] = int(proxy["awg_jc"])
            if proxy.get("awg_jmin"):
                amnezia_params["jmin"] = int(proxy["awg_jmin"])
            if proxy.get("awg_jmax"):
                amnezia_params["jmax"] = int(proxy["awg_jmax"])
            if proxy.get("awg_h1"):
                amnezia_params["h1"] = int(proxy["awg_h1"])
            if proxy.get("awg_h2"):
                amnezia_params["h2"] = int(proxy["awg_h2"])
            if proxy.get("awg_h3"):
                amnezia_params["h3"] = int(proxy["awg_h3"])
            if proxy.get("awg_h4"):
                amnezia_params["h4"] = int(proxy["awg_h4"])
            if amnezia_params:
                base["amnezia"] = amnezia_params
    else:
        base["local_address"] = f'{proxy["wg_ipv4"]}/32'
        base["private_key"] = proxy["wg_pk"]
        base["peer_public_key"] = proxy["wg_server_pub"]

        base["pre_shared_key"] = proxy["wg_psk"]

        base["mtu"] = 1380
        if g.user_agent.get('is_hiddify') and hutils.flask.is_client_version(hutils.flask.ClientVersion.hiddify_next, 0, 15, 0):
            if proxy.get("awg_jc"):
                base["jc"] = int(proxy["awg_jc"])
            if proxy.get("awg_jmin"):
                base["jmin"] = int(proxy["awg_jmin"])
            if proxy.get("awg_jmax"):
                base["jmax"] = int(proxy["awg_jmax"])
            if proxy.get("awg_h1"):
                base["h1"] = int(proxy["awg_h1"])
            if proxy.get("awg_h2"):
                base["h2"] = int(proxy["awg_h2"])
            if proxy.get("awg_h3"):
                base["h3"] = int(proxy["awg_h3"])
            if proxy.get("awg_h4"):
                base["h4"] = int(proxy["awg_h4"])


def add_shadowsocks_base(all_base: list[dict], proxy: dict):
    base = all_base[0]
    base["type"] = "shadowsocks"
    base["method"] = proxy["cipher"]
    base["password"] = proxy["password"]
    add_udp_over_tcp(base)
    add_multiplex(base, proxy)
    if proxy["transport"] == "faketls":
        base["plugin"] = "obfs-local"
        base["plugin_opts"] = f'obfs=tls;obfs-host={proxy["fakedomain"]}'
    if proxy['proto'] == 'v2ray':
        base["plugin"] = "v2ray-plugin"
        # "skip-cert-verify": proxy["mode"] == "Fake" or proxy['allow_insecure'],
        base["plugin_opts"] = f'mode=websocket;path={proxy["path"]};host={proxy["host"]};tls'

    if proxy["transport"] == "shadowtls":
        base['detour'] = base['tag'] + "_shadowtls-out §hide§"

        shadowtls_base = {
            "type": "shadowtls",
            "tag": base['detour'],
            "server": base['server'],
            "server_port": base['server_port'],
            "version": 3,
            "password": proxy["shared_secret"],
            "tls": {
                "enabled": True,
                "server_name": proxy["fakedomain"],
                "utls": {
                    "enabled": True,
                    "fingerprint": proxy.get('fingerprint', 'none')
                },
                # "alpn": proxy['alpn'].split(',')
            }
        }
        # add_utls(shadowtls_base)
        del base['server']
        del base['server_port']
        all_base.append(shadowtls_base)


def add_ssh(all_base: list[dict], proxy: dict):
    base = all_base[0]
    # base["client_version"]= "{{ssh_client_version}}"
    base["user"] = proxy['uuid']
    base["private_key"] = proxy['private_key']  # .replace('\n', '\\n')
    base["udp_over_tcp"]= True
    base["host_key"] = proxy.get('host_keys', [])


def add_tuic(base: dict, proxy: dict):
    base['congestion_control'] = proxy.get('tuic_congestion_control') or "cubic"
    base['udp_relay_mode'] = 'native'
    base['zero_rtt_handshake'] = True
    base['heartbeat'] = "10s"
    base['password'] = proxy['uuid']
    base['uuid'] = proxy['uuid']



def add_anytls(base: dict, proxy: dict):
    # AnyTLS inbound uses uuid directly as the password.
    # Schema: {type: anytls, users:[{name, password}], tls:{...}}
    # No extra per-proxy fields needed beyond what add_tls() already sets.
    base['password'] = proxy['uuid']


def add_hysteria(base: dict, proxy: dict):
    # make_proxy() stores these under string keys ('hysteria_up_mbps' /
    # 'hysteria_down_mbps'); reading them with the ConfigEnum member as the
    # key (which is a FastEnum, not str-equal to the key) silently returned
    # None, so sing-box/Hiddify-app clients never got the configured speeds.
    #
    # hysteria_up_mbps/hysteria_down_mbps are _StrConfigDscr hconfigs, so
    # these come through as strings ("150") - sing-box's schema requires
    # up_mbps/down_mbps to be JSON integers and hard-rejects the whole
    # config ("cannot unmarshal string into Go value of type int") if
    # they're left as strings, so cast them here.
    def _to_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    base['up_mbps'] = _to_int(proxy.get('hysteria_up_mbps'))
    base['down_mbps'] = _to_int(proxy.get('hysteria_down_mbps'))
    # TODO: check the obfs should be empty or not exists at all
    if proxy.get('hysteria_obfs_enable'):
        base['obfs'] = {
            "type": "salamander",
            "password": proxy.get('hysteria_obfs_password')
        }
    base['password'] = proxy['uuid']
