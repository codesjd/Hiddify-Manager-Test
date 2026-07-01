from flask_babel import lazy_gettext as _
from .adminlte import AdminLTEModelView
from hiddifypanel.auth import login_required
from hiddifypanel.models import *
from hiddifypanel import hutils


class InboundOverrideAdmin(AdminLTEModelView):
    """Hiddify auto-generates one inbound per enabled
    protocol/transport/CDN-mode combination (the checkboxes on the 'Xray
    Configs' page control which combinations exist at all). This page lets
    you edit the generated JSON for a specific one of those combinations,
    instead of it being 100% derived from global settings.

    Uses the Proxy.params field, which already existed on the model but
    wasn't actually applied anywhere until now.
    """
    column_hide_backrefs = False
    column_list = ["name", "proto", "transport", "cdn", "l3", "enable"]
    form_columns = ["name", "enable", "params"]
    column_editable_list = ["enable"]

    column_labels = {
        "name": _("Name"),
        "proto": _("Protocol"),
        "transport": _("Transport"),
        "cdn": _("Mode"),
        "l3": _("Layer 3"),
        "enable": _("Enable"),
        "params": _("Override Params (JSON)"),
    }
    column_descriptions = dict(
        params=_('JSON merged onto this inbound\'s generated config, e.g. {"fingerprint": "firefox", "alpn": "h2"}. '
                  'Applies to every domain using this protocol/transport/mode combination - for a SINGLE domain instead, '
                  'use the "Extra Params / Per-Domain Override" field on that domain, which wins if both are set.'),
    )
    form_widget_args = {
        'params': {'rows': 4},
        'proto': {'disabled': True},
        'transport': {'disabled': True},
        'cdn': {'disabled': True},
        'l3': {'disabled': True},
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

    def after_model_change(self, form, model, is_created):
        hutils.proxy.get_proxies.invalidate_all()
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
