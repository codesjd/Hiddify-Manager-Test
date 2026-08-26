import wtforms as wtf
import flask_admin
from flask_admin import expose
from flask import redirect, request
from markupsafe import Markup
from flask_babel import lazy_gettext as _
from .adminlte import AdminLTEModelView
from hiddifypanel.auth import login_required
from hiddifypanel.models import *
from hiddifypanel import hutils


class RoutingRuleAdmin(AdminLTEModelView):
    """Custom Xray routing rules - route specific domains/IPs/inbounds to a
    specific outbound (built-in ones like freedom/blackhole, or one of
    your own from the Outbounds page). Evaluated in Priority order (lowest
    first), always before Hiddify's own built-in catch-all rule.

    Priority is no longer a manually-typed number - it's driven by the
    row's position in this list (top = highest priority) via the move up/
    down arrows in the Priority column, matching how an admin actually
    thinks about rule order. The underlying `priority` integer column is
    unchanged (still what xray/singbox's ORDER BY reads); only *how it's
    edited* changed.
    """
    column_hide_backrefs = False
    list_template = 'model/routingrule_list.html'
    column_list = ["priority", "outbound_tag", "inbound_tags", "domains", "ips", "port", "network", "enable", "comment"]
    form_columns = ["enable", "outbound_tag", "inbound_tags", "domains", "ips", "port", "network",
                    "source_ips", "source_port", "protocols", "user_emails", "comment"]

    column_labels = {
        "priority": _("Priority"),
        "outbound_tag": _("Outbound Tag"),
        "inbound_tags": _("Match Inbound(s)"),
        "domains": _("Domains"),
        "ips": _("IPs"),
        "port": _("Port"),
        "network": _("Network"),
        "source_ips": _("Source IPs"),
        "source_port": _("Source Port"),
        "protocols": _("Protocol"),
        "user_emails": _("User"),
        "comment": _("Comment"),
        "enable": _("Enable"),
    }
    column_descriptions = dict(
        outbound_tag=_("Must match a Tag from the Outbounds page, or a built-in tag: freedom, blackhole. WARP: create an Outbound with Protocol \"amneziawg\" (address=engage.cloudflareclient.com, port=2408) on the Outbounds page, then pick its Tag here."),
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
        source_ips=_("Optional. Match by the client's source IP - one per line, plain IPs/CIDRs or \"geoip:ir\" etc."),
        source_port=_('Optional, e.g. "443" or "1000-2000". Match by the client\'s source port.'),
        protocols=_('Optional. Match sniffed protocol(s), comma-separated: "http", "tls", "quic", "bittorrent". Requires sniffing on the inbound.'),
        user_emails=_("Optional. Match by inbound user email/identifier - one per line."),
    )

    form_widget_args = {
        'domains': {'rows': 3},
        'ips': {'rows': 3},
        'source_ips': {'rows': 3},
        'user_emails': {'rows': 2},
        # inbound_tags is upgraded client-side by update_hiddify_ui() in
        # flaskadmin-layout.html ($.multipleSelect() keyed on this element's
        # id, same as DomainAdmin's show_domains/download_domain). Setting
        # data-role="select2" here made flask-admin's own form.js *also*
        # initialize select2 on the same <select>, and the two widgets
        # fighting over one element broke the dropdown entirely.
    }
    form_extra_fields = {
        "outbound_tag": wtf.SelectField(_("Outbound Tag")),
        "inbound_tags": wtf.SelectMultipleField(_("Match Inbound(s)")),
    }

    can_export = False
    column_sortable_list = ["outbound_tag", "enable"]
    column_default_sort = "priority"

    def _enable_formatter(view, context, model, name):
        return Markup(hutils.flask.hf_status_circle(bool(model.enable)))

    def _priority_formatter(view, context, model, name):
        rules = CustomRoutingRule.query.filter_by(child_id=model.child_id).order_by(CustomRoutingRule.priority.asc()).all()
        ids = [r.id for r in rules]
        idx = ids.index(model.id) if model.id in ids else -1
        up_url = hutils.flask.hurl_for('flask.customroutingrule.move_up', id=model.id)
        down_url = hutils.flask.hurl_for('flask.customroutingrule.move_down', id=model.id)
        up_disabled = 'disabled' if idx <= 0 else ''
        down_disabled = 'disabled' if idx == -1 or idx >= len(ids) - 1 else ''
        return Markup(
            f'<div class="hf-priority-order">'
            f'<a class="hf-priority-btn {up_disabled}" href="{up_url}" title="{_("Move up (higher priority)")}">&uarr;</a>'
            f'<a class="hf-priority-btn {down_disabled}" href="{down_url}" title="{_("Move down (lower priority)")}">&darr;</a>'
            f'</div>'
        )

    column_formatters = {
        "enable": _enable_formatter,
        "priority": _priority_formatter,
    }

    @expose('/move_up/<int:id>')
    def move_up(self, id):
        return self._move(id, -1)

    @expose('/move_down/<int:id>')
    def move_down(self, id):
        return self._move(id, 1)

    def _move(self, id, direction):
        """Swap this rule's priority with its neighbor in evaluation order
        (direction -1 = up/earlier, +1 = down/later). Rules are always
        re-fetched sorted by priority, so a swap here is exactly "move one
        row up/down in the list" regardless of what the underlying integer
        values happen to be."""
        if not login_required(roles={Role.super_admin}, permissions={Permission.manage_settings})(lambda: True)():
            return redirect(hutils.flask.hurl_for('flask.customroutingrule.index_view'))
        model = CustomRoutingRule.query.get(id)
        if model:
            rules = CustomRoutingRule.query.filter_by(child_id=model.child_id).order_by(CustomRoutingRule.priority.asc()).all()
            ids = [r.id for r in rules]
            idx = ids.index(model.id) if model.id in ids else -1
            neighbor_idx = idx + direction
            if idx != -1 and 0 <= neighbor_idx < len(rules):
                neighbor = rules[neighbor_idx]
                model.priority, neighbor.priority = neighbor.priority, model.priority
                db.session.commit()
                build_custom_xray_extra.invalidate_all()
                build_custom_singbox_extra.invalidate_all()
                hutils.apply_scope.mark_dirty(hutils.apply_scope.CORE_ONLY_SUBSYSTEMS)
                hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
        return redirect(request.referrer or hutils.flask.hurl_for('flask.customroutingrule.index_view'))

    def is_accessible(self):
        if login_required(roles={Role.super_admin}, permissions={Permission.manage_settings})(lambda: True)() != True:
            return False
        return True

    def create_form(self, obj=None):
        form = super().create_form(obj)
        form.inbound_tags.choices = get_available_inbound_tags()
        
        choices = [
            ('freedom', 'freedom (Direct)'),
            ('blackhole', 'blackhole (Block)'),
        ]
        outbounds = CustomOutbound.query.filter_by(child_id=Child.current().id, enable=True).all()
        for o in outbounds:
            choices.append((o.tag, o.tag))
        form.outbound_tag.choices = choices
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

        choices = [
            ('freedom', 'freedom (Direct)'),
            ('blackhole', 'blackhole (Block)'),
        ]
        outbounds = CustomOutbound.query.filter_by(child_id=Child.current().id, enable=True).all()
        for o in outbounds:
            choices.append((o.tag, o.tag))
        form.outbound_tag.choices = choices
        return form

    def on_form_prefill(self, form, id):
        obj = CustomRoutingRule.query.get(id)
        stored = (obj.inbound_tags or '') if obj else ''
        form.inbound_tags.data = [t.strip() for t in stored.split(',') if t.strip()]

    def on_model_change(self, form, model, is_created):
        model.child_id = Child.current().id
        # Several choices in inbound_tags.choices can share the same
        # underlying tag (one per enabled Proxy row riding that shared
        # inbound - see get_available_inbound_tags()), so dedupe before
        # storing rather than joining raw.
        model.inbound_tags = ','.join(dict.fromkeys(form.inbound_tags.data or []))
        if is_created:
            # No more manually-typed priority - a new rule always starts at
            # the bottom (lowest priority) of this child's list; the admin
            # moves it up with the arrows if it needs to match earlier.
            last = CustomRoutingRule.query.filter_by(child_id=model.child_id).order_by(CustomRoutingRule.priority.desc()).first()
            model.priority = (last.priority + 10) if last else 10

    def after_model_change(self, form, model, is_created):
        build_custom_xray_extra.invalidate_all()
        build_custom_singbox_extra.invalidate_all()
        hutils.apply_scope.mark_dirty(hutils.apply_scope.CORE_ONLY_SUBSYSTEMS)
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)

    def after_model_delete(self, model):
        build_custom_xray_extra.invalidate_all()
        build_custom_singbox_extra.invalidate_all()
        hutils.apply_scope.mark_dirty(hutils.apply_scope.CORE_ONLY_SUBSYSTEMS)
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)

    def after_model_delete(self, model):
        hutils.apply_scope.mark_dirty(hutils.apply_scope.CORE_ONLY_SUBSYSTEMS)
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
