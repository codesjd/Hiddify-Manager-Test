import json

import wtforms as wtf
from flask_babel import lazy_gettext as _
from markupsafe import Markup
from wtforms.validators import ValidationError

from hiddifypanel import hutils
from hiddifypanel.auth import login_required
from hiddifypanel.models import *

from .adminlte import AdminLTEModelView
from .InboundOverrideAdmin import (
    _ALPN_CHOICES,
    _FINGERPRINT_CHOICES,
    _MANAGED_KEYS,
    _NAME_CHIP_COLORS,
    _XHTTP_MODE_CHOICES,
)


class DomainProxyOverrideAdmin(AdminLTEModelView):
    """Per-(domain, proxy) overrides - lets one specific domain force one
    specific proxy row (protocol/transport/cdn combination) on or off, or
    tweak its generated config, without that also affecting every other
    domain sharing the same proxy row (that's Proxy.params/'Inbound
    Overrides') or every other proxy on this same domain (that's
    Domain.extra_params).

    Reuses InboundOverrideAdmin's managed-key list and choice fields for
    the same set of transport/security knobs, so the two pages behave
    consistently - the only real difference is that domain/proxy are
    picked per row here instead of being fixed context for an existing
    Proxy row.
    """

    column_list = ["domain", "proxy", "enable"]
    form_columns = [
        "domain",
        "proxy",
        "enable",
        "sni",
        "host",
        "path",
        "fingerprint",
        "alpn",
        "mode",
        "hysteria_obfs_password",
        "advanced_json",
    ]
    column_editable_list = ["enable"]
    column_sortable_list = ["enable"]

    column_labels = {
        "domain": _("Domain"),
        "proxy": _("Proxy"),
        "enable": _("Enable"),
    }

    form_args = {
        "domain": {
            "query_factory": lambda: Domain.query.filter(Domain.child_id == Child.current().id).order_by(Domain.domain),
        },
        "proxy": {
            "query_factory": lambda: Proxy.query.filter(Proxy.child_id == Child.current().id).order_by(Proxy.name),
            "get_label": lambda p: p.name,
        },
    }
    form_extra_fields = {
        # The model's `enable` column is nullable (None = "don't touch the
        # on/off decision get_valid_proxies() would otherwise make" - see
        # DomainProxyOverride's docstring), but a create/edit form has no
        # natural third checkbox state. In practice an override row only
        # exists because an admin deliberately created one for this exact
        # (domain, proxy) pair, so "inherit" is already represented by
        # simply not creating a row at all - within a row that does exist,
        # checked/default (True) keeps the proxy included while applying
        # the overrides below, and unchecking it is the explicit "force
        # this off for this domain" action.
        "enable": wtf.BooleanField(
            _("Enable"),
            default=True,
            description=_(
                "Uncheck to force this proxy off for this domain only, even if it's enabled everywhere else. Leave checked to keep its normal on/off state and just apply the overrides below."
            ),
        ),
        "sni": wtf.StringField(
            _("SNI"),
            description=_(
                "Override the Server Name Indication sent to the client's config. Leave blank to use the domain's own SNI."
            ),
        ),
        "host": wtf.StringField(
            _("Host header"),
            description=_("Override the Host header (WS/CDN transports). Leave blank for the default."),
        ),
        "path": wtf.StringField(
            _("Path"),
            description=_(
                "Override the transport path (WS/httpupgrade/xhttp) or gRPC service name. Leave blank for the auto-generated one."
            ),
        ),
        "fingerprint": wtf.SelectField(_("uTLS Fingerprint"), choices=_FINGERPRINT_CHOICES, default=""),
        "alpn": wtf.SelectField(_("ALPN"), choices=_ALPN_CHOICES, default=""),
        "mode": wtf.SelectField(
            _("XHTTP Mode"), choices=_XHTTP_MODE_CHOICES, default="", render_kw={"id": "domain_proxy_override_mode"}
        ),
        "hysteria_obfs_password": wtf.StringField(
            _("Hysteria2 Obfs Password"),
            description=_("Only applies to hysteria2 proxies. Leave blank to use the global obfuscation password."),
        ),
        "advanced_json": wtf.TextAreaField(
            _("Advanced Override (JSON)"),
            description=_(
                'Deep-merged on top of everything above, for anything the fields don\'t cover, e.g. {"mux_enable": true}. '
                "Leave empty to only use the fields above."
            ),
        ),
    }

    can_export = False

    def _domain_formatter(view, context, model, name):
        if not model.domain:
            return ""
        return Markup(f'<span class="hf-chip">{model.domain.domain}</span>')

    def _proxy_formatter(view, context, model, name):
        if not model.proxy:
            return ""
        chips = []
        for part in (model.proxy.name or "").split():
            key = part.split("=")[0]
            color_var = _NAME_CHIP_COLORS.get(key, "--text-secondary")
            chips.append(f'<span class="hf-chip" style="background:var({color_var});">{part}</span>')
        return Markup(f'<div class="hf-chips">{"".join(chips)}</div>')

    column_formatters = {
        "domain": _domain_formatter,
        "proxy": _proxy_formatter,
    }

    def get_query(self):
        return super().get_query().join(Domain).filter(Domain.child_id == Child.current().id)

    def get_count_query(self):
        return super().get_count_query().join(Domain).filter(Domain.child_id == Child.current().id)

    def is_accessible(self):
        if login_required(roles={Role.super_admin}, permissions={Permission.manage_settings})(lambda: True)() != True:
            return False
        return True

    def create_form(self, obj=None):
        return self._disable_select2(super().create_form(obj))

    def edit_form(self, obj=None):
        return self._disable_select2(super().edit_form(obj))

    def on_form_prefill(self, form, id):
        override = DomainProxyOverride.query.get(id)
        params = (override and override.params) or {}
        for key in _MANAGED_KEYS:
            getattr(form, key).data = params.get(key, "")
        extra = {k: v for k, v in params.items() if k not in _MANAGED_KEYS}
        if extra:
            form.advanced_json.data = json.dumps(extra, indent=2)

    def on_model_change(self, form, model, is_created):
        # A (domain, proxy) pair with two override rows would be ambiguous -
        # which one wins is undefined. The model's own UniqueConstraint
        # would also catch this, but only as a raw IntegrityError after
        # commit; this gives the admin an actual field-level message instead.
        # is_created rows have no model.id yet (None), so the dup.id != None
        # comparison already correctly treats any existing row as a conflict.
        dup = DomainProxyOverride.query.filter_by(domain_id=form.domain.data.id, proxy_id=form.proxy.data.id).first()
        if dup and dup.id != model.id:
            raise ValidationError(_("An override for this domain+proxy pair already exists. Edit that one instead."))

        params = dict(model.params or {})
        for key in _MANAGED_KEYS:
            value = getattr(form, key).data
            if value:
                params[key] = value
            else:
                params.pop(key, None)

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
        hutils.proxy.get_domain_proxy_overrides.invalidate_all()
        hutils.apply_scope.mark_dirty(hutils.apply_scope.CORE_ONLY_SUBSYSTEMS)
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)

    def after_model_delete(self, model):
        hutils.proxy.get_domain_proxy_overrides.invalidate_all()
        hutils.apply_scope.mark_dirty(hutils.apply_scope.CORE_ONLY_SUBSYSTEMS)
