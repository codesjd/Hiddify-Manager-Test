import datetime
import json
import os
import random
import sys
import uuid


from hiddifypanel import Events, hutils
from hiddifypanel.cache import cache
from hiddifypanel.models import *

from hiddifypanel.database import db, db_execute


from loguru import logger
MAX_DB_VERSION = 140


def _v139(child_id):
    """make_proxy_rows() used to seed an xhttp Proxy row's download-channel
    alpn (params.download.alpn) crossed against every l3 - e.g. a "tls"
    (h1) row also got dl=h2/dl=h3 variants, "tls_h2" got a dl=h3 variant,
    and h3_quic got dl=h1/dl=h2 variants - so the download channel could
    silently negotiate a different protocol than the row's own l3 label
    promised (confirmed live: a "tls_h2 xhttp direct vless dl=h3" row).
    Delete the mismatched rows; the one correctly-matching variant for
    each l3 (already seeded alongside them, e.g. "... dl=h1" for tls) is
    left untouched, as is every non-xhttp row."""
    expected_dl = {ProxyL3.h3_quic: 'h3', ProxyL3.tls_h2: 'h2', ProxyL3.tls: 'http/1.1'}
    for p in Proxy.query.filter_by(transport=ProxyTransport.xhttp, child_id=child_id).all():
        if p.l3 not in expected_dl:
            continue
        dl = (p.params or {}).get('download', {}).get('alpn')
        if dl and dl != expected_dl[p.l3]:
            db.session.delete(p)
    db.session.commit()


def _v138(child_id):
    """Phases A+B+C+D: kernel TLS offload flag, AnyTLS inbound, TUIC
    congestion-control setting, and Hysteria2 description seeds.

    tls_kernel_offload: default False (needs Linux 5.1+ CONFIG_TLS).
    anytls_enable: default False (Hiddify app doesn't support AnyTLS yet;
        only NekoBox/v2rayN >=7.14.3 can use it via singbox subscription).
    anytls_port: random unused port (same pattern as tuic_port).
    tuic_congestion_control: "cubic" (TUIC's own documented default).
    Hysteria2 mbps: no schema change -- defaults already seeded by _v111.
    AnyTLS Proxy rows: one direct + one relay, mirroring the tuic rows."""
    add_config_if_not_exist(ConfigEnum.tls_kernel_offload, False)
    add_config_if_not_exist(ConfigEnum.anytls_enable, False)
    add_config_if_not_exist(ConfigEnum.anytls_port, hutils.random.get_random_unused_port())
    add_config_if_not_exist(ConfigEnum.tuic_congestion_control, "cubic")
    # Seed default Proxy rows for AnyTLS (direct + relay), mirroring tuic
    for cdn in [ProxyCDN.direct, ProxyCDN.relay]:
        if not Proxy.query.filter_by(
            proto=ProxyProto.anytls, l3=ProxyL3.tls, cdn=cdn, child_id=child_id
        ).first():
            db.session.add(Proxy(
                name=f"AnyTLS{'Relay' if cdn == ProxyCDN.relay else ''}",
                proto=ProxyProto.anytls,
                l3=ProxyL3.tls,
                transport=ProxyTransport.custom,
                cdn=cdn,
                enable=True,
                child_id=child_id,
            ))
    db.session.commit()

def _v137(child_id):
    """KCP (the vless-over-kcp transport option) is retired - its whole
    value proposition (surviving high packet loss) has been superseded by
    Hysteria2/QUIC-family transports this panel already offers, and it
    never had an admin-facing toggle to begin with (kcp_enable has been
    ConfigCategory.hidden all along). Force it off for every install
    regardless of previous value, mirroring exactly how _v127 retired
    WireGuard - force the flag, leave the (now permanently unreachable)
    xray template/serialization code alone rather than sweeping every
    reference, same as _v127 did for wireguard's own branches."""
    set_hconfig(ConfigEnum.kcp_enable, False, child_id=child_id)


def _v136(child_id):
    """New CustomOutbound columns for TUIC and Mieru outbound support -
    xray-core has no native dialer for either (same situation as
    hysteria2/naive), so these only take effect when core_type=singbox;
    to_xray_dict() blackholes them. tuic_congestion_control defaults to
    "cubic" (TUIC's own documented default); mieru_transport/multiplexing
    default to sing-box's own "tcp"/"MULTIPLEXING_LOW" defaults so an
    existing row that never touches these fields still serializes to a
    complete, working outbound rather than an empty/invalid one."""
    add_column(CustomOutbound.tuic_congestion_control)
    add_column(CustomOutbound.mieru_transport)
    add_column(CustomOutbound.mieru_multiplexing)


def _v135(child_id):
    """AmneziaWG 2.0 completion, part 2: H1-H4 range/header-obfuscation
    columns for the Outbounds page's per-row amneziawg tunnels
    (CustomOutbound) - _v133 added S1-S4/I1-I5 there but missed H1-H4,
    the same oversight _v129 already fixed once for the client-facing
    side. Existing rows get NULL, which render_amneziawg_conf() treats
    as "omit the line", so nothing changes for outbounds that don't set
    them."""
    add_column(CustomOutbound.awg_h1)
    add_column(CustomOutbound.awg_h2)
    add_column(CustomOutbound.awg_h3)
    add_column(CustomOutbound.awg_h4)


def _v134(child_id):
    """AmneziaWG 2.0 completion, part 1: S1-S4/I1-I5 obfuscation params for
    the client-facing hiddifyawg interface - _v133 added these same
    parameters for the Outbounds page's per-row amneziawg tunnels but
    missed the client-facing side entirely. Seeded blank (not a shared
    default like Jc/Jmin/Jmax below) - a canned mimicry template shipped
    identically on every install would itself become a fingerprint, so
    this is opt-in; an empty StrConfig row just makes the field show up
    in Settings for an admin to fill in."""
    add_config_if_not_exist(ConfigEnum.amneziawg_s1, "")
    add_config_if_not_exist(ConfigEnum.amneziawg_s2, "")
    add_config_if_not_exist(ConfigEnum.amneziawg_s3, "")
    add_config_if_not_exist(ConfigEnum.amneziawg_s4, "")
    add_config_if_not_exist(ConfigEnum.amneziawg_i1, "")
    add_config_if_not_exist(ConfigEnum.amneziawg_i2, "")
    add_config_if_not_exist(ConfigEnum.amneziawg_i3, "")
    add_config_if_not_exist(ConfigEnum.amneziawg_i4, "")
    add_config_if_not_exist(ConfigEnum.amneziawg_i5, "")


def _v133(child_id):
    """New AmneziaWG outbound fields: raw .conf paste plus S1-S4 and I1-I5
    obfuscation parameters. All optional/blank on existing rows."""
    add_column(CustomOutbound.awg_conf)
    add_column(CustomOutbound.awg_s1)
    add_column(CustomOutbound.awg_s2)
    add_column(CustomOutbound.awg_s3)
    add_column(CustomOutbound.awg_s4)
    add_column(CustomOutbound.awg_i1)
    add_column(CustomOutbound.awg_i2)
    add_column(CustomOutbound.awg_i3)
    add_column(CustomOutbound.awg_i4)
    add_column(CustomOutbound.awg_i5)


def _v132(child_id):
    """Extra CustomRoutingRule match conditions to complete the routing form
    against the reference (source IP/CIDR, source port, sniffed protocol,
    inbound user email). Existing rules get NULL = "not part of the match",
    so behavior is unchanged for rules that don't set them."""
    add_column(CustomRoutingRule.source_ips)
    add_column(CustomRoutingRule.source_port)
    add_column(CustomRoutingRule.protocols)
    add_column(CustomRoutingRule.user_emails)


def _v131(child_id):
    """hysteria2 outbound support on the Outbounds page - three new
    CustomOutbound columns (Salamander obfs password + optional up/down
    bandwidth hints); server/port/password/sni reuse the existing shared
    columns. Existing rows get NULL, which to_singbox_dict() treats as
    "omit", so nothing changes for non-hysteria outbounds."""
    add_column(CustomOutbound.hysteria_obfs_password)
    add_column(CustomOutbound.hysteria_up_mbps)
    add_column(CustomOutbound.hysteria_down_mbps)


def _v130(child_id):
    """New CustomOutbound columns for the expanded Outbounds form: vless
    encryption, shadowsocks cipher method, REALITY public_key/short_id (a
    real, confirmed bug - to_xray_dict()/to_singbox_dict() never sent these
    at all, so every "reality" security outbound could never actually
    complete a handshake regardless of what else was configured), and
    xray-core's real sockopt/happyEyeballs/mux fields, none of which had
    dedicated columns before (extra_json was the only way to set them)."""
    add_column(CustomOutbound.encryption)
    add_column(CustomOutbound.reality_public_key)
    add_column(CustomOutbound.reality_short_id)
    add_column(CustomOutbound.ss_method)
    add_column(CustomOutbound.sockopt_mark)
    add_column(CustomOutbound.sockopt_tcp_fast_open)
    add_column(CustomOutbound.sockopt_tproxy)
    add_column(CustomOutbound.sockopt_domain_strategy)
    add_column(CustomOutbound.sockopt_dialer_proxy)
    add_column(CustomOutbound.sockopt_interface)
    add_column(CustomOutbound.sockopt_tcp_keep_alive_interval)
    add_column(CustomOutbound.sockopt_tcp_keep_alive_idle)
    add_column(CustomOutbound.sockopt_tcp_user_timeout)
    add_column(CustomOutbound.sockopt_tcp_max_seg)
    add_column(CustomOutbound.sockopt_tcp_window_clamp)
    add_column(CustomOutbound.sockopt_tcp_mptcp)
    add_column(CustomOutbound.sockopt_penetrate)
    add_column(CustomOutbound.sockopt_address_port_strategy)
    add_column(CustomOutbound.he_try_delay_ms)
    add_column(CustomOutbound.he_prioritize_ipv6)
    add_column(CustomOutbound.he_interleave)
    add_column(CustomOutbound.he_max_concurrent_try)
    add_column(CustomOutbound.mux_enabled)
    add_column(CustomOutbound.mux_concurrency)
    add_column(CustomOutbound.mux_xudp_concurrency)
    add_column(CustomOutbound.mux_xudp_proxy_udp_443)


def _v129(child_id):
    """H1-H4 (the AmneziaWG header-obfuscation magic values) were missed in
    _v128 - they're part of the same Jc/Jmin/Jmax obfuscation scheme, and
    leaving them unset relies on the client and server both falling back to
    the same implicit default, which isn't guaranteed across every client
    implementation. 1/2/3/4 are the documented AmneziaWG defaults (== real
    WireGuard's own message-type bytes, i.e. no header obfuscation) - a
    safe, working baseline an admin can later tune for stronger DPI
    resistance."""
    add_config_if_not_exist(ConfigEnum.amneziawg_h1, "1")
    add_config_if_not_exist(ConfigEnum.amneziawg_h2, "2")
    add_config_if_not_exist(ConfigEnum.amneziawg_h3, "3")
    add_config_if_not_exist(ConfigEnum.amneziawg_h4, "4")


def _v128(child_id):
    """One-time setup for AmneziaWG as the client-facing protocol replacing
    WireGuard (_v127) - mirrors _v69's wireguard bootstrap: generate the
    server's own interface keypair once, set default subnet/port/
    obfuscation values, and add the default Proxy rows users connect
    through. amneziawg_client_enable itself defaults to False - turning
    the whole thing on is a deliberate admin action, matching how a fresh
    install's wireguard_enable used to default to True but this one
    doesn't (avoids silently opening a new UDP port on upgrade)."""
    add_config_if_not_exist(ConfigEnum.amneziawg_client_enable, False)
    add_config_if_not_exist(ConfigEnum.amneziawg_port, hutils.random.get_random_unused_port())
    add_config_if_not_exist(ConfigEnum.amneziawg_ipv4, "10.91.0.1")
    add_config_if_not_exist(ConfigEnum.amneziawg_ipv6, "fd42:42:91::1")
    awg_pk, awg_pub, _ = hutils.crypto.get_wg_private_public_psk_pair()
    add_config_if_not_exist(ConfigEnum.amneziawg_private_key, awg_pk)
    add_config_if_not_exist(ConfigEnum.amneziawg_public_key, awg_pub)
    add_config_if_not_exist(ConfigEnum.amneziawg_jc, "4")
    add_config_if_not_exist(ConfigEnum.amneziawg_jmin, "40")
    add_config_if_not_exist(ConfigEnum.amneziawg_jmax, "70")

    default_rows = [
        Proxy(l3=ProxyL3.udp, transport=ProxyTransport.custom, cdn=ProxyCDN.direct, proto=ProxyProto.amneziawg, enable=True, name="AmneziaWG", child_id=child_id),
        Proxy(l3=ProxyL3.udp, transport=ProxyTransport.custom, cdn=ProxyCDN.relay, proto=ProxyProto.amneziawg, enable=True, name="AmneziaWG Relay", child_id=child_id),
    ]
    for p in default_rows:
        is_exist = Proxy.query.filter(Proxy.name == p.name, Proxy.child_id == child_id).first() or Proxy.query.filter(
            Proxy.l3 == p.l3, Proxy.transport == p.transport, Proxy.cdn == p.cdn, Proxy.proto == p.proto, Proxy.child_id == child_id).first()
        if not is_exist:
            db.session.add(p)
    db.session.commit()


def _v127(child_id):
    """WireGuard (the client-facing proxy protocol toggle) is being retired
    in favor of AmneziaWG - force it off for every install regardless of
    its previous value, since the toggle itself is being removed from the
    Proxies/Quick Setup UI and would otherwise be stuck on with no way to
    turn it off."""
    set_hconfig(ConfigEnum.wireguard_enable, False, child_id=child_id)


def _v126(child_id):
    """Backfill default admin/admin credentials onto the existing Owner
    account for installs that predate username/password login. Only
    touches fields that are genuinely unset - never overwrites a
    username or password an admin has actually chosen."""
    if child_id != 0:
        return
    admin = AdminUser.by_id(1)
    if not admin:
        return
    from werkzeug.security import generate_password_hash
    changed = False
    if not admin.username:
        if not AdminUser.query.filter(AdminUser.username == "admin", AdminUser.id != 1).first():
            admin.username = "admin"
            changed = True
    if not admin.password:
        admin.password = generate_password_hash("admin")
        changed = True
    if changed:
        db.session.commit()


def _v125(child_id):
    add_column(CustomOutbound.peer_public_key)
    add_column(CustomOutbound.preshared_key)
    add_column(CustomOutbound.local_address)
    add_column(CustomOutbound.dns)
    add_column(CustomOutbound.jc)
    add_column(CustomOutbound.jmin)
    add_column(CustomOutbound.jmax)


def _v124(child_id):
    add_config_if_not_exist(ConfigEnum.amneziawg_enable, False)
    add_config_if_not_exist(ConfigEnum.amneziawg_config, "")


def _v123(child_id):
    add_column(CustomOutbound.host_header)
    add_column(CustomOutbound.fingerprint)
    add_column(CustomOutbound.flow)
    add_column(CustomRoutingRule.inbound_tags)


def _v122(child_id):
    db.create_all()


def _v121(child_id):
    add_column(AdminUser.permissions)


def _v120(child_id):
    add_config_if_not_exist(ConfigEnum.webhook_enable, False)
    add_config_if_not_exist(ConfigEnum.webhook_url, "")
    add_config_if_not_exist(ConfigEnum.webhook_signing_key, "")


def _v119(child_id):
    set_hconfig(ConfigEnum.dnstt_resolvers,"8.8.8.8:53,8.8.4.4:53,auto")
    
def _v118(child_id):
    alter_column(Domain.extra_params)
    key_pair = hutils.crypto.generate_x25519_keys(False)
    add_config_if_not_exist(ConfigEnum.dnstt_private_key, key_pair['private_key'])
    add_config_if_not_exist(ConfigEnum.dnstt_public_key, key_pair['public_key'])

    

def _v116(child_id):
    set_hconfig(ConfigEnum.dnstt_enable, True)
    set_hconfig(ConfigEnum.dnstt_resolvers,"8.8.8.8:53,8.8.4.4:53")
    db.session.bulk_save_objects([
            Proxy(l3=ProxyL3.custom, transport=ProxyTransport.custom, cdn='direct', proto=ProxyProto.dnstt, enable=True, name="DNSTT"),
    ])


def _v115(child_id):
    set_hconfig(ConfigEnum.additional_configs_urls, "")
    set_hconfig(ConfigEnum.additional_configs_singbox, "")
    set_hconfig(ConfigEnum.additional_configs_xrayjson, "")

    
def _v114(child_id):
    db.session.bulk_save_objects([
        Proxy(l3=ProxyL3.tls_h2_h1, transport=ProxyTransport.custom, cdn=ProxyCDN.relay, proto=ProxyProto.naive, enable=True, name="NaiveTLS"),
        Proxy(l3=ProxyL3.h3_quic, transport=ProxyTransport.custom, cdn=ProxyCDN.relay, proto=ProxyProto.naive, enable=True, name="NaiveQuic"),
        Proxy(l3=ProxyL3.custom, transport=ProxyTransport.tcp, cdn=ProxyCDN.relay, proto=ProxyProto.mieru, enable=True, name="MieruTCP"),
        Proxy(l3=ProxyL3.custom, transport=ProxyTransport.udp, cdn=ProxyCDN.relay, proto=ProxyProto.mieru, enable=True, name="MieruUDP"),
    ]    
    )
def _v113(child_id):
    set_hconfig(ConfigEnum.telegram_lib, "telemt")
    

def _v111(child_id):
    set_hconfig(ConfigEnum.path_naive, hutils.random.get_random_string(7, 15))
    set_hconfig(ConfigEnum.naive_port, hutils.random.get_random_unused_port())
    
    set_hconfig(ConfigEnum.h2_enable,True)

    add_config_if_not_exist(ConfigEnum.naive_enable, True)
    add_config_if_not_exist(ConfigEnum.mieru_enable, True)
    

    if p:=hutils.random.get_random_unused_port():
        set_hconfig(ConfigEnum.mieru_tcp_ports, ",".join([f'{p+i}' for i in range(4)]))
    if p:=hutils.random.get_random_unused_port():
        set_hconfig(ConfigEnum.mieru_udp_ports, ",".join([f'{p+i}' for i in range(4)]))

    db.session.bulk_save_objects([
        Proxy(l3=ProxyL3.tls_h2_h1, transport=ProxyTransport.custom, cdn='direct', proto=ProxyProto.naive, enable=True, name="NaiveTLS"),
        Proxy(l3=ProxyL3.h3_quic, transport=ProxyTransport.custom, cdn='direct', proto=ProxyProto.naive, enable=True, name="NaiveQuic"),
        Proxy(l3=ProxyL3.custom, transport=ProxyTransport.tcp, cdn='direct', proto=ProxyProto.mieru, enable=True, name="MieruTCP"),
        Proxy(l3=ProxyL3.custom, transport=ProxyTransport.udp, cdn='direct', proto=ProxyProto.mieru, enable=True, name="MieruUDP"),
    ]    
    )
    add_config_if_not_exist(ConfigEnum.tls_fragment_packets, "tlshello")
    add_config_if_not_exist(ConfigEnum.mieru_handshake, MieruHandshake.HANDSHAKE_NO_WAIT)
    add_config_if_not_exist(ConfigEnum.mieru_multiplexing, MieruMultiplexing.MULTIPLEXING_HIGH)
    add_config_if_not_exist(ConfigEnum.tls_ech_enable, False)
    

def _v108(child_id):
    Domain.query.filter(Domain.mode==DomainType.auto_cdn_ip).update({
        "mode":"cdn",
        "resolve_ip":True
    })



    
def _v107(child_id):
    # set_hconfig(ConfigEnum.core_type,'xray') # disable singbox core temporary
    execute("UPDATE proxy SET params = '{}' WHERE params is NULL;")

def _v106(child_id):
    set_hconfig(ConfigEnum.use_ip_in_config,True)

    if rport:=hconfig(ConfigEnum.reality_port):
        set_hconfig(ConfigEnum.special_port,rport)
    StrConfig.query.filter(StrConfig.key==ConfigEnum.reality_port).delete()
    set_hconfig(ConfigEnum.default_useragent_string,hutils.network.get_random_user_agent())
    for d in Domain.query.filter(Domain.mode==DomainType.reality,Domain.child_id == child_id).all():
        d.mode=DomainType.special_reality_tcp
    set_hconfig(ConfigEnum.h2_enable,False)
    db.session.bulk_save_objects(get_proxy_rows_v1())

def _v103(child_id):

    add_usage_proc=    """
DROP PROCEDURE IF EXISTS add_usage_json;

CREATE PROCEDURE add_usage_json(IN usage_data JSON, IN cur_time DATETIME)
BEGIN
  DECLARE u_id INT DEFAULT NULL;
  DECLARE u_uuid CHAR(36) DEFAULT NULL;
  DECLARE u_usage BIGINT;
  DECLARE done BOOL DEFAULT FALSE;
  DECLARE cur_date DATE;


  DECLARE cur CURSOR FOR
    SELECT  jt.uuid, jt.usage FROM JSON_TABLE(
      usage_data, '$[*]' COLUMNS (
        uuid CHAR(36) PATH '$.uuid', `usage` BIGINT PATH '$.usage')) AS jt;

  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
  SET cur_date = DATE(cur_time);
  OPEN cur;

  read_loop: LOOP
    FETCH cur INTO  u_uuid, u_usage;
    IF done THEN
      LEAVE read_loop;
    END IF;

    
    UPDATE `user`
    SET current_usage = current_usage + u_usage, last_online = cur_time, start_date = CASE WHEN start_date IS NULL THEN cur_date ELSE start_date END
    WHERE uuid = u_uuid;


    COMMIT;
  END LOOP;

  CLOSE cur;
END

    """

    db_execute(add_usage_proc,commit=True)
    

def _v101(child_id):
    add_config_if_not_exist(ConfigEnum.path_xhttp, hutils.random.get_random_string(7, 15))
    add_config_if_not_exist(ConfigEnum.xhttp_enable, False)
    


def _v97(child_id):
    keys = hutils.crypto.generate_ssh_host_keys()
    # set_hconfig(ConfigEnum.ssh_host_dsa_pk, keys['dsa']['pk'])
    # set_hconfig(ConfigEnum.ssh_host_dsa_pub, keys['dsa']['pub'])
    set_hconfig(ConfigEnum.ssh_host_rsa_pk, keys['rsa']['pk'])
    set_hconfig(ConfigEnum.ssh_host_rsa_pub, keys['rsa']['pub'])
    set_hconfig(ConfigEnum.ssh_host_ed25519_pk, keys['ed25519']['pk'])
    set_hconfig(ConfigEnum.ssh_host_ed25519_pub, keys['ed25519']['pub'])
    set_hconfig(ConfigEnum.ssh_host_ecdsa_pk, keys['ecdsa']['pk'])
    set_hconfig(ConfigEnum.ssh_host_ecdsa_pub, keys['ecdsa']['pub'])

    for a in AdminUser.query.all():
        a.password = ""
    for a in User.query.all():
        a.password = ""


def _v96(child_id):
    from sqlalchemy import func
    result = (db.session.query(DailyUsage.child_id, DailyUsage.admin_id, DailyUsage.date, func.max(DailyUsage.online).label('online'), func.sum(DailyUsage.usage).label('usage'), func.count(DailyUsage.usage).label('count'), )
              .group_by(DailyUsage.child_id, DailyUsage.admin_id, DailyUsage.date)
              .all())

    for r in result:
        if r.count > 1:
            # Delete existing records for this group
            db.session.query(DailyUsage).filter(DailyUsage.child_id == r.child_id, DailyUsage.admin_id == r.admin_id, DailyUsage.date == r.date).delete()

            # Add the aggregated record
            new_record = DailyUsage(child_id=r.child_id, admin_id=r.admin_id, date=r.date, online=r.online, usage=r.usage)
            db.session.add(new_record)

    # Commit the changes to the database
    db.session.commit()


def _v94(child_id):
    set_hconfig(ConfigEnum.wireguard_noise_trick, "0-0")


def _v93(child_id):
    set_hconfig(ConfigEnum.quic_enable, True)
    set_hconfig(ConfigEnum.xhttp_enable, True)


def _v92(child_id):
    db.session.bulk_save_objects(get_proxy_rows_v1())


def _v89(child_id):
    set_hconfig(ConfigEnum.path_xhttp, hutils.random.get_random_string(7, 15))
    set_hconfig(ConfigEnum.xhttp_enable, False)
    pass


def _v86(child_id):
    set_hconfig(ConfigEnum.hiddifycli_enable, True)


def _v85(child_id):
    set_hconfig(ConfigEnum.sub_full_singbox_enable, True)
    set_hconfig(ConfigEnum.sub_singbox_ssh_enable, True)
    set_hconfig(ConfigEnum.sub_full_xray_json_enable, True)
    set_hconfig(ConfigEnum.sub_full_links_enable, True)
    set_hconfig(ConfigEnum.sub_full_links_b64_enable, True)
    set_hconfig(ConfigEnum.sub_full_clash_enable, True)
    set_hconfig(ConfigEnum.sub_full_clash_meta_enable, True)


def _v84(child_id):
    # the 2022-blake3-chacha20-poly1305 encryption method doesn't support multiuser config
    if hconfig(ConfigEnum.shadowsocks2022_method) == '2022-blake3-chacha20-poly1305':
        set_hconfig(ConfigEnum.shadowsocks2022_method, '2022-blake3-aes-256-gcm')


def _v83(child_id):
    set_hconfig(ConfigEnum.log_level, LogLevel.CRITICAL)


def _v82(child_id):
    set_hconfig(ConfigEnum.vless_enable, True)
    set_hconfig(ConfigEnum.trojan_enable, False)
    set_hconfig(ConfigEnum.reality_enable, False)
    set_hconfig(ConfigEnum.tcp_enable, True)
    set_hconfig(ConfigEnum.quic_enable, False)
    set_hconfig(ConfigEnum.xtls_enable, False)
    set_hconfig(ConfigEnum.h2_enable, True)


def _v81(child_id):
    # password now stores a werkzeug scrypt hash (a fixed 162 chars), not a
    # plaintext password - the old VARCHAR(100) truncated/rejected every
    # hash, which made it impossible to ever log into an account after its
    # password was hashed (including a fresh install's first password set
    # through Quick Setup).
    execute("ALTER TABLE user MODIFY COLUMN password VARCHAR(255);")
    execute("ALTER TABLE admin_user MODIFY COLUMN password VARCHAR(255);")


def _v80(child_id):
    set_hconfig(ConfigEnum.parent_domain, '')
    set_hconfig(ConfigEnum.parent_admin_proxy_path, '')


def _v79(child_id):
    set_hconfig(ConfigEnum.panel_mode, PanelMode.standalone)


def _v78(child_id):
    # equalize panel unique id and root child unique id
    root_child_unique_id = Child.query.filter(Child.name == "Root").first().unique_id
    set_hconfig(ConfigEnum.unique_id, root_child_unique_id)


def _v77(child_id):
    pass


def _v75(child_id):
    for u in User.query.all():
        hutils.model.gen_wg_keys(u)


def _v74(child_id):
    set_hconfig(ConfigEnum.ws_enable, False)
    set_hconfig(ConfigEnum.grpc_enable, True)
    set_hconfig(ConfigEnum.httpupgrade_enable, True)
    set_hconfig(ConfigEnum.shadowsocks2022_port, hutils.random.get_random_unused_port())
    set_hconfig(ConfigEnum.shadowsocks2022_method, "2022-blake3-aes-256-gcm")
    set_hconfig(ConfigEnum.shadowsocks2022_enable, False)
    set_hconfig(ConfigEnum.path_httpupgrade, hutils.random.get_random_string(7, 15))
    db.session.bulk_save_objects(get_proxy_rows_v1())

    for i in range(1, 10):
        for d in hutils.network.get_random_domains(50):
            if hutils.network.is_domain_reality_friendly(d):
                set_hconfig(ConfigEnum.shadowtls_fakedomain, d)
                return
    set_hconfig(ConfigEnum.shadowtls_fakedomain, "captive.apple.com")


def _v71(child_id):
    add_config_if_not_exist(ConfigEnum.tuic_port, hutils.random.get_random_unused_port())
    add_config_if_not_exist(ConfigEnum.hysteria_port, hutils.random.get_random_unused_port())
    add_config_if_not_exist(ConfigEnum.ssh_server_port, hutils.random.get_random_unused_port())
    add_config_if_not_exist(ConfigEnum.wireguard_port, hutils.random.get_random_unused_port())


def _v70(child_id):
    Domain.query.filter(Domain.child_id != 0).delete()
    StrConfig.query.filter(StrConfig.child_id != 0).delete()
    BoolConfig.query.filter(BoolConfig.child_id != 0).delete()
    Proxy.query.filter(Proxy.child_id != 0).delete()
    Child.query.filter(Child.id != 0).delete()

    child = Child.by_id(0)
    child.unique_id = str(uuid.uuid4())
    child.type = ChildMode.virtual


# using child_id in lower version is not needed as it is introduced in v70


def _v69():
    db.session.bulk_save_objects(get_proxy_rows_v1())
    add_config_if_not_exist(ConfigEnum.wireguard_enable, True)
    add_config_if_not_exist(ConfigEnum.wireguard_port, hutils.random.get_random_unused_port())
    add_config_if_not_exist(ConfigEnum.wireguard_ipv4, "10.90.0.1")
    add_config_if_not_exist(ConfigEnum.wireguard_ipv6, "fd42:42:90::1")
    wg_pk, wg_pub, _ = hutils.crypto.get_wg_private_public_psk_pair()
    add_config_if_not_exist(ConfigEnum.wireguard_private_key, wg_pk)
    add_config_if_not_exist(ConfigEnum.wireguard_public_key, wg_pub)
    for u in User.query.all():
        u.wg_pk, u.wg_pub, u.wg_psk = hutils.crypto.get_wg_private_public_psk_pair()


def _v65():
    add_config_if_not_exist(ConfigEnum.mux_enable, False)
    add_config_if_not_exist(ConfigEnum.mux_protocol, 'smux')
    add_config_if_not_exist(ConfigEnum.mux_max_connections, '4')
    add_config_if_not_exist(ConfigEnum.mux_min_streams, '4')
    add_config_if_not_exist(ConfigEnum.mux_max_streams, '0')
    add_config_if_not_exist(ConfigEnum.mux_padding_enable, False)
    add_config_if_not_exist(ConfigEnum.mux_brutal_enable, False)
    add_config_if_not_exist(ConfigEnum.mux_brutal_up_mbps, '100')
    add_config_if_not_exist(ConfigEnum.mux_brutal_down_mbps, '100')


def _v63():
    add_config_if_not_exist(ConfigEnum.hysteria_enable, True)
    add_config_if_not_exist(ConfigEnum.hysteria_port, hutils.random.get_random_unused_port())
    add_config_if_not_exist(ConfigEnum.hysteria_obfs_enable, True)
    add_config_if_not_exist(ConfigEnum.hysteria_up_mbps, "150")
    add_config_if_not_exist(ConfigEnum.hysteria_down_mbps, "300")


def _v62():
    add_config_if_not_exist(ConfigEnum.tls_fragment_enable, False)
    add_config_if_not_exist(ConfigEnum.tls_fragment_size, "10-100")
    add_config_if_not_exist(ConfigEnum.tls_fragment_sleep, "50-200")
    add_config_if_not_exist(ConfigEnum.tls_mixed_case, False)
    add_config_if_not_exist(ConfigEnum.tls_padding_enable, False)
    add_config_if_not_exist(ConfigEnum.tls_padding_length, "50-200")


def _v61():
    execute("ALTER TABLE user MODIFY COLUMN username VARCHAR(100);")
    execute("ALTER TABLE user MODIFY COLUMN password VARCHAR(100);")


def _v60():
    add_config_if_not_exist(ConfigEnum.proxy_path_admin, hutils.random.get_random_string())
    add_config_if_not_exist(ConfigEnum.proxy_path_client, hutils.random.get_random_string())


def _v59():
    # set user model username and password
    for u in User.query.all():
        hutils.model.gen_username(u)
        # hutils.model.gen_password(u)

    # set admin model username and password
    for a in AdminUser.query.all():
        hutils.model.gen_username(a)
        # hutils.model.gen_password(a)


def _v57():
    add_config_if_not_exist(ConfigEnum.warp_sites, "")


def _v56():
    set_hconfig(ConfigEnum.special_port, hutils.random.get_random_unused_port())


def _v55():
    tuic_port = hutils.random.get_random_unused_port()
    hystria_port = hutils.random.get_random_unused_port()
    set_hconfig(ConfigEnum.tuic_port, tuic_port)
    set_hconfig(ConfigEnum.hysteria_port, hystria_port)
    set_hconfig(ConfigEnum.tuic_enable, True)
    set_hconfig(ConfigEnum.hysteria_enable, True)
    Proxy.query.filter(Proxy.proto.in_(["tuic", "hysteria2", "hysteria"])).delete()
    db.session.add(Proxy(l3='tls', transport='custom', cdn='direct', proto='tuic', enable=True, name="TUIC"))
    db.session.add(Proxy(l3='tls', transport='custom', cdn='direct', proto='hysteria2', enable=True, name="Hysteria2"))


def _v52():
    db.session.bulk_save_objects(get_proxy_rows_v1())


def _v51():
    Proxy.query.filter(Proxy.l3.in_([ProxyL3.h3_quic])).delete()


def _v50():
    set_hconfig(ConfigEnum.show_usage_in_sublink, True)


def _v49():

    for u in User.query.all():
        priv, publ = hutils.crypto.get_ed25519_private_public_pair()
        u.ed25519_private_key = priv
        u.ed25519_public_key = publ


def _v48():
    add_config_if_not_exist(ConfigEnum.ssh_server_enable, True)
    set_hconfig(ConfigEnum.ssh_server_enable, True)


def _v47():
    StrConfig.query.filter(StrConfig.key == ConfigEnum.ssh_server_enable).delete()


def _v45():

    if not Proxy.query.filter(Proxy.name == "SSH").first():
        db.session.add(Proxy(l3='ssh', transport='ssh', cdn='direct', proto='ssh', enable=True, name="SSH"))

    add_config_if_not_exist(ConfigEnum.ssh_server_port, hutils.random.get_random_unused_port())
    add_config_if_not_exist(ConfigEnum.ssh_server_enable, False)
# def _v43():
#     if not (Domain.query.filter(Domain.domain==hconfig(ConfigEnum.domain_fronting_domain)).first()):
#         db.session.add(Domain(domain=hconfig(ConfigEnum.domain_fronting_domain),servernames=hconfig(ConfigEnum.domain_fronting_domain),mode=DomainType.cdn))

# v7.0.0


def _v42():

    for k in [ConfigEnum.telegram_fakedomain, ConfigEnum.ssfaketls_fakedomain, ConfigEnum.shadowtls_fakedomain]:
        if not hconfig(k):
            rnd_domains = hutils.network.get_random_domains(1)
            add_config_if_not_exist(k, rnd_domains[0])


def _v41():
    add_config_if_not_exist(ConfigEnum.core_type, "xray")
    if not (Domain.query.filter(Domain.domain == hconfig(ConfigEnum.reality_fallback_domain)).first()):
        db.session.add(Domain(domain=hconfig(ConfigEnum.reality_fallback_domain), servernames=hconfig(ConfigEnum.reality_server_names), mode=DomainType.reality))


def _v38():
    add_config_if_not_exist(ConfigEnum.dns_server, "1.1.1.1")
    add_config_if_not_exist(ConfigEnum.warp_mode, "all" if hconfig(ConfigEnum.warp_enable) else "disable")
    add_config_if_not_exist(ConfigEnum.warp_plus_code, '')


# def _v34():
#     add_config_if_not_exist(ConfigEnum.show_usage_in_sublink, True)


def _v33():
    Proxy.query.filter(Proxy.l3 == ProxyL3.reality).delete()
    _v31()


def _v31():
    add_config_if_not_exist(ConfigEnum.reality_short_ids, uuid.uuid4().hex[0:random.randint(1, 8) * 2])
    key_pair = hutils.crypto.generate_x25519_keys()
    add_config_if_not_exist(ConfigEnum.reality_private_key, key_pair['private_key'])
    add_config_if_not_exist(ConfigEnum.reality_public_key, key_pair['public_key'])
    db.session.bulk_save_objects(get_proxy_rows_v1())
    if not (AdminUser.query.filter(AdminUser.id == 1).first()):
        db.session.add(AdminUser(id=1, uuid=hconfig(ConfigEnum.admin_secret), name="Owner", mode=AdminMode.super_admin, comment=""))
        execute("update admin_user set id=1 where name='owner'")
    for i in range(1, 10):
        for d in hutils.network.get_random_domains(50):
            if hutils.network.is_domain_reality_friendly(d):
                add_config_if_not_exist(ConfigEnum.reality_fallback_domain, d)
                add_config_if_not_exist(ConfigEnum.reality_server_names, d)
                return
    add_config_if_not_exist(ConfigEnum.reality_fallback_domain, "yahoo.com")
    add_config_if_not_exist(ConfigEnum.reality_server_names, "yahoo.com")

    # add_config_if_not_exist(ConfigEnum.cloudflare, "")


def _v27():
    # add_config_if_not_exist(ConfigEnum.cloudflare, "")
    set_hconfig(ConfigEnum.netdata, False)


def _v26():
    add_config_if_not_exist(ConfigEnum.cloudflare, "")
    add_config_if_not_exist(ConfigEnum.country, "ir")
    add_config_if_not_exist(ConfigEnum.parent_panel, "")
    add_config_if_not_exist(ConfigEnum.is_parent, False)
    add_config_if_not_exist(ConfigEnum.license, "")


def _v21():
    db.session.bulk_save_objects(get_proxy_rows_v1())


def _v20():
    if hconfig(ConfigEnum.domain_fronting_domain):
        fake_domains = [hconfig(ConfigEnum.domain_fronting_domain)]

        direct_domain = Domain.query.filter(Domain.mode in [DomainType.direct, DomainType.relay]).first()
        if direct_domain:
            direct_host = direct_domain.domain
        else:
            direct_host = hutils.network.get_ip_str(4)

        for fd in fake_domains:
            if not Domain.query.filter(Domain.domain == fd).first():
                db.session.add(Domain(domain=fd, mode='fake', alias='moved from domain fronting', cdn_ip=direct_host))


def _v19():
    set_hconfig(ConfigEnum.path_trojan, hutils.random.get_random_string(7, 15))
    set_hconfig(ConfigEnum.path_vless, hutils.random.get_random_string(7, 15))
    set_hconfig(ConfigEnum.path_vmess, hutils.random.get_random_string(7, 15))
    set_hconfig(ConfigEnum.path_ss, hutils.random.get_random_string(7, 15))
    set_hconfig(ConfigEnum.path_grpc, hutils.random.get_random_string(7, 15))
    set_hconfig(ConfigEnum.path_tcp, hutils.random.get_random_string(7, 15))
    set_hconfig(ConfigEnum.path_ws, hutils.random.get_random_string(7, 15))
    add_config_if_not_exist(ConfigEnum.tuic_enable, False)
    add_config_if_not_exist(ConfigEnum.shadowtls_enable, False)
    add_config_if_not_exist(ConfigEnum.shadowtls_fakedomain, "en.wikipedia.org")
    add_config_if_not_exist(ConfigEnum.utls, "chrome")
    add_config_if_not_exist(ConfigEnum.telegram_bot_token, "")
    add_config_if_not_exist(ConfigEnum.package_mode, "release")


# def _v17():
#     for u in User.query.all():
#         if u.expiry_time:
#             if not u.package_days:
#                 if not u.last_reset_time:
#                     u.package_days = (u.expiry_time - datetime.date.today()).days
#                     u.start_date = datetime.date.today()
#                 else:
#                     u.package_days = (u.expiry_time - u.last_reset_time).days
#                     u.start_date = u.last_reset_time
#             u.expiry_time = None


def _v1():
    external_ip = str(hutils.network.get_ip_str(4))
    rnd_domains = hutils.network.get_random_domains(5)

    data = [
        
        StrConfig(key=ConfigEnum.db_version, value=1), User(name="default", usage_limit_GB=3000, package_days=3650, mode=UserMode.weekly),
        Domain(domain=external_ip, mode=DomainType.direct), 
        Domain(domain=external_ip + ".sslip.io", mode=DomainType.direct), 
        StrConfig(key=ConfigEnum.admin_secret, value=uuid.uuid4()), StrConfig(key=ConfigEnum.http_ports, value="80"), StrConfig(key=ConfigEnum.tls_ports, value="443"), BoolConfig(key=ConfigEnum.first_setup, value=True), StrConfig(key=ConfigEnum.decoy_domain, value=hutils.network.get_random_decoy_domain()), StrConfig(key=ConfigEnum.proxy_path, value=hutils.random.get_random_string()), BoolConfig(key=ConfigEnum.firewall, value=False), BoolConfig(key=ConfigEnum.netdata, value=True), StrConfig(key=ConfigEnum.lang, value='en'), BoolConfig(key=ConfigEnum.block_iran_sites, value=True), BoolConfig(key=ConfigEnum.allow_invalid_sni, value=True), BoolConfig(key=ConfigEnum.kcp_enable, value=False), StrConfig(key=ConfigEnum.kcp_ports, value="88"), BoolConfig(key=ConfigEnum.auto_update, value=os.environ.get('HIDDIFY_DISABLE_UPDATE',"").lower() not in {'1','true'}), BoolConfig(key=ConfigEnum.only_ipv4, value=False), BoolConfig(key=ConfigEnum.vmess_enable, value=True), BoolConfig(key=ConfigEnum.http_proxy_enable, value=True), StrConfig(key=ConfigEnum.shared_secret, value=str(uuid.uuid4())), BoolConfig(key=ConfigEnum.telegram_enable, value=False), # StrConfig(key=ConfigEnum.telegram_secret,value=uuid.uuid4().hex), StrConfig(key=ConfigEnum.telegram_adtag, value=""), StrConfig(key=ConfigEnum.telegram_fakedomain, value=rnd_domains[1]), BoolConfig(key=ConfigEnum.ssfaketls_enable, value=False), # StrConfig(key=ConfigEnum.ssfaketls_secret,value=str(uuid.uuid4())), StrConfig(key=ConfigEnum.ssfaketls_fakedomain, value=rnd_domains[2]), BoolConfig(key=ConfigEnum.shadowtls_enable, value=False), # StrConfig(key=ConfigEnum.shadowtls_secret,value=str(uuid.uuid4())), StrConfig(key=ConfigEnum.shadowtls_fakedomain, value=rnd_domains[3]), 
        BoolConfig(key=ConfigEnum.ssr_enable, value=False), # StrConfig(key=ConfigEnum.ssr_secret,value=str(uuid.uuid4())), StrConfig(key=ConfigEnum.ssr_fakedomain, value=rnd_domains[4]), 
        # BoolConfig(key=ConfigEnum.tuic_enable, value=False), # StrConfig(key=ConfigEnum.tuic_port, value=3048), 
        BoolConfig(key=ConfigEnum.domain_fronting_tls_enable, value=False), BoolConfig(key=ConfigEnum.domain_fronting_http_enable, value=False), StrConfig(key=ConfigEnum.domain_fronting_domain, value=""), 
        # BoolConfig(key=ConfigEnum.torrent_block,value=False), 
        *get_proxy_rows_v1()
    ]
    # fake_domains=['speedtest.net']
    # for fd in fake_domains:
    #     if not Domain.query.filter(Domain.domain==fd).first():
    #         db.session.add(Domain(domain=fd,mode='fake',alias='fake domain',cdn_ip=external_ip))
    db.session.bulk_save_objects(data)


def _v7():
    try:
        Proxy.query.filter(Proxy.name == 'tls XTLS direct trojan').delete()
        Proxy.query.filter(Proxy.name == 'tls XTLSVision direct trojan').delete()
    except BaseException:
        pass
    add_config_if_not_exist(ConfigEnum.telegram_lib, "erlang")
    add_config_if_not_exist(ConfigEnum.admin_lang, hconfig(ConfigEnum.lang))
    add_config_if_not_exist(ConfigEnum.branding_title, "")
    add_config_if_not_exist(ConfigEnum.branding_site, "")
    add_config_if_not_exist(ConfigEnum.branding_freetext, "")
    add_config_if_not_exist(ConfigEnum.v2ray_enable, False)
    add_config_if_not_exist(ConfigEnum.is_parent, False)
    add_config_if_not_exist(ConfigEnum.parent_panel, '')
    add_config_if_not_exist(ConfigEnum.unique_id, str(uuid.uuid4()))


def _v9():
    # add_column(User.mode)
    # add_column(User.comment)
    try:
        for u in User.query.all():
            u.mode = UserMode.monthly if u.monthly else UserMode.no_reset
    except BaseException:
        pass


def _v10():
    all_configs = get_hconfigs()
    execute("ALTER TABLE `str_config` RENAME TO `str_config_old`")
    execute("ALTER TABLE `bool_config` RENAME TO `bool_config_old`")
    # db.create_all()
    rows = []
    for c, v in all_configs.items():
        if c.type == bool:
            rows.append(BoolConfig(key=c, value=v, child_id=0))
        else:
            rows.append(StrConfig(key=c, value=v, child_id=0))

    db.session.bulk_save_objects(rows)


def get_proxy_rows_v1():
    rows = list(make_proxy_rows([
        "h2 direct vless", 
        # "XTLS direct vless",
        "WS direct vless", 
        "WS direct trojan", 
        "WS direct vmess", 
        "httpupgrade direct vless", 
        # "httpupgrade direct trojan", 
        "httpupgrade direct vmess", 
        "xhttp direct vless", 
        # "xhttp direct trojan", 
        "xhttp direct vmess", 
        "tcp direct vless",
        "tcp direct trojan",
        "tcp direct vmess",
        "grpc direct vless",
        "grpc direct trojan",
        "grpc direct vmess",
        "faketls direct ss",
        "WS direct v2ray",
        "h2 relay vless",
        # "XTLS relay vless",
        "WS relay vless",
        "WS relay trojan",
        "WS relay vmess",
        "httpupgrade relay vless",
        # "httpupgrade relay trojan",
        "httpupgrade relay vmess",
        
        "xhttp relay vless",
        # "xhttp relay trojan",
        "xhttp relay vmess",
        
        "tcp relay vless",
        "tcp relay trojan",
        "tcp relay vmess",
        "grpc relay vless",
        "grpc relay trojan",
        "grpc relay vmess",
        "faketls relay ss",
        "WS relay v2ray",
        
        # "restls1_2 direct ss",
        # "restls1_3 direct ss",
        # "tcp direct ssr",
        "WS CDN v2ray",
        "WS CDN vless",
        "WS CDN trojan",
        "WS CDN vmess",
        "httpupgrade CDN vless",
        # "httpupgrade CDN trojan",
        "httpupgrade CDN vmess",
        
        "xhttp CDN vless",
        # "xhttp CDN trojan",
        "xhttp CDN vmess",
        
        
        "grpc CDN vless",
        "grpc CDN trojan",
        "grpc CDN vmess",
        
    ]))
    rows.append(Proxy(l3=ProxyL3.custom, transport=ProxyTransport.shadowsocks, cdn='direct', proto='ss', enable=True, name="ShadowSocks2022"))
    rows.append(Proxy(l3=ProxyL3.custom, transport=ProxyTransport.shadowsocks, cdn='relay', proto='ss', enable=True, name="ShadowSocks2022 Relay"))

    rows.append(Proxy(l3=ProxyL3.tls, transport=ProxyTransport.shadowtls, cdn='direct', proto='ss', enable=True, name="ShadowTLS"))
    rows.append(Proxy(l3=ProxyL3.tls, transport=ProxyTransport.shadowtls, cdn='relay', proto='ss', enable=True, name="ShadowTLS Relay"))
    rows.append(Proxy(l3='ssh', transport='ssh', cdn='direct', proto='ssh', enable=True, name="SSH"))
    rows.append(Proxy(l3='ssh', transport=ProxyTransport.ssh, cdn=ProxyCDN.relay, proto=ProxyProto.ssh, enable=True, name="SSH Relay"))

    rows.append(Proxy(l3='tls', transport='custom', cdn='direct', proto='tuic', enable=True, name="TUIC"))
    rows.append(Proxy(l3='tls', transport='custom', cdn='relay', proto='tuic', enable=True, name="TUIC Relay"))
    rows.append(Proxy(l3='tls', transport='custom', cdn='direct', proto='hysteria2', enable=True, name="Hysteria2"))
    rows.append(Proxy(l3='tls', transport='custom', cdn='relay', proto='hysteria2', enable=True, name="Hysteria2 Relay"))
    rows.append(Proxy(l3=ProxyL3.udp, transport=ProxyTransport.custom, cdn=ProxyCDN.direct, proto=ProxyProto.wireguard, enable=True, name="WireGuard"))
    rows.append(Proxy(l3=ProxyL3.udp, transport=ProxyTransport.custom, cdn=ProxyCDN.relay, proto=ProxyProto.wireguard, enable=True, name="WireGuard Relay"))
    for p in rows:
        is_exist = Proxy.query.filter(Proxy.name == p.name).first() or Proxy.query.filter(
            Proxy.l3 == p.l3, Proxy.transport == p.transport, Proxy.cdn == p.cdn, Proxy.proto == p.proto).first()
        if not is_exist:
            yield p


def make_proxy_rows(cfgs):
    # "h3_quic", 
    for l3 in [ProxyL3.h3_quic, "tls_h2", "tls", "http", "reality"]:
        for c in cfgs:
            transport, cdn, proto = c.split(" ")
            if transport != ProxyTransport.xhttp and l3 == ProxyL3.h3_quic:
                continue
            if l3 in ["kcp", 'reality'] and cdn != "direct":
                continue
            if l3 == "reality" and ((transport not in ['tcp', 'grpc', 'XTLS',ProxyTransport.xhttp]) or proto != 'vless'):
                continue
            if proto == "trojan" and l3 not in ["tls", 'xtls', 'tls_h2', 'h3_quic']:
                continue
            if transport in ["grpc", "XTLS", "faketls"] and l3 == "http":
                continue
            if transport in ["h2"] and l3 != "reality":
                continue
            if l3 in [ProxyL3.h3_quic,ProxyL3.tls_h2] and transport in [ProxyTransport.httpupgrade, ProxyTransport.WS]:
                continue

            

            # if l3 == "tls_h2" and transport =="grpc":
            #     continue
            enable = l3 != "http" or proto == "vmess"
            enable = enable and (transport != 'tcp' or l3=="reality")
            name = f'{l3} {c}'
            # is_exist = Proxy.query.filter(Proxy.name == name).first() or Proxy.query.filter(            #     Proxy.l3 == l3, Proxy.transport == transport, Proxy.cdn == cdn, Proxy.proto == proto).first()
            # if not is_exist:
            params_list=[('',{})]

            if transport=="xhttp" and l3 not in [ProxyL3.reality,ProxyL3.http]:
                # The download-channel alpn must match this row's own l3,
                # not every possible alpn - seeding all three (h1/h2/h3) for
                # every l3 produced e.g. a "tls" (h1) row whose download
                # channel negotiated h2/h3, and a "tls_h2" row that
                # negotiated h3, silently contradicting the row's own l3
                # label. Only the one variant that actually matches this
                # row's l3 is generated.
                dl = 'h3' if l3 == ProxyL3.h3_quic else ('h2' if l3 == 'tls_h2' else 'http/1.1')
                name_postfix = f' dl={dl}'.replace("http/1.1", 'h1')
                params_list = [(name_postfix, {'download': {'alpn': dl}})]

            for name_postfix,params in params_list:
                yield Proxy(l3=l3, transport=transport, cdn=cdn, proto=proto, enable=enable, name=name+name_postfix, params=params)


def add_config_if_not_exist(key: "ConfigEnum", val: str | int, child_id: int | None = None):
    if child_id is None:
        child_id = Child.current().id

    old_val = hconfig(key, child_id)
    if old_val is None:
        set_hconfig(key, val)


def add_column(column):
    try:
        column_type = column.type.compile(db.engine.dialect)

        db_execute(f'ALTER TABLE {column.table.name} ADD COLUMN {column.name} {column_type}', commit=True)
    except BaseException:
        pass


def alter_column(column):
    try:
        column_type = column.type.compile(db.engine.dialect)

        db_execute(f'ALTER TABLE {column.table.name} MODIFY COLUMN {column.name} {column_type}', commit=True)
    except BaseException:
        pass


def execute(query: str):
    try:
        return db_execute(query)
    except BaseException as e:
        logger.debug(f'migrating_db: {e}')
        pass


def add_new_enum_values():
    columns = [
        Proxy.l3, Proxy.proto, Proxy.cdn, Proxy.transport, User.mode, Domain.mode, BoolConfig.key, StrConfig.key
    ]
    from sqlalchemy import text
    for col in columns:
        enum_class = col.type.enum_class
        column_name = col.name
        table_name = col.table

        # Get the existing values in the enum
        existing_values = [f'{e}' if isinstance(e, ConfigEnum) else e.value for e in enum_class]

        # Get the values in the enum column in the database
        # result = db.engine.execute(f"SELECT DISTINCT `{column_name}` FROM {table_name}")
        # db_values = {row[0] for row in result}
        
        result = db.session.execute(text(f"SHOW COLUMNS FROM {table_name} LIKE :col;"), {"col": column_name}).fetchall()
        db_values = []

        for row in result:
            if "enum" in row[1]:
                db_values = row[1][5:-1].split(",")
                break
        db_values = [value.strip("'") for value in db_values]

        # Find the new values that need to be added to the enum column in the database
        new_values = set(existing_values) - set(db_values)
        old_values = set(db_values) - set(existing_values)

        if len(new_values) == 0 and len(old_values) == 0:
            continue

        # Add the new value to the enum column in the database
        # enumstr = ','.join([f"'{a}'" for a in [*existing_values, *old_values]])
        enumstr = ','.join([f"'{a}'" for a in [*existing_values]])
        expired_enumstr = ','.join([f"'{a}'" for a in [*old_values]])
        if expired_enumstr:
            db_execute(f"delete from {table_name} where `{column_name}` in ({expired_enumstr});", commit=True)
        db_execute(f"ALTER TABLE {table_name} MODIFY COLUMN `{column_name}` ENUM({enumstr});", commit=True)


def current_db_version()->int:
    try:
        if db_version:=db.session.execute(db.text("select value from str_config where `key`='db_version'")).fetchall():
            return int(db_version[0][0])
    except:
        pass
    logger.warning("db version not found")
    return 0

def is_db_latest()->bool:
    return current_db_version()==latest_db_version()

def latest_db_version():
    for ver in range(MAX_DB_VERSION, 1, -1):
        db_action = sys.modules[__name__].__dict__.get(f'_v{ver}', None)
        if db_action:
            return ver
    return 0


def upgrade_database():
    panel_root = '/opt/hiddify-manager/hiddify-panel/'
    backup_root = f"{panel_root}backup/"
    sqlite_db = f"{panel_root}hiddifypanel.db"
    if not os.path.isdir(backup_root) or len(os.listdir(backup_root)) == 0:
        if os.path.isfile(sqlite_db):
            os.rename(sqlite_db, sqlite_db + ".old")
        logger.info("no backup found...")
        return
    if os.path.isfile(sqlite_db):
        logger.info("Finding Old Version Database... importing configs from latest backup")
        newest_file = max([(f, os.path.getmtime(os.path.join(backup_root, f)))
                          for f in os.listdir(backup_root) if os.path.isfile(os.path.join(backup_root, f))], key=lambda x: x[1])[0]
        with open(f'{backup_root}{newest_file}', 'r') as f:
            logger.info(f"importing configs from {newest_file}")
            json_data = json.load(f)
            from hiddifypanel.panel import hiddify
            hiddify.set_db_from_json(json_data, set_users=True, set_domains=True, remove_domains=True, remove_users=True, set_settings=True, override_unique_id=True, set_admins=True, override_root_admin=True, override_child_unique_id=0, replace_owner_admin=True)
            db_version = int([d['value'] for d in json_data['hconfigs'] if d['key'] == "db_version"][0])
            os.rename(sqlite_db, sqlite_db + ".old")
            set_hconfig(ConfigEnum.db_version, db_version, commit=True)

        logger.info("Upgrading to the new dataset succuess.")


def _ensure_mieru_naive_relay_variants():
    """Defensive backfill for the _v114 migration.

    _v114 adds cdn=relay Proxy rows for mieru/naive so those protocols can be
    served from relay domains, not just direct ones. On installs where that
    bulk_save_objects() call partially failed (e.g. a unique/name collision
    from a manually-edited proxy table) db_version still advances, so this
    never gets retried. This just checks whether the relay rows exist and
    (re)creates only what's missing, every time init_db() runs on an
    up-to-date install. It never touches or removes existing rows.
    """
    try:
        wanted = [
            (ProxyProto.mieru, ProxyTransport.tcp, "MieruTCP", ProxyL3.custom),
            (ProxyProto.mieru, ProxyTransport.udp, "MieruUDP", ProxyL3.custom),
            (ProxyProto.naive, ProxyTransport.custom, "NaiveTLS", ProxyL3.tls_h2_h1),
            (ProxyProto.naive, ProxyTransport.custom, "NaiveQuic", ProxyL3.h3_quic),
        ]
        to_add = []
        for proto, transport, name, l3 in wanted:
            exists = Proxy.query.filter_by(proto=proto, transport=transport, cdn=ProxyCDN.relay, child_id=0).first()
            if not exists:
                to_add.append(Proxy(l3=l3, transport=transport, cdn=ProxyCDN.relay, proto=proto, enable=True, name=name))
        if to_add:
            db.session.bulk_save_objects(to_add)
            db.session.commit()
            logger.info(f"Backfilled {len(to_add)} missing mieru/naive relay proxy row(s).")
    except Exception:
        logger.exception("Failed to backfill mieru/naive relay proxy variants (non-fatal).")
        db.session.rollback()


def _ensure_default_proxy_rows():
    """get_proxy_rows_v1() is called from inside several version-gated
    migrations (_v.. functions that only ever run once). On installs where
    one of those specific migrations got interrupted (crashed mid-way,
    partial DB from a previous broken install attempt, etc.) db_version can
    end up past that point without the CDN/relay proxy rows ever actually
    being created - e.g. only 'direct' mode shows up on the Xray Configs
    page, CDN/relay never appear no matter how many domains you add.

    get_proxy_rows_v1() already only yields rows that don't exist yet, so
    it's safe to call unconditionally here on every init_db() run."""
    try:
        rows = list(get_proxy_rows_v1())
        if rows:
            db.session.bulk_save_objects(rows)
            db.session.commit()
            logger.info(f"Backfilled {len(rows)} missing default proxy row(s).")
    except Exception:
        logger.exception("Failed to backfill default proxy rows (non-fatal).")
        db.session.rollback()


def init_db():
    # set_hconfig(ConfigEnum.db_version,113) 
    # set_hconfig(ConfigEnum.db_version,110)
    db_version = current_db_version()
    if db_version == latest_db_version():
        # Backfill new settings for already-upgraded installations.
        db.create_all()
        db.session.commit()
        # Renamed/removed ConfigEnum members (e.g. a field renamed after an
        # earlier install already wrote the old name into str_config/bool_config)
        # normally only get cleaned up inside migrate(), which this fast path
        # skips entirely. Without this, a stale key left over from a previous
        # install attempt makes every future config read raise LookupError
        # forever, since db_version never drops below latest to re-trigger it.
        add_new_enum_values()
        _ensure_mieru_naive_relay_variants()
        _ensure_default_proxy_rows()
        return
    
    db.create_all()
    
    # temporary fix
    add_column(Child.mode)
    add_column(Child.name)

    from flask import g
    cache.invalidate_all_cached_functions()
    migrate(db_version)

    child = Child.by_id(0)
    if child is None:
        tmp_uuid = str(uuid.uuid4())
        db.session.add(Child(id=0, unique_id=tmp_uuid, name="Root"))
        db.session.commit()
        db_execute("update child set id=0 where unique_id=:u", u=tmp_uuid, commit=True)
        child = Child.by_id(0)  

    child.mode = ChildMode.virtual
    # if db_version < 69:
    #     _v70(0)

    db.session.commit()

    for child in Child.query.filter(Child.mode == ChildMode.virtual).all():
        g.child = child
        db_version = int(hconfig(ConfigEnum.db_version, child.id) or 0)
        start_version = db_version

        for ver in range(1, MAX_DB_VERSION):
            if ver <= db_version:
                continue

            db_action = sys.modules[__name__].__dict__.get(f'_v{ver}', None)
            if not db_action or (start_version == 0 and ver == 10):
                continue

            logger.info(f"Updating db from version {db_version} for node {child.id}")

            if ver < 70:
                if child.id != 0:
                    continue
                db_action()
            else:
                db_action(child.id)

            Events.db_init_event.notify(db_version=db_version)
            logger.info(f"Updated successfuly db from version {db_version} to {ver}")

            db_version = ver
            db.session.commit()
            set_hconfig(ConfigEnum.db_version, db_version, child_id=child.id, commit=False)

        db.session.commit()
    g.child = Child.by_id(0)
    return BoolConfig.query.all()


def migrate(db_version):
    for table_name, table_obj in db.metadata.tables.items():
        for column in table_obj.columns:
            add_column(column)
    Events.db_prehook.notify()
    if db_version < 100:
        execute('update str_config set `key`="xhttp_enable" where `key`="splithttp_enable";')
        execute('update str_config set `key`="path_xhttp" where `key`="path_splithttp";')
        execute("UPDATE proxy SET transport = 'xhttp' WHERE transport = 'splithttp';")
    if db_version < 97:
        execute('ALTER TABLE str_config MODIFY value VARCHAR(3072);')
    if db_version < 82:
        execute('ALTER TABLE child DROP INDEX `name`;')
    if db_version < 77:
        execute('ALTER TABLE user_detail DROP COLUMN connected_ips;')
        execute('update user_detail set connected_devices="" where connected_devices IS NULL')

    if db_version < 70:
        execute('CREATE INDEX date ON daily_usage (date);')
        execute('CREATE INDEX username ON user (username);')
        execute('CREATE INDEX username ON admin_user (username);')
        execute('CREATE INDEX telegram_id ON user (telegram_id);')
        execute('CREATE INDEX telegram_id ON admin_user (telegram_id);')

        execute('ALTER TABLE proxy DROP INDEX `name`;')

        execute("ALTER TABLE user MODIFY COLUMN telegram_id BIGINT;")
        execute("ALTER TABLE admin_user MODIFY COLUMN telegram_id BIGINT;")

        # aaa
        # # add_column(UserDetail.connected_devices)
        # add_column(Child.mode)
        # add_column(Child.name)
        # add_column(User.lang)
        # add_column(AdminUser.lang)
        # add_column(User.username)
        # add_column(User.password)
        # add_column(AdminUser.username)
        # add_column(AdminUser.password)
        # add_column(User.wg_pk)
        # add_column(User.wg_pub)
        # add_column(User.wg_psk)

        # add_column(Domain.extra_params)

    if db_version < 52:
        execute(f'update domain set mode="sub_link_only", sub_link_only=false where sub_link_only = true or mode=1  or mode="1"')
        execute(f'update domain set mode="direct", sub_link_only=false where mode=0  or mode="0"')
        execute(f'update proxy set transport="WS" where transport = "ws"')
        execute(f'update admin_user set mode="agent" where mode = "slave"')
        execute(f'update admin_user set mode="super_admin" where id=1')
        execute(f'DELETE from proxy where transport = "h1"')
        # add_column(Domain.grpc)
        # add_column(ParentDomain.alias)
        # add_column(User.ed25519_private_key)
        # add_column(User.ed25519_public_key)
        # add_column(User.start_date)
        # add_column(User.package_days)
        # add_column(User.telegram_id)
        # add_column(Child.unique_id)
        # add_column(Domain.alias)
        # add_column(Domain.sub_link_only)
        # add_column(Domain.child_id)
        # add_column(Proxy.child_id)
        # add_column(User.added_by)
        # add_column(User.max_ips)
        # add_column(AdminUser.parent_admin_id)
        # add_column(AdminUser.can_add_admin)
        # add_column(AdminUser.max_active_users)
        # add_column(AdminUser.max_users)
        # add_column(BoolConfig.child_id)
        # add_column(StrConfig.child_id)
        # add_column(DailyUsage.admin_id)
        # add_column(DailyUsage.child_id)
        # add_column(User.monthly)
        # add_column(User.enable)
        # add_column(Domain.cdn_ip)
        # add_column(Domain.servernames)
        # add_column(User.lang)

        if len(Domain.query.all()) != 0 and BoolConfig.query.count() == 0:
            execute(f'DROP TABLE bool_config')
            execute(f'ALTER TABLE bool_config_old RENAME TO bool_config')
        if len(Domain.query.all()) != 0 and StrConfig.query.count() == 0:
            execute(f'DROP TABLE str_config')
            execute(f'ALTER TABLE str_config_old RENAME TO str_config')

        execute('ALTER TABLE user RENAME COLUMN monthly_usage_limit_GB TO usage_limit_GB')
        execute(f'update admin_user set parent_admin_id=1 where parent_admin_id is NULL and 1!=id')
        execute(f'update admin_user set max_users=100,max_active_users=100 where max_users is NULL')
        execute(f'update dailyusage set child_id=0 where child_id is NULL')
        execute(f'update dailyusage set admin_id=1 where admin_id is NULL')
        execute(f'update dailyusage set admin_id=1 where admin_id = 0')
        execute(f'update user set added_by=1 where added_by = 1')
        execute(f'update user set enable=True, mode="no_reset" where enable is NULL')
        execute(f'update user set enable=False, mode="no_reset" where mode = "disable"')
        execute(f'update user set added_by=1 where added_by is NULL')
        execute(f'update user set max_ips=10000 where max_ips is NULL')
        execute(f'update str_config set child_id=0 where child_id is NULL')
        execute(f'update bool_config set child_id=0 where child_id is NULL')
        execute(f'update domain set child_id=0 where child_id is NULL')
        execute(f'update domain set sub_link_only=False where sub_link_only is NULL')
        execute(f'update proxy set child_id=0 where child_id is NULL')

    add_new_enum_values()

    AdminUser.get_super_admin()  # to create super admin if not exist

    upgrade_database()
    db.session.commit()

