from flask_babel import lazy_gettext as _
from .adminlte import AdminLTEModelView
from hiddifypanel.auth import login_required
from hiddifypanel.models import *
from hiddifypanel import hutils


class RoutingRuleAdmin(AdminLTEModelView):
    """Custom Xray routing rules - route specific domains/IPs to a specific
    outbound (built-in ones like freedom/blackhole/WARP, or one of your own
    from the Outbounds page). Evaluated in Priority order (lowest first),
    always before Hiddify's own built-in catch-all rule.
    """
    column_hide_backrefs = False
    column_list = ["priority", "outbound_tag", "domains", "ips", "port", "network", "enable", "comment"]
    form_columns = ["enable", "priority", "outbound_tag", "domains", "ips", "port", "network", "comment"]

    column_labels = {
        "priority": _("Priority"),
        "outbound_tag": _("Outbound Tag"),
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
        domains=_("One per line. Plain domains, \"domain:example.com\", or \"geosite:netflix\" etc."),
        ips=_("One per line. Plain IPs/CIDRs, or \"geoip:ir\" etc."),
        port=_('Optional, e.g. "443" or "1000-2000". Leave empty to match any port.'),
        network=_('Optional: "tcp", "udp", or "tcp,udp". Leave empty to match both.'),
    )

    form_widget_args = {
        'domains': {'rows': 3},
        'ips': {'rows': 3},
    }

    can_export = False
    column_sortable_list = ["priority", "outbound_tag", "enable"]
    column_default_sort = "priority"

    def is_accessible(self):
        if login_required(roles={Role.super_admin}, permissions={Permission.manage_settings})(lambda: True)() != True:
            return False
        return True

    def on_model_change(self, form, model, is_created):
        model.child_id = Child.current().id

    def after_model_change(self, form, model, is_created):
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
