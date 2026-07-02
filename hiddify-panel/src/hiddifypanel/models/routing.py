from strenum import StrEnum
from enum import auto
from sqlalchemy import Column, String, Integer, Boolean, Enum, ForeignKey, Text

from hiddifypanel.database import db


class OutboundProtocol(StrEnum):
    vless = auto()
    vmess = auto()
    trojan = auto()
    shadowsocks = auto()
    socks = auto()
    http = auto()
    wireguard = auto()
    freedom = auto()
    # Not a real dialed protocol - binds outbound traffic to the standalone
    # AmneziaWG interface other/amneziawg/ brings up (hiddify0), the same
    # way the built-in WARP outbound binds to the "warp" interface. No
    # address/port/uuid needed; see CustomOutbound.to_xray_dict()/
    # to_singbox_dict().
    amneziawg = auto()


class OutboundNetwork(StrEnum):
    tcp = auto()
    ws = auto()
    grpc = auto()
    httpupgrade = auto()
    xhttp = auto()


class OutboundSecurity(StrEnum):
    none = auto()
    tls = auto()
    reality = auto()


class CustomOutbound(db.Model):  # type: ignore
    """A custom Xray outbound the admin defines from the panel (instead of
    hand-editing xray/configs/06_outbounds.json.j2 over SSH). Typical use:
    chain traffic for a specific routing rule to another one of your own
    servers, or add a fixed SOCKS/HTTP upstream proxy.

    Built from-scratch config only (protocol/address/port/credential
    fields). For anything this simple form can't express (multiplexing,
    custom stream settings, etc.), `extra_json` is merged on top of the
    generated outbound object - same escape-hatch pattern as
    Domain.extra_params.
    """
    id = Column(Integer, primary_key=True, autoincrement=True)
    child_id = Column(Integer, ForeignKey('child.id'), default=0)
    enable = Column(Boolean, default=True, nullable=False)
    tag = Column(String(100), nullable=False, unique=True)
    protocol = Column(Enum(OutboundProtocol), nullable=False, default=OutboundProtocol.vless)
    address = Column(String(300), nullable=True, default='')
    port = Column(Integer, nullable=True, default=443)
    uuid_or_password = Column(String(300), nullable=True, default='')
    network = Column(Enum(OutboundNetwork), nullable=False, default=OutboundNetwork.tcp)
    security = Column(Enum(OutboundSecurity), nullable=False, default=OutboundSecurity.tls)
    sni = Column(String(300), nullable=True, default='')
    ws_path = Column(String(300), nullable=True, default='')
    # Host header for ws/httpupgrade/xhttp (usually the CDN's origin
    # hostname, separate from the TLS SNI) and uTLS fingerprint for
    # tls/reality - both extremely common on real vless/vmess share links,
    # so they get dedicated fields instead of forcing every import through
    # extra_json.
    host_header = Column(String(300), nullable=True, default='')
    fingerprint = Column(String(50), nullable=True, default='')
    # vless-only xtls flow control, e.g. "xtls-rprx-vision".
    flow = Column(String(50), nullable=True, default='')
    # wireguard/amneziawg peer fields. address/port above double as the
    # Endpoint host/port and uuid_or_password as the local PrivateKey for
    # both protocols (same convention xray/singbox already use elsewhere in
    # this file), these four are the rest of a [Peer]/[Interface] pair that
    # didn't have dedicated columns before.
    peer_public_key = Column(String(100), nullable=True, default='')
    preshared_key = Column(String(100), nullable=True, default='')
    local_address = Column(String(300), nullable=True, default='')  # client-side [Interface] Address, e.g. "10.0.0.2/32"
    dns = Column(String(300), nullable=True, default='')
    # AmneziaWG-only obfuscation params (junk packet count/min/max size) -
    # meaningless for plain "wireguard", only read by the amneziawg branch.
    jc = Column(Integer, nullable=True)
    jmin = Column(Integer, nullable=True)
    jmax = Column(Integer, nullable=True)
    comment = Column(String(300), nullable=True, default='')
    # Advanced escape hatch: raw JSON merged on top of the generated
    # outbound dict (e.g. {"streamSettings": {"grpcSettings": {...}}}).
    extra_json = Column(Text, nullable=True, default='{}')

    @property
    def amneziawg_interface(self) -> str:
        """Linux interface name for this row's AmneziaWG tunnel - derived
        from the row id (not the tag) so it's always short enough
        (IFNAMSIZ) regardless of what the admin names the tag, and stable
        across tag renames."""
        return f"awg{self.id}"

    def render_amneziawg_conf(self) -> str:
        """The actual AmneziaWG [Interface]/[Peer] .conf content for this
        row - written to /etc/amnezia/amneziawg/{interface}.conf and loaded
        by awg-quick@{interface}.service. Only meaningful for protocol ==
        amneziawg.

        Table = off is critical here: with AllowedIPs = 0.0.0.0/0, ::/0 (set
        below), awg-quick/wg-quick's default behavior is to ALSO change the
        *server's own* default route to go through this interface - not just
        make it available for xray/singbox's bind_interface to opt into.
        That took an entire test server offline (SSH included) the first
        time this ran, because it isn't a client machine that wants all its
        own traffic tunneled - only whichever proxy connections
        bind_interface explicitly points at this interface should use it.
        Table = off makes wg-quick/awg-quick create/address/bring up the
        interface only, with no routing table changes - exactly the same
        fix other/warp/wireguard/run.sh.j2 already applies to its own
        interface for the identical reason."""
        lines = [
            "[Interface]",
            f"PrivateKey = {self.uuid_or_password or ''}",
            "Table = off",
        ]
        if self.local_address:
            lines.append(f"Address = {self.local_address}")
        if self.dns:
            lines.append(f"DNS = {self.dns}")
        if self.jc:
            lines.append(f"Jc = {self.jc}")
        if self.jmin:
            lines.append(f"Jmin = {self.jmin}")
        if self.jmax:
            lines.append(f"Jmax = {self.jmax}")
        lines += [
            "",
            "[Peer]",
            f"PublicKey = {self.peer_public_key or ''}",
        ]
        if self.preshared_key:
            lines.append(f"PresharedKey = {self.preshared_key}")
        lines += [
            "AllowedIPs = 0.0.0.0/0, ::/0",
            f"Endpoint = {self.address or ''}:{self.port or ''}",
            "PersistentKeepalive = 25",
        ]
        return "\n".join(lines) + "\n"

    def to_xray_dict(self) -> dict:
        import json

        if self.protocol == OutboundProtocol.amneziawg:
            # xray has no native AmneziaWG support either (same as
            # sing-box) - this binds a plain "freedom" outbound to the
            # per-row AmneziaWG interface other/amneziawg/ brings up from
            # this row's own fields (see render_amneziawg_conf()), xray-
            # core's Linux SO_BINDTODEVICE equivalent to sing-box's
            # bind_interface. No network/security apply.
            return {"tag": self.tag, "protocol": "freedom", "settings": {}, "streamSettings": {"sockopt": {"interface": self.amneziawg_interface}}}

        settings: dict = {}
        stream: dict = {}

        if self.protocol in (OutboundProtocol.vless, OutboundProtocol.vmess):
            user = {"id": self.uuid_or_password or ""}
            if self.protocol == OutboundProtocol.vless:
                user["encryption"] = "none"
                if self.flow:
                    user["flow"] = self.flow
            else:
                user["security"] = "auto"
            settings = {"vnext": [{"address": self.address or "", "port": self.port or 443, "users": [user]}]}
        elif self.protocol == OutboundProtocol.trojan:
            settings = {"servers": [{"address": self.address or "", "port": self.port or 443, "password": self.uuid_or_password or ""}]}
        elif self.protocol == OutboundProtocol.shadowsocks:
            settings = {"servers": [{"address": self.address or "", "port": self.port or 443, "password": self.uuid_or_password or "", "method": "chacha20-ietf-poly1305"}]}
        elif self.protocol in (OutboundProtocol.socks, OutboundProtocol.http):
            server = {"address": self.address or "", "port": self.port or 1080}
            if self.uuid_or_password:
                user, _, pw = self.uuid_or_password.partition(':')
                server["users"] = [{"user": user, "pass": pw}]
            settings = {"servers": [server]}
        elif self.protocol == OutboundProtocol.wireguard:
            settings = {"secretKey": self.uuid_or_password or "", "address": [self.address] if self.address else [], "peers": []}
        elif self.protocol == OutboundProtocol.freedom:
            settings = {}

        if self.network != OutboundNetwork.tcp:
            stream["network"] = self.network.value
            if self.network == OutboundNetwork.ws:
                stream["wsSettings"] = {"path": self.ws_path or "/"}
                if self.host_header:
                    stream["wsSettings"]["headers"] = {"Host": self.host_header}
            elif self.network == OutboundNetwork.grpc:
                stream["grpcSettings"] = {"serviceName": self.ws_path or ""}
            elif self.network in (OutboundNetwork.httpupgrade, OutboundNetwork.xhttp):
                stream[f"{self.network.value}Settings"] = {"path": self.ws_path or "/"}
                if self.host_header:
                    stream[f"{self.network.value}Settings"]["host"] = self.host_header

        if self.security == OutboundSecurity.tls:
            stream["security"] = "tls"
            stream["tlsSettings"] = {"serverName": self.sni or self.address or ""}
            if self.fingerprint:
                stream["tlsSettings"]["fingerprint"] = self.fingerprint
        elif self.security == OutboundSecurity.reality:
            stream["security"] = "reality"
            stream["realitySettings"] = {"serverName": self.sni or self.address or ""}
            if self.fingerprint:
                stream["realitySettings"]["fingerprint"] = self.fingerprint

        out = {"tag": self.tag, "protocol": self.protocol.value, "settings": settings}
        if stream:
            out["streamSettings"] = stream

        if self.extra_json and self.extra_json.strip() not in ('', '{}'):
            try:
                extra = json.loads(self.extra_json)
                out = _deep_merge(out, extra)
            except Exception:
                pass
        return out

    def to_singbox_dict(self) -> dict:
        """sing-box's outbound schema (used by singbox/configs/06_outbounds.
        json.j2, merged the same way xray's is: build_custom_singbox_extra()
        -> all_configs_for_cli() -> additional_configs_singbox).

        ⚠️ Written directly from sing-box's documented outbound schema, not
        verified against a real server - in particular the "wireguard"
        outbound type is the pre-1.11 schema (this codebase's other singbox
        templates don't use the newer 1.11+ "endpoints" array anywhere, so
        that's assumed to be what's actually deployed, but isn't confirmed).
        """
        import json

        if self.protocol == OutboundProtocol.amneziawg:
            # Same reasoning as to_xray_dict() - bind to this row's own
            # AmneziaWG interface (other/amneziawg/run.sh.j2 brings it up
            # from render_amneziawg_conf()), sing-box itself never dials
            # AmneziaWG's obfuscated protocol directly.
            return {"tag": self.tag, "type": "direct", "bind_interface": self.amneziawg_interface}

        out: dict = {"tag": self.tag}

        if self.protocol == OutboundProtocol.freedom:
            out["type"] = "direct"
        elif self.protocol == OutboundProtocol.wireguard:
            out["type"] = "wireguard"
            out["server"] = self.address or ""
            out["server_port"] = self.port or 51820
            out["private_key"] = self.uuid_or_password or ""
            out["peer_public_key"] = self.peer_public_key or ""
            out["local_address"] = [self.local_address] if self.local_address else ["10.0.0.2/32"]
        else:
            type_map = {
                OutboundProtocol.vless: "vless", OutboundProtocol.vmess: "vmess",
                OutboundProtocol.trojan: "trojan", OutboundProtocol.shadowsocks: "shadowsocks",
                OutboundProtocol.socks: "socks", OutboundProtocol.http: "http",
            }
            out["type"] = type_map[self.protocol]
            out["server"] = self.address or ""
            out["server_port"] = self.port or 443

            if self.protocol in (OutboundProtocol.vless, OutboundProtocol.vmess):
                out["uuid"] = self.uuid_or_password or ""
                if self.protocol == OutboundProtocol.vless:
                    if self.flow:
                        out["flow"] = self.flow
                else:
                    out["security"] = "auto"
            elif self.protocol == OutboundProtocol.trojan:
                out["password"] = self.uuid_or_password or ""
            elif self.protocol == OutboundProtocol.shadowsocks:
                out["password"] = self.uuid_or_password or ""
                out["method"] = "chacha20-ietf-poly1305"
            elif self.protocol in (OutboundProtocol.socks, OutboundProtocol.http):
                if self.uuid_or_password:
                    user, _, pw = self.uuid_or_password.partition(':')
                    out["username"] = user
                    out["password"] = pw

            if self.protocol in (OutboundProtocol.vless, OutboundProtocol.vmess, OutboundProtocol.trojan):
                if self.network != OutboundNetwork.tcp:
                    transport: dict = {"type": self.network.value}
                    if self.network == OutboundNetwork.ws:
                        transport["path"] = self.ws_path or "/"
                        if self.host_header:
                            transport["headers"] = {"Host": self.host_header}
                    elif self.network == OutboundNetwork.grpc:
                        transport["service_name"] = self.ws_path or ""
                    elif self.network in (OutboundNetwork.httpupgrade, OutboundNetwork.xhttp):
                        transport["path"] = self.ws_path or "/"
                        if self.host_header:
                            transport["host"] = self.host_header
                    out["transport"] = transport

                if self.security in (OutboundSecurity.tls, OutboundSecurity.reality):
                    tls: dict = {"enabled": True, "server_name": self.sni or self.address or ""}
                    if self.fingerprint:
                        tls["utls"] = {"enabled": True, "fingerprint": self.fingerprint}
                    if self.security == OutboundSecurity.reality:
                        tls["reality"] = {"enabled": True}
                    out["tls"] = tls

        if self.extra_json and self.extra_json.strip() not in ('', '{}'):
            try:
                extra = json.loads(self.extra_json)
                out = _deep_merge(out, extra)
            except Exception:
                pass
        return out


def parse_vless_link(link: str) -> dict:
    """Parse a vless:// share link into the field values CustomOutbound
    needs, so an admin can paste a link from another panel/provider instead
    of manually copying uuid/host/port/sni/etc into separate form fields.

    Raises ValueError with a human-readable reason on anything unparseable -
    the caller (OutboundAdmin.on_model_change) turns that into a form
    ValidationError.
    """
    from urllib.parse import urlparse, parse_qs, unquote

    link = (link or '').strip()
    if not link.lower().startswith('vless://'):
        raise ValueError('Only vless:// links are supported')

    parsed = urlparse(link)
    if not parsed.username:
        raise ValueError('Link is missing the UUID (vless://UUID@host:port...)')
    if not parsed.hostname:
        raise ValueError('Link is missing the server address')

    # parse_qs already percent-decodes both keys and values.
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    network_map = {
        'ws': OutboundNetwork.ws, 'grpc': OutboundNetwork.grpc,
        'httpupgrade': OutboundNetwork.httpupgrade, 'xhttp': OutboundNetwork.xhttp,
        'tcp': OutboundNetwork.tcp, 'raw': OutboundNetwork.tcp,
    }
    security_map = {
        'none': OutboundSecurity.none, 'tls': OutboundSecurity.tls,
        'reality': OutboundSecurity.reality, 'xtls': OutboundSecurity.tls,
    }

    network_key = (q.get('type') or 'tcp').lower()
    security_key = (q.get('security') or 'none').lower()
    path = q.get('serviceName') if network_key == 'grpc' else q.get('path')

    return {
        'protocol': OutboundProtocol.vless,
        'address': parsed.hostname,
        'port': parsed.port or 443,
        'uuid_or_password': parsed.username,
        'network': network_map.get(network_key, OutboundNetwork.tcp),
        'security': security_map.get(security_key, OutboundSecurity.none),
        'sni': q.get('sni', ''),
        'ws_path': path or '',
        'host_header': q.get('host', ''),
        'fingerprint': q.get('fp', ''),
        'flow': q.get('flow', ''),
        'comment': unquote(parsed.fragment) if parsed.fragment else '',
    }


class CustomRoutingRule(db.Model):  # type: ignore
    """A custom Xray routing rule. Evaluated in `priority` order (lowest
    first), and always BEFORE Hiddify's own built-in catch-all rule so a
    custom rule always gets a chance to match first.
    """
    id = Column(Integer, primary_key=True, autoincrement=True)
    child_id = Column(Integer, ForeignKey('child.id'), default=0)
    enable = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=100, nullable=False)
    outbound_tag = Column(String(100), nullable=False)
    domains = Column(Text, nullable=True, default='')   # newline-separated, e.g. domain:example.com / geosite:netflix
    ips = Column(Text, nullable=True, default='')        # newline-separated, e.g. 1.2.3.4 / geoip:ir
    port = Column(String(100), nullable=True, default='')  # e.g. "443" or "1000-2000"
    network = Column(String(20), nullable=True, default='')  # "", "tcp", "udp", "tcp,udp"
    # comma-separated xray inbound tags (see get_available_inbound_tags()) -
    # matches traffic by which inbound it arrived on, instead of/alongside
    # domain or IP.
    inbound_tags = Column(Text, nullable=True, default='')
    comment = Column(String(300), nullable=True, default='')

    def to_xray_dict(self) -> dict:
        rule: dict = {"type": "field", "outboundTag": self.outbound_tag}
        domains = [d.strip() for d in (self.domains or '').splitlines() if d.strip()]
        ips = [i.strip() for i in (self.ips or '').splitlines() if i.strip()]
        inbound_tags = [t.strip() for t in (self.inbound_tags or '').split(',') if t.strip()]
        if inbound_tags:
            rule["inboundTag"] = inbound_tags
        if domains:
            rule["domain"] = domains
        if ips:
            rule["ip"] = ips
        if self.port:
            rule["port"] = self.port
        if self.network:
            rule["network"] = self.network
        return rule

    def to_singbox_dict(self) -> dict:
        """sing-box's rule schema (1.8+ 'action' style, matching this
        codebase's other singbox templates): no "type":"field" wrapper,
        "inbound"/"outbound" instead of xray's "inboundTag"/"outboundTag".
        Reuses the exact same inbound_tags/domains/ips/port/network fields -
        whichever tags don't apply to the currently-active core (e.g. xray-
        only tags while running singbox) simply never match anything."""
        rule: dict = {"outbound": self.outbound_tag}
        domains = [d.strip() for d in (self.domains or '').splitlines() if d.strip()]
        ips = [i.strip() for i in (self.ips or '').splitlines() if i.strip()]
        inbound_tags = [t.strip() for t in (self.inbound_tags or '').split(',') if t.strip()]
        if inbound_tags:
            rule["inbound"] = inbound_tags
        if domains:
            rule["domain"] = domains
        if ips:
            rule["ip_cidr"] = ips
        if self.port:
            rule["port"] = self.port
        if self.network:
            rule["network"] = self.network
        return rule


def get_available_inbound_tags() -> list[tuple[str, str]]:
    """The real xray inbound tags that will actually exist in the generated
    config, so a routing rule can match "traffic that came in on this
    inbound" (inboundTag) instead of only domain/IP.

    Hiddify does NOT create one inbound per Proxy row (protocol/transport/
    cdn-mode/domain combination) - most protocol+transport combinations
    share a single inbound routed to by HAProxy/SNI regardless of which
    domain or CDN mode the client used (see xray/configs/05_inbounds_new.
    json.j2: tag "v10-{protocol}-{stream}"). So the granularity here is
    "this protocol over this transport", not a specific domain/mode/proxy
    combination - the closest real match to what actually exists on the
    wire. Reality is the one exception: each reality domain gets its own
    dedicated inbound (xray/configs/05_inbounds_02_reality_main.json.j2:
    tag "realityin_{stream}_{port}"), so those are listed per-domain.

    Returns a list of (tag, human-readable label) tuples for use as
    SelectField choices, mirroring the *_enable flags and loops the
    templates themselves use so this only ever lists tags that will really
    be generated.
    """
    from hiddifypanel.models.config import hconfig
    from hiddifypanel.models.config_enum import ConfigEnum
    from hiddifypanel.models.domain import Domain, DomainType
    from hiddifypanel.models.child import Child

    child_id = Child.current().id
    choices = []

    core_type = hconfig(ConfigEnum.core_type, child_id)
    for protocol in ['vless', 'vmess', 'trojan']:
        if not hconfig(getattr(ConfigEnum, f'{protocol}_enable'), child_id):
            continue
        for stream in ['xhttp', 'ws', 'grpc', 'tcp', 'httpupgrade']:
            if stream != 'xhttp' and core_type != 'xray':
                continue
            if not hconfig(getattr(ConfigEnum, f'{stream}_enable'), child_id):
                continue
            tag = f'v10-{protocol}-{stream}'
            choices.append((tag, f'{protocol} / {stream} (any domain, direct+CDN+relay)'))

    if hconfig(ConfigEnum.vless_enable, child_id) and hconfig(ConfigEnum.kcp_enable, child_id):
        choices.append(('kcp', 'vless / kcp'))

    if hconfig(ConfigEnum.reality_enable, child_id):
        reality_streams = {
            DomainType.special_reality_tcp: 'tcp',
            DomainType.special_reality_xhttp: 'xhttp',
            DomainType.special_reality_grpc: 'grpc',
        }
        domains = Domain.query.filter(Domain.child_id == child_id, Domain.mode.in_(list(reality_streams.keys()))).all()
        for d in domains:
            port = d.internal_port_special
            if not port:
                continue
            stream = reality_streams[d.mode]
            tag = f'realityin_{stream}_{port}'
            choices.append((tag, f'{d.domain} - reality {stream}'))

    # mieru/naive/tuic/hysteria2 only exist under singbox in this codebase
    # (no xray equivalent at all - see singbox/configs/05_inbounds_mieru.
    # json.j2 etc.), so these only ever mean anything with core_type=
    # singbox, but are listed regardless of core_type since a routing rule
    # picked now still applies correctly if core_type is switched later.
    if hconfig(ConfigEnum.mieru_enable, child_id):
        if hconfig(ConfigEnum.mieru_tcp_ports, child_id):
            choices.append(('v10-mieru-tcp', 'mieru / tcp'))
        if hconfig(ConfigEnum.mieru_udp_ports, child_id):
            choices.append(('v10-mieru-udp', 'mieru / udp'))

    if hconfig(ConfigEnum.naive_enable, child_id):
        choices.append(('v10-naive', 'naive / tcp (any domain)'))

    domains_for_ports = Domain.query.filter(Domain.child_id == child_id).all()
    if hconfig(ConfigEnum.tuic_enable, child_id):
        for d in domains_for_ports:
            if d.internal_port_tuic:
                choices.append((f'tuic_in_{d.internal_port_tuic}', f'{d.domain} - tuic'))
    if hconfig(ConfigEnum.hysteria_enable, child_id):
        for d in domains_for_ports:
            if d.internal_port_hysteria2:
                choices.append((f'hysteria_in_{d.internal_port_hysteria2}', f'{d.domain} - hysteria2'))
    if hconfig(ConfigEnum.naive_enable, child_id):
        for d in domains_for_ports:
            if d.internal_port_naive:
                choices.append((f'v10-naive-quic{d.internal_port_naive}', f'{d.domain} - naive quic'))

    return choices


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def build_custom_xray_extra() -> dict:
    """Serialize all enabled CustomOutbound/CustomRoutingRule rows (for the
    current child) into the {"outbounds": [...], "routing_rules": [...]}
    shape that xray/configs/06_outbounds.json.j2 and 03_routing.json.j2
    already know how to merge in."""
    from hiddifypanel.models.child import Child
    child_id = Child.current().id
    outbounds = [
        o.to_xray_dict()
        for o in CustomOutbound.query.filter_by(child_id=child_id, enable=True).all()
    ]
    rules = [
        r.to_xray_dict()
        for r in CustomRoutingRule.query.filter_by(child_id=child_id, enable=True).order_by(CustomRoutingRule.priority.asc()).all()
    ]
    return {"outbounds": outbounds, "routing_rules": rules}


def build_custom_singbox_extra() -> dict:
    """Same as build_custom_xray_extra() but in sing-box's schema, merged
    into additional_configs_singbox and read by singbox/configs/
    06_outbounds.json.j2 and 03_routing.json.j2. Same underlying
    CustomOutbound/CustomRoutingRule rows as the xray version - one set of
    admin-entered outbounds/rules, rendered in whichever core's own schema
    is actually needed, so switching core_type doesn't require re-entering
    anything."""
    from hiddifypanel.models.child import Child
    child_id = Child.current().id
    outbounds = [
        o.to_singbox_dict()
        for o in CustomOutbound.query.filter_by(child_id=child_id, enable=True).all()
    ]
    rules = [
        r.to_singbox_dict()
        for r in CustomRoutingRule.query.filter_by(child_id=child_id, enable=True).order_by(CustomRoutingRule.priority.asc()).all()
    ]
    return {"outbounds": outbounds, "routing_rules": rules}


def get_amneziawg_outbounds() -> list[dict]:
    """Every enabled Outbound with Protocol=amneziawg, serialized for
    other/amneziawg/run.sh.j2 (a Jinja template, same as other/wireguard/
    run.sh.j2) to write one /etc/amnezia/amneziawg/{interface}.conf per row
    and bring up its awg-quick@{interface} instance. Read via
    all_configs_for_cli() -> current.json -> common/jinja.py, exactly like
    `users`/`domains` already are for other templates."""
    from hiddifypanel.models.child import Child
    child_id = Child.current().id
    rows = CustomOutbound.query.filter_by(child_id=child_id, protocol=OutboundProtocol.amneziawg, enable=True).all()
    return [{"interface": o.amneziawg_interface, "conf": o.render_amneziawg_conf()} for o in rows]
