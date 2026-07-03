from flask import render_template, request, g, redirect
from hiddifypanel.hutils.flask import hurl_for
from flask_classful import FlaskView, route
from flask_babel import lazy_gettext as _
from apiflask import abort
from sqlalchemy import func as sa_func
import datetime


from hiddifypanel.auth import login_required
from hiddifypanel.database import db
from hiddifypanel.panel import hiddify
from hiddifypanel.models import *
from hiddifypanel.models import ONE_GIG
from hiddifypanel import hutils
import hiddifypanel


def _sparkline_points(values: list, w: int = 200, h: int = 40, pad: int = 4) -> dict:
    """SVG polyline points for a sparkline, plus a filled-area polygon under
    the line - same normalization the design reference's spark() does
    client-side, computed server-side here since the data is real and
    static per page load (no need to ship the raw series and recompute in
    JS)."""
    if not values:
        values = [0]
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    step = (w - pad * 2) / max(1, len(values) - 1)
    pts = []
    for i, v in enumerate(values):
        x = pad + i * step
        y = h - pad - (v - lo) / rng * (h - pad * 2)
        pts.append(f"{x:.1f},{y:.1f}")
    line = " ".join(pts)
    fill = f"{pad},{h} " + line + f" {w - pad},{h}"
    return {"line": line, "fill": fill}


def _gauge_dash(pct: float, r: int) -> str:
    """SVG stroke-dasharray for a ring gauge showing `pct`% around a circle
    of radius `r` (rounded stroke cap, drawn from -90deg in the template)."""
    import math
    # total_usage_gb/total_quota_gb (the only caller that can hit this) come
    # from SQL SUM() aggregates over decimal.Decimal-typed DB columns, unlike
    # every other gauge's plain-float psutil reading - Python refuses to mix
    # float and Decimal in arithmetic, so this needs an explicit cast.
    pct = max(0, min(100, float(pct)))
    c = 2 * math.pi * r
    return f"{c * pct / 100:.1f} {c:.1f}"


class Dashboard(FlaskView):

    @login_required(roles={Role.super_admin, Role.admin, Role.agent})
    def index(self):
        if hconfig(ConfigEnum.first_setup):
            return redirect(hurl_for("admin.QuickSetup:index"))

        if hutils.utils.is_panel_outdated():
            hutils.flask.flash(_('outdated_panel'), "danger")  # type: ignore

        childs = None
        admin_id = request.args.get("admin_id") or g.account.id
        if admin_id not in g.account.recursive_sub_admins_ids():
            abort(403, _("Access Denied!"))

        child_id = request.args.get("child_id") or None
        user_query = User.query
        if admin_id:
            user_query = user_query.filter(User.added_by == admin_id)
        if hutils.node.is_parent():
            childs = Child.query.filter(Child.id != 0).all()
            for c in childs:
                c.is_active = False
                for d in c.domains:
                    d.is_active = hutils.node.parent.is_child_domain_active(c, d)
                    if d.is_active:
                        c.is_active = True

        def_user = None if len(User.query.all()) > 1 else User.query.filter(User.name == 'default').first()
        domains = Domain.get_domains()
        sslip_domains = [d.domain for d in domains if "sslip.io" in d.domain]

        if def_user and sslip_domains:
            quick_setup = hurl_for("admin.QuickSetup:index")
            hutils.flask.flash((_('admin.incomplete_setup_warning', quick_setup=quick_setup)), 'warning')  # type: ignore
            if hutils.node.is_parent():
                hutils.flask.flash(
                    _("Please understand that parent panel is under test and the plan and the condition of use maybe change at anytime."), "danger")  # type: ignore
        elif len(sslip_domains):
            hutils.flask.flash((_('It seems that you are using default domain (%(domain)s) which is not recommended.',
                               domain=sslip_domains[0])), 'warning')  # type: ignore
            if hutils.node.is_parent():
                hutils.flask.flash(
                    _("Please understand that parent panel is under test and the plan and the condition of use maybe change at anytime."), "danger")  # type: ignore

    # except:
    #     hutils.flask.flash((_('Error!!!')),'info')

        top5 = hutils.system.top_processes()
        stats = {'system': hutils.system.system_stats(cpu_percent=top5.get('system_cpu_percent')), 'top5': top5}
        usage_history = DailyUsage.get_daily_usage_stats(admin_id, child_id)

        if hutils.node.is_parent():
            # The modern redesign (see index_modern.html) only covers the
            # standard single-panel dashboard per its design brief - parent
            # mode's child-status view (parent_dash.html) is a distinct,
            # separately-scoped screen this redesign doesn't address.
            return render_template('index.html', stats=stats, usage_history=usage_history, childs=childs)

        # 60 days of real per-day usage (bytes) powers both the sparklines
        # and the delta badges on the modern dashboard - one query instead
        # of hand-rolling multiple date-range sums.
        daily_series = DailyUsage.get_recent_daily_series(60, admin_id, child_id)

        def pct_delta(curr, prev):
            if not prev:
                return None
            return round((curr - prev) / prev * 100)

        today_bytes, yesterday_bytes, day_before_bytes = daily_series[-1], daily_series[-2], daily_series[-3]
        monthly_now = sum(daily_series[-30:])
        monthly_prev = sum(daily_series[-60:-30])

        total_quota_bytes = user_query.filter(User.enable == True).with_entities(  # noqa: E712
            sa_func.coalesce(sa_func.sum(User.usage_limit), 0)).scalar() or 0
        total_quota_gb = total_quota_bytes / ONE_GIG

        sys = stats['system']
        total_users = usage_history['total']['users']
        total_usage_gb = usage_history['total']['usage'] / ONE_GIG
        ram_pct = (sys['ram_used'] / sys['ram_total'] * 100) if sys['ram_total'] else 0
        disk_pct = (sys['disk_used'] / sys['disk_total'] * 100) if sys['disk_total'] else 0
        other_disk_gb = max(0, sys['disk_used'] - sys['hiddify_used'])

        usage_cards = [
            {
                'label': _('Today'), 'value': today_bytes / ONE_GIG, 'delta': pct_delta(today_bytes, yesterday_bytes),
                'online': usage_history['today']['online'], 'color': 'accent',
                'spark': _sparkline_points(daily_series[-10:]),
            },
            {
                'label': _('Yesterday'), 'value': yesterday_bytes / ONE_GIG, 'delta': pct_delta(yesterday_bytes, day_before_bytes),
                'online': usage_history['yesterday']['online'], 'color': 'blue',
                'spark': _sparkline_points(daily_series[-11:-1]),
            },
            {
                'label': _('Monthly'), 'value': monthly_now / ONE_GIG, 'delta': pct_delta(monthly_now, monthly_prev),
                'online': usage_history['last_30_days']['online'], 'color': 'teal',
                'spark': _sparkline_points(daily_series[-30:]),
            },
        ]

        cpu_top = [p for p in stats['top5']['cpu'] if p[0].strip()][:3]
        ram_top = [p for p in stats['top5']['ram'] if p[0].strip()][:3]

        gauges = [
            {
                'id': 'cpu',
                'label': _('CPU'), 'sub': f"{sys['num_cpus']} " + str(_('core') if sys['num_cpus'] == 1 else _('cores')),
                'pct': round(sys['cpu_percent']), 'color': 'purple', 'dash': _gauge_dash(sys['cpu_percent'], 34),
                'breakdown': [{'name': name, 'pct': round(val)} for name, val in cpu_top],
            },
            {
                'id': 'ram',
                'label': _('RAM'), 'sub': f"{sys['ram_used']:.1f} / {sys['ram_total']:.1f} GB",
                'pct': round(ram_pct), 'color': 'magenta', 'dash': _gauge_dash(ram_pct, 34),
                'breakdown': [{'name': name, 'pct': round(val / sys['ram_total'] * 100) if sys['ram_total'] else 0} for name, val in ram_top],
            },
            {
                'id': 'disk',
                'label': _('Disk'), 'sub': f"{sys['disk_used']:.1f} / {sys['disk_total']:.1f} GB",
                'pct': round(disk_pct), 'color': 'blue', 'dash': _gauge_dash(disk_pct, 34),
                'breakdown': [
                    {'name': 'Hiddify', 'pct': round(sys['hiddify_used'] / sys['disk_used'] * 100) if sys['disk_used'] else 0},
                    {'name': _('Other'), 'pct': round(other_disk_gb / sys['disk_used'] * 100) if sys['disk_used'] else 0},
                ],
            },
        ]

        return render_template(
            'index_modern.html',
            stats=stats,
            usage_history=usage_history,
            usage_cards=usage_cards,
            gauges=gauges,
            total_quota_gb=total_quota_gb,
            total_usage_gb=total_usage_gb,
            total_dash=_gauge_dash((total_usage_gb / total_quota_gb * 100) if total_quota_gb else 0, 40),
            online_pct=(usage_history['m5']['online'] / total_users * 100) if total_users else 0,
            total_users=total_users,
            now_year=datetime.datetime.now().year,
        )

    @ login_required(roles={Role.super_admin})
    @ route('remove_child', methods=['POST'])
    def remove_child(self):
        child_id = request.form['child_id']
        child = Child.query.filter(Child.id == child_id).first()
        db.session.delete(child)
        db.session.commit()
        hutils.flask.flash(_("child has been removed!"), "success")  # type: ignore
        return self.index()
