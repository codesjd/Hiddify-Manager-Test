from enum import auto
import ipaddress
import json
import re
from typing import Dict, List
from flask import request

from sqlalchemy.orm import backref
from strenum import StrEnum


from hiddifypanel.database import db
from hiddifypanel.models.config import hconfig
from .child import Child
from hiddifypanel.models.config_enum import ConfigEnum


class DomainType(StrEnum):
    direct = auto()
    sub_link_only = auto()
    cdn = auto()
    auto_cdn_ip = auto()
    relay = auto()
    worker = auto()
    fake = auto()

    reality = auto() #deprecated
    special_reality_tcp = auto()
    special_reality_xhttp = auto()
    special_reality_grpc = auto()
    old_xtls_direct = auto() #deprecated
    dnstt = auto()
    # DNS-tunneled and ICMP-tunneled traffic via Xray-core's finalmask
    # (xdns/xicmp masks, XTLS/Xray-core#5560/#5633). Modeled the same way
    # as dnstt above - each is its own dedicated mKCP+finalmask Xray inbound
    # on a per-domain auto-allocated port (see internal_port_xdns/
    # internal_port_xicmp below), never sharing the plain xhttp/ws/grpc
    # inbounds every other mode uses. finalmask changes the wire format for
    # the whole inbound it's attached to, so masked traffic must never be
    # stacked onto an inbound normal clients also connect through.
    xdns = auto()
    xicmp = auto()
    # special_shadowtls = auto()

    # fake_cdn = "fake_cdn"
    # telegram_faketls = "telegram_faketls"
    # ss_faketls = "ss_faketls"


ShowDomain = db.Table('show_domain',
                      db.Column('domain_id', db.Integer, db.ForeignKey('domain.id'), primary_key=True),
                      db.Column('related_id', db.Integer, db.ForeignKey('domain.id'), primary_key=True)
                      )



class Domain(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    child_id = db.Column(db.Integer, db.ForeignKey('child.id'), default=0)
    domain = db.Column(db.String(200), nullable=True, unique=False)
    alias = db.Column(db.String(200))
    sub_link_only = db.Column(db.Boolean, nullable=False, default=False)
    mode = db.Column(db.Enum(DomainType), nullable=False, default=DomainType.direct)
    cdn_ip = db.Column(db.Text(2000), nullable=True, default='')
    # port_index=db.Column(db.Integer, nullable=True, default=0)
    grpc = db.Column(db.Boolean, nullable=True, default=False)
    servernames = db.Column(db.String(1000), nullable=True, default='')
    # show_all=db.Column(db.Boolean, nullable=True)
    show_domains = db.relationship('Domain', secondary=ShowDomain,
                                   primaryjoin=id == ShowDomain.c.domain_id,
                                   secondaryjoin=id == ShowDomain.c.related_id,
                                   backref=backref('showed_by_domains', lazy='dynamic')
                                   )
    download_domain_id= db.Column(db.Integer, db.ForeignKey('domain.id', ondelete='SET NULL'), default=None,nullable=True)
    download_domain = db.relationship('Domain',remote_side=[id],    foreign_keys=[download_domain_id])
    extra_params = db.Column(db.String(2000), nullable=True, default='{}')
    resolve_ip= db.Column(db.Boolean, nullable=True, default=False)
    # Per-domain HTTP/TLS port override, replacing the old global Settings-page
    # http_ports/tls_ports lists. NULL means "use the shared default port"
    # (80 for http, 443 for tls) - every existing domain keeps working
    # unchanged. A non-default value is exclusive to this domain: haproxy
    # (haproxy/fronts/in_tcpmode.cfg.pj2, sni_proxy.cfg.pj2) rejects that
    # domain's traffic on any other port, and rejects every other domain's
    # traffic on this one.
    http_port = db.Column(db.Integer, nullable=True, default=None)
    tls_port = db.Column(db.Integer, nullable=True, default=None)
    # Per-domain REALITY port/keys/short ID, replacing the old global
    # Settings-page special_port/reality_private_key/reality_public_key/
    # reality_short_ids fields. NULL means "fall back to the previous
    # global-config-derived value" (see effective_reality_*/
    # internal_port_special below) - every existing REALITY domain keeps
    # serving the exact same port/keys/short ID it already handed out to
    # clients. DomainAdmin auto-generates fresh, independent values for
    # each *new* reality-mode domain (see DomainAdmin._validate_reality_settings),
    # while still letting the admin override them by hand afterward.
    reality_port = db.Column(db.Integer, nullable=True, default=None)
    reality_private_key = db.Column(db.String(100), nullable=True, default=None)
    reality_public_key = db.Column(db.String(100), nullable=True, default=None)
    reality_short_id = db.Column(db.String(200), nullable=True, default=None)

    def extra_params_json(self):
        import json
        try:
            return json.loads(self.extra_params)
        except:
            return {}
    def __repr__(self):
        return f'{self.domain}'

    def get_cdn_ips_parsed(self):
        ips = re.split('[ \t\r\n;,]+', self.cdn_ip.strip())
        res = set()
        for ip in ips:
            try:
                res.add(ipaddress.ip_address(ip))
            except:
                pass
        return res

    def to_dict(self, dump_ports=False, dump_child_id=False):
        try:
            extra=json.loads(self.extra_params or "{}")
        except:
            extra={}
        data = {
            'domain': self.domain.lower(),
            'mode': self.mode,
            'alias': self.alias,
            'sub_link_only': self.sub_link_only,
            'child_unique_id': self.child.unique_id if self.child else '',  # type: ignore
            'cdn_ip': self.cdn_ip,
            'servernames': self.servernames,
            'grpc': self.grpc,
            'download_domain':self.download_domain.domain if self.download_domain else "",
            'show_domains': [dd.domain for dd in self.show_domains],  # type: ignore
            "resolve_ip":self.resolve_ip,
            "extra_params":extra,
            "http_port": self.http_port,
            "tls_port": self.tls_port,
        }
        if dump_child_id:
            data['child_id'] = self.child_id
        if dump_ports:
            data["internal_port_hysteria2"] = self.internal_port_hysteria2
            data["internal_port_xray_hysteria"] = self.internal_port_xray_hysteria
            data["internal_port_tuic"] = self.internal_port_tuic
            data["internal_port_naive"] = self.internal_port_naive
            data["internal_port_special"] = self.internal_port_special
            data["internal_port_dnstt"] = self.internal_port_dnstt
            data["internal_port_xdns"] = self.internal_port_xdns
            data["internal_port_xicmp"] = self.internal_port_xicmp
            data["xdns_resolvers"] = self.effective_xdns_resolvers
            data["internal_port_anytls"] = self.internal_port_anytls
            data["need_valid_ssl"] = self.need_valid_ssl
            data["reality_private_key"] = self.effective_reality_private_key
            data["reality_public_key"] = self.effective_reality_public_key
            data["reality_short_id"] = self.effective_reality_short_id

        return data

    @staticmethod
    def from_schema(schema):
        return schema.dump(Domain())

    def to_schema(self):
        domain_dict = self.to_dict()
        from hiddifypanel.panel.commercial.restapi.v2.parent.schema import DomainSchema
        return DomainSchema().load(domain_dict)


    def auto_cdn_ip(self):
        from hiddifypanel import hutils
        if self.cdn_ip:
            return hutils.network.auto_ip_selector.get_clean_ip(self.cdn_ip)
        return None

    @property
    def need_valid_ssl(self):
        if self.mode not in [DomainType.direct, DomainType.cdn, DomainType.worker, DomainType.relay, DomainType.auto_cdn_ip, DomainType.old_xtls_direct, DomainType.sub_link_only]:
            return False
        try:
            # A bare IP address (e.g. the auto-seeded "external_ip" bootstrap
            # domain from init_db.py's _v1) can never get a real CA-signed
            # cert - acme.sh/Let's Encrypt don't issue certs for IPs here -
            # so it always ends up self-signed. Claiming it "needs" a valid
            # cert both (a) triggered a doomed ACME issuance attempt on
            # every save (DomainAdmin.after_model_change) and (b) left
            # allow_insecure/pinned-cert-hash off when generating its
            # tuic/naive/hysteria2/anytls links (shared.py), so those
            # clients did strict CA validation against a self-signed cert
            # and failed outright instead of falling back to pinning like
            # every other self-signed domain does.
            ipaddress.ip_address(self.domain)
            return False
        except ValueError:
            return True

    @property
    def port_index(self):
        return self.id

    @property
    def effective_http_port(self) -> int:
        return self.http_port or 80

    @property
    def effective_tls_port(self) -> int:
        return self.tls_port or 443

    @staticmethod
    def _safe_port_offset(base_port: int, offset: int) -> int:
        """Combine a configured base port with a per-domain offset (port_index)
        and keep the result inside the valid TCP/UDP port range.

        Previously internal_port_hysteria2/tuic/naive/special/dnstt just did
        `base_port + port_index` with a bare '# TODO: check validity of the
        range of the port' and no check at all. With enough domains, that sum
        silently walks past 65535 (wraps to garbage in some clients) or lands
        on a low/reserved port (e.g. 22, 80, 443) already used by ssh/nginx,
        and the collision only shows up as a service refusing to bind - no
        error pointing back at the cause.
        """
        import logging
        port = base_port + offset
        if port > 65535:
            # wrap back into the high, mostly-unused range instead of
            # producing an invalid port number
            port = 20000 + (port % 10000)
            logging.getLogger(__name__).warning(
                f"Domain port offset overflowed 65535 (base={base_port}, offset={offset}); "
                f"wrapped to {port}. Consider lowering the base port or the number of domains."
            )
        elif port < 1024:
            logging.getLogger(__name__).warning(
                f"Domain computed port {port} falls in the reserved/well-known range "
                f"(base={base_port}, offset={offset}); this may collide with ssh/nginx/etc."
            )
        return port

    @property
    def internal_port_hysteria2(self):
        if self.mode not in [DomainType.direct, DomainType.relay, DomainType.fake]:
            return 0
        return self._safe_port_offset(int(hconfig(ConfigEnum.hysteria_port, self.child_id)), self.port_index)

    @property
    def internal_port_xray_hysteria(self):
        # Xray-core's own native "hysteria" protocol needs its own inbound/
        # port, separate from internal_port_hysteria2 above - Xray's
        # implementation has no salamander/obfs support, so it can't share
        # the sing-box hysteria2 inbound's port.
        if self.mode not in [DomainType.direct, DomainType.relay, DomainType.fake]:
            return 0
        return self._safe_port_offset(int(hconfig(ConfigEnum.xray_hysteria_port, self.child_id)), self.port_index)

    @property
    def internal_port_dnstt(self):
        if self.mode not in [DomainType.dnstt]:
            return 0
        return self._safe_port_offset(5400, self.port_index)

    @property
    def internal_port_xdns(self):
        # Own base offset (distinct from dnstt's 5400), so a server running
        # both dnstt and xdns domains never collides on the same port.
        if self.mode not in [DomainType.xdns]:
            return 0
        return self._safe_port_offset(5500, self.port_index)

    @property
    def internal_port_xicmp(self):
        if self.mode not in [DomainType.xicmp]:
            return 0
        return self._safe_port_offset(5600, self.port_index)


    @property
    def internal_port_tuic(self):
        if self.mode not in [DomainType.direct, DomainType.relay, DomainType.fake]:
            return 0
        return self._safe_port_offset(int(hconfig(ConfigEnum.tuic_port, self.child_id)), self.port_index)

    @property
    def internal_port_anytls(self):
        if self.mode not in [DomainType.direct, DomainType.relay, DomainType.fake]:
            return 0
        return self._safe_port_offset(int(hconfig(ConfigEnum.anytls_port, self.child_id)), self.port_index)

    @property
    def internal_port_naive(self):
        if self.mode not in [DomainType.direct, DomainType.relay]:
            return 0
        return self._safe_port_offset(int(hconfig(ConfigEnum.naive_port, self.child_id)), self.port_index)

    @property
    def internal_port_special(self):
        if self.mode != DomainType.reality and "special" not in self.mode.value:
            return 0
        if self.reality_port:
            return self.reality_port
        return self._safe_port_offset(int(hconfig(ConfigEnum.special_port, self.child_id)), self.port_index)

    @property
    def effective_reality_private_key(self) -> str:
        return self.reality_private_key or hconfig(ConfigEnum.reality_private_key, self.child_id)

    @property
    def effective_reality_public_key(self) -> str:
        return self.reality_public_key or hconfig(ConfigEnum.reality_public_key, self.child_id)

    @property
    def effective_reality_short_id(self) -> str:
        return self.reality_short_id or hconfig(ConfigEnum.reality_short_ids, self.child_id)

    @property
    def effective_xdns_resolvers(self) -> str:
        return self.extra_params_json().get('xdns_resolvers') or hconfig(ConfigEnum.xdns_resolvers, self.child_id) or "8.8.8.8:53,1.1.1.1:53"

    @classmethod
    def by_mode(cls, mode: DomainType) -> List['Domain']:
        domains = Domain.query.filter(Domain.mode == mode).all()
        if domains:
            return [d.domain for d in domains]
        return []

    @classmethod
    def modes_and_domains(cls) -> Dict[DomainType, List['Domain']]:
        return {mode: cls.by_mode(mode) for mode in DomainType}

    @classmethod
    def by_domain(cls, domain: str) -> 'Domain | None':
        return Domain.query.filter(Domain.domain == domain).first()

    @classmethod
    def get_panel_link(cls, child_id: int | None = None) -> str | None:
        if child_id is None:
            child_id = Child.current().id  # type: ignore
        domains = Domain.query.filter(Domain.mode.in_(
            [DomainType.direct, DomainType.cdn, DomainType.worker, DomainType.relay, DomainType.auto_cdn_ip, DomainType.old_xtls_direct, DomainType.sub_link_only]),
            Domain.child_id == child_id
        ).all()
        if not domains:
            return None
        return domains[0].domain

    @classmethod
    def get_domains(cls, always_add_ip=False, always_add_all_domains=False) -> List['Domain']:
        from hiddifypanel import hutils
        domains = []
        domains = db.session.query(Domain).filter(Domain.mode == DomainType.sub_link_only, Domain.child_id == Child.current().id).all()
        if not len(domains) or always_add_all_domains:
            domains = db.session.query(Domain).filter(Domain.mode.notin_([DomainType.fake, DomainType.reality,DomainType.special_reality_tcp,DomainType.special_reality_xhttp,DomainType.special_reality_grpc])).all()

        if len(domains) == 0 and request:
            domains = [Domain(domain=request.host)]  # type: ignore
        if len(domains) == 0 or always_add_ip:
            domains += [Domain(domain=hutils.network.get_ip_str(4))]  # type: ignore
        return domains

    @classmethod
    def add_or_update(cls, commit=True, child_id=0, **domain):
        dbdomain = Domain.query.filter(Domain.domain == domain['domain']).first()
        if not dbdomain:
            dbdomain = Domain(domain=domain['domain'])  # type: ignore
            db.session.add(dbdomain)
        dbdomain.child_id = child_id

        dbdomain.mode = domain['mode']
        if (str(domain.get('sub_link_only', False)).lower() == 'true'):
            dbdomain.mode = DomainType.sub_link_only
        dbdomain.cdn_ip = domain.get('cdn_ip', '')
        dbdomain.alias = domain.get('alias', '')
        dbdomain.grpc = domain.get('grpc', False)
        dbdomain.servernames = domain.get('servernames', '')
        dbdomain.resolve_ip=domain.get("resolve_ip",False)
        dbdomain.extra_params=domain.get("extra_params","")
        dbdomain.http_port = domain.get("http_port") or None
        dbdomain.tls_port = domain.get("tls_port") or None
        dbdomain.reality_port = domain.get("reality_port") or None
        dbdomain.reality_private_key = domain.get("reality_private_key") or None
        dbdomain.reality_public_key = domain.get("reality_public_key") or None
        dbdomain.reality_short_id = domain.get("reality_short_id") or None
        show_domains = domain.get('show_domains', [])
        dbdomain.show_domains = Domain.query.filter(Domain.domain.in_(show_domains)).all()
        dl_domain=domain.get("download_domain")
        if dl_domain:
            dbdldomain = Domain.query.filter(Domain.domain == dl_domain).first()
            if not dbdldomain:
                dbdldomain = Domain(domain=dl_domain)  # type: ignore
                db.session.add(dbdldomain)
                db.session.commit()
                dbdldomain=Domain.query.filter(Domain.domain == dl_domain).first()
            assert dbdldomain
            dbdomain.download_domain_id=dbdldomain.id
        else:
            dbdomain.download_domain_id = None
        if commit:
            db.session.commit()

    @classmethod
    def bulk_register(cls, domains, commit=True, remove=False, force_child_unique_id: str | None = None):
        from hiddifypanel.panel import hiddify
        child_ids = {}
        for domain in domains:
            child_id = hiddify.get_child(unique_id=force_child_unique_id)
            child_ids[child_id] = 1
            cls.add_or_update(commit=False, child_id=child_id, **domain)
        if remove and len(child_ids):
            dd = {d['domain']: 1 for d in domains}
            for d in Domain.query.filter(Domain.child_id.in_(child_ids)):
                if d.domain not in dd:
                    db.session.delete(d)

        if commit:
            db.session.commit()
