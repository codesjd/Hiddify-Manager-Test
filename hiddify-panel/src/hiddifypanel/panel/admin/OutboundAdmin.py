import json
import wtforms as wtf
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

    def __init__(self, label='', script='', **kwargs):
        super().__init__(label=label, **kwargs)
        self._script = script

    def process_formdata(self, valuelist):
        pass

    def _value(self):
        return ''

    def __call__(self, **kwargs):
        return Markup(self._script or _PROTOCOL_FIELD_SCRIPT)


_PROTOCOL_FIELD_SCRIPT = """
<script>
(function() {
  function byName(n) { return document.querySelector('[name="' + n + '"]'); }
  function wrapper(el) { return el ? (el.closest('.form-group') || el.parentElement) : null; }

  var ALL = ['address', 'port', 'uuid_or_password', 'network', 'security', 'sni',
             'ws_path', 'host_header', 'fingerprint', 'flow', 'encryption', 'ss_method',
             'peer_public_key', 'preshared_key', 'local_address', 'dns', 'jc', 'jmin', 'jmax',
             'sockopt_mark', 'sockopt_tcp_fast_open', 'sockopt_tproxy', 'sockopt_domain_strategy',
             'sockopt_dialer_proxy', 'sockopt_interface', 'sockopt_tcp_keep_alive_interval',
             'sockopt_tcp_keep_alive_idle', 'sockopt_tcp_user_timeout', 'sockopt_tcp_max_seg',
             'sockopt_tcp_window_clamp', 'sockopt_tcp_mptcp', 'sockopt_penetrate',
             'sockopt_address_port_strategy', 'he_try_delay_ms', 'he_prioritize_ipv6',
             'he_interleave', 'he_max_concurrent_try', 'mux_enabled', 'mux_concurrency',
             'mux_xudp_concurrency', 'mux_xudp_proxy_udp_443',
             'hysteria_obfs_password', 'hysteria_up_mbps', 'hysteria_down_mbps',
             'awg_conf', 'awg_s1', 'awg_s2', 'awg_s3', 'awg_s4',
             'awg_i1', 'awg_i2', 'awg_i3', 'awg_i4', 'awg_i5',
             'awg_h1', 'awg_h2', 'awg_h3', 'awg_h4',
             'tuic_congestion_control', 'mieru_transport', 'mieru_multiplexing'];

  // Every real (non-amneziawg/wireguard/freedom) protocol shares the same
  // sockopt/mux block - xray-core doesn't vary these by protocol, and the
  // reference forms show the identical set for vless/vmess/trojan/
  // shadowsocks/socks/http.
  var SOCKOPT_MUX = ['sockopt_mark', 'sockopt_tcp_fast_open', 'sockopt_tproxy', 'sockopt_domain_strategy',
             'sockopt_dialer_proxy', 'sockopt_interface', 'sockopt_tcp_keep_alive_interval',
             'sockopt_tcp_keep_alive_idle', 'sockopt_tcp_user_timeout', 'sockopt_tcp_max_seg',
             'sockopt_tcp_window_clamp', 'sockopt_tcp_mptcp', 'sockopt_penetrate',
             'sockopt_address_port_strategy', 'he_try_delay_ms', 'he_prioritize_ipv6',
             'he_interleave', 'he_max_concurrent_try', 'mux_enabled', 'mux_concurrency',
             'mux_xudp_concurrency', 'mux_xudp_proxy_udp_443'];

  // Which of the fields above are actually meaningful for each Protocol -
  // everything not listed here gets hidden. address/port double as the
  // wireguard/amneziawg Endpoint, uuid_or_password as the PrivateKey (same
  // convention the Python side uses in routing.py).
  var SHOW_FOR = {
    vless: ['address', 'port', 'uuid_or_password', 'network', 'security', 'sni',
            'ws_path', 'host_header', 'fingerprint', 'flow', 'encryption'].concat(SOCKOPT_MUX),
    vmess: ['address', 'port', 'uuid_or_password', 'network', 'security', 'sni', 'ws_path', 'host_header', 'fingerprint'].concat(SOCKOPT_MUX),
    trojan: ['address', 'port', 'uuid_or_password', 'network', 'security', 'sni', 'ws_path', 'host_header', 'fingerprint'].concat(SOCKOPT_MUX),
    shadowsocks: ['address', 'port', 'uuid_or_password', 'ss_method', 'network', 'security', 'sni', 'ws_path', 'host_header', 'fingerprint'].concat(SOCKOPT_MUX),
    socks: ['address', 'port', 'uuid_or_password'].concat(SOCKOPT_MUX),
    http: ['address', 'port', 'uuid_or_password'].concat(SOCKOPT_MUX),
    // hysteria2 is QUIC/TLS with its own obfs+bandwidth knobs; no network/
    // transport/mux selectors apply. sni is its TLS server_name.
    hysteria: ['address', 'port', 'uuid_or_password', 'sni', 'hysteria_obfs_password', 'hysteria_up_mbps', 'hysteria_down_mbps'],
    // NaiveProxy is always TLS (HTTP/2-over-TLS) with no separate transport
    // selector; uuid_or_password is user:pass same as socks/http. No
    // uTLS fingerprint field - NaiveProxy uses Chromium's actual network
    // stack rather than a uTLS mimicry layer, so that field has no effect
    // here.
    naive: ['address', 'port', 'uuid_or_password', 'sni'].concat(SOCKOPT_MUX),
    // TUIC: uuid_or_password is "uuid:password". Always TLS, no separate
    // transport selector.
    tuic: ['address', 'port', 'uuid_or_password', 'sni', 'tuic_congestion_control'].concat(SOCKOPT_MUX),
    // Mieru: uuid_or_password is "username:password". No TLS/security field
    // - Mieru does its own obfuscation, not a TLS wrapper.
    mieru: ['address', 'port', 'uuid_or_password', 'mieru_transport', 'mieru_multiplexing'].concat(SOCKOPT_MUX),
    wireguard: ['address', 'port', 'uuid_or_password', 'peer_public_key', 'local_address'],
    // AmneziaWG gets a raw .conf paste field plus its full obfuscation
    // params on top of the wireguard basics (Jc/Jmin/Jmax + S1-S4 + I1-I5).
    amneziawg: ['address', 'port', 'uuid_or_password', 'peer_public_key', 'preshared_key', 'local_address', 'dns',
                'jc', 'jmin', 'jmax',
                'awg_h1', 'awg_h2', 'awg_h3', 'awg_h4',
                'awg_s1', 'awg_s2', 'awg_s3', 'awg_s4',
                'awg_i1', 'awg_i2', 'awg_i3', 'awg_i4', 'awg_i5',
                'awg_conf'],
    freedom: []
  };
  // reality_public_key/reality_short_id only ever matter when Security is
  // actually set to "reality" - shown/hidden by a second, independent
  // toggle keyed on that field rather than baked into SHOW_FOR per protocol,
  // since it's the Security *value*, not the Protocol, that decides this.
  var REALITY_ONLY = ['reality_public_key', 'reality_short_id'];

  function applyProtocol() {
    var sel = byName('protocol');
    if (!sel) return;
    var show = SHOW_FOR[sel.value] || [];
    ALL.forEach(function(n) {
      var w = wrapper(byName(n));
      if (w) w.style.display = show.indexOf(n) === -1 ? 'none' : '';
    });
    applyReality();
  }

  function applyReality() {
    var protoSel = byName('protocol');
    var secSel = byName('security');
    var show = (SHOW_FOR[protoSel && protoSel.value] || []).indexOf('security') !== -1
               && secSel && secSel.value === 'reality';
    REALITY_ONLY.forEach(function(n) {
      var w = wrapper(byName(n));
      if (w) w.style.display = show ? '' : 'none';
    });
  }

  function init() {
    var sel = byName('protocol');
    var secSel = byName('security');
    if (!sel || sel.dataset.protocolToggleBound) return;
    sel.dataset.protocolToggleBound = '1';
    sel.addEventListener('change', applyProtocol);
    if (secSel) secSel.addEventListener('change', applyReality);
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
    column_list = ["tag", "protocol", "address", "port", "network", "security", "comment"]
    form_columns = ["tag", "awg_conf", "protocol", "address", "port", "uuid_or_password", "ss_method",
                     "peer_public_key", "preshared_key", "local_address", "dns", "jc", "jmin", "jmax",
                     "network", "security", "sni", "ws_path", "host_header", "fingerprint", "flow", "encryption",
                     "reality_public_key", "reality_short_id",
                     "sockopt_mark", "sockopt_tcp_fast_open", "sockopt_tproxy", "sockopt_domain_strategy",
                     "sockopt_dialer_proxy", "sockopt_interface", "sockopt_tcp_keep_alive_interval",
                     "sockopt_tcp_keep_alive_idle", "sockopt_tcp_user_timeout", "sockopt_tcp_max_seg",
                     "sockopt_tcp_window_clamp", "sockopt_tcp_mptcp", "sockopt_penetrate",
                     "sockopt_address_port_strategy", "he_try_delay_ms", "he_prioritize_ipv6",
                     "he_interleave", "he_max_concurrent_try",
                     "mux_enabled", "mux_concurrency", "mux_xudp_concurrency", "mux_xudp_proxy_udp_443",
                     "hysteria_obfs_password", "hysteria_up_mbps", "hysteria_down_mbps",
                     "awg_h1", "awg_h2", "awg_h3", "awg_h4",
                     "awg_s1", "awg_s2", "awg_s3", "awg_s4",
                     "awg_i1", "awg_i2", "awg_i3", "awg_i4", "awg_i5",
                     "tuic_congestion_control", "mieru_transport", "mieru_multiplexing",
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
        "encryption": _("Encryption (vless, e.g. none)"),
        "ss_method": _("Encryption Method (shadowsocks)"),
        "reality_public_key": _("Reality Public Key"),
        "reality_short_id": _("Reality Short ID"),
        "sockopt_mark": _("Mark (fwmark)"),
        "sockopt_tcp_fast_open": _("TCP Fast Open"),
        "sockopt_tproxy": _("TProxy"),
        "sockopt_domain_strategy": _("Domain Strategy"),
        "sockopt_dialer_proxy": _("Dialer Proxy"),
        "sockopt_interface": _("Interface"),
        "sockopt_tcp_keep_alive_interval": _("TCP Keep-Alive Interval"),
        "sockopt_tcp_keep_alive_idle": _("TCP Keep-Alive Idle (s)"),
        "sockopt_tcp_user_timeout": _("TCP User Timeout (ms)"),
        "sockopt_tcp_max_seg": _("TCP Max Seg"),
        "sockopt_tcp_window_clamp": _("TCP Window Clamp"),
        "sockopt_tcp_mptcp": _("Multipath TCP"),
        "sockopt_penetrate": _("Penetrate"),
        "sockopt_address_port_strategy": _("Address+Port Strategy"),
        "he_try_delay_ms": _("Happy Eyeballs: Try Delay (ms)"),
        "he_prioritize_ipv6": _("Happy Eyeballs: Prioritize IPv6"),
        "he_interleave": _("Happy Eyeballs: Interleave"),
        "he_max_concurrent_try": _("Happy Eyeballs: Max Concurrent Try"),
        "mux_enabled": _("Mux"),
        "mux_concurrency": _("Mux Concurrency"),
        "mux_xudp_concurrency": _("Mux xudp Concurrency"),
        "mux_xudp_proxy_udp_443": _("Mux xudp UDP 443 (reject/allow/skip)"),
        "hysteria_obfs_password": _("Obfs Password (hysteria2 salamander)"),
        "hysteria_up_mbps": _("Up Mbps (hysteria2)"),
        "hysteria_down_mbps": _("Down Mbps (hysteria2)"),
        "awg_h1": _("H1 (AmneziaWG)"),
        "awg_h2": _("H2 (AmneziaWG)"),
        "awg_h3": _("H3 (AmneziaWG)"),
        "awg_h4": _("H4 (AmneziaWG)"),
        "awg_s1": _("S1 (AmneziaWG)"),
        "awg_s2": _("S2 (AmneziaWG)"),
        "awg_s3": _("S3 (AmneziaWG)"),
        "awg_s4": _("S4 (AmneziaWG)"),
        "awg_i1": _("I1 (AmneziaWG)"),
        "awg_i2": _("I2 (AmneziaWG)"),
        "awg_i3": _("I3 (AmneziaWG)"),
        "awg_i4": _("I4 (AmneziaWG)"),
        "awg_i5": _("I5 (AmneziaWG)"),
        "awg_conf": _("Raw .conf paste (AmneziaWG)"),
        "tuic_congestion_control": _("Congestion Control (TUIC)"),
        "mieru_transport": _("Transport (Mieru)"),
        "mieru_multiplexing": _("Multiplexing (Mieru)"),
        "comment": _("Comment"),
        "extra_json": _("Advanced Override (JSON)"),
    }
    column_descriptions = dict(
        tag=_("Unique identifier for this outbound. Reference it as the Outbound Tag in a Routing Rule to send matching traffic here."),
        address=_("The destination server's IP or domain - e.g. another one of your own servers, for chaining, or the wireguard/amneziawg peer's Endpoint host. Not used for freedom."),
        uuid_or_password=_("UUID for vless/vmess, password for trojan/shadowsocks, user:pass for socks/http/naive, uuid:password for tuic, username:password for mieru, or PrivateKey for wireguard/amneziawg. For a 2022-blake3-* Encryption Method, this must be the exact-length base64 PSK that method requires, not an arbitrary password. Not used for freedom."),
        ss_method=_("Encryption method. The 2022-blake3-* methods require the password above to be an exact-length base64 pre-shared key (16 bytes for aes-128-gcm, 32 bytes for aes-256-gcm/chacha20-poly1305) - an arbitrary password will fail to connect."),
        peer_public_key=_("The remote peer's PublicKey - same value as [Peer] PublicKey in a WireGuard/AmneziaWG .conf."),
        preshared_key=_("The remote peer's PresharedKey, if it has one - same value as [Peer] PresharedKey in an AmneziaWG .conf. Leave blank if not used."),
        local_address=_("This tunnel's own address, same as [Interface] Address in a WireGuard/AmneziaWG .conf, e.g. \"10.0.0.2/32\"."),
        dns=_("Optional, same as [Interface] DNS in an AmneziaWG .conf."),
        jc=_("AmneziaWG obfuscation - number of junk packets sent before the handshake. Leave blank for a plain (non-obfuscated) tunnel."),
        jmin=_("AmneziaWG obfuscation - minimum junk packet size in bytes."),
        jmax=_("AmneziaWG obfuscation - maximum junk packet size in bytes."),
        reality_public_key=_("Required for Security=reality - the remote server's Reality public key (pbk)."),
        reality_short_id=_("Required for Security=reality - the remote server's Reality short ID (sid)."),
        sockopt_mark=_("Linux SO_MARK (fwmark) applied to this outbound's sockets. Leave blank unless you use policy routing."),
        sockopt_dialer_proxy=_("Chain through another Outbound's Tag before dialing this one."),
        sockopt_domain_strategy=_('e.g. "UseIP", "UseIPv4", "UseIPv6", "AsIs". Leave blank for the default.'),
        sockopt_interface=_("Bind outbound connections to this network interface (Linux SO_BINDTODEVICE)."),
        hysteria_obfs_password=_("hysteria2 Salamander obfuscation password. Must match the server's obfs password. Leave blank if the server has no obfs."),
        hysteria_up_mbps=_("Optional hysteria2 upload bandwidth hint in Mbps. Leave blank to let congestion control decide."),
        hysteria_down_mbps=_("Optional hysteria2 download bandwidth hint in Mbps. Leave blank to let congestion control decide."),
        awg_conf=_("Optional. Paste a complete AmneziaWG .conf here (contents of your amnezia_for_awg.conf); when set, it replaces the [Interface]/[Peer] block generated from the fields above. `Table = off` is added automatically if missing so the server default route isn't hijacked. Leave blank to build the .conf from the discrete fields instead."),
        awg_h1=_("AmneziaWG obfuscation - replaces WireGuard's real message-1 type byte on the wire. A single value or a min-max range (e.g. \"5-10\"). Leave blank for no header obfuscation."),
        awg_h2=_("AmneziaWG obfuscation - same as H1, for message type 2."),
        awg_h3=_("AmneziaWG obfuscation - same as H1, for message type 3."),
        awg_h4=_("AmneziaWG obfuscation - same as H1, for message type 4."),
        awg_s1=_("AmneziaWG obfuscation - init-packet magic byte size 1."),
        awg_s2=_("AmneziaWG obfuscation - init-packet magic byte size 2."),
        awg_s3=_("AmneziaWG obfuscation - init-packet magic byte size 3."),
        awg_s4=_("AmneziaWG obfuscation - init-packet magic byte size 4."),
        awg_i1=_("AmneziaWG obfuscation - special-junk pattern I1."),
        awg_i2=_("AmneziaWG obfuscation - special-junk pattern I2."),
        awg_i3=_("AmneziaWG obfuscation - special-junk pattern I3."),
        awg_i4=_("AmneziaWG obfuscation - special-junk pattern I4."),
        awg_i5=_("AmneziaWG obfuscation - special-junk pattern I5."),
        tuic_congestion_control=_("TUIC congestion control algorithm. sing-box only - xray-core has no TUIC dialer, so this outbound is dropped (blackholed) while the panel's core is Xray."),
        mieru_transport=_("Mieru's underlying transport protocol. sing-box only - xray-core has no Mieru dialer, so this outbound is dropped (blackholed) while the panel's core is Xray."),
        mieru_multiplexing=_("Mieru's multiplexing level - higher levels trade some latency for better throughput/obfuscation."),
        extra_json=_('Optional. Deep-merged on top of the generated outbound JSON for anything the form above can\'t express, '
                      'e.g. {"streamSettings": {"sockopt": {"dialerProxy": "another-tag"}}} to chain through yet another outbound.'),
    )

    form_extra_fields = {
        "ss_method": wtf.SelectField(
            _("Encryption Method (shadowsocks)"),
            choices=[(m, m) for m in [
                "chacha20-ietf-poly1305", "aes-256-gcm", "aes-128-gcm",
                "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305",
            ]],
        ),
        "tuic_congestion_control": wtf.SelectField(
            _("Congestion Control (TUIC)"),
            choices=[(m, m) for m in ["cubic", "bbr", "new_reno"]],
        ),
        "mieru_transport": wtf.SelectField(
            _("Transport (Mieru)"),
            choices=[("tcp", "TCP"), ("udp", "UDP")],
        ),
        "mieru_multiplexing": wtf.SelectField(
            _("Multiplexing (Mieru)"),
            choices=[(m, m) for m in [
                "MULTIPLEXING_OFF", "MULTIPLEXING_LOW", "MULTIPLEXING_MIDDLE", "MULTIPLEXING_HIGH",
            ]],
        ),
        "protocol_field_script": _ScriptField(label=""),
    }

    form_widget_args = {
        'extra_json': {'rows': 4},
    }

    # The protocol dropdown is restricted to the approved set only
    # (vmess/vless/trojan/shadowsocks/amneziawg/hysteria/socks/http/naive/
    # tuic/mieru).
    # OutboundProtocol still defines wireguard/freedom because existing rows
    # and internal fallbacks reference them, but they're not offered here:
    # wireguard is retired in favor of amneziawg, and freedom (plain direct)
    # isn't a "custom outbound" an admin needs - the built-in freedom tag is
    # already available in Routing Rules. A row already saved with one of
    # those protocols is untouched; it just can't be re-selected if edited.
    _ALLOWED_PROTOCOLS = [
        OutboundProtocol.vmess, OutboundProtocol.vless, OutboundProtocol.trojan,
        OutboundProtocol.shadowsocks, OutboundProtocol.amneziawg, OutboundProtocol.hysteria,
        OutboundProtocol.socks, OutboundProtocol.http, OutboundProtocol.naive,
        OutboundProtocol.tuic, OutboundProtocol.mieru,
    ]
    form_choices = {
        'protocol': [(p.value, p.value) for p in _ALLOWED_PROTOCOLS],
    }

    can_export = False
    column_sortable_list = ["tag", "protocol"]

    def is_accessible(self):
        if login_required(roles={Role.super_admin}, permissions={Permission.manage_settings})(lambda: True)() != True:
            return False
        return True

    def create_form(self, obj=None):
        return self._disable_select2(super().create_form(obj))

    def edit_form(self, obj=None):
        return self._disable_select2(super().edit_form(obj))

    def on_model_change(self, form, model, is_created):
        model.child_id = Child.current().id

    def after_model_change(self, form, model, is_created):
        hutils.apply_scope.mark_dirty(hutils.apply_scope.OUTBOUND_CHANGE_SUBSYSTEMS)
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
