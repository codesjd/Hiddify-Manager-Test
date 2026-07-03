import wtforms as wtf
from wtforms.validators import ValidationError
from markupsafe import Markup
from flask_babel import lazy_gettext as _
from .adminlte import AdminLTEModelView
from hiddifypanel.auth import login_required
from hiddifypanel.models import *
from hiddifypanel import hutils


# Renders as a plain <script> tag wherever it's placed in form_columns -
# WTForms/flask-admin just call the field to get its HTML, there's no
# input/label for this one. Used to show/hide the fields that are actually
# relevant to whichever Protocol is selected (wireguard/amneziawg/freedom
# don't need SNI/network/security/etc, only vless has Flow, etc) instead of
# always showing every field for every protocol.
#
# Field name must NOT start with an underscore - WTForms' FormMeta silently
# excludes leading-underscore class attributes from Form._fields, which
# means the field would never actually render (confirmed by testing).
#
# ⚠️ Not verified in a live browser - this project's forms load via a
# Bootstrap modal (edit_modal/create_modal), and whether the modal's AJAX
# loader re-executes embedded <script> tags depends on how that's wired
# (jQuery's html()/load() do this automatically; a raw .innerHTML= does
# not). If fields don't actually show/hide when you change Protocol, open
# the browser console for errors - that'll tell us which case this is.
class _ScriptField(wtf.Field):
    widget = None

    def process_formdata(self, valuelist):
        pass

    def _value(self):
        return ''

    def __call__(self, **kwargs):
        return Markup(_PROTOCOL_FIELD_SCRIPT)


_PROTOCOL_FIELD_SCRIPT = """
<script>
(function() {
  function byName(n) { return document.querySelector('[name="' + n + '"]'); }
  function wrapper(el) { return el ? (el.closest('.form-group') || el.parentElement) : null; }

  var ALL = ['address', 'port', 'uuid_or_password', 'network', 'security', 'sni',
             'ws_path', 'host_header', 'fingerprint', 'flow', 'import_link',
             'peer_public_key', 'preshared_key', 'local_address', 'dns', 'jc', 'jmin', 'jmax'];

  // Which of the fields above are actually meaningful for each Protocol -
  // everything not listed here gets hidden. address/port double as the
  // wireguard/amneziawg Endpoint, uuid_or_password as the PrivateKey (same
  // convention the Python side uses in routing.py).
  var SHOW_FOR = {
    vless: ['address', 'port', 'uuid_or_password', 'network', 'security', 'sni',
            'ws_path', 'host_header', 'fingerprint', 'flow', 'import_link'],
    vmess: ['address', 'port', 'uuid_or_password', 'network', 'security', 'sni', 'ws_path', 'host_header', 'fingerprint'],
    trojan: ['address', 'port', 'uuid_or_password', 'network', 'security', 'sni', 'ws_path', 'host_header', 'fingerprint'],
    shadowsocks: ['address', 'port', 'uuid_or_password', 'network', 'security', 'sni', 'ws_path', 'host_header', 'fingerprint'],
    socks: ['address', 'port', 'uuid_or_password'],
    http: ['address', 'port', 'uuid_or_password'],
    wireguard: ['address', 'port', 'uuid_or_password', 'peer_public_key', 'local_address'],
    amneziawg: ['address', 'port', 'uuid_or_password', 'peer_public_key', 'preshared_key', 'local_address', 'dns', 'jc', 'jmin', 'jmax'],
    freedom: []
  };

  function applyProtocol() {
    var sel = byName('protocol');
    if (!sel) return;
    var show = SHOW_FOR[sel.value] || [];
    ALL.forEach(function(n) {
      var w = wrapper(byName(n));
      if (w) w.style.display = show.indexOf(n) === -1 ? 'none' : '';
    });
  }

  function init() {
    var sel = byName('protocol');
    if (!sel || sel.dataset.protocolToggleBound) return;
    sel.dataset.protocolToggleBound = '1';
    sel.addEventListener('change', applyProtocol);
    applyProtocol();
  }

  init();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  }
  // Modal content can be inserted after this script already ran once and
  // found nothing yet (id not in DOM at parse time) - retry briefly.
  var tries = 0;
  var retry = setInterval(function() {
    init();
    if (byName('protocol') || ++tries > 20) clearInterval(retry);
  }, 150);
})();
</script>
"""


class OutboundAdmin(AdminLTEModelView):
    """Custom Xray/singbox outbounds - lets an admin add/chain outbound
    proxies (e.g. point traffic at another one of your own servers, or bind
    to the AmneziaWG interface other/amneziawg/ brings up) from the panel
    instead of hand-editing the *_outbounds.json.j2 templates over SSH.

    Same rows drive both xray's and singbox's generated config
    (CustomOutbound.to_xray_dict()/to_singbox_dict()) - whichever core is
    actually running reads the matching one, so this form isn't tied to one
    core_type.
    """
    column_hide_backrefs = False
    list_template = 'model/outbound_list.html'
    column_list = ["tag", "protocol", "address", "port", "network", "security", "enable", "comment"]
    form_columns = ["enable", "tag", "import_link", "protocol", "address", "port", "uuid_or_password",
                     "peer_public_key", "preshared_key", "local_address", "dns", "jc", "jmin", "jmax",
                     "network", "security", "sni", "ws_path", "host_header", "fingerprint", "flow",
                     "comment", "extra_json", "protocol_field_script"]

    column_labels = {
        "tag": _("Tag"),
        "protocol": _("Protocol"),
        "address": _("Server Address / Endpoint Host"),
        "port": _("Port / Endpoint Port"),
        "uuid_or_password": _("UUID / Password / Private Key"),
        "peer_public_key": _("Peer Public Key (wireguard/amneziawg)"),
        "preshared_key": _("Preshared Key (amneziawg, optional)"),
        "local_address": _("Local Address (wireguard/amneziawg, e.g. 10.0.0.2/32)"),
        "dns": _("DNS (amneziawg, optional)"),
        "jc": _("Jc (amneziawg junk packet count)"),
        "jmin": _("Jmin (amneziawg junk packet min size)"),
        "jmax": _("Jmax (amneziawg junk packet max size)"),
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
        address=_("The destination server's IP or domain - e.g. another one of your own servers, for chaining, or the wireguard/amneziawg peer's Endpoint host. Not used for freedom."),
        uuid_or_password=_("UUID for vless/vmess, password for trojan/shadowsocks, user:pass for socks/http, or PrivateKey for wireguard/amneziawg. Not used for freedom."),
        peer_public_key=_("The remote peer's PublicKey - same value as [Peer] PublicKey in a WireGuard/AmneziaWG .conf."),
        preshared_key=_("The remote peer's PresharedKey, if it has one - same value as [Peer] PresharedKey in an AmneziaWG .conf. Leave blank if not used."),
        local_address=_("This tunnel's own address, same as [Interface] Address in a WireGuard/AmneziaWG .conf, e.g. \"10.0.0.2/32\"."),
        dns=_("Optional, same as [Interface] DNS in an AmneziaWG .conf."),
        jc=_("AmneziaWG obfuscation - number of junk packets sent before the handshake. Leave blank for a plain (non-obfuscated) tunnel."),
        jmin=_("AmneziaWG obfuscation - minimum junk packet size in bytes."),
        jmax=_("AmneziaWG obfuscation - maximum junk packet size in bytes."),
        extra_json=_('Optional. Deep-merged on top of the generated outbound JSON for anything the form above can\'t express, '
                      'e.g. {"streamSettings": {"sockopt": {"dialerProxy": "another-tag"}}} to chain through yet another outbound.'),
    )

    form_extra_fields = {
        "import_link": wtf.TextAreaField(
            _("Import Link (vless://...)"),
            description=_('Paste a vless:// share link here and save - it fills in Address/Port/UUID/Network/Security/SNI/Path/Host/'
                           'Fingerprint/Flow below from it (overwriting whatever was there). Leave blank to edit the fields manually instead.'),
        ),
        "protocol_field_script": _ScriptField(label=""),
    }

    form_widget_args = {
        'extra_json': {'rows': 4},
        'import_link': {'rows': 3, 'style': 'font-family: monospace'},
    }

    # WireGuard is retired in favor of AmneziaWG - form_choices overrides
    # the auto-generated Enum dropdown (which would otherwise list every
    # OutboundProtocol member) so new outbounds can't select it. An existing
    # row already saved with protocol=wireguard is untouched by this - it
    # just can't be changed to "wireguard" again if edited away from it.
    form_choices = {
        'protocol': [(p.value, p.value) for p in OutboundProtocol if p != OutboundProtocol.wireguard],
    }

    can_export = False
    column_sortable_list = ["tag", "protocol", "enable"]

    def _enable_formatter(view, context, model, name):
        return Markup(hutils.flask.hf_status_circle(bool(model.enable)))

    column_formatters = {
        "enable": _enable_formatter,
    }

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
        hutils.apply_scope.mark_dirty(hutils.apply_scope.OUTBOUND_CHANGE_SUBSYSTEMS)
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
