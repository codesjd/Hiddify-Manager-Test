import wtforms as wtf
from flask_babel import lazy_gettext as _
from .adminlte import AdminLTEModelView
from hiddifypanel.auth import login_required
from hiddifypanel.models import *
from hiddifypanel import hutils


class RoutingRuleAdmin(AdminLTEModelView):
    """Custom Xray routing rules - route specific domains/IPs/inbounds to a
    specific outbound (built-in ones like freedom/blackhole/WARP, or one of
    your own from the Outbounds page). Evaluated in Priority order (lowest
    first), always before Hiddify's own built-in catch-all rule.
    """
    column_hide_backrefs = False
    column_list = ["priority", "outbound_tag", "inbound_tags", "domains", "ips", "port", "network", "enable", "comment"]
    form_columns = ["enable", "priority", "outbound_tag", "inbound_tags", "domains", "ips", "port", "network", "comment"]

    column_labels = {
        "priority": _("Priority"),
        "outbound_tag": _("Outbound Tag"),
        "inbound_tags": _("Match Inbound(s)"),
        "domains": _("Domains"),
        "ips": _("IPs"),
        "port": _("Port"),
        "network": _("Network"),
        "comment": _("Comment"),
        "enable": _("Enable"),
    }
    column_descriptions = dict(
        priority=_("Lower number = checked first. Rules are evaluated in this order; the first match wins."),
        outbound_tag=_("Must match a Tag from the Outbounds page, or a built-in tag: freedom, blackhole, WARP, forbidden_sites."),
        inbound_tags=_("Optional. Match traffic that arrived on these inbounds specifically - covers both xray tags (vless/vmess/"
                        "trojan over a transport, plus Reality per-domain) and, when running singbox, mieru/naive/tuic/hysteria2 "
                        "(only the ones relevant to your current core_type will ever actually match anything). Hiddify shares one "
                        "inbound per protocol+transport across every domain/CDN mode (except Reality, which gets one per domain), "
                        "so a plain protocol entry matches \"vless over ws from anywhere\", not one specific domain/proxy row. "
                        "Combine with Domains below if you need to narrow it further."),
        domains=_("One per line. Plain domains, \"domain:example.com\", or \"geosite:netflix\" etc."),
        ips=_("One per line. Plain IPs/CIDRs, or \"geoip:ir\" etc."),
        port=_('Optional, e.g. "443" or "1000-2000". Leave empty to match any port.'),
        network=_('Optional: "tcp", "udp", or "tcp,udp". Leave empty to match both.'),
    )

    form_widget_args = {
        'domains': {'rows': 3},
        'ips': {'rows': 3},
    }
    form_extra_fields = {
        "inbound_tags": wtf.SelectMultipleField(_("Match Inbound(s)")),
    }

    can_export = False
    column_sortable_list = ["priority", "outbound_tag", "enable"]
    column_default_sort = "priority"

    def is_accessible(self):
        if login_required(roles={Role.super_admin}, permissions={Permission.manage_settings})(lambda: True)() != True:
            return False
        return True

    def create_form(self, obj=None):
        form = super().create_form(obj)
        form.inbound_tags.choices = get_available_inbound_tags()
        return form

    def edit_form(self, obj=None):
        # Choices must be set on every call (GET *and* POST - WTForms
        # validates submitted values against them), but the actual
        # selected values must only ever be prefilled from the DB on GET.
        # on_form_prefill() below is flask-admin's hook for exactly that
        # distinction; doing it here in edit_form() would also run on a
        # successful POST and silently overwrite what the admin just
        # submitted with the old stored value.
        form = super().edit_form(obj)
        form.inbound_tags.choices = get_available_inbound_tags()
        return form

    def on_form_prefill(self, form, id):
        obj = CustomRoutingRule.query.get(id)
        stored = (obj.inbound_tags or '') if obj else ''
        form.inbound_tags.data = [t.strip() for t in stored.split(',') if t.strip()]

    def on_model_change(self, form, model, is_created):
        model.child_id = Child.current().id
        model.inbound_tags = ','.join(form.inbound_tags.data or [])

    def after_model_change(self, form, model, is_created):
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
