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
    # hysteria2 outbound. sing-box-only: xray-core has no hysteria dialer at
    # all, so to_xray_dict() emits a fail-closed blackhole for this protocol
    # (see there) - it only actually dials when singbox is the active core.
    hysteria = auto()
    wireguard = auto()
    freedom = auto()
    # Not a real dialed protocol - binds outbound traffic to a standalone
    # per-row AmneziaWG interface (awg{id}) that other/amneziawg/ brings up,
    # the same way the built-in WARP outbound binds to the "warp" interface.
    # The address/port/uuid/peer fields describe that tunnel's [Interface]/
    # [Peer]; see CustomOutbound.render_amneziawg_conf()/to_xray_dict()/
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
    # vless-only encryption (e.g. "none", or a post-quantum ML-KEM option) -
    # was hardcoded to "none" below; xray-core actually reads this per-user.
    encryption = Column(String(100), nullable=True, default='none')
    # REALITY needs the server's actual public key/short id to connect at
    # all - these were missing entirely (to_xray_dict()/to_singbox_dict()
    # only ever sent serverName/fingerprint), making every "reality"
    # security outbound unusable regardless of what else was configured.
    reality_public_key = Column(String(100), nullable=True, default='')
    reality_short_id = Column(String(50), nullable=True, default='')
    # shadowsocks cipher - was hardcoded to chacha20-ietf-poly1305
    # regardless of what the real upstream server actually uses.
    ss_method = Column(String(50), nullable=True, default='chacha20-ietf-poly1305')

    # Xray-core's sockopt block (real, documented fields - shared verbatim
    # across every stream-based protocol, xray-core doesn't vary this by
    # protocol). Left NULL/blank = omitted entirely, since 0 is a
    # meaningful non-default value for several of these (e.g. mark, tcp_fast_open).
    sockopt_mark = Column(Integer, nullable=True)
    sockopt_tcp_fast_open = Column(Boolean, nullable=True)
    sockopt_tproxy = Column(String(20), nullable=True, default='')  # "off"/"redirect"/"tproxy"
    sockopt_domain_strategy = Column(String(30), nullable=True, default='')
    sockopt_dialer_proxy = Column(String(100), nullable=True, default='')
    sockopt_interface = Column(String(50), nullable=True, default='')
    sockopt_tcp_keep_alive_interval = Column(Integer, nullable=True)
    sockopt_tcp_keep_alive_idle = Column(Integer, nullable=True)
    sockopt_tcp_user_timeout = Column(Integer, nullable=True)
    sockopt_tcp_max_seg = Column(Integer, nullable=True)
    sockopt_tcp_window_clamp = Column(Integer, nullable=True)
    sockopt_tcp_mptcp = Column(Boolean, nullable=True)
    sockopt_penetrate = Column(Boolean, nullable=True)
    sockopt_address_port_strategy = Column(String(30), nullable=True, default='')
    # Happy Eyeballs (RFC 8305) dual-stack dial racing - xray-core's own
    # sockopt.happyEyeballs sub-object.
    he_try_delay_ms = Column(Integer, nullable=True)
    he_prioritize_ipv6 = Column(Boolean, nullable=True)
    he_interleave = Column(Integer, nullable=True)
    he_max_concurrent_try = Column(Integer, nullable=True)

    # xray-core's per-outbound mux (connection multiplexing).
    mux_enabled = Column(Boolean, nullable=True, default=False)
    mux_concurrency = Column(Integer, nullable=True)
    mux_xudp_concurrency = Column(Integer, nullable=True)
    mux_xudp_proxy_udp_443 = Column(String(20), nullable=True, default='')  # "reject"/"allow"/"skip"
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
    # hysteria2-only. password reuses uuid_or_password; server/port reuse
    # address/port; sni reuses the shared sni field. These three cover the
    # rest of a hysteria2 outbound: Salamander obfuscation password (blank =
    # no obfs) and the optional client bandwidth hints (0/blank = omit, let
    # hysteria2's congestion control decide).
    hysteria_obfs_password = Column(String(200), nullable=True, default='')
    hysteria_up_mbps = Column(Integer, nullable=True)
    hysteria_down_mbps = Column(Integer, nullable=True)
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

    def _xray_sockopt(self) -> dict:
        """xray-core's sockopt object - real, documented fields, shared
        verbatim across every stream-based protocol. Only ever set when the
        admin actually entered something (None/'' left out entirely rather
        than sent as a false/0/empty value xray-core would treat as an
        explicit override)."""
        sockopt: dict = {}
        if self.sockopt_mark is not None:
            sockopt["mark"] = self.sockopt_mark
        if self.sockopt_tcp_fast_open is not None:
            sockopt["tcpFastOpen"] = self.sockopt_tcp_fast_open
        if self.sockopt_tproxy:
            sockopt["tproxy"] = self.sockopt_tproxy
        if self.sockopt_domain_strategy:
            sockopt["domainStrategy"] = self.sockopt_domain_strategy
        if self.sockopt_dialer_proxy:
            sockopt["dialerProxy"] = self.sockopt_dialer_proxy
        if self.sockopt_interface:
            sockopt["interface"] = self.sockopt_interface
        if self.sockopt_tcp_keep_alive_interval is not None:
            sockopt["tcpKeepAliveInterval"] = self.sockopt_tcp_keep_alive_interval
        if self.sockopt_tcp_keep_alive_idle is not None:
            sockopt["tcpKeepAliveIdle"] = self.sockopt_tcp_keep_alive_idle
        if self.sockopt_tcp_user_timeout is not None:
            sockopt["tcpUserTimeout"] = self.sockopt_tcp_user_timeout
        if self.sockopt_tcp_max_seg is not None:
            sockopt["tcpMaxSeg"] = self.sockopt_tcp_max_seg
        if self.sockopt_tcp_window_clamp is not None:
            sockopt["tcpWindowClamp"] = self.sockopt_tcp_window_clamp
        if self.sockopt_tcp_mptcp is not None:
            sockopt["tcpMptcp"] = self.sockopt_tcp_mptcp
        if self.sockopt_penetrate is not None:
            sockopt["penetrate"] = self.sockopt_penetrate
        if self.sockopt_address_port_strategy:
            sockopt["addressPortStrategy"] = self.sockopt_address_port_strategy
        he: dict = {}
        if self.he_try_delay_ms is not None:
            he["tryDelayMs"] = self.he_try_delay_ms
        if self.he_prioritize_ipv6 is not None:
            he["prioritizeIPv6"] = self.he_prioritize_ipv6
        if self.he_interleave is not None:
            he["interleave"] = self.he_interleave
        if self.he_max_concurrent_try is not None:
            he["maxConcurrentTry"] = self.he_max_concurrent_try
        if he:
            sockopt["happyEyeballs"] = he
        return sockopt

    def _xray_mux(self) -> dict:
        if not self.mux_enabled:
            return {}
        mux: dict = {"enabled": True}
        if self.mux_concurrency is not None:
            mux["concurrency"] = self.mux_concurrency
        if self.mux_xudp_concurrency is not None:
            mux["xudpConcurrency"] = self.mux_xudp_concurrency
        if self.mux_xudp_proxy_udp_443:
            mux["xudpProxyUDP443"] = self.mux_xudp_proxy_udp_443
        return mux

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

        if self.protocol == OutboundProtocol.hysteria:
            # xray-core has no hysteria/hysteria2 outbound at all. Both cores'
            # outbound JSON is precomputed (build_custom_xray_extra runs even
            # when singbox is active), so this row still has to serialize to
            # *valid* xray - emit a blackhole carrying the tag. That keeps any
            # routing rule pointing at this tag resolvable (an unknown
            # outboundTag would make xray reject the whole config) and fails
            # closed: while xray is the active core, traffic routed here is
            # dropped rather than silently leaking out the direct connection.
            return {"tag": self.tag, "protocol": "blackhole", "settings": {}}

        settings: dict = {}
        stream: dict = {}

        if self.protocol in (OutboundProtocol.vless, OutboundProtocol.vmess):
            user = {"id": self.uuid_or_password or ""}
            if self.protocol == OutboundProtocol.vless:
                user["encryption"] = self.encryption or "none"
                if self.flow:
                    user["flow"] = self.flow
            else:
                user["security"] = "auto"
            settings = {"vnext": [{"address": self.address or "", "port": self.port or 443, "users": [user]}]}
        elif self.protocol == OutboundProtocol.trojan:
            settings = {"servers": [{"address": self.address or "", "port": self.port or 443, "password": self.uuid_or_password or ""}]}
        elif self.protocol == OutboundProtocol.shadowsocks:
            settings = {"servers": [{"address": self.address or "", "port": self.port or 443, "password": self.uuid_or_password or "", "method": self.ss_method or "chacha20-ietf-poly1305"}]}
        elif self.protocol in (OutboundProtocol.socks, OutboundProtocol.http):
            server = {"address": self.address or "", "port": self.port or 1080}
            if self.uuid_or_password:
                user, _, pw = self.uuid_or_password.partition(':')
                server["users"] = [{"user": user, "pass": pw}]
            settings = {"servers": [server]}
        elif self.protocol == OutboundProtocol.wireguard:
            # xray wireguard outbound: secretKey is the local private key,
            # "address" is this side's tunnel address (local_address, NOT
            # the endpoint host), and the peer carries the remote endpoint/
            # public key. An empty peers list here would produce a config
            # that can never connect.
            peer: dict = {
                "publicKey": self.peer_public_key or "",
                "endpoint": f"{self.address or ''}:{self.port or 51820}",
                "allowedIPs": ["0.0.0.0/0", "::/0"],
            }
            if self.preshared_key:
                peer["preSharedKey"] = self.preshared_key
            settings = {
                "secretKey": self.uuid_or_password or "",
                "address": [self.local_address] if self.local_address else ["10.0.0.2/32"],
                "peers": [peer],
            }
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
            # publicKey/shortId are not optional extras - REALITY cannot
            # complete a handshake without the server's actual values here.
            stream["realitySettings"] = {
                "serverName": self.sni or self.address or "",
                "publicKey": self.reality_public_key or "",
                "shortId": self.reality_short_id or "",
            }
            if self.fingerprint:
                stream["realitySettings"]["fingerprint"] = self.fingerprint

        sockopt = self._xray_sockopt()
        if sockopt:
            stream["sockopt"] = sockopt

        out = {"tag": self.tag, "protocol": self.protocol.value, "settings": settings}
        if stream:
            out["streamSettings"] = stream

        mux = self._xray_mux()
        if mux:
            out["mux"] = mux

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

        if self.protocol == OutboundProtocol.hysteria:
            # sing-box hysteria2 outbound. TLS is intrinsic to hysteria2
            # (it's QUIC/TLS), so it's always emitted; server_name falls back
            # to the address when no explicit SNI is set.
            out["type"] = "hysteria2"
            out["server"] = self.address or ""
            out["server_port"] = self.port or 443
            out["password"] = self.uuid_or_password or ""
            if self.hysteria_up_mbps:
                out["up_mbps"] = self.hysteria_up_mbps
            if self.hysteria_down_mbps:
                out["down_mbps"] = self.hysteria_down_mbps
            if self.hysteria_obfs_password:
                out["obfs"] = {"type": "salamander", "password": self.hysteria_obfs_password}
            tls: dict = {"enabled": True, "server_name": self.sni or self.address or ""}
            out["tls"] = tls
            dial = self._singbox_dial_fields()
            out.update(dial)
            if self.extra_json and self.extra_json.strip() not in ('', '{}'):
                try:
                    out = _deep_merge(out, json.loads(self.extra_json))
                except Exception:
                    pass
            return out

        if self.protocol == OutboundProtocol.freedom:
            out["type"] = "direct"
        elif self.protocol == OutboundProtocol.wireguard:
            out["type"] = "wireguard"
            out["server"] = self.address or ""
            out["server_port"] = self.port or 51820
            out["private_key"] = self.uuid_or_password or ""
            out["peer_public_key"] = self.peer_public_key or ""
            if self.preshared_key:
                out["pre_shared_key"] = self.preshared_key
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
                out["method"] = self.ss_method or "chacha20-ietf-poly1305"
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
                        # Same fix as to_xray_dict() - public_key/short_id
                        # are required for a real handshake, not optional.
                        tls["reality"] = {
                            "enabled": True,
                            "public_key": self.reality_public_key or "",
                            "short_id": self.reality_short_id or "",
                        }
                    out["tls"] = tls

            # sing-box's multiplex applies to http/socks/shadowsocks too,
            # not just vless/vmess/trojan - matches xray's broader mux scope
            # and the reference forms, which showed mux fields for all of
            # these protocol types.
            multiplex = self._singbox_multiplex()
            if multiplex:
                out["multiplex"] = multiplex

        dial = self._singbox_dial_fields()
        out.update(dial)

        if self.extra_json and self.extra_json.strip() not in ('', '{}'):
            try:
                extra = json.loads(self.extra_json)
                out = _deep_merge(out, extra)
            except Exception:
                pass
        return out

    def _singbox_dial_fields(self) -> dict:
        """sing-box's dial-behavior fields live directly on the outbound
        (not nested like xray's sockopt) - the subset that maps cleanly
        onto xray's sockopt fields above, for admins who switch core_type
        without re-entering these."""
        out: dict = {}
        if self.sockopt_interface:
            out["bind_interface"] = self.sockopt_interface
        if self.sockopt_mark is not None:
            out["routing_mark"] = self.sockopt_mark
        if self.sockopt_tcp_fast_open is not None:
            out["tcp_fast_open"] = self.sockopt_tcp_fast_open
        if self.sockopt_tcp_mptcp is not None:
            out["tcp_multi_path"] = self.sockopt_tcp_mptcp
        if self.sockopt_domain_strategy:
            out["domain_strategy"] = self.sockopt_domain_strategy
        return out

    def _singbox_multiplex(self) -> dict:
        if not self.mux_enabled:
            return {}
        mux: dict = {"enabled": True, "protocol": "h2mux"}
        if self.mux_concurrency is not None:
            mux["max_streams"] = self.mux_concurrency
        return mux


_LINK_NETWORK_MAP = {
    'ws': OutboundNetwork.ws, 'grpc': OutboundNetwork.grpc,
    'httpupgrade': OutboundNetwork.httpupgrade, 'xhttp': OutboundNetwork.xhttp,
    'tcp': OutboundNetwork.tcp, 'raw': OutboundNetwork.tcp,
}
_LINK_SECURITY_MAP = {
    'none': OutboundSecurity.none, '': OutboundSecurity.none, 'tls': OutboundSecurity.tls,
    'reality': OutboundSecurity.reality, 'xtls': OutboundSecurity.tls,
}


def _b64_maybe(s: str) -> str:
    """Decode a base64/base64url blob to text, or return it unchanged if it
    isn't base64 (share links mix plain and base64-encoded userinfo)."""
    import base64
    s = s.strip()
    try:
        padded = s + '=' * (-len(s) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode('utf-8')
        # Only treat as base64 if the result is printable text - a plain
        # "method:password" also happens to be valid base64 alphabet, but
        # decoding it yields garbage bytes, so fall back to the original.
        if decoded and all(c.isprintable() or c in '\t' for c in decoded):
            return decoded
    except Exception:
        pass
    return s


def _split_hostport(hostport: str, default_port: int) -> tuple:
    hostport = hostport.strip().strip('/')
    if hostport.startswith('['):  # bracketed IPv6
        host, _, rest = hostport[1:].partition(']')
        port = rest.lstrip(':')
        return host, int(port) if port.isdigit() else default_port
    host, _, port = hostport.rpartition(':')
    if not host:  # no colon -> whole thing is the host
        return hostport, default_port
    return host, int(port) if port.isdigit() else default_port


def parse_share_link(link: str) -> dict:
    """Dispatch a proxy share link to the right per-scheme parser and return
    the CustomOutbound field values it implies, so an admin can paste a link
    from another panel/provider instead of hand-copying every field.

    Supports vless/vmess/trojan/ss(shadowsocks)/socks/http/hysteria2. Raises
    ValueError with a human-readable reason on anything unparseable - the
    caller (OutboundAdmin.on_model_change) turns that into a form
    ValidationError. AmneziaWG has no share-link format; it's imported from a
    .conf, handled separately."""
    link = (link or '').strip()
    if not link:
        raise ValueError('empty link')
    scheme = link.split('://', 1)[0].lower() if '://' in link else ''
    if scheme == 'vless':
        return parse_vless_link(link)
    if scheme == 'vmess':
        return parse_vmess_link(link)
    if scheme == 'trojan':
        return parse_trojan_link(link)
    if scheme == 'ss':
        return parse_ss_link(link)
    if scheme in ('socks', 'socks5'):
        return parse_socks_http_link(link, OutboundProtocol.socks)
    if scheme == 'http':
        return parse_socks_http_link(link, OutboundProtocol.http)
    if scheme in ('hysteria2', 'hy2'):
        return parse_hysteria2_link(link)
    raise ValueError('Unsupported link type "%s://". Supported: vless, vmess, trojan, ss, socks, http, hysteria2.' % scheme)


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

    network_key = (q.get('type') or 'tcp').lower()
    security_key = (q.get('security') or 'none').lower()
    path = q.get('serviceName') if network_key == 'grpc' else q.get('path')

    return {
        'protocol': OutboundProtocol.vless,
        'address': parsed.hostname,
        'port': parsed.port or 443,
        'uuid_or_password': parsed.username,
        'network': _LINK_NETWORK_MAP.get(network_key, OutboundNetwork.tcp),
        'security': _LINK_SECURITY_MAP.get(security_key, OutboundSecurity.none),
        'sni': q.get('sni', ''),
        'ws_path': path or '',
        'host_header': q.get('host', ''),
        'fingerprint': q.get('fp', ''),
        'flow': q.get('flow', ''),
        'encryption': q.get('encryption', 'none'),
        'reality_public_key': q.get('pbk', ''),
        'reality_short_id': q.get('sid', ''),
        'comment': unquote(parsed.fragment) if parsed.fragment else '',
    }


def parse_vmess_link(link: str) -> dict:
    """vmess:// links are base64-encoded JSON (the v2rayN format)."""
    import base64
    import json
    b64 = link[len('vmess://'):].strip()
    b64 += '=' * (-len(b64) % 4)
    try:
        data = json.loads(base64.b64decode(b64).decode('utf-8', 'ignore'))
    except Exception:
        raise ValueError('vmess link is not valid base64-encoded JSON')
    if not data.get('add'):
        raise ValueError('vmess link is missing the server address ("add")')

    net = str(data.get('net', 'tcp')).lower()
    tls = str(data.get('tls', '')).lower()
    try:
        port = int(data.get('port') or 443)
    except (TypeError, ValueError):
        port = 443
    return {
        'protocol': OutboundProtocol.vmess,
        'address': data.get('add', ''),
        'port': port,
        'uuid_or_password': data.get('id', ''),
        'network': _LINK_NETWORK_MAP.get(net, OutboundNetwork.tcp),
        'security': _LINK_SECURITY_MAP.get(tls, OutboundSecurity.none),
        'sni': data.get('sni') or data.get('host', ''),
        'ws_path': data.get('path', ''),
        'host_header': data.get('host', ''),
        'fingerprint': data.get('fp', ''),
        'comment': data.get('ps', ''),
    }


def parse_trojan_link(link: str) -> dict:
    """trojan://password@host:port?type=..&security=..&sni=..#name"""
    from urllib.parse import urlparse, parse_qs, unquote
    parsed = urlparse(link)
    if not parsed.hostname:
        raise ValueError('trojan link is missing the server address')
    if not parsed.username:
        raise ValueError('trojan link is missing the password (trojan://password@host:port)')
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    network_key = (q.get('type') or 'tcp').lower()
    # trojan is TLS by default (that's its whole point); only "none" turns it off.
    security_key = (q.get('security') or 'tls').lower()
    path = q.get('serviceName') if network_key == 'grpc' else q.get('path')
    return {
        'protocol': OutboundProtocol.trojan,
        'address': parsed.hostname,
        'port': parsed.port or 443,
        'uuid_or_password': unquote(parsed.username),
        'network': _LINK_NETWORK_MAP.get(network_key, OutboundNetwork.tcp),
        'security': _LINK_SECURITY_MAP.get(security_key, OutboundSecurity.tls),
        'sni': q.get('sni', ''),
        'ws_path': path or '',
        'host_header': q.get('host', ''),
        'fingerprint': q.get('fp', ''),
        'comment': unquote(parsed.fragment) if parsed.fragment else '',
    }


def parse_ss_link(link: str) -> dict:
    """shadowsocks ss:// - both the SIP002 (userinfo base64, host in clear)
    and the legacy fully-base64 forms."""
    from urllib.parse import unquote
    body = link[len('ss://'):]
    name = ''
    if '#' in body:
        body, frag = body.split('#', 1)
        name = unquote(frag)
    if '?' in body:  # drop plugin/query part - not modelled here
        body = body.split('?', 1)[0]
    body = body.strip()

    if '@' in body:
        userinfo, hostport = body.rsplit('@', 1)
        creds = _b64_maybe(userinfo)
        host, port = _split_hostport(hostport, 443)
    else:
        dec = _b64_maybe(body)
        creds, _, hostport = dec.rpartition('@')
        if not hostport:
            raise ValueError('ss link is not in a recognized shadowsocks format')
        host, port = _split_hostport(hostport, 443)
    method, _, password = creds.partition(':')
    if not host or not method:
        raise ValueError('ss link is missing method/host')
    return {
        'protocol': OutboundProtocol.shadowsocks,
        'address': host,
        'port': port,
        'uuid_or_password': password,
        'ss_method': method,
        'network': OutboundNetwork.tcp,
        'security': OutboundSecurity.none,
        'comment': name,
    }


def parse_socks_http_link(link: str, proto: 'OutboundProtocol') -> dict:
    """socks:// / socks5:// / http:// upstream proxy links. Userinfo may be
    plain user:pass or a base64 blob of the same."""
    from urllib.parse import urlparse, unquote
    parsed = urlparse(link)
    host = parsed.hostname
    if not host:
        raise ValueError('proxy link is missing the server address')
    default_port = 1080 if proto == OutboundProtocol.socks else 8080
    port = parsed.port or default_port
    user = unquote(parsed.username) if parsed.username else ''
    pw = unquote(parsed.password) if parsed.password else ''
    if user and not pw:  # some links base64 the whole "user:pass" as the username
        decoded = _b64_maybe(user)
        if ':' in decoded:
            user, _, pw = decoded.partition(':')
    uop = f'{user}:{pw}' if (user or pw) else ''
    return {
        'protocol': proto,
        'address': host,
        'port': port,
        'uuid_or_password': uop,
        'network': OutboundNetwork.tcp,
        'security': OutboundSecurity.none,
        'comment': unquote(parsed.fragment) if parsed.fragment else '',
    }


def parse_hysteria2_link(link: str) -> dict:
    """hysteria2:// / hy2://auth@host:port?obfs=salamander&obfs-password=..&sni=..#name"""
    from urllib.parse import urlparse, parse_qs, unquote
    parsed = urlparse(link)
    if not parsed.hostname:
        raise ValueError('hysteria2 link is missing the server address')
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    obfs_pw = q.get('obfs-password', '') if (q.get('obfs', '').lower() == 'salamander') else ''
    return {
        'protocol': OutboundProtocol.hysteria,
        'address': parsed.hostname,
        'port': parsed.port or 443,
        'uuid_or_password': unquote(parsed.username) if parsed.username else '',
        'sni': q.get('sni', ''),
        'hysteria_obfs_password': obfs_pw,
        'network': OutboundNetwork.tcp,
        'security': OutboundSecurity.none,
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
    # Additional xray/singbox routing match conditions (from the reference
    # routing form): source IP/CIDR, source port, sniffed protocol, and
    # inbound auth user/email. All optional - blank = not part of the match.
    source_ips = Column(Text, nullable=True, default='')      # newline-separated, e.g. geoip:ir / 1.2.3.0/24
    source_port = Column(String(100), nullable=True, default='')  # e.g. "443" or "1000-2000"
    protocols = Column(String(100), nullable=True, default='')    # comma-separated sniffed protocols: http,tls,bittorrent,quic
    user_emails = Column(Text, nullable=True, default='')     # newline/comma-separated inbound user emails
    comment = Column(String(300), nullable=True, default='')

    def to_xray_dict(self) -> dict:
        rule: dict = {"type": "field", "outboundTag": self.outbound_tag}
        domains = [d.strip() for d in (self.domains or '').splitlines() if d.strip()]
        ips = [i.strip() for i in (self.ips or '').splitlines() if i.strip()]
        inbound_tags = [t.strip() for t in (self.inbound_tags or '').split(',') if t.strip()]
        source_ips = [s.strip() for s in (self.source_ips or '').splitlines() if s.strip()]
        protocols = [p.strip() for p in (self.protocols or '').split(',') if p.strip()]
        users = [u.strip() for u in (self.user_emails or '').replace(',', '\n').splitlines() if u.strip()]
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
        if source_ips:
            rule["source"] = source_ips
        if self.source_port:
            rule["sourcePort"] = self.source_port
        if protocols:
            rule["protocol"] = protocols
        if users:
            rule["user"] = users
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
        source_ips = [s.strip() for s in (self.source_ips or '').splitlines() if s.strip()]
        protocols = [p.strip() for p in (self.protocols or '').split(',') if p.strip()]
        users = [u.strip() for u in (self.user_emails or '').replace(',', '\n').splitlines() if u.strip()]
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
        if source_ips:
            rule["source_ip_cidr"] = source_ips
        if self.source_port:
            rule["source_port"] = self.source_port
        if protocols:
            rule["protocol"] = protocols
        if users:
            rule["auth_user"] = users
        return rule


def get_available_inbound_tags() -> list[tuple[str, str]]:
    """The real xray inbound tags that will actually exist in the generated
    config, so a routing rule can match "traffic that came in on this
    inbound" (inboundTag) instead of only domain/IP.

    Hiddify does NOT create one inbound per Proxy row (protocol/transport/
    cdn-mode/domain combination) - most protocol+transport combinations
    share a single inbound routed to by HAProxy/SNI regardless of which
    domain or CDN mode the client used (see xray/configs/05_inbounds_new.
    json.j2: tag "v10-{protocol}-{stream}"). So the underlying *value* here
    is still "this protocol over this transport", not a specific domain/
    mode/proxy - the closest real match to what actually exists on the
    wire. Reality is the one exception: each reality domain gets its own
    dedicated inbound (xray/configs/05_inbounds_02_reality_main.json.j2:
    tag "realityin_{stream}_{port}"), so those are listed per-domain.

    What DOES vary is the *label*: rather than one opaque "(any domain)"
    catch-all per protocol+transport, list every enabled Proxy row that
    actually rides that shared inbound individually by its own configured
    name - same granularity as the Proxies and Inbound Override pages, even
    though several of those rows (one per CDN mode) resolve to the exact
    same tag under the hood. Selecting more than one that shares a tag is
    harmless (on_model_change dedupes before storing).

    Returns a list of (tag, human-readable label) tuples for use as
    SelectField choices, mirroring the *_enable flags and loops the
    templates themselves use so this only ever lists tags that will really
    be generated.
    """
    from hiddifypanel.models.config import hconfig
    from hiddifypanel.models.config_enum import ConfigEnum
    from hiddifypanel.models.domain import Domain, DomainType
    from hiddifypanel.models.child import Child
    from hiddifypanel.models.proxy import Proxy

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
            rows = [r for r in Proxy.query.filter(
                Proxy.child_id == child_id, Proxy.enable == True, Proxy.proto == protocol).all()
                if str(r.transport).lower() == stream]
            if rows:
                for r in rows:
                    choices.append((tag, r.name))
            else:
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
