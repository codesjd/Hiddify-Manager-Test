
from strenum import StrEnum
from enum import auto
from sqlalchemy import Column, String, Integer, Boolean, Enum, ForeignKey

from hiddifypanel.database import db

from sqlalchemy.types import JSON


class ProxyTransport(StrEnum):
    h2 = auto()
    grpc = auto()
    # XTLS = auto()
    faketls = auto()
    shadowtls = auto()
    restls1_2 = auto()
    restls1_3 = auto()
    # h1=auto()
    WS = auto()
    tcp = auto()
    ssh = auto()
    httpupgrade = auto()
    xhttp = auto()
    custom = auto()
    shadowsocks = auto()
    udp = auto()


class ProxyCDN(StrEnum):
    CDN = auto()
    direct = auto()
    Fake = auto()
    relay = auto()


class ProxyProto(StrEnum):
    vless = auto()
    trojan = auto()
    vmess = auto()
    ss = auto()
    v2ray = auto()
    ssr = auto()
    ssh = auto()
    tuic = auto()
    hysteria = auto()
    hysteria2 = auto()
    wireguard = auto()
    naive = auto()
    mieru = auto()
    dnstt = auto()
    amneziawg = auto()
    anytls = auto()
    # DNS-tunneled / ICMP-tunneled vless via Xray-core's finalmask
    # (XTLS/Xray-core#5560/#5633) - unlike dnstt, these ARE real vless
    # connections a finalmask-aware client can dial directly, see
    # to_link()'s xdns/xicmp branches.
    xdns = auto()
    xicmp = auto()


class ProxyL3(StrEnum):
    tls = auto()
    tls_h2 = auto()
    tls_h2_h1 = auto()
    h3_quic = auto()
    reality = auto()
    http = auto()
    kcp = auto()
    ssh = auto()
    udp = auto()
    custom = auto()


class Proxy(db.Model):  # type: ignore
    id = Column(Integer, primary_key=True, autoincrement=True)
    child_id = Column(Integer, ForeignKey('child.id'), default=0)
    name = Column(String(200), nullable=False, unique=False)
    enable = Column(Boolean, nullable=False)
    proto = Column(Enum(ProxyProto), nullable=False)
    l3 = Column(Enum(ProxyL3), nullable=False)
    transport = Column(Enum(ProxyTransport), nullable=False)
    cdn = Column(Enum(ProxyCDN), nullable=False)
    # A literal {} default would be the same dict instance reused by
    # SQLAlchemy for every row that doesn't set params explicitly - a
    # callable default gets invoked fresh per-row instead.
    params = Column(JSON, default=dict)

    @property
    def enabled(self):
        return self.enable * 1

    def to_dict(self):
        return {
            'name': self.name,
            'enable': self.enable,
            'proto': self.proto,
            'l3': self.l3,
            'transport': self.transport,
            'cdn': self.cdn,
            'child_unique_id': self.child.unique_id if self.child else '',
            'params': self.params
        }

    def __str__(self):
        return str(self.to_dict())

    @staticmethod
    def add_or_update(commit=True, child_id=0, _dto=None, **proxy):
        from hiddifypanel.models.dto import ProxyDTO, _as_dto
        u = _dto or _as_dto(proxy, ProxyDTO)
        proxy_name = u.name if _dto else proxy['name']
        dbproxy = Proxy.query.filter(Proxy.name == proxy_name).first()
        if not dbproxy:
            dbproxy = Proxy()
            db.session.add(dbproxy)  # type: ignore
        dbproxy.enable = u.enable if _dto else proxy['enable']
        dbproxy.name = proxy_name
        dbproxy.proto = u.proto if _dto else proxy['proto']
        transport = u.transport if _dto else proxy['transport']
        if transport == "splithttp":
            transport = "xhttp"
        dbproxy.transport = transport
        dbproxy.cdn = u.cdn if _dto else proxy['cdn']
        dbproxy.l3 = u.l3 if _dto else proxy['l3']
        dbproxy.params = u.params if _dto else proxy['params']
        dbproxy.child_id = child_id
        if commit:
            db.session.commit()  # type: ignore

    @staticmethod
    def from_schema(schema):
        return schema.dump(Proxy())

    def to_schema(self):
        proxy_dict = self.to_dict()
        from hiddifypanel.panel.commercial.restapi.v2.parent.schema import ProxySchema
        return ProxySchema().load(proxy_dict)

    @staticmethod
    def bulk_register(proxies, commit=True, force_child_unique_id: str | None = None):
        from hiddifypanel.panel import hiddify
        from hiddifypanel.models.dto import ProxyDTO, _as_dto
        proxies = [_as_dto(p, ProxyDTO) for p in proxies]
        for proxy in proxies:
            child_id = hiddify.get_child(unique_id=force_child_unique_id)
            Proxy.add_or_update(commit=False, child_id=child_id, _dto=proxy)
        if commit:
            db.session.commit()  # type: ignore


class DomainProxyOverride(db.Model):  # type: ignore
    """A per-(domain, proxy) override - the axis neither existing override
    mechanism actually covers.

    InboundOverrideAdmin's Proxy.params overrides a proto/transport/cdn
    combination for every domain that uses it. Domain.extra_params
    overrides every proxy generated for one domain. Neither lets an admin
    say "just THIS domain, just THIS one inbound combination" - which is
    exactly the request this model exists for: force a specific proxy row
    on or off for one domain only, or tweak its generated config (sni,
    fingerprint, alpn, ...) without that also touching every other domain
    sharing the same proxy row, or every other proxy on this same domain.

    enable=None means "don't touch the decision get_valid_proxies() would
    otherwise make" (respects the global protocol toggle and the Proxy
    row's own enable flag). enable=True forces this proxy on for this
    domain even if it's disabled everywhere else; enable=False forces it
    off for this domain even if it's enabled everywhere else.

    params is deep-merged on top of the generated proxy dict in
    get_valid_proxies(), after both Proxy.params and Domain.extra_params -
    it's the most specific override, so it wins on any key conflict.
    """
    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_id = Column(Integer, ForeignKey('domain.id', ondelete='CASCADE'), nullable=False)
    proxy_id = Column(Integer, ForeignKey('proxy.id', ondelete='CASCADE'), nullable=False)
    domain = db.relationship('Domain', foreign_keys=[domain_id])
    proxy = db.relationship('Proxy', foreign_keys=[proxy_id])
    enable = Column(Boolean, nullable=True)
    params = Column(JSON, default=dict)

    __table_args__ = (
        db.UniqueConstraint('domain_id', 'proxy_id', name='uq_domain_proxy_override'),
    )

