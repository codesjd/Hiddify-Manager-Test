import json
import ipaddress
from urllib.parse import urlparse
from flask_classful import FlaskView, route
from flask import render_template, request, redirect, g
from hiddifypanel.hutils.flask import hurl_for
from hiddifypanel.auth import login_required
from flask import current_app as app
from flask_babel import gettext as _


from hiddifypanel import hutils
from hiddifypanel.models import *
from hiddifypanel.panel import hiddify, usage
from hiddifypanel.panel.run_commander import commander, Command


class Actions(FlaskView):

    @login_required(roles={Role.super_admin})
    def index(self):
        return render_template('index.html')



    @login_required(roles={Role.super_admin})
    @route('apply_configs', methods=['POST'])
    def apply_configs(self):
        return self.reinstall(False)

    @login_required(roles={Role.super_admin})
    @route('set_language', methods=['POST'])
    def set_language(self):
        # Admin language used to only be reachable from deep inside Settings
        # (a whole category for one field) - moved to the topbar since it's
        # something an admin picks once and rarely needs the rest of that
        # page for. Same set_hconfig+refresh sequence QuickSetup's own
        # language step uses.
        import flask_babel
        lang = request.form.get('lang', '')
        if lang in [l.value for l in Lang]:
            set_hconfig(ConfigEnum.lang, lang)
            set_hconfig(ConfigEnum.admin_lang, lang)
            flask_babel.refresh()
        # request.referrer is attacker-controlled the same way a ?redirect=
        # query param is (a crafted Referer header on a cross-site POST) -
        # only redirect back to it if it's actually a local, path-relative
        # target, otherwise this is an open redirect after a state-changing
        # admin POST.
        referrer = request.referrer
        if referrer and not hutils.flask.is_safe_redirect_target(urlparse(referrer).path):
            referrer = None
        return redirect(referrer or hurl_for('admin.Dashboard:index'))

    @route('reset', methods=['POST'])
    @login_required(roles={Role.super_admin})
    def reset(self):
        return self.reset2()

    @login_required(roles={Role.super_admin})
    def reset2(self):
        res = render_template("result.html",
                              out_type="info",
                              out_msg="",
                              log_file_url=get_log_api_url(),
                              log_file='restart.log',
                              show_success=True,
                              domains=get_domains())

        # run restart.sh
        commander(Command.restart_services)

        return res

    @login_required(roles={Role.admin})
    def all_public_ports(self):
        tcp_ports={80,443}
        udp_ports={443,}
        if hconfig(ConfigEnum.wireguard_enable):
            udp_ports.add(hconfig(ConfigEnum.wireguard_port))
        if hconfig(ConfigEnum.shadowsocks2022_enable) and (p:=hconfig(ConfigEnum.shadowsocks2022_port)):
            udp_ports.add(p)
            tcp_ports.add(p)
        if hconfig(ConfigEnum.mieru_enable):
            for p in hconfig(ConfigEnum.mieru_tcp_ports).split(","):
                tcp_ports.add(p)
            for p in hconfig(ConfigEnum.mieru_udp_ports).split(","):
                udp_ports.add(p)
        if hconfig(ConfigEnum.ssh_server_enable):
            tcp_ports.add(hconfig(ConfigEnum.ssh_server_port))
        if hconfig(ConfigEnum.l2tp_enable):
            # L2TP/IPsec: IKE (500), NAT-T (4500) and the L2TP tunnel (1701),
            # all UDP. ESP (IP proto 50) rides inside UDP/4500 for the NAT'd
            # clients this is aimed at, so no extra rule is needed for it.
            for p in (500, 4500, 1701):
                udp_ports.add(p)

        for d in Domain.query.all():
            udp_ports.add(d.internal_port_tuic)
            udp_ports.add(d.internal_port_naive)
            udp_ports.add(d.internal_port_hysteria2)
            # xdns/xicmp (finalmask) ride mKCP, which is UDP-based, same as
            # every other finalmask/QUIC protocol above.
            udp_ports.add(d.internal_port_xdns)
            udp_ports.add(d.internal_port_xicmp)
            # AnyTLS is TCP-based (unlike its QUIC/UDP siblings above).
            tcp_ports.add(d.internal_port_anytls)
            if d.tls_port:
                tcp_ports.add(d.tls_port)
                udp_ports.add(d.tls_port)
            if d.http_port:
                tcp_ports.add(d.http_port)
            # tcp+vision REALITY now binds directly instead of only being
            # reachable via HAProxy on 443 (see get_port() in
            # hutils/proxy/shared.py) - needs its own firewall opening too.
            if d.mode == DomainType.special_reality_tcp:
                tcp_ports.add(d.internal_port_special)

        def to_int(ports):
            r=set()
            for p in ports:
                try:
                    if ip:=int(p):
                        r.add(ip)
                except:
                    pass
            return list(r)
        return {"tcp":to_int(tcp_ports),"udp":to_int(udp_ports)}
    

    @login_required(roles={Role.super_admin})
    @route('reinstall', methods=['POST'])
    def reinstall(self, complete_install=True, domain_changed=False):
        return self.reinstall2(complete_install, domain_changed)
    def get_domain_ip(self,domain:str):
        return "<br>".join([str(ip) for ip in hutils.network.get_domain_ips(domain)])
    @login_required(roles={Role.super_admin})
    def reinstall2(self, complete_install=True, domain_changed=False):
        if int(hconfig(ConfigEnum.db_version)) < 9:
            return ("Please update your panel before this action.")
        if hutils.node.is_child():
            hutils.node.run_node_op_in_bg(hutils.node.child.sync_with_parent)

        domain_changed = request.args.get("domain_changed", str(domain_changed)).lower() == "true"
        complete_install = request.args.get("complete_install", str(complete_install)).lower() == "true"
        if not complete_install and hiddify.amneziawg_needs_full_install():
            complete_install = True
            hutils.flask.flash((_('AmneziaWG needs a one-time setup - running a full install instead of a quick apply.')), 'info')
        if not complete_install and hiddify.l2tp_needs_full_install():
            complete_install = True
            hutils.flask.flash((_('L2TP/IPsec needs a one-time setup - running a full install instead of a quick apply.')), 'info')
        if not complete_install and hiddify.core_needs_full_install():
            complete_install = True
            hutils.flask.flash((_('The selected core needs a one-time setup - running a full install instead of a quick apply.')), 'info')
        if domain_changed:
            hutils.flask.flash((_('domain.changed_in_domain_warning')), 'info')
        # hutils.flask.flash(f'complete_install={complete_install} domain_changed={domain_changed} ', 'info')
        # return render_template("result.html")
        # hiddify.add_temporary_access()
        domains = Domain.get_domains()
        # Quick Setup stores the user's preferred domain type in session; use it for redirect
        from flask import session as flask_session
        preferred_type = flask_session.pop('qs_preferred_domain', None) or request.args.get('preferred_domain', None)
        
        def is_ip_or_auto_ip_domain(host):
            host = (host or '').lower()
            if host.endswith(('.sslip.io', '.nip.io')):
                return True
            try:
                ipaddress.ip_address(host)
                return True
            except ValueError:
                return False

        redirect_host = hutils.network.get_ip_str(4)
        
        if preferred_type == 'cdn':
            cdn_domains = [d for d in domains if d.mode in ['cdn', 'auto_cdn_ip']]
            if cdn_domains:
                redirect_host = cdn_domains[0].domain
        elif preferred_type == 'direct':
            direct_domains = [d for d in domains if d.mode == 'direct']
            direct_domain = next((d for d in direct_domains if not is_ip_or_auto_ip_domain(d.domain)), None)
            if direct_domain:
                redirect_host = direct_domain.domain
        elif preferred_type == 'ip':
            # Explicit "redirect to IP" choice (e.g. Quick Setup, when the
            # domain's DNS isn't pointed at this server yet) - redirect_host
            # already defaults to the IP above, so this is a no-op, but it
            # must stay its own branch. Falling through to the "no
            # preference" else below would let the "stay on current host"
            # check silently override an explicit IP choice back onto
            # whatever domain the admin happens to be browsing from right
            # now - including the one they just added in this same step.
            pass
        else:
            # If no preference is specified (e.g. standard Apply Configs button),
            # stay on the same host the admin is currently using, if valid.
            current_host = request.host.split(':')[0]
            if any(d.domain == current_host for d in domains):
                redirect_host = current_host

        redirect_url = hiddify.get_admin_login_link(redirect_host)

        resp = render_template("result.html",
                               out_type="info",
                               out_msg=_("admin.waiting_for_update"),
                               redirect_url=redirect_url,
                               log_file_url=get_log_api_url(),
                               log_file="0-install.log",
                               show_success=True,
                               domains=get_domains())

        # subprocess.Popen(f"sudo {config['HIDDIFY_CONFIG_PATH']}/{file} --no-gui".split(" "), cwd=f"{config['HIDDIFY_CONFIG_PATH']}", start_new_session=True)

        # run install.sh or apply_configs.sh
        if complete_install:
            # A full install/reinstall always touches everything, regardless
            # of any narrower scope tracked since the last apply.
            commander(Command.install)
        else:
            # None (unknown/unmapped change since the last apply) makes
            # commander() omit --subsystems entirely, which is the exact
            # same command line as before this feature existed - full width,
            # not "touch nothing".
            commander(Command.apply, subsystems=hutils.apply_scope.get_pending_subsystems())
        hutils.apply_scope.clear_pending_subsystems()

        # import time
        # time.sleep(1)
        return resp

    @login_required(roles={Role.super_admin})
    def change_reality_keys(self):
        key = hutils.crypto.generate_x25519_keys()
        set_hconfig(ConfigEnum.reality_private_key, key['private_key'])
        set_hconfig(ConfigEnum.reality_public_key, key['public_key'])
        # Best-effort: the migration that first tries this
        # (init_db.py's _v150) can silently skip if the xray binary wasn't
        # downloaded yet at that point in bootstrap - this button runs well
        # after installation, so it's a reliable place to actually get it
        # populated. Still best-effort (returns None on any failure) since
        # PQ signing is optional hardening, never required for REALITY to
        # work.
        mldsa65_keys = hutils.crypto.generate_mldsa65_keys()
        if mldsa65_keys:
            set_hconfig(ConfigEnum.reality_mldsa65_seed, mldsa65_keys['seed'])
            set_hconfig(ConfigEnum.reality_mldsa65_verify, mldsa65_keys['verify'])
        hutils.apply_scope.mark_dirty(hutils.apply_scope.CORE_ONLY_SUBSYSTEMS)
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
        return redirect(hurl_for('admin.SettingAdmin:index'))

    @ login_required(roles={Role.super_admin})
    def status(self):
        # run status.sh
        commander(Command.status)
        return render_template("result.html",
                               out_type="info",
                               out_msg=_("see the log in the bellow screen"),
                               log_file_url=get_log_api_url(),
                               log_file="status.log",
                               show_success=False,
                               domains=get_domains())

    @ route('update', methods=['POST'])
    @ login_required(roles={Role.super_admin})
    def update(self):
        return self.update2()

    @login_required(roles={Role.super_admin})
    def update2(self):
        # hiddify.add_temporary_access()
        # run update.sh

        commander(Command.update)

        return render_template("result.html",
                               out_type="success",
                               out_msg=_("Success! Please wait around 5 minutes to make sure everything is updated."),
                               show_success=True,
                               log_file_url=get_log_api_url(),
                               log_file="update.log",
                               domains=get_domains())

    @login_required(roles={Role.super_admin})
    def get_some_random_reality_friendly_domain(self):
        test_domain = request.args.get("test_domain")
        import ping3
        from hiddifypanel.hutils.network.auto_ip_selector import IPASN, IPCOUNTRY
        ipv4 = hutils.network.get_ip_str(4)
        server_country = (IPCOUNTRY.get(ipv4) or {}).get('country', {}).get('iso_code', 'unknown')
        server_asn = (IPASN.get(ipv4) or {}).get('autonomous_system_organization', 'unknown')
        res = "<table><tr><th>Domain</th><th>IP</th><th>Country</th><th>ASN</th><th>Ping (ms)</th><th>TCP ping (ms)</th></tr>"
        res += f"<tr><td>Your Server</td><td>{ipv4}</td><td>{server_country}</td><td>{server_asn}</td><td>0</td></tr>"
        import time
        start = time.time()
        for d in [test_domain, *hutils.network.get_random_domains(30)]:
            if not d:
                continue
            if time.time() - start > 20:
                break

            tcp_ping = hutils.network.is_domain_reality_friendly(d)
            if tcp_ping:
                dip = str(hutils.network.get_domain_ip(d))
                dip_country = (IPCOUNTRY.get(dip) or {}).get('country', {}).get('iso_code', 'unknown')
                if dip_country == "IR":
                    continue
                response_time = -1
                try:
                    response_time = ping3.ping(d, unit='ms')
                    if response_time:
                        response_time = int(response_time)
                except BaseException:
                    pass
                dip_asn = (IPASN.get(dip) or {}).get('autonomous_system_organization', 'unknown')
                res += f"<tr><td>{d}</td><td>{dip}</td><td>{dip_country}</td><td>{dip_asn}</td><td>{response_time}</td><td>{tcp_ping}<td></tr>"

        return res + "</table>"

    @ login_required(roles={Role.super_admin})
    def update_usage(self):
        color = 'white' if g.darkmode else 'black'
        return render_template("result.html",
                               out_type="info",
                               out_msg=f'<pre class="ltr" style="color:{color};">{json.dumps(usage.update_local_usage(),indent=2)}</pre>',
                               log_file_url=None
                               )


def get_log_api_url():
    return f'/{g.get("new_proxy_path",g.proxy_path)}/api/v2/admin/log/'


def get_domains():
    return [str(d.domain).replace("*", hutils.random.get_random_string(3, 6)) for d in Domain.get_domains(always_add_all_domains=True, always_add_ip=False)]
