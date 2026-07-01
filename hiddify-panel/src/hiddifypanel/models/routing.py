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
            elif self.network == OutboundNetwork.grpc:
                stream["grpcSettings"] = {"serviceName": self.ws_path or ""}
            elif self.network in (OutboundNetwork.httpupgrade, OutboundNetwork.xhttp):
                stream[f"{self.network.value}Settings"] = {"path": self.ws_path or "/"}

        if self.security == OutboundSecurity.tls:
            stream["security"] = "tls"
            stream["tlsSettings"] = {"serverName": self.sni or self.address or ""}
        elif self.security == OutboundSecurity.reality:
            stream["security"] = "reality"
            stream["realitySettings"] = {"serverName": self.sni or self.address or ""}

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
    comment = Column(String(300), nullable=True, default='')

    def to_xray_dict(self) -> dict:
        rule: dict = {"type": "field", "outboundTag": self.outbound_tag}
        domains = [d.strip() for d in (self.domains or '').splitlines() if d.strip()]
        ips = [i.strip() for i in (self.ips or '').splitlines() if i.strip()]
        if domains:
            rule["domain"] = domains
        if ips:
            rule["ip"] = ips
        if self.port:
            rule["port"] = self.port
        if self.network:
            rule["network"] = self.network
        return rule


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
