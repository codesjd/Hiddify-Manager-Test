from hiddifypanel import hutils
from hiddifypanel.models.config_enum import ApplyMode
from hiddifypanel.models.role import Role
import wtforms as wtf
from flask_wtf import FlaskForm
from flask_bootstrap import SwitchField
from flask_babel import gettext as _
from flask import render_template, abort, redirect

from hiddifypanel.models import Child, Domain, Proxy, DomainProxyOverride, get_hconfigs
from hiddifypanel.database import db
from hiddifypanel.hutils.flask import hurl_for
from flask_classful import FlaskView
from hiddifypanel.auth import login_required


# Same "other" bucket ProxyAdmin.get_all_proxy_form() uses, so protocols
# without a dedicated transport identity (wireguard/tuic/ssh/hysteria2/
# mieru) don't each get their own single-row group here either.
_PROTO_GROUP = {
    'wireguard': 'other', 'tuic': 'other', 'ssh': 'other', 'hysteria2': 'other', 'mieru': 'other',
}


def _get_applicable_proxies(domain: Domain) -> list[Proxy]:
    """Every proxy row that could plausibly apply to this domain, in either
    direction: the ones currently active for it (via the global protocol
    toggle + Proxy.enable) AND the ones currently off everywhere (so an
    admin can force one on for just this domain). Uses only_enabled=False
    to see the full universe, then is_proxy_valid() to drop combinations
    that could never apply to this domain's mode regardless of any
    override (e.g. a REALITY-only proxy row on a plain direct domain) -
    showing a toggle for something that can never actually take effect
    here would be actively misleading.
    """
    hconfigs = get_hconfigs(domain.child_id)
    universe = hutils.proxy.get_proxies(domain.child_id, only_enabled=False)
    applicable = []
    for proxy in universe:
        # get_valid_proxies() picks the real per-protocol pport
        # (shadowsocks2022_port, ssh_server_port, ...) via a per-proto
        # `options` dict; get_port()'s final catch-all branch does
        # `int(pport)` for every protocol not special-cased earlier
        # (ShadowSocks2022 - l3=custom, proto=ss - is one), so passing None
        # through unconditionally crashes there. The actual port value
        # doesn't matter here - only is_proxy_valid()'s truthiness check on
        # it ("port not defined") does - so a non-zero placeholder is
        # correct and safe for this applicability check.
        port = hutils.proxy.get_port(proxy, hconfigs, domain, domain.effective_tls_port, domain.effective_http_port, 1)
        if hutils.proxy.is_proxy_valid(proxy, domain, port) is None:
            applicable.append(proxy)
    return applicable


def _build_form(domain: Domain, empty=False):
    # Flat SwitchField-per-proxy, same shape quick_setup.html's step 4 form
    # already uses (and the toggle-grid CSS was written for) - ProxyAdmin's
    # own nested FormField(cdn -> proto -> proxy) grouping looks like the
    # more natural fit, but proxy.html never actually renders
    # detailed_config_form at all, so that shape isn't a proven-working
    # pattern in this codebase's current templates. Proxies are pre-sorted
    # by protocol/name so same-protocol rows still land next to each other
    # without needing real nested subforms to get there.
    proxies = _get_applicable_proxies(domain)
    proxies.sort(key=lambda p: (_PROTO_GROUP.get(p.proto, p.proto), p.name))
    baseline_ids = {p.id for p in hutils.proxy.get_proxies(domain.child_id, only_enabled=True)}
    overrides = hutils.proxy.get_domain_proxy_overrides(domain.id)

    class DynamicForm(FlaskForm):
        pass

    for proxy in proxies:
        override = overrides.get(proxy.id)
        baseline = proxy.id in baseline_ids
        # A tri-state override.enable of None means "exists only to carry
        # params, doesn't touch on/off" - fall back to the baseline state.
        current = override.enable if (override and override.enable is not None) else baseline
        field = SwitchField(proxy.name, default=current, description=f"l3:{proxy.l3} transport:{proxy.transport} cdn:{proxy.cdn}")
        setattr(DynamicForm, f"p_{proxy.id}", field)

    setattr(DynamicForm, "submit_detail", wtf.fields.SubmitField(_('Submit')))
    if empty:
        return DynamicForm(None)
    return DynamicForm()


class DomainProxyManage(FlaskView):
    """Per-domain proxy on/off management - the page 'Manage Proxies'
    (a link on each Domain row) leads to. Unlike Settings > Proxies
    (ProxyAdmin, which flips Proxy.enable globally for every domain) this
    only ever reads/writes DomainProxyOverride rows scoped to one domain,
    so switching something off here can never affect any other domain
    sharing the same proxy row.

    Deliberately just enable/disable - the per-domain SNI/host/path/
    fingerprint/etc. field overrides already have their own dedicated
    editor (Domain Proxy Overrides / DomainProxyOverrideAdmin), linked
    from this page's template rather than duplicated here.
    """
    decorators = [login_required({Role.super_admin})]

    def _get_domain(self, domain_id):
        domain = Domain.query.filter(Domain.id == domain_id, Domain.child_id == Child.current().id).first()
        if not domain:
            abort(404)
        return domain

    def index(self, domain_id):
        domain = self._get_domain(domain_id)
        return render_template('domain_proxy_manage.html', domain=domain, form=_build_form(domain))

    def post(self, domain_id):
        domain = self._get_domain(domain_id)
        form = _build_form(domain)
        if not form.validate_on_submit():
            hutils.flask.flash((_('config.validation-error')), 'danger')
            return render_template('domain_proxy_manage.html', domain=domain, form=form)

        baseline_ids = {p.id for p in hutils.proxy.get_proxies(domain.child_id, only_enabled=True)}
        overrides_by_proxy = {o.proxy_id: o for o in DomainProxyOverride.query.filter_by(domain_id=domain.id).all()}

        for field_name, submitted in form.data.items():
            if not field_name.startswith("p_"):
                continue
            try:
                proxy_id = int(field_name.split('_')[-1])
            except ValueError:
                continue
            baseline = proxy_id in baseline_ids
            existing = overrides_by_proxy.get(proxy_id)
            if submitted == baseline:
                # Matches the natural state - no need to force it either
                # way. Keep the row if it still carries param overrides
                # (just stop it from pinning on/off), otherwise drop it
                # entirely so an empty, do-nothing row doesn't linger.
                if existing:
                    if existing.params:
                        existing.enable = None
                    else:
                        db.session.delete(existing)
            else:
                if existing:
                    existing.enable = submitted
                else:
                    db.session.add(DomainProxyOverride(domain_id=domain.id, proxy_id=proxy_id, enable=submitted, params={}))

        db.session.commit()
        hutils.proxy.get_domain_proxy_overrides.invalidate_all()
        hutils.apply_scope.mark_dirty(hutils.apply_scope.CORE_ONLY_SUBSYSTEMS)
        hutils.flask.flash_config_success(restart_mode=ApplyMode.apply_config, domain_changed=False)
        return redirect(hurl_for('admin.DomainProxyManage:index', domain_id=domain.id))
