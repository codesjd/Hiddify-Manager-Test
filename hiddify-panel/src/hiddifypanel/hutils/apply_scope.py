"""Maps config/DB changes to the specific install.sh subsystems they
actually affect, so "Apply Configs" can touch only what's needed instead of
unconditionally re-running every subsystem's run.sh (cert issuance included)
on every click.

Safety principle: an unmapped/uncertain change must never narrow the apply
scope - `subsystems_for_key()` returns None for anything not confidently
known, and every helper here treats None as "do a full, untargeted apply",
exactly like every existing caller behaved before this module existed. It's
fine to occasionally do more work than strictly necessary; it is not fine to
silently skip a subsystem that actually needed touching.
"""
from strenum import StrEnum

from hiddifypanel.models import ConfigEnum, ConfigCategory, hconfig, set_hconfig


class Subsystem(StrEnum):
    """Canonical subsystem tokens - each one is exactly the first argument
    install.sh's install_run() is called with for that subsystem, so the
    shell side needs zero translation."""
    xray = 'xray'
    singbox = 'singbox'
    haproxy = 'haproxy'
    acme = 'acme.sh'
    nginx = 'nginx'
    wireguard = 'other/wireguard'
    amneziawg = 'other/amneziawg'
    ssh = 'other/ssh'
    warp = 'other/warp'
    dnstt = 'other/dnstt'
    telegram = 'other/telegram'
    ssfaketls = 'other/ssfaketls'
    hiddifycli = 'other/hiddify-cli'
    l2tp = 'other/l2tp'


# Domain records aren't ConfigEnum-backed (see DomainAdmin), but this is the
# fixed subsystem set any domain create/update/delete affects: haproxy's
# per-domain fronts/backends, acme's cert issuance, nginx's acme-challenge
# config, and both cores' inbound templates (which bake domain values in).
DOMAIN_CHANGE_SUBSYSTEMS = frozenset({
    Subsystem.haproxy, Subsystem.acme, Subsystem.nginx, Subsystem.xray, Subsystem.singbox,
})

# RoutingRule/Outbound/InboundOverride/per-Proxy-row changes: all four are
# proxy-core concepts (routing rules, outbounds, inbound overrides, and
# individual proxy enable/disable all live inside xray/singbox's own
# generated configs), never haproxy/nginx/acme.
CORE_ONLY_SUBSYSTEMS = frozenset({Subsystem.xray, Subsystem.singbox})

# Outbounds can additionally be AmneziaWG tunnels (CustomOutbound rows with
# their own run.sh-managed .conf files under other/amneziawg), so that
# admin view needs one more subsystem than routing rules/inbound overrides.
OUTBOUND_CHANGE_SUBSYSTEMS = frozenset({Subsystem.xray, Subsystem.singbox, Subsystem.amneziawg})

# Every protocol/transport-tuning ConfigCategory lives inside xray/singbox's
# own templates - both get touched (whichever core is actually active does
# the real work; the other one's install_run just re-confirms it's stopped,
# which is cheap).
_PROTOCOL_CATEGORIES = frozenset({
    ConfigCategory.proxies, ConfigCategory.tls, ConfigCategory.tls_trick,
    ConfigCategory.mux, ConfigCategory.http, ConfigCategory.mieru,
    ConfigCategory.shadowtls, ConfigCategory.restls, ConfigCategory.tuic,
    ConfigCategory.hysteria, ConfigCategory.ssr, ConfigCategory.kcp,
    ConfigCategory.reality, ConfigCategory.shadowsocks, ConfigCategory.domain_fronting,
})

CATEGORY_SUBSYSTEMS: dict[ConfigCategory, frozenset[str]] = {
    ConfigCategory.wireguard: frozenset({Subsystem.wireguard}),
    ConfigCategory.amneziawg: frozenset({Subsystem.amneziawg}),
    ConfigCategory.ssh: frozenset({Subsystem.ssh}),
    ConfigCategory.telegram: frozenset({Subsystem.telegram}),
    ConfigCategory.dnstt: frozenset({Subsystem.dnstt}),
    ConfigCategory.warp: frozenset({Subsystem.warp}),
    # L2TP/IPsec is its own strongSwan+xl2tpd subsystem (other/l2tp), not an
    # xray/singbox protocol, so both l2tp_enable and l2tp_psk only need that
    # one subsystem re-run on Apply Configs.
    ConfigCategory.l2tp: frozenset({Subsystem.l2tp}),
    **{cat: frozenset({Subsystem.xray, Subsystem.singbox}) for cat in _PROTOCOL_CATEGORIES},
    # ConfigCategory.proxies holds the {vless,vmess,trojan}_enable and
    # {ws,grpc,tcp,httpupgrade,xhttp}_enable toggles. haproxy/maps/path_v10.j2
    # and haproxy/fronts/in_tcpmode.cfg.pj2 branch on these exact same flags
    # to decide which v10-{protocol}-{stream} backends and path-map entries
    # even exist, so scoping a protocol/transport toggle to xray/singbox only
    # left haproxy routing against a stale backend/map set - a just-enabled
    # transport had no map entry yet (falls through to nginx's own,
    # separately-stale dispatch -> 502), and a just-disabled one kept being
    # served. Overrides the broader _PROTOCOL_CATEGORIES entry above.
    ConfigCategory.proxies: frozenset({Subsystem.xray, Subsystem.singbox, Subsystem.haproxy}),
}

# Per-key overrides for keys whose ConfigCategory doesn't match their real
# install.sh footprint (e.g. ssfaketls_enable is filed under
# ConfigCategory.shadowsocks but is really its own other/ssfaketls
# subsystem), or that span more than their category alone would suggest.
#
# ssfaketls/telegram/shadowtls all also have their own SNI-based routing
# rule in haproxy/fronts/sni_proxy.cfg.pj2 (use_backend ssfake/telegram/
# shadowtls if req.ssl_sni matches these exact *_fakedomain values, gated
# on the matching *_enable flag too) - haproxy has to be included or it
# keeps routing on the stale fakedomain/gate indefinitely, even though the
# backend service itself picks up the change correctly. This was the
# actual cause of "changed the Telegram fake domain and it stopped
# working" - the mtproxy service had the new domain, haproxy was still
# looking for the old one.
KEY_SUBSYSTEM_OVERRIDES: dict[ConfigEnum, frozenset[str]] = {
    ConfigEnum.ssfaketls_enable: frozenset({Subsystem.ssfaketls, Subsystem.haproxy}),
    ConfigEnum.ssfaketls_fakedomain: frozenset({Subsystem.ssfaketls, Subsystem.haproxy}),
    ConfigEnum.telegram_enable: frozenset({Subsystem.telegram, Subsystem.haproxy}),
    ConfigEnum.telegram_fakedomain: frozenset({Subsystem.telegram, Subsystem.haproxy}),
    ConfigEnum.shadowtls_enable: frozenset({Subsystem.xray, Subsystem.singbox, Subsystem.haproxy}),
    ConfigEnum.shadowtls_fakedomain: frozenset({Subsystem.xray, Subsystem.singbox, Subsystem.haproxy}),
    # core_type toggles which of xray/singbox actually runs, and other/ssh's
    # own .env.j2 reads core_type too (its SOCKS_PROXY port differs by core).
    ConfigEnum.core_type: frozenset({Subsystem.xray, Subsystem.singbox, Subsystem.ssh}),
    ConfigEnum.hiddifycli_enable: frozenset({Subsystem.hiddifycli}),
    # Filed under ConfigCategory.hidden rather than .wireguard, but these are
    # unambiguously wireguard-only settings (interface IPs and keys).
    ConfigEnum.wireguard_ipv6: frozenset({Subsystem.wireguard}),
    ConfigEnum.wireguard_ipv4: frozenset({Subsystem.wireguard}),
    ConfigEnum.wireguard_private_key: frozenset({Subsystem.wireguard}),
    ConfigEnum.wireguard_public_key: frozenset({Subsystem.wireguard}),
    # Same reasoning as the wireguard_* overrides above, for AmneziaWG's own
    # client-facing interface settings.
    ConfigEnum.amneziawg_ipv6: frozenset({Subsystem.amneziawg}),
    ConfigEnum.amneziawg_ipv4: frozenset({Subsystem.amneziawg}),
    ConfigEnum.amneziawg_private_key: frozenset({Subsystem.amneziawg}),
    ConfigEnum.amneziawg_public_key: frozenset({Subsystem.amneziawg}),
    # tls_ports/http_ports are filed under ConfigCategory.tls/.http (both
    # scoped to {xray, singbox} only via _PROTOCOL_CATEGORIES), but
    # haproxy/fronts/sni_proxy.cfg.pj2 and in_tcpmode.cfg.pj2 read these
    # exact values for their own `bind :{{port}}` lines - 443/80 are always
    # prepended so the panel itself never goes offline, but any *additional*
    # port an admin adds/removes here only actually starts/stops being
    # listened on once haproxy itself is scoped in. The other keys in those
    # two categories (tls_ech_enable, allow_invalid_sni, http_proxy_enable,
    # tls_kernel_offload) are pure client-link-generation or xray/singbox
    # template flags with no haproxy footprint, so this is deliberately a
    # per-key override rather than broadening the whole category.
    ConfigEnum.tls_ports: frozenset({Subsystem.xray, Subsystem.singbox, Subsystem.haproxy}),
    ConfigEnum.http_ports: frozenset({Subsystem.xray, Subsystem.singbox, Subsystem.haproxy}),
}


def subsystems_for_key(key: ConfigEnum) -> frozenset[str] | None:
    """The install.sh subsystems a change to this key affects, or None if
    that isn't confidently known - callers MUST treat None as "do a full
    apply", never as "touch nothing"."""
    if key in KEY_SUBSYSTEM_OVERRIDES:
        return KEY_SUBSYSTEM_OVERRIDES[key]
    return CATEGORY_SUBSYSTEMS.get(key.category)


def get_pending_subsystems() -> set[str] | None:
    """None means the next Apply Configs must be full-width (no narrow scope
    is known yet, or an unmapped change wiped out any earlier narrow scope).
    A non-empty set means it's safe to touch only those subsystems."""
    raw = (hconfig(ConfigEnum.pending_apply_subsystems) or '').strip()
    if not raw:
        return None
    return {s for s in raw.split(',') if s}


def mark_dirty(subsystems: frozenset[str] | set[str] | None) -> None:
    """Record that `subsystems` need touching on the next Apply Configs.
    Pass None when a change's scope isn't confidently known - this forces
    the next apply to be full-width, discarding any previously-narrowed
    scope (correct: we can no longer vouch that only the old narrow set is
    enough, since something-we-don't-understand also changed)."""
    if subsystems is None:
        set_hconfig(ConfigEnum.pending_apply_subsystems, '')
        return
    if not subsystems:
        return
    current = get_pending_subsystems() or set()
    updated = current | set(subsystems)
    set_hconfig(ConfigEnum.pending_apply_subsystems, ','.join(sorted(updated)))


def clear_pending_subsystems() -> None:
    """Called once an apply has actually been dispatched (whether full-width
    or scoped) - back to the safe "unknown, do everything" default."""
    set_hconfig(ConfigEnum.pending_apply_subsystems, '')
