import ipaddress
import random
import uuid
from typing import Literal
from hiddifypanel.auth import login_required, current_account

from hiddifypanel.hutils.flask import hurl_for
from hiddifypanel.models import *
import re
from flask import g, request  # type: ignore
from markupsafe import Markup

from flask_babel import gettext as __
from flask_babel import lazy_gettext as _
from hiddifypanel.panel.run_commander import Command, commander
from hiddifypanel.database import db
import wtforms as wtf
from wtforms.validators import Regexp, ValidationError, Optional, NumberRange
from sqlalchemy import inspect as sa_inspect

from hiddifypanel.models import *
from hiddifypanel.panel import hiddify, custom_widgets
from .adminlte import AdminLTEModelView
from hiddifypanel import hutils

from loguru import logger
from flask import current_app
from pydantic import BaseModel, Field, ConfigDict
# Define a custom field type for the related domains


# class ConfigDomainsField(SelectField):
#     def __init__(self, label=None, validators=None,*args, **kwargs):
#         kwargs.pop("allow_blank")
#         super().__init__(label, validators,*args, **kwargs)
#         self.choices=[(d.id,d.domain) for d in Doamin.query.filter(Domain.sub_link_only!=True).all()]

class DnsTT(BaseModel):
    # extra='allow': this JSON field (Domain.extra_params) is also now used
    # as a generic per-domain override (see apply_domain_overrides() in
    # hutils/proxy/shared.py) - e.g. put {"fingerprint": "firefox",
    # "hysteria_obfs_password": "..."} on a specific relay/CDN domain to
    # override just that domain's transport/security params without
    # touching the global config. Without extra='allow', pydantic silently
    # dropped any key that wasn't one of the dnstt-specific fields below.
    #
    # Also doubles as the per-domain override schema for xdns-mode domains
    # (xdns_resolvers below) - same reasoning, this mode has no dedicated DB
    # column either.
    model_config = ConfigDict(extra='allow')

    mtu: int = Field(0, description="dnstt: maximum size of DNS responses (0-> default 1232). xdns: mKCP MTU for this domain's Xray inbound (0-> default 500) - lower this if xdns handshakes but data doesn't actually flow, which usually means the real path's usable payload per round-trip is smaller than the current MTU.")

    keepalive: int = Field(0, description='keepalive ping interval in seconds; must be less than idle-timeout (0-> use default 2s)', ge=0,le=100)
    idle_timeout:int = Field(0, description='session idle timeout in seconds; tears down sessions with no data within this period (0-> use default 10 seconds)', ge=0,le=100)
    clientid_size:int=Field(0, description="client ID size in bytes (ignored when dnstt_compat is true) (0-> use default 2)")
    dnstt_compat:bool=Field(False,description="use original dnstt wire format (8-byte ClientID, padding prefixes)")
    record_type:Literal["","txt", "cname", "a", "aaaa", "mx", "ns", "srv"] =Field("",description='DNS record type for downstream data (txt, cname, a, aaaa, mx, ns, srv) (""->default "txt")')
    max_qname_len: int= Field(0, description='maximum total QNAME length in wire format (253 per RFC 1035) (0->default 101)')
    open_stream_timeout: int = Field(0, description='timeout for opening an smux stream (e.g. 500ms, 3s) (0->default "10s")')

    # xdns mode only (Xray-core finalmask, XTLS/Xray-core#5633): comma-separated
    # "ip:port" public DNS resolvers this domain's clients should route their
    # DNS-tunneled queries through. Empty -> falls back to the server-wide
    # xdns_resolvers hconfig default.
    xdns_resolvers: str = Field("", description='comma-separated "ip:port" resolvers for this xdns domain ("" -> use the server default)')
    # No admin-facing xicmp knobs at all: the server always needs a real raw
    # ICMP socket (dgram=false - Xray already runs as root, so CAP_NET_RAW
    # is never actually a problem) and the client link/config always asks
    # for the unprivileged datagram socket (dgram=true, Xray's own
    # recommended default for end-user clients that don't run elevated).
    # Both sides are hardcoded (xray/configs/05_inbounds_06_xicmp.json.j2,
    # xrayjson.py's add_mask_finalmask_stream()) rather than exposed here,
    # since there's no scenario where either side legitimately wants the
    # other value. There's also no per-domain "id"/echo-ID concept in
    # Xray-core's current xicmp finalmask schema (v26.6.1+) - client
    # demuxing is done via an embedded client ID in the ICMP payload
    # instead, not anything configured in JSON.


class DomainAdmin(AdminLTEModelView):
    # edit_modal = False
    # create_modal = False
    column_hide_backrefs = False

    list_template = 'model/domain_list.html'
    # edit_modal = True
    form_overrides = {'mode': custom_widgets.EnumSelectField,
                    # "extra_params":custom_widgets.CustomJSONField(DnsTT, "Extra Params")
                    }
    form_extra_fields = {
        "extra_params": custom_widgets.CustomJSONField(DnsTT, "Extra Params / Per-Domain Override"),
        # xicmp needs no DNS/NS setup (see the mode description below), so
        # the server's own IP works as an xicmp target exactly as well as
        # any other domain would - this just automates creating/removing
        # the companion Domain(mode=xicmp) row that actually makes it one,
        # instead of requiring a second, manually-created "Add Domain" for
        # the identical domain string. See after_model_change() below.
        "also_enable_xicmp": wtf.BooleanField(_("Also enable xICMP on this domain")),
    }
    form_widget_args = {
        'description': {
            'rows': 100,
            'style': 'font-family: monospace; direction:ltr'
        },
        
    }
    column_descriptions = dict(
        domain=_("domain.description"),
        mode=_("Direct mode means you want to use your server directly (for usual use), CDN means that you use your server on behind of a CDN provider. "
               "Fake mode defaults to your server's own direct IP unless you set a different IP/domain in the 'cdn_ip' field below - set it explicitly if you don't want this domain tied to your direct settings. "
               "dnstt mode is DNS tunneling: it does NOT work like the other modes (no CDN/A-record setup). You must delegate an NS record for this subdomain to your server's IP first, or it will never connect. "
               "xdns mode tunnels traffic inside DNS queries (Xray-core's xdns finalmask) - same NS delegation requirement as dnstt, and gets its own isolated inbound so it never affects your other connection modes. "
               "xicmp mode tunnels traffic inside ICMP (ping) packets (Xray-core's xicmp finalmask) - no DNS/NS setup needed, but the server needs CAP_NET_RAW to open a raw ICMP socket."),
        also_enable_xicmp=_("xICMP needs no DNS/NS setup, so this domain (including a bare server IP) can serve xICMP at the same time as its main mode. Creates/removes a matching xICMP entry for you - equivalent to adding it separately with the same domain value."),
        cdn_ip=_("config.cdn_forced_host.description"),
        show_domains=_('domain.show_domains_description'),
        alias=_('The name shown in the configs for this domain.'),
        servernames=_('config.reality_server_names.description'),
        sub_link_only=_('This can be used for giving your users a permanent non blockable links.'),
        grpc=_('grpc-proxy.description'),
        download_domain=_('download_domain.description'),
        resolve_ip=_("domain.resolveip.description"),
        http_port=_("Plain-HTTP port for this domain. Leave empty to use the default port 80. A custom port is exclusive to this domain - no other domain can use it, and this domain won't be reachable on 80 anymore."),
        tls_port=_("TLS port for this domain. Leave empty to use the default port 443. A custom port is exclusive to this domain - no other domain can use it, and this domain won't be reachable on 443 anymore."),
        reality_port=_("REALITY direct port for this domain (special_reality_* modes only). Auto-generated the first time this domain is saved as a REALITY mode if left empty; edit it to set your own."),
        reality_private_key=_("REALITY private key for this domain. Auto-generated the first time this domain is saved as a REALITY mode if left empty; edit it to set your own."),
        reality_public_key=_("REALITY public key for this domain, matching the private key above. Auto-generated the first time this domain is saved as a REALITY mode if left empty; edit it to set your own."),
        reality_short_id=_("REALITY short ID for this domain. Auto-generated the first time this domain is saved as a REALITY mode if left empty; edit it to set your own."),
        extra_params=_("The dnstt-specific fields below are pre-filled with defaults. You can also add ANY other key here "
                        "(e.g. \"fingerprint\": \"firefox\", \"hysteria_obfs_password\": \"...\", \"alpn\": \"h2\") to override "
                        "just THIS domain's transport/security settings instead of the global config every domain shares."),
        
    )
    # create_modal = True
    can_export = False
    form_widget_args = {
        # data-role is intentionally left blank here: show_domains/download_domain
        # are upgraded client-side by update_hiddify_ui() in flaskadmin-layout.html
        # (a $.multipleSelect() call keyed on these exact element ids). Setting
        # data-role="select2" makes flask-admin's own form.js *also* initialize
        # select2 on the same <select>, and the two widgets fighting over one
        # element is what breaks the dropdown (empty/blank results on open).
        'show_domains': {'class': 'form-control ltr', 'data-role': u''},
        'download_domain': {'class': 'form-control ltr', 'data-role': u''}
    }

    form_args = {
        'mode': {'enum': DomainType},
        
        'show_domains': {
            'query_factory': lambda: Domain.query.filter(     Domain.sub_link_only == False),
        },
        'domain': {
            'validators': [
                Regexp(r'^(\*\.)?([A-Za-z0-9\-\.]+\.[a-zA-Z]{2,})$|^$|^(\d{1,3}\.){3}\d{1,3}$|^([0-9a-fA-F]{1,4}:){1,7}(:|[0-9a-fA-F]{1,4})$',message=__("Should be a valid domain"))]},
        "cdn_ip": {
            'validators': [
                Regexp(r"(((((25[0-5]|(2[0-4]|1\d|[1-9]|)\d).){3}(25[0-5]|(2[0-4]|1\d|[1-9]|)\d))|^([A-Za-z0-9\-\.]+\.[a-zA-Z]{2,}))[ \t\n,;]*\w{3}[ \t\n,;]*)*",message=__("Invalid IP or domain"))]},
        "servernames": {
            'validators': [
                Regexp(r"^([\w-]+\.)+[\w-]+(,\s*([\w-]+\.)+[\w-]+)*$",re.IGNORECASE,_("Invalid REALITY hostnames"))]},
        "http_port": {
            'validators': [Optional(), NumberRange(min=1, max=65535, message=__("Invalid port"))]},
        "tls_port": {
            'validators': [Optional(), NumberRange(min=1, max=65535, message=__("Invalid port"))]},
        "reality_port": {
            'validators': [Optional(), NumberRange(min=1, max=65535, message=__("Invalid port"))]}}
    column_list = ["domain", "alias", "mode",  "show_domains"]
    column_editable_list = ["alias"]
    # column_filters=["domain","mode"]
    # form_excluded_columns=['work_with']
    column_searchable_list = ["domain", "mode"]
    column_labels = {
        "domain": _("domain.domain"),
        'also_enable_xicmp': _('Also enable xICMP on this domain'),
        'sub_link_only': _('Only for sublink?'),
        "mode": _("domain.mode"),
        "cdn_ip": _("config.cdn_forced_host.label"),
        'domain_ip': _('domain.ip'),
        'servernames': _('config.reality_server_names.label'),
        'show_domains': _('Show Domains'),
        'alias': _('Alias'),
        'grpc': _('gRPC'),
        "download_domain":_('download_domain.label'),
        'resolve_ip':_("domain.resolveip.label"),
        'http_port': _('HTTP Port'),
        'tls_port': _('TLS Port'),
        'reality_port': _('REALITY Port'),
        'reality_private_key': _('REALITY Private Key'),
        'reality_public_key': _('REALITY Public Key'),
        'reality_short_id': _('REALITY Short ID'),
    }

    form_columns = ['mode', 'domain', 'also_enable_xicmp', 'alias', 'servernames', 'cdn_ip', 'resolve_ip', 'http_port', 'tls_port',
                    'reality_port', 'reality_private_key', 'reality_public_key', 'reality_short_id',
                    'show_domains', 'download_domain', "extra_params"]
    
    def _domain_admin_link(view, context, model, name):
        if hiddify.is_fake_domain(model):
            return Markup(hutils.flask.hf_chip(model.domain))
        resolve_url = hurl_for('admin.Actions:get_domain_ip', domain=model.domain)
        resolve_title = _("Resolve IP")
        return Markup(
            hutils.flask.hf_chip(model.domain) +
            f' <a href="{resolve_url}" title="{resolve_title}"><i class="fa-solid fa-dharmachakra"></i></a>')

    def _domain_ip(view, context, model, name):
        dips = hutils.network.get_domain_ips_cached(model.domain)
        # The get_domain_ip function uses the socket library, which relies on the system DNS resolver. So it may sometimes use cached data, which is not desirable
        # if not dips:
        #     dip = hutils.network.resolve_domain_with_api(model.domain)
        myips = set(hutils.network.get_ips())
        all_res = ""
        for dip in dips:
            if dip in myips and model.mode in [DomainType.direct, DomainType.sub_link_only]:
                badge_type = ''
            elif dip and dip not in myips and model.mode != DomainType.direct:
                badge_type = 'warning'
            else:
                badge_type = 'danger'
            res = f'<span class="badge badge-{badge_type}">{dip}</span>'
            if model.sub_link_only:
                res += f'<span class="badge badge-success">{_("SubLink")}</span>'
            all_res += res
        return Markup(all_res)

    def _show_domains_formater(view, context, model, name):
        if hiddify.is_fake_domain(model):
            return ""
        if not len(model.show_domains):
            return _("All")
        else:
            return Markup(" ".join([hiddify.get_domain_btn_link(d) for d in model.show_domains]))

    column_formatters = {
        # 'domain_ip': _domain_ip,
        'domain': _domain_admin_link,
        'show_domains': _show_domains_formater
    }

    def search_placeholder(self):
        return f"{_('search')} {_('domain.domain')} {_('domain.mode')}"

    def create_form(self, obj=None):
        # Pre-fill the REALITY fields with fresh, ready-to-use values on a
        # brand new Add Domain page (GET only - a POST re-render after a
        # validation error already has the admin's just-submitted values in
        # form.data, which must not be clobbered). They stay hidden (see
        # flaskadmin-layout.html's hide_domain_elements()) unless/until the
        # admin actually picks a REALITY mode, and on_model_change below
        # blanks them right back out if the domain isn't saved as one - so
        # this is purely a preview for whoever does pick a REALITY mode,
        # not something that can leak onto a non-REALITY domain.
        form = super().create_form(obj)
        if request.method == 'GET':
            if not form.reality_port.data:
                form.reality_port.data = hutils.random.get_random_unused_port()
            if not form.reality_private_key.data or not form.reality_public_key.data:
                keys = hutils.crypto.generate_x25519_keys()
                form.reality_private_key.data = keys['private_key']
                form.reality_public_key.data = keys['public_key']
            if not form.reality_short_id.data:
                form.reality_short_id.data = uuid.uuid4().hex[0:random.randint(1, 8) * 2]
        return form

    def edit_form(self, obj=None):
        # also_enable_xicmp isn't a model column - it's a plain checkbox
        # (see form_extra_fields), so it has no obj value to prefill from
        # automatically the way every real column does. Reflect whether a
        # companion xICMP row already exists for this domain string, or
        # editing-and-resaving without touching the checkbox would read as
        # "no" and after_model_change() below would delete it.
        form = super().edit_form(obj)
        if request.method == 'GET' and obj is not None:
            form.also_enable_xicmp.data = Domain.query.filter(
                Domain.domain == obj.domain,
                Domain.mode == DomainType.xicmp,
                Domain.child_id == obj.child_id,
                Domain.id != obj.id,
            ).first() is not None
        return form

    # def on_form_prefill(self, form, id):
        # Get the Domain object being edited
        # domain = self.session.query(Domain).get(id)

        # Pre-select the related domains in the checkbox list
        # form.show_domains = [d.id for d in Domain.query.all()]

    # TODO: refactor this function
    def on_model_change(self, form, model, is_created):
        # Sanitize domain input
        model.domain = (model.domain or '').lower().strip()
        # A domain's cert can be mid-issuance right when it's added/edited
        # (ACME runs async, after this request). Busting any stale pin here
        # means the next subscription request re-fetches instead of serving
        # whatever cert happened to be live at the moment this domain was
        # first touched for up to 300s afterward - see get_pinned_cert_sha256.
        if model.domain:
            hutils.network.invalidate_pinned_cert_cache(model.domain)
        if model.download_domain and model.domain==model.download_domain.domain:
            model.download_domain_id=None
            model.download_domain=None
        # REALITY's port/keys/short id are meaningless (and hidden - see
        # flaskadmin-layout.html) for every other mode. Also guards against
        # create_form()'s GET-time preview values above ending up saved onto
        # a non-REALITY domain if the admin never actually switches the
        # Mode dropdown away from its hidden pre-filled state.
        if "reality" not in model.mode:
            model.reality_port = None
            model.reality_private_key = None
            model.reality_public_key = None
            model.reality_short_id = None
        # Basic validation
        if model.domain == '' and model.mode != DomainType.fake:
            raise ValidationError(_("domain.empty.allowed_for_fake_only"))

        self._validate_not_used_before(model,is_created)
        self._validate_port_exclusivity(model)
        ipv4_list = hutils.network.get_ips(4)
        ipv6_list = hutils.network.get_ips(6)
        server_ips = [*ipv4_list, *ipv6_list]

        if not server_ips:
            raise ValidationError(_("Couldn't find your ip addresses"))

        # Validate domain based on mode
        if "*" in model.domain and model.mode not in [DomainType.cdn, DomainType.auto_cdn_ip]:
            raise ValidationError(_("Domain can not be resolved! there is a problem in your domain"))

        cloudflare_updated=self._update_cloudflare(model, ipv4_list,ipv6_list)
        
        if not cloudflare_updated:
            self._validate_domain_ips(model, server_ips)

        # Handle CDN IP settings
        if  model.mode == DomainType.direct and model.cdn_ip:
            model.cdn_ip = ""
            raise ValidationError(_("Specifying CDN IP is only valid for CDN mode"))
            
        if model.mode == DomainType.fake and not model.cdn_ip:
            model.cdn_ip = str(server_ips[0])
            
        if model.cdn_ip:
            try:
                hutils.network.auto_ip_selector.get_clean_ip(str(model.cdn_ip))
            except Exception:
                raise ValidationError(_("Error in auto cdn format"))
                    
        # Update show domains
        if len(model.show_domains) == Domain.query.count():
            model.show_domains = []
                
        # Handle mode-specific settings
        if model.mode == DomainType.old_xtls_direct and not hconfig(ConfigEnum.xtls_enable):
            set_hconfig(ConfigEnum.xtls_enable, True)
            hutils.proxy.get_proxies.invalidate_all()
        elif "reality" in  model.mode:
            self._validate_reality_settings(model, server_ips, is_created)
                
            # Signal config update if needed
        old_db_domain = Domain.by_domain(model.domain)
        if is_created or not old_db_domain or old_db_domain.mode != model.mode:
            # return hiddify.reinstall_action(complete_install=False, domain_changed=True)
            hutils.apply_scope.mark_dirty(hutils.apply_scope.DOMAIN_CHANGE_SUBSYSTEMS)
            hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=True)
        elif any(sa_inspect(model).attrs[attr].history.has_changes()
                 for attr in ('http_port', 'tls_port', 'reality_port', 'reality_private_key', 'reality_public_key', 'reality_short_id')):
            # Not a new domain / mode change, but a port/key binding itself
            # changed - haproxy's bind lists/dst_port ACLs and the
            # xray/singbox REALITY inbounds need to be regenerated too.
            hutils.apply_scope.mark_dirty(hutils.apply_scope.DOMAIN_CHANGE_SUBSYSTEMS)
            hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=True)



    def _validate_port_exclusivity(self, model):
        # "Exclusive to that domain": a custom (non-default) port can only
        # ever belong to one domain at a time - reject the save instead of
        # silently letting haproxy's dst_port ACLs end up ambiguous between
        # two domains claiming the same port.
        if model.http_port and model.http_port != 80:
            conflict = Domain.query.filter(Domain.http_port == model.http_port, Domain.id != model.id, Domain.child_id == model.child_id).first()
            if conflict:
                raise ValidationError(_("This HTTP port is already assigned to domain: ") + conflict.domain)
        if model.tls_port and model.tls_port != 443:
            conflict = Domain.query.filter(Domain.tls_port == model.tls_port, Domain.id != model.id, Domain.child_id == model.child_id).first()
            if conflict:
                raise ValidationError(_("This TLS port is already assigned to domain: ") + conflict.domain)
        if model.reality_port:
            # Unlike http_port/tls_port, a REALITY port has no shared
            # default to fall back to - xray/singbox bind it directly, so
            # any collision between two domains would fail outright.
            conflict = Domain.query.filter(Domain.reality_port == model.reality_port, Domain.id != model.id, Domain.child_id == model.child_id).first()
            if conflict:
                raise ValidationError(_("This REALITY port is already assigned to domain: ") + conflict.domain)

    def _update_cloudflare(self, model, ipv4_list,ipv6_list):
        if hconfig(ConfigEnum.cloudflare) and model.mode not in [DomainType.fake, DomainType.relay, DomainType.reality]:
            try:
                proxied = model.mode in [DomainType.cdn, DomainType.auto_cdn_ip]
                if ipv4_list:
                    hutils.network.cf_api.add_or_update_dns_record(model.domain, str(ipv4_list[0]), "A", proxied=proxied)
                if ipv6_list:
                    hutils.network.cf_api.add_or_update_dns_record(model.domain, str(ipv6_list[0]), "AAAA", proxied=proxied)
                return True
            except Exception as e:
                raise ValidationError(__("cloudflare.error") + f' {e}')
        return False

    def _validate_reality_settings(self, model, server_ips, is_created):
        """Validate REALITY protocol settings with proper error handling"""
        if not hconfig(ConfigEnum.reality_enable):
            set_hconfig(ConfigEnum.reality_enable, True)
            hutils.proxy.get_proxies.invalidate_all()

        model.servernames = (model.servernames or model.domain).lower().strip()

        # Auto-generate this new domain's own REALITY port/keys/short ID -
        # only on creation, never on a later edit of an already-existing
        # domain, since regenerating them out from under a domain that's
        # already handed its port/keys out to real clients would silently
        # break every one of them. An admin can still set/change any of
        # these by hand at any time; this only fills in blanks at creation.
        if is_created:
            if not model.reality_port:
                model.reality_port = hutils.random.get_random_unused_port()
            if not model.reality_private_key or not model.reality_public_key:
                keys = hutils.crypto.generate_x25519_keys()
                model.reality_private_key = keys['private_key']
                model.reality_public_key = keys['public_key']
            if not model.reality_short_id:
                model.reality_short_id = uuid.uuid4().hex[0:random.randint(1, 8) * 2]

        domains_to_check = set()
        for v in [model.domain, model.servernames]:
            domains_to_check.update(d.strip() for d in v.split(",") if d.strip())

        for d in domains_to_check:
            # Check REALITY compatibility
            if not hutils.network.is_domain_reality_friendly(d):
                raise ValidationError(_("Domain is not REALITY friendly!") + f' {d}')

            try:
                if not hutils.network.is_in_same_asn(d, server_ips[0]):
                    domain_ips = hutils.network.get_domain_ips(d)
                    if domain_ips:
                        dip = next(iter(domain_ips))
                        server_asn = hutils.network.get_ip_asn(server_ips[0])
                        domain_asn = hutils.network.get_ip_asn(dip)
                        msg = _("domain.reality.asn_issue")
                        if server_asn or domain_asn:
                            msg += f"<br> Server ASN={server_asn}<br>{d}_ASN={domain_asn}"
                        hutils.flask.flash(msg, 'warning')
            except Exception as e:
                logger.warning(f"ASN check failed for domain {d}: {str(e)}")

        # Check fallback compatibility
        for d in model.servernames.split(","):
            if d.strip() and not hutils.network.fallback_domain_compatible_with_servernames(model.domain, d):
                msg = _("REALITY Fallback domain is not compatible with server names!") + f' {d} != {model.domain}'
                hutils.flask.flash(msg, 'warning')


    def _validate_not_used_before(self, model,is_created):
        configs = get_hconfigs()
        for c in configs:
            if "domain" in c and c not in [ConfigEnum.decoy_domain, ConfigEnum.reality_fallback_domain] and c.category != 'hidden':
                if model.domain == configs[c]:
                    raise ValidationError(_("You have used this domain in: ") + _(f"config.{c}.label"))

        for td in Domain.query.filter(Domain.mode.in_([DomainType.reality,DomainType.special_reality_xhttp,DomainType.special_reality_grpc,DomainType.special_reality_tcp]), Domain.domain != model.domain).all():
            # print(td)
            if td.servernames and (model.domain in td.servernames.split(",")):
                raise ValidationError(_("You have used this domain in: ") + _(f"config.reality_server_names.label") + td.domain)

        if is_created and Domain.query.filter(Domain.domain == model.domain, Domain.child_id == model.child_id).count() > 1:
            raise ValidationError(_("You have used this domain in: "))

    def _validate_domain_ips(self, model, server_ips):
        """Validate domain IP resolution and matching"""
        
        # Skip validation for wildcard or empty domains
        if (model.domain.startswith('*') or not model.domain) and model.mode not in [DomainType.direct]:
            return True
        if model.mode in [DomainType.fake, DomainType.reality, DomainType.relay, DomainType.dnstt, DomainType.xdns, DomainType.xicmp]:
            return True
        if "special" in model.mode:
            return True
        # Resolve domain IPs with timeout
        try:
            dips = hutils.network.get_domain_ips(model.domain)
        except Exception as e:
            logger.error(f"Error resolving domain {model.domain}: {str(e)}")
            raise ValidationError(_("Domain cannot be resolved! Please check DNS settings"))
        
        # Validate resolution success
        if not dips:
            raise ValidationError(_("Domain cannot be resolved! Please check DNS settings"))
        
        # Check IP matching based on mode
        domain_ip_matches_server = any(ip in dips for ip in server_ips)
        server_ips_str = ', '.join(map(str, server_ips))
        dips_str = ', '.join(map(str, dips))
    
        if not domain_ip_matches_server and model.mode in [DomainType.direct]:
            raise ValidationError(
                __("Domain IP=%(domain_ip)s is not matched with your ip=%(server_ip)s which is required in direct mode",
                    server_ip=server_ips_str, domain_ip=dips_str))
                
        if domain_ip_matches_server and model.mode in [DomainType.cdn, DomainType.relay, DomainType.fake, DomainType.auto_cdn_ip]:
            raise ValidationError(
                __("In CDN mode, Domain IP=%(domain_ip)s should be different to your ip=%(server_ip)s",
                    server_ip=server_ips_str, domain_ip=dips_str))
                
        return True
    
        
    # def after_model_change(self,form, model, is_created):
    #     if model.show_domains.count==0:
    #         db.session.bulk_save_objects(ShowDomain(model.id,model.id))

    def on_model_delete(self, model):
        if len(Domain.query.all()) <= 1:
            raise ValidationError(f"at least one domain should exist")
        if hconfig(ConfigEnum.cloudflare) and model.mode not in [DomainType.fake, DomainType.reality, DomainType.relay] and "special" not in model.mode:
            if not hutils.network.cf_api.delete_dns_record(model.domain):
                hutils.flask.flash(_('cf-delete.failed'), 'warning')  # type: ignore
        if model.mode == DomainType.direct:
            # Companion of after_model_change()'s also_enable_xicmp sync -
            # don't leave an orphaned xICMP entry behind once the direct
            # domain it was tied to is gone.
            Domain.query.filter(
                Domain.domain == model.domain,
                Domain.mode == DomainType.xicmp,
                Domain.child_id == model.child_id,
                Domain.id != model.id,
            ).delete()
        model.showed_by_domains = []
        # db.session.commit()
        hutils.apply_scope.mark_dirty(hutils.apply_scope.DOMAIN_CHANGE_SUBSYSTEMS)
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=True)

    def after_model_delete(self, model):
        if hutils.node.is_child():
            hutils.node.run_node_op_in_bg(hutils.node.child.sync_with_parent, *[hutils.node.child.SyncFields.domains])

    def after_model_change(self, form, model, is_created):
        if hconfig(ConfigEnum.first_setup):
            set_hconfig(ConfigEnum.first_setup, False)
        if model.need_valid_ssl and "*" not in model.domain:
            commander(Command.get_cert, domain=model.domain)
        if model.mode == DomainType.direct:
            # also_enable_xicmp (form_extra_fields above) isn't a real
            # column on `model` - sync a companion Domain(mode=xicmp) row
            # with the same domain string to match it. Only for direct
            # mode: xicmp needs no DNS/NS setup (unlike dnstt/xdns), so a
            # bare server IP works here exactly as well as a real domain -
            # this is what lets one domain (or the IP itself) serve both
            # Direct and xICMP at once instead of requiring two separate
            # "Add Domain" entries with the identical value.
            xicmp_companion = Domain.query.filter(
                Domain.domain == model.domain,
                Domain.mode == DomainType.xicmp,
                Domain.child_id == model.child_id,
                Domain.id != model.id,
            ).first()
            if form.also_enable_xicmp.data:
                if not xicmp_companion:
                    db.session.add(Domain(domain=model.domain, mode=DomainType.xicmp, child_id=model.child_id))
                    db.session.commit()
                    hutils.apply_scope.mark_dirty(hutils.apply_scope.DOMAIN_CHANGE_SUBSYSTEMS)
            elif xicmp_companion:
                db.session.delete(xicmp_companion)
                db.session.commit()
                hutils.apply_scope.mark_dirty(hutils.apply_scope.DOMAIN_CHANGE_SUBSYSTEMS)
        if hutils.node.is_child():
            hutils.node.run_node_op_in_bg(hutils.node.child.sync_with_parent, *[hutils.node.child.SyncFields.domains])

    def is_accessible(self):
        if login_required(roles={Role.super_admin, Role.admin}, permissions={Permission.manage_domains})(lambda: True)() != True:
            return False
        return True

    # def form_choices(self, field, *args, **kwargs):
    #     if field.type == "Enum":
    #         return [(enum_value.name, _(enum_value.name)) for enum_value in field.type.__members__.values()]
    #     return super().form_choices(field, *args, **kwargs)

    # @property
    # def server_ips(self):
    #     return hiddify.get_ip(4)

    def get_query(self):
        query = super().get_query()
        return query.filter(Domain.child_id == Child.current().id)
