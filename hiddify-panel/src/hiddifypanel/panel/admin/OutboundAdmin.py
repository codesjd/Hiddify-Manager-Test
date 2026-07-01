import wtforms as wtf
from wtforms.validators import ValidationError
from flask_babel import lazy_gettext as _
from .adminlte import AdminLTEModelView
from hiddifypanel.auth import login_required
from hiddifypanel.models import *
from hiddifypanel import hutils


class OutboundAdmin(AdminLTEModelView):
    """Custom Xray outbounds - lets an admin add/chain outbound proxies
    (e.g. point traffic at another one of your own servers) from the panel
    instead of hand-editing xray/configs/06_outbounds.json.j2 over SSH.
    """
    column_hide_backrefs = False
    column_list = ["tag", "protocol", "address", "port", "network", "security", "enable", "comment"]
    form_columns = ["enable", "tag", "import_link", "protocol", "address", "port", "uuid_or_password",
                     "network", "security", "sni", "ws_path", "host_header", "fingerprint", "flow",
                     "comment", "extra_json"]

    column_labels = {
        "tag": _("Tag"),
        "protocol": _("Protocol"),
        "address": _("Server Address"),
        "port": _("Port"),
        "uuid_or_password": _("UUID / Password"),
        "network": _("Network"),
        "security": _("Security"),
        "sni": _("SNI"),
        "ws_path": _("Path (WS/gRPC service name/HTTPUpgrade path)"),
        "host_header": _("Host Header (WS/HTTPUpgrade/XHTTP)"),
        "fingerprint": _("uTLS Fingerprint"),
        "flow": _("Flow (vless xtls, e.g. xtls-rprx-vision)"),
        "comment": _("Comment"),
        "extra_json": _("Advanced Override (JSON)"),
        "enable": _("Enable"),
    }
    column_descriptions = dict(
        tag=_("Unique identifier for this outbound. Reference it as the Outbound Tag in a Routing Rule to send matching traffic here."),
        address=_("The destination server's IP or domain - e.g. another one of your own servers, for chaining."),
        uuid_or_password=_("UUID for vless/vmess, password for trojan/shadowsocks/wireguard private key, or user:pass for socks/http."),
        extra_json=_('Optional. Deep-merged on top of the generated outbound JSON for anything the form above can\'t express, '
                      'e.g. {"streamSettings": {"sockopt": {"dialerProxy": "another-tag"}}} to chain through yet another outbound.'),
    )

    form_extra_fields = {
        "import_link": wtf.TextAreaField(
            _("Import Link (vless://...)"),
            description=_('Paste a vless:// share link here and save - it fills in Address/Port/UUID/Network/Security/SNI/Path/Host/'
                           'Fingerprint/Flow below from it (overwriting whatever was there). Leave blank to edit the fields manually instead.'),
        ),
    }

    form_widget_args = {
        'extra_json': {'rows': 4},
        'import_link': {'rows': 3, 'style': 'font-family: monospace'},
    }

    can_export = False
    column_sortable_list = ["tag", "protocol", "enable"]

    def is_accessible(self):
        if login_required(roles={Role.super_admin}, permissions={Permission.manage_settings})(lambda: True)() != True:
            return False
        return True

    def on_model_change(self, form, model, is_created):
        model.child_id = Child.current().id

        raw_link = (form.import_link.data or '').strip()
        if raw_link:
            try:
                parsed = parse_vless_link(raw_link)
            except ValueError as e:
                raise ValidationError(str(e))
            for key, value in parsed.items():
                setattr(model, key, value)

    def after_model_change(self, form, model, is_created):
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
