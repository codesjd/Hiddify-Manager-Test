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
    comment = Column(String(300), nullable=True, default='')
    # Advanced escape hatch: raw JSON merged on top of the generated
    # outbound dict (e.g. {"streamSettings": {"grpcSettings": {...}}}).
    extra_json = Column(Text, nullable=True, default='{}')

    def to_xray_dict(self) -> dict:
        import json
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
