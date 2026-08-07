import os
from enum import Enum, auto
from typing import Union

from fast_enum import FastEnum
from strenum import StrEnum


class HEnum(StrEnum):
    @classmethod
    def from_str(cls, key: str) -> "HEnum":
        return cls[key]


class Lang(HEnum):
    en = auto()
    fa = auto()
    ru = auto()
    pt = auto()
    zh = auto()
    my = auto()


class PanelMode(HEnum):
    standalone = auto()
    parent = auto()
    child = auto()


class MieruMultiplexing(HEnum):
    MULTIPLEXING_DEFAULT = auto()
    MULTIPLEXING_LOW = auto()
    MULTIPLEXING_MIDDLE = auto()
    MULTIPLEXING_HIGH = auto()


class MieruHandshake(HEnum):
    HANDSHAKE_DEFAULT = auto()
    HANDSHAKE_NO_WAIT = auto()
    HANDSHAKE_STANDARD = auto()


class LogLevel(HEnum):
    TRACE = auto()
    DEBUG = auto()
    INFO = auto()
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


class ConfigCategory(StrEnum):
    admin = auto()
    branding = auto()
    general = auto()
    proxies = auto()
    domain_fronting = auto()
    telegram = auto()
    http = auto()
    tls = auto()
    mux = auto()
    tls_trick = auto()
    ssh = auto()
    ssfaketls = auto()
    mieru = auto()
    shadowtls = auto()
    restls = auto()
    tuic = auto()
    hysteria = auto()
    ssr = auto()
    kcp = auto()
    hidden = auto()
    advanced = auto()
    too_advanced = auto()
    warp = auto()
    reality = auto()
    wireguard = auto()
    shadowsocks = auto()
    additional_configs = auto()
    dnstt = auto()
    webhook = auto()
    amneziawg = auto()
    anytls = auto()
    l2tp = auto()


class ApplyMode(StrEnum):
    apply_config = auto()
    reinstall = auto()
    nothing = auto()


def _BoolConfigDscr(
    category: ConfigCategory,
    apply_mode: ApplyMode = ApplyMode.nothing,
    show_in_parent: bool = True,
    hide_in_virtual_child=False,
) -> "ConfigEnum":
    return category, apply_mode, bool, show_in_parent


def _StrConfigDscr(
    category: ConfigCategory,
    apply_mode: ApplyMode = ApplyMode.nothing,
    show_in_parent: bool = True,
    hide_in_virtual_child=False,
) -> "ConfigEnum":
    return category, apply_mode, str, show_in_parent


def _IntConfigDscr(
    category: ConfigCategory,
    apply_mode: ApplyMode = ApplyMode.nothing,
    show_in_parent: bool = True,
    hide_in_virtual_child=False,
) -> "ConfigEnum":
    return category, apply_mode, int, show_in_parent


def _TypedConfigDscr(
    ctype: type,
    category: ConfigCategory,
    apply_mode: ApplyMode = ApplyMode.nothing,
    show_in_parent: bool = True,
    hide_in_virtual_child=False,
) -> "ConfigEnum":
    return category, apply_mode, ctype, show_in_parent


class ConfigEnum(metaclass=FastEnum):
    # category: ConfigCategory
    __slots__ = ("name", "value", "category", "apply_mode", "type", "show_in_parent", "hide_in_virtual_child")

    def __init__(
        self,
        category: ConfigCategory,
        apply_mode: ApplyMode = ApplyMode.apply_config,
        ctype=type,
        show_in_parent: bool = True,
        hide_in_virtual_child=False,
        name=auto,
    ):
        self.value = name
        self.name = name
        self.category = category
        self.apply_mode = apply_mode
        self.type = ctype
        self.show_in_parent = show_in_parent
        self.hide_in_virtual_child = hide_in_virtual_child

    @classmethod
    def dbvalues(cls):
        return {c.name: c for c in ConfigEnum}

    create_easysetup_link = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.nothing, hide_in_virtual_child=True)
    wireguard_enable = _BoolConfigDscr(ConfigCategory.wireguard, ApplyMode.reinstall, hide_in_virtual_child=True)
    wireguard_port = _StrConfigDscr(ConfigCategory.wireguard, ApplyMode.apply_config, hide_in_virtual_child=True)
    wireguard_ipv6 = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    wireguard_ipv4 = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    wireguard_private_key = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    wireguard_public_key = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    wireguard_noise_trick = _StrConfigDscr(ConfigCategory.wireguard, ApplyMode.apply_config)

    # Client-facing AmneziaWG - a shared "hiddifyawg" interface (like
    # wireguard_* above's "hiddifywg"), replacing WireGuard as the protocol
    # users connect to directly. Distinct from the pre-existing
    # amneziawg_enable/amneziawg_config (marked removed below) which were an
    # earlier, abandoned single-tunnel design, and distinct from the
    # Outbounds page's per-row amneziawg tunnels (CustomOutbound.jc/jmin/jmax)
    # used for chaining - those keep their own per-row settings.
    amneziawg_client_enable = _BoolConfigDscr(ConfigCategory.amneziawg, ApplyMode.reinstall, hide_in_virtual_child=True)
    amneziawg_port = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_ipv6 = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_ipv4 = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_private_key = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_public_key = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_jc = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_jmin = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_jmax = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    # H1-H4: the magic header values AmneziaWG substitutes for WireGuard's
    # real message-type bytes (1/2/3/4) on the wire, part of the same
    # obfuscation scheme as Jc/Jmin/Jmax above - initially left out on the
    # assumption that omitting them everywhere would make both ends fall
    # back to the same default consistently, but a real client app is not
    # guaranteed to apply that default the same way the server's awg-quick
    # does. Setting them explicitly on both ends removes that ambiguity.
    amneziawg_h1 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_h2 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_h3 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_h4 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    # S1-S4/I1-I5: AmneziaWG 2.0 additions on top of the Jc/Jmin/Jmax/H1-H4
    # "classic" scheme above - S1-S4 pad the handshake messages themselves,
    # I1-I5 are custom signature/junk packets (hex+tag templates, e.g.
    # "<b 0xAABB><r 16>") sent to mimic a real protocol (DNS/QUIC/SIP)
    # instead of just junk bytes. Left with no default (unlike Jc/Jmin/Jmax
    # below, which do have one) - a canned default mimicry template shipped
    # identically on every install would itself become a distinguishing
    # fingerprint, defeating the point. See
    # https://docs.amnezia.org/documentation/amnezia-wg/ for the exact
    # tag syntax; admins opt in by filling these in themselves.
    amneziawg_s1 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_s2 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_s3 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_s4 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_i1 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_i2 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_i3 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_i4 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)
    amneziawg_i5 = _StrConfigDscr(ConfigCategory.amneziawg, ApplyMode.apply_config, hide_in_virtual_child=True)

    ssh_server_redis_url = _StrConfigDscr(ConfigCategory.hidden, hide_in_virtual_child=True)
    ssh_server_port = _StrConfigDscr(ConfigCategory.ssh, ApplyMode.apply_config, hide_in_virtual_child=True)
    ssh_server_enable = _BoolConfigDscr(ConfigCategory.ssh, ApplyMode.reinstall)
    first_setup = _BoolConfigDscr(ConfigCategory.hidden)
    core_type = _StrConfigDscr(ConfigCategory.advanced, ApplyMode.reinstall, hide_in_virtual_child=True)
    # Whether core_type is auto-managed (recomputed from actual xhttp usage
    # on every Apply Configs, see install.sh) vs explicitly pinned by the
    # admin. Seeded True only for genuinely fresh installs (init_db.py's
    # `if child is None` block) - existing installs keep their historical
    # explicit "xray" default untouched. Flips to False permanently the
    # instant an admin picks a value via Settings (SettingAdmin.py), so
    # auto-management can never silently override a deliberate choice.
    # No standalone UI of its own - hidden on purpose. It's driven
    # entirely through core_type's own dropdown (SettingAdmin.py), which
    # has an "Auto" choice alongside Xray/Sing-box instead of a second,
    # separate toggle next to it.
    core_type_auto = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.reinstall, hide_in_virtual_child=True)
    # WARP used to be its own Settings section (mode toggle + plus-code +
    # custom-sites list) driving a hardcoded "WARP" outbound bound to a
    # wgcf-managed wg-quick@warp interface, plus built-in geo-routing rules
    # that auto-routed streaming/blocked sites through it. Retired in favor
    # of a plain Outbound (Protocol "amneziawg" - a real WireGuard peer like
    # Cloudflare's WARP endpoint tolerates the Jc/Jmin/Jmax junk-packet
    # obfuscation fine, just not the H1-H4/S1-S4/I1-I5 params that change the
    # actual handshake bytes) on the Outbounds page, selectable from any
    # Routing Rule like any other outbound - same pattern as the
    # amneziawg_enable/amneziawg_config retirement above. Kept here (hidden)
    # instead of deleted outright so old DB rows from before this change
    # don't error.
    warp_enable = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.reinstall, hide_in_virtual_child=True)  # removed
    warp_mode = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)  # removed
    warp_plus_code = _StrConfigDscr(
        ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True
    )  # removed
    warp_sites = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)  # removed

    # AmneziaWG used to be a separate Settings section (toggle + one global
    # pasted .conf) - moved into the Outbounds form instead (Protocol
    # "amneziawg", one row per tunnel with its own PrivateKey/PublicKey/
    # Jc/Jmin/Jmax fields, see CustomOutbound.render_amneziawg_conf()), so
    # any number of AmneziaWG outbounds can exist and each gets torn down
    # when its row is disabled/deleted. Kept here (hidden) instead of
    # deleted outright so old DB rows from before this change don't error.
    amneziawg_enable = _BoolConfigDscr(
        ConfigCategory.hidden, ApplyMode.reinstall, hide_in_virtual_child=True
    )  # removed
    amneziawg_config = _StrConfigDscr(
        ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True
    )  # removed
    dns_server = _StrConfigDscr(ConfigCategory.general, ApplyMode.apply_config, hide_in_virtual_child=True)
    reality_fallback_domain = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)  # removed
    reality_server_names = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)  # removed
    # Reality Settings section removed - special_port/reality_private_key/
    # reality_public_key/reality_short_ids are now a per-domain
    # Domain.reality_port/reality_private_key/reality_public_key/
    # reality_short_id override (see DomainAdmin.py), auto-generated the
    # first time a domain is saved as a REALITY mode. Retired to
    # ConfigCategory.hidden rather than deleted - Domain.effective_reality_*
    # and internal_port_special still fall back to these exact keys for any
    # existing domain that hasn't been given its own value yet.
    reality_short_ids = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    reality_private_key = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    reality_public_key = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    # ML-DSA-65 post-quantum REALITY signature (XTLS/Xray-core only - sing-box's
    # REALITY has no equivalent, confirmed against sing-box.sagernet.org/
    # configuration/shared/tls/). Global-only, no per-domain override (unlike
    # reality_private_key/public_key above) - deliberately scoped smaller: adding
    # this would mean new Domain columns + DomainAdmin.py form fields, more UI
    # surface than this optional hardening field is worth. Generated (if at
    # all) via init_db.py's migration shelling out to the real `xray mldsa65`
    # CLI command rather than reimplementing FIPS 204 key derivation in Python -
    # a bit-mismatch between a from-scratch Python implementation and Xray-
    # core's own Go/CIRCL one would silently break every REALITY handshake
    # using it, so correctness-by-construction (using Xray's own binary) beats
    # reimplementing and hoping.
    reality_mldsa65_seed = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    reality_mldsa65_verify = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    reality_port = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    special_port = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)

    restls1_2_domain = _StrConfigDscr(ConfigCategory.hidden)
    restls1_3_domain = _StrConfigDscr(ConfigCategory.hidden)
    show_usage_in_sublink = _BoolConfigDscr(ConfigCategory.general)
    cloudflare = _StrConfigDscr(ConfigCategory.too_advanced)
    license = _StrConfigDscr(ConfigCategory.hidden)
    country = _StrConfigDscr(ConfigCategory.general, ApplyMode.reinstall, hide_in_virtual_child=True)
    # Package Update Mode section removed from Settings - retired to
    # ConfigCategory.hidden (same pattern as tls_ports/http_proxy_enable
    # above) rather than deleted, since hiddify.py's reinstall_action still
    # reads this key to decide whether a package_mode change needs a
    # do_update reinstall.
    package_mode = _StrConfigDscr(ConfigCategory.hidden, hide_in_virtual_child=True)
    utls = _StrConfigDscr(ConfigCategory.advanced)
    # Opt-in periodic uTLS rotation (see hutils/tls_fingerprint_rotation.py):
    # cycles `utls` itself among the real-browser fingerprint choices every
    # utls_rotate_days (+/- jitter) instead of leaving it pinned to one
    # value forever. Deliberately distinct from utls's own "random"/
    # "randomized" choices, which pick per-connection rather than rotating
    # a stable value over days. Flips back to False the instant an admin
    # manually edits `utls` directly (see SettingAdmin.py's save loop) -
    # same "explicit choice wins" rule as core_type/core_type_auto.
    utls_auto_rotate = _BoolConfigDscr(ConfigCategory.advanced)
    utls_rotate_days = _IntConfigDscr(ConfigCategory.advanced)
    # Bookkeeping only (never rendered - ConfigCategory.hidden is skipped
    # entirely by SettingAdmin's form loop): ISO timestamp of the last
    # auto-rotation, so the periodic task knows whether one is due yet.
    utls_last_rotated_at = _StrConfigDscr(ConfigCategory.hidden)
    telegram_bot_token = _StrConfigDscr(ConfigCategory.telegram, hide_in_virtual_child=True)

    # Generic outgoing webhook - POSTs a JSON payload to your own endpoint on
    # user lifecycle events (activated/deactivated i.e. traffic exceeded or
    # renewed/expiry). Independent from the telegram bot notification.
    webhook_enable = _BoolConfigDscr(ConfigCategory.webhook, hide_in_virtual_child=True)
    webhook_url = _StrConfigDscr(ConfigCategory.webhook, hide_in_virtual_child=True)
    webhook_signing_key = _StrConfigDscr(ConfigCategory.webhook, hide_in_virtual_child=True)

    additional_configs_urls = _StrConfigDscr(ConfigCategory.additional_configs)
    # additional_configs_singbox/xrayjson are no longer admin-editable text
    # fields (the UI-managed Outbounds/Routing Rules pages replace that) -
    # ConfigCategory.hidden so they drop out of the Settings form entirely,
    # but the keys themselves stay: hiddify.py's all_configs_for_cli() still
    # writes the *merged* CustomOutbound/CustomRoutingRule JSON into them,
    # since that's the actual value xray/configs/06_outbounds.json.j2 and
    # singbox's equivalent read - this is now a purely internal/computed
    # value, not something an admin ever sets directly.
    additional_configs_singbox = _StrConfigDscr(ConfigCategory.hidden)
    additional_configs_xrayjson = _StrConfigDscr(ConfigCategory.hidden)

    # region child-parent
    # deprecated
    is_parent = _BoolConfigDscr(ConfigCategory.hidden)
    # parent panel domain
    parent_panel = _StrConfigDscr(ConfigCategory.hidden)  # should be able to change by user
    parent_domain = _StrConfigDscr(ConfigCategory.hidden)
    parent_admin_proxy_path = _StrConfigDscr(ConfigCategory.hidden)

    # the panel mode could be one of these: "parent", "child", "standalone"
    # this config value would be 'standalone' by default. and would be set by panel itself
    panel_mode = _TypedConfigDscr(PanelMode, ConfigCategory.hidden, hide_in_virtual_child=True)
    # endregion

    # Visible (not hidden): _v83() force-sets this to CRITICAL for every
    # install (quieter logs/less disk by default), which also makes
    # xray/configs/00_log.json.j2 turn output/error/access/dnsLog fully
    # off - there was previously no way to turn logging back on short of
    # a direct DB edit, which meant every "check the Xray logs" diagnosis
    # request had nothing to work with by default.
    log_level = _TypedConfigDscr(LogLevel, ConfigCategory.advanced, ApplyMode.reinstall, hide_in_virtual_child=True)

    unique_id = _StrConfigDscr(ConfigCategory.hidden)
    last_hash = _StrConfigDscr(ConfigCategory.hidden)
    # Comma-separated install.sh subsystem names (hutils.apply_scope.Subsystem)
    # accumulated since the last "Apply Configs" - lets that action touch only
    # the subsystems actually affected instead of always doing a full-width
    # apply. Empty/unset means "unknown scope, do everything" (the safe
    # default and today's unconditional behavior), never "narrow to nothing".
    pending_apply_subsystems = _StrConfigDscr(ConfigCategory.hidden, hide_in_virtual_child=True)
    cdn_forced_host = _StrConfigDscr(ConfigCategory.hidden)  # removed
    lang = _TypedConfigDscr(Lang, ConfigCategory.branding)
    admin_lang = _TypedConfigDscr(Lang, ConfigCategory.admin)
    admin_secret = _StrConfigDscr(ConfigCategory.hidden)  # removed

    default_useragent_string = _StrConfigDscr(ConfigCategory.general)
    use_ip_in_config = _BoolConfigDscr(ConfigCategory.hidden)
    # tls
    # retired - HTTP/TLS ports are now a per-domain Domain.http_port/tls_port
    # override (see DomainAdmin.py) instead of one global list shared by
    # every domain. Kept under ConfigCategory.hidden (not deleted) only so
    # old DB rows/migrations referencing this key don't error, same pattern
    # as the retired kcp_ports/wireguard_* fields.
    tls_ports = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)

    tls_fragment_enable = _BoolConfigDscr(ConfigCategory.tls_trick)
    tls_fragment_size = _StrConfigDscr(ConfigCategory.tls_trick)
    tls_fragment_sleep = _StrConfigDscr(ConfigCategory.tls_trick)
    tls_fragment_packets = _StrConfigDscr(ConfigCategory.tls_trick)
    tls_mixed_case = _BoolConfigDscr(ConfigCategory.tls_trick)
    tls_padding_enable = _BoolConfigDscr(ConfigCategory.tls_trick, ApplyMode.apply_config)
    tls_padding_length = _StrConfigDscr(ConfigCategory.tls_trick, ApplyMode.apply_config)
    # Removed from the TLS Settings section - retired to ConfigCategory.hidden
    # (same pattern as tls_ports above) rather than deleted, since old DB
    # rows/migrations still reference the key.
    tls_ech_enable = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)

    # mux
    mux_enable = _BoolConfigDscr(ConfigCategory.mux, ApplyMode.apply_config)
    mux_protocol = _StrConfigDscr(ConfigCategory.mux, ApplyMode.apply_config)
    mux_max_connections = _IntConfigDscr(ConfigCategory.mux, ApplyMode.apply_config)
    mux_min_streams = _IntConfigDscr(ConfigCategory.mux, ApplyMode.apply_config)
    mux_max_streams = _IntConfigDscr(ConfigCategory.mux, ApplyMode.apply_config)
    mux_padding_enable = _BoolConfigDscr(ConfigCategory.mux, ApplyMode.apply_config)
    mux_brutal_enable = _BoolConfigDscr(ConfigCategory.mux, ApplyMode.apply_config)
    mux_brutal_up_mbps = _IntConfigDscr(ConfigCategory.mux, ApplyMode.apply_config)
    mux_brutal_down_mbps = _IntConfigDscr(ConfigCategory.mux, ApplyMode.apply_config)

    # retired - see tls_ports above; replaced by the per-domain Domain.http_port.
    http_ports = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)
    mieru_tcp_ports = _StrConfigDscr(ConfigCategory.mieru, ApplyMode.apply_config, hide_in_virtual_child=True)
    mieru_udp_ports = _StrConfigDscr(ConfigCategory.mieru, ApplyMode.apply_config, hide_in_virtual_child=True)
    # retired (_v137 forces kcp_enable off for every install) - KCP's whole
    # value proposition (surviving high packet loss) has been superseded by
    # Hysteria2/QUIC-family transports; kept only so old DB rows/migrations
    # referencing these keys don't error, same pattern as the retired
    # wireguard_* fields.
    kcp_ports = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)
    kcp_enable = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)
    decoy_domain = _StrConfigDscr(ConfigCategory.general, ApplyMode.apply_config, hide_in_virtual_child=True)

    dnstt_enable = _BoolConfigDscr(ConfigCategory.dnstt, ApplyMode.apply_config, hide_in_virtual_child=True)
    dnstt_resolvers = _StrConfigDscr(ConfigCategory.dnstt, ApplyMode.apply_config, hide_in_virtual_child=True)
    dnstt_private_key = _StrConfigDscr(ConfigCategory.dnstt, ApplyMode.apply_config, hide_in_virtual_child=True)
    dnstt_public_key = _StrConfigDscr(ConfigCategory.dnstt, ApplyMode.apply_config, hide_in_virtual_child=True)

    # will be deprecated
    proxy_path = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    proxy_path_admin = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)
    proxy_path_client = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)
    firewall = _BoolConfigDscr(ConfigCategory.general, ApplyMode.apply_config, hide_in_virtual_child=True)
    netdata = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.reinstall)  # removed
    # HTTP Configuration section removed from Settings - http_ports (above)
    # was the only other member of this category, so this was the last field
    # keeping the section around. Retired to ConfigCategory.hidden rather
    # than deleted, since old DB rows/migrations still reference the key,
    # and hutils/proxy/shared.py still reads it to decide whether to offer
    # plain-HTTP proxy links at all.
    http_proxy_enable = _BoolConfigDscr(ConfigCategory.hidden)
    block_iran_sites = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config, hide_in_virtual_child=True)
    allow_invalid_sni = _BoolConfigDscr(ConfigCategory.tls, ApplyMode.apply_config, hide_in_virtual_child=True)
    auto_update = _BoolConfigDscr(
        (
            ConfigCategory.hidden
            if os.environ.get("HIDDIFY_DISABLE_UPDATE", "").lower() in {"1", "true"}
            else ConfigCategory.general
        ),
        ApplyMode.apply_config,
        True,
        hide_in_virtual_child=True,
    )
    only_ipv4 = _BoolConfigDscr(ConfigCategory.general, ApplyMode.apply_config, hide_in_virtual_child=True)

    shared_secret = _StrConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config, hide_in_virtual_child=True)

    telegram_enable = _BoolConfigDscr(ConfigCategory.telegram, ApplyMode.reinstall)
    # telegram_secret=auto()
    telegram_adtag = _StrConfigDscr(ConfigCategory.telegram, ApplyMode.reinstall, hide_in_virtual_child=True)
    telegram_lib = _StrConfigDscr(ConfigCategory.telegram, ApplyMode.reinstall, hide_in_virtual_child=True)
    telegram_fakedomain = _StrConfigDscr(ConfigCategory.telegram, ApplyMode.reinstall, hide_in_virtual_child=True)

    v2ray_enable = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.reinstall)
    torrent_block = _BoolConfigDscr(ConfigCategory.general, ApplyMode.apply_config)

    tuic_enable = _BoolConfigDscr(ConfigCategory.tuic, ApplyMode.apply_config)
    tuic_port = _StrConfigDscr(ConfigCategory.tuic, ApplyMode.apply_config, hide_in_virtual_child=True)

    # TUIC inbound congestion control (server-global).
    # Choices: `cubic` / `bbr` / `new_reno`.
    # Distinct from CustomOutbound.tuic_congestion_control (per-outbound dialer).
    tuic_congestion_control = _StrConfigDscr(ConfigCategory.tuic, ApplyMode.apply_config)

    # AnyTLS inbound -- sing-box 1.12+, gated off by default.
    # Hiddify app does not yet support AnyTLS (issues #1810/#2077/#2222);
    # only NekoBox / v2rayN >=7.14.3 consume the singbox subscription.
    anytls_enable = _BoolConfigDscr(ConfigCategory.anytls, ApplyMode.apply_config)
    anytls_port = _StrConfigDscr(ConfigCategory.anytls, ApplyMode.apply_config, hide_in_virtual_child=True)

    # L2TP/IPsec inbound - a standalone strongSwan+xl2tpd subsystem (see
    # other/l2tp/), NOT an xray/singbox protocol. Legacy access method for
    # the built-in OS VPN clients; each user authenticates with their UUID
    # and the shared l2tp_psk. Default off. PPTP is deliberately not offered
    # (broken MS-CHAPv2 crypto). reinstall because enabling installs the
    # strongswan/xl2tpd packages.
    l2tp_enable = _BoolConfigDscr(ConfigCategory.l2tp, ApplyMode.reinstall)
    # The IPsec pre-shared key. hide_in_virtual_child: L2TP terminates on the
    # host that runs the daemon, not a virtual child.
    l2tp_psk = _StrConfigDscr(ConfigCategory.l2tp, ApplyMode.apply_config, hide_in_virtual_child=True)
    # Tag of a CustomOutbound (Protocol=l2tp or amneziawg) to route
    # L2TP-inbound clients' traffic through, instead of straight out the
    # server's public NIC. Empty = today's direct behavior. See
    # models/routing.py's get_l2tp_route_interface() and
    # other/l2tp/run.sh.j2 - both l2tp and amneziawg outbounds are real
    # kernel network interfaces (unlike xray-protocol outbounds, which only
    # exist inside xray's own process), so this is plain source-based
    # policy routing, not a transparent-proxy redirect.
    l2tp_outbound_tag = _StrConfigDscr(ConfigCategory.l2tp, ApplyMode.apply_config, hide_in_virtual_child=True)

    # the hysteria is refereing to hysteria2

    # Kernel TLS offload (kTLS) for sing-box TLS-terminating inbounds.
    # Requires Linux 5.1+ with CONFIG_TLS and TLS 1.3. Default off.
    # Enabling on a kernel without kTLS will silently break all TLS inbounds.
    tls_kernel_offload = _BoolConfigDscr(ConfigCategory.tls, ApplyMode.apply_config)
    hysteria_enable = _BoolConfigDscr(ConfigCategory.hysteria, ApplyMode.apply_config)
    hysteria_port = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    # if be enable hysteria2 will be use salamander as obfs
    hysteria_obfs_enable = _BoolConfigDscr(ConfigCategory.hysteria, ApplyMode.apply_config)
    hysteria_up_mbps = _StrConfigDscr(ConfigCategory.hysteria, ApplyMode.apply_config)
    hysteria_down_mbps = _StrConfigDscr(ConfigCategory.hysteria, ApplyMode.apply_config)
    # Orphaned: was the port for Xray-core's native "hysteria" protocol
    # ("Hysteria (Xray)"), removed entirely (see init_db.py's _v149) - no
    # obfuscation support in Xray's implementation meant its plain QUIC
    # handshake couldn't survive network paths that only pass obfuscated
    # traffic cleanly. Left defined (unused) since _v148's historical
    # migration still references this key and migrations aren't rewritten.
    xray_hysteria_port = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)

    shadowsocks2022_enable = _BoolConfigDscr(ConfigCategory.shadowsocks, ApplyMode.apply_config)
    shadowsocks2022_method = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)
    shadowsocks2022_port = _StrConfigDscr(ConfigCategory.shadowsocks, ApplyMode.apply_config)
    ssfaketls_enable = _BoolConfigDscr(ConfigCategory.shadowsocks, ApplyMode.reinstall)
    ssfaketls_fakedomain = _StrConfigDscr(
        ConfigCategory.shadowsocks, ApplyMode.apply_config, hide_in_virtual_child=True
    )
    shadowtls_enable = _BoolConfigDscr(ConfigCategory.shadowsocks, ApplyMode.apply_config)
    shadowtls_fakedomain = _StrConfigDscr(
        ConfigCategory.shadowsocks, ApplyMode.apply_config, hide_in_virtual_child=True
    )

    ssr_enable = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)
    # ssr_secret="ssr_secret"
    ssr_fakedomain = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)

    vmess_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    domain_fronting_domain = _StrConfigDscr(ConfigCategory.hidden)  # removed
    domain_fronting_http_enable = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)  # removed
    domain_fronting_tls_enable = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)  # removed

    ws_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    grpc_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    httpupgrade_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    xhttp_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    # Default public DNS resolvers for xdns-mode domains (Xray-core's xdns
    # finalmask, XTLS/Xray-core#5560/#5633 - see DomainType.xdns in
    # models/domain.py). Hidden like special_port/hysteria_port above:
    # there's no separate on/off switch here, a domain opts in by setting
    # its own 'mode' to xdns, and can override this default per-domain via
    # extra_params.xdns_resolvers.
    xdns_resolvers = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)
    # Admin on/off switches for the xdns/xicmp Proxy rows (get_proxies()),
    # same role dnstt_enable plays for the DNSTT proxy row above - separate
    # from a domain actually being in xdns/xicmp mode, which is what makes
    # the underlying inbound/config functionally exist at all.
    xdns_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    xicmp_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)

    naive_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    naive_port = _StrConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    mieru_enable = _BoolConfigDscr(ConfigCategory.mieru, ApplyMode.apply_config)
    mieru_multiplexing = _TypedConfigDscr(MieruMultiplexing, ConfigCategory.mieru)
    mieru_handshake = _TypedConfigDscr(MieruHandshake, ConfigCategory.mieru)
    vless_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    trojan_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    reality_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    tcp_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)
    quic_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)

    xtls_enable = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config)  # deprecated
    h2_enable = _BoolConfigDscr(ConfigCategory.proxies, ApplyMode.apply_config)  # deprecated

    db_version = _StrConfigDscr(ConfigCategory.hidden)
    last_priodic_usage_check = _IntConfigDscr(ConfigCategory.hidden)

    branding_title = _StrConfigDscr(ConfigCategory.branding)
    branding_site = _StrConfigDscr(ConfigCategory.branding)
    branding_freetext = _StrConfigDscr(ConfigCategory.branding)
    not_found = _StrConfigDscr(ConfigCategory.hidden)
    path_vmess = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)
    path_vless = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)
    path_trojan = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)
    path_naive = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)
    path_v2ray = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)  # deprecated
    path_ss = _StrConfigDscr(ConfigCategory.hidden, ApplyMode.apply_config, hide_in_virtual_child=True)

    path_xhttp = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)
    path_httpupgrade = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)
    path_ws = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)
    path_tcp = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)
    path_grpc = _StrConfigDscr(ConfigCategory.too_advanced, ApplyMode.apply_config, hide_in_virtual_child=True)

    # subs
    sub_full_singbox_enable = _BoolConfigDscr(ConfigCategory.hidden)
    sub_singbox_ssh_enable = _BoolConfigDscr(ConfigCategory.hidden)
    sub_full_xray_json_enable = _BoolConfigDscr(ConfigCategory.proxies)
    sub_full_links_enable = _BoolConfigDscr(ConfigCategory.hidden)
    sub_full_links_b64_enable = _BoolConfigDscr(ConfigCategory.hidden)
    sub_full_clash_enable = _BoolConfigDscr(ConfigCategory.hidden)
    sub_full_clash_meta_enable = _BoolConfigDscr(ConfigCategory.hidden)

    # ssh host keys
    ssh_host_rsa_pk = _StrConfigDscr(ConfigCategory.hidden)
    ssh_host_rsa_pub = _StrConfigDscr(ConfigCategory.hidden)
    ssh_host_ed25519_pk = _StrConfigDscr(ConfigCategory.hidden)
    ssh_host_ed25519_pub = _StrConfigDscr(ConfigCategory.hidden)
    ssh_host_ecdsa_pk = _StrConfigDscr(ConfigCategory.hidden)
    ssh_host_ecdsa_pub = _StrConfigDscr(ConfigCategory.hidden)
    ssh_host_dsa_pk = _StrConfigDscr(ConfigCategory.hidden)
    ssh_host_dsa_pub = _StrConfigDscr(ConfigCategory.hidden)

    hiddifycli_enable = _BoolConfigDscr(ConfigCategory.hidden, ApplyMode.reinstall)

    @classmethod
    def __missing__(cls, value):
        return ConfigEnum.not_found

    def __contains__(self, other):
        return other in self.name

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return f"{self}" == f"{other}"

    def __neg__(self, other):
        return not self.__eq__(other)

    def endswith(self, other):
        return self.name.endswith(other)  # type: ignore

    def startswith(self, other):
        return self.name.startswith(other)  # type: ignore
