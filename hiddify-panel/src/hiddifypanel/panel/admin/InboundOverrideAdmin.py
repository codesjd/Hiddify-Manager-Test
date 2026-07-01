import json
from flask_babel import lazy_gettext as _
import wtforms as wtf
from wtforms.validators import ValidationError
from .adminlte import AdminLTEModelView
from hiddifypanel.auth import login_required
from hiddifypanel.models import *
from hiddifypanel import hutils


# Keys managed by the explicit form fields below. Anything else already
# present in Proxy.params (e.g. hand-written JSON from before this form
# existed, or a key this form doesn't know about) is left untouched by
# on_model_change - only these keys get added/updated/cleared.
_MANAGED_KEYS = ["sni", "host", "path", "fingerprint", "alpn", "mode", "hysteria_obfs_password"]

_FINGERPRINT_CHOICES = [
    ("", _("(no override)")), ("none", "None"), ("chrome", "Chrome"), ("edge", "Edge"), ("ios", "iOS"),
    ("android", "Android"), ("safari", "Safari"), ("firefox", "Firefox"), ("random", "random"), ("randomized", "randomized"),
]
_ALPN_CHOICES = [
    ("", _("(no override)")), ("h2", "h2"), ("http/1.1", "http/1.1"), ("h2,http/1.1", "h2,http/1.1"), ("h3", "h3"),
]
_XHTTP_MODE_CHOICES = [
    ("", _("(no override, default: auto)")), ("auto", "auto"), ("packet-up", "packet-up"), ("stream-up", "stream-up"),
]


class InboundOverrideAdmin(AdminLTEModelView):
    """Hiddify auto-generates one inbound per enabled
    protocol/transport/CDN-mode combination (the checkboxes on the 'Xray
    Configs' page control which combinations exist at all). This page lets
    you override a handful of transport/security knobs for a specific one
    of those combinations, instead of it being 100% derived from global
    settings.

    Only fields that are actually read back out during config generation
    (apply_proxy_overrides() in hutils/proxy/shared.py, plus the `mode` key
    read directly in make_proxy() for xhttp) are exposed here - not Port or
    Security, which aren't per-inbound concepts in Hiddify: most protocols
    share a single HAProxy/xray entrypoint routed by SNI, so a per-inbound
    port field would either do nothing or advertise a port nothing listens
    on to the client. `advanced_json` remains as an escape hatch for
    anything else, deep-merged the same way the old raw JSON field was.

    Uses the Proxy.params field, which already existed on the model but
    wasn't actually applied anywhere until now.
    """
    column_hide_backrefs = False
    column_list = ["name", "proto", "transport", "cdn", "l3", "enable"]
    form_columns = ["name", "enable"]
    column_editable_list = ["enable"]

    column_labels = {
        "name": _("Name"),
        "proto": _("Protocol"),
        "transport": _("Transport"),
        "cdn": _("Mode"),
        "l3": _("Layer 3"),
        "enable": _("Enable"),
    }
    form_widget_args = {
        'proto': {'disabled': True},
        'transport': {'disabled': True},
        'cdn': {'disabled': True},
        'l3': {'disabled': True},
    }
    form_extra_fields = {
        "sni": wtf.StringField(_("SNI"), description=_("Override the Server Name Indication sent to the client's config. Leave blank to use the domain's own SNI.")),
        "host": wtf.StringField(_("Host header"), description=_("Override the Host header (WS/CDN transports). Leave blank for the default.")),
        "path": wtf.StringField(_("Path"), description=_("Override the transport path (WS/httpupgrade/xhttp) or gRPC service name. Leave blank for the auto-generated one.")),
        "fingerprint": wtf.SelectField(_("uTLS Fingerprint"), choices=_FINGERPRINT_CHOICES, default=""),
        "alpn": wtf.SelectField(_("ALPN"), choices=_ALPN_CHOICES, default=""),
        "mode": wtf.SelectField(_("XHTTP Mode"), choices=_XHTTP_MODE_CHOICES, default=""),
        "hysteria_obfs_password": wtf.StringField(_("Hysteria2 Obfs Password"), description=_("Only applies to hysteria2 proxies. Leave blank to use the global obfuscation password.")),
        "advanced_json": wtf.TextAreaField(_("Advanced Override (JSON)"),
                                            description=_('Deep-merged on top of everything above, for anything the fields don\'t cover, e.g. {"mux_enable": true}. '
                                                           'Leave empty to only use the fields above.')),
    }

    can_create = False
    can_delete = False
    can_export = False
    column_sortable_list = ["name", "proto", "enable"]

    def get_query(self):
        return super().get_query().filter(Proxy.child_id == Child.current().id)

    def is_accessible(self):
        if login_required(roles={Role.super_admin}, permissions={Permission.manage_settings})(lambda: True)() != True:
            return False
        return True

    def on_form_prefill(self, form, id):
        proxy = Proxy.query.get(id)
        params = (proxy and proxy.params) or {}
        for key in _MANAGED_KEYS:
            getattr(form, key).data = params.get(key, "")
        extra = {k: v for k, v in params.items() if k not in _MANAGED_KEYS}
        if extra:
            form.advanced_json.data = json.dumps(extra, indent=2)

    def on_model_change(self, form, model, is_created):
        params = dict(model.params or {})
        for key in _MANAGED_KEYS:
            value = getattr(form, key).data
            if value:
                params[key] = value
            else:
                params.pop(key, None)

        # advanced_json fully replaces the non-managed keyspace (round-trip
        # with on_form_prefill), so clearing a key from the text box actually
        # removes it instead of only ever being additive.
        for key in [k for k in params if k not in _MANAGED_KEYS]:
            del params[key]

        raw_advanced = (form.advanced_json.data or "").strip()
        if raw_advanced:
            try:
                advanced = json.loads(raw_advanced)
            except Exception as e:
                raise ValidationError(f"Invalid JSON in Advanced Override: {e}")
            if not isinstance(advanced, dict):
                raise ValidationError("Advanced Override must be a JSON object")
            for key in _MANAGED_KEYS:
                advanced.pop(key, None)
            params.update(advanced)

        model.params = params

    def after_model_change(self, form, model, is_created):
        hutils.proxy.get_proxies.invalidate_all()
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
