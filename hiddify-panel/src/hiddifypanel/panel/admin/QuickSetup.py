import re
import flask_babel
import uuid
# from flask_babelex import lazy_gettext as _
from flask import render_template, g, request
from flask_babel import gettext as _
from markupsafe import Markup
import wtforms as wtf
from flask_wtf import FlaskForm
from flask_bootstrap import SwitchField
from hiddifypanel.panel import hiddify
from flask_classful import FlaskView
from wtforms.validators import ValidationError, Length, InputRequired
# from gettext import gettext as _

from hiddifypanel.models import Domain, DomainType, StrConfig, ConfigEnum, get_hconfigs
from hiddifypanel.database import db
from hiddifypanel.auth import login_required
from hiddifypanel import hutils
from hiddifypanel.models import *


class QuickSetup(FlaskView):
    decorators = [login_required({Role.super_admin})]

    def current_form(self, step=None, empty=False, next=False):
        step = int(step or request.form.get("step") or request.args.get('step', "1"))
        if next:
            step = step + 1
        form = {1: get_lang_form,
                2: get_password_form,
                3: get_quick_setup_form,
                4: get_proxy_form}

        return form[step](empty=empty or next)

    def index(self):

        return render_template(
            'quick_setup.html',
            form=self.current_form(),
            # ipv4=hutils.network.get_ip_str(4),
            # ipv6=hutils.network.get_ip_str(6),
            admin_link=admin_link(),
            show_domain_info=True)

    def post(self):
        if request.args.get('changepw') == "true":
            AdminUser.current_admin_or_owner().uuid = str(uuid.uuid4())
            # AdminUser.current_admin_or_owner().password = hutils.random.get_random_password()
            db.session.commit()

        set_hconfig(ConfigEnum.first_setup, False)
        form = self.current_form()
        if not form.validate_on_submit() or form.step.data not in ["1", "2", "3","4"]:
            hutils.flask.flash(_('config.validation-error'), 'danger')
            return render_template(
                'quick_setup.html', form=form,
                admin_link=admin_link(),
                ipv4=hutils.network.get_ip_str(4),
                ipv6=hutils.network.get_ip_str(6),
                show_domain_info=False)
        return form.post(self)


def get_lang_form(empty=False):
    class LangForm(FlaskForm):
        step = wtf.HiddenField(default="1")
        admin_lang = wtf.SelectField(
            _("config.admin_lang.label"), choices=[("en", _("lang.en")), ("fa", _("lang.fa")), ("pt", _("lang.pt")), ("zh", _("lang.zh")), ("ru", _("lang.ru")), ("my", _("lang.my"))],
            description=_("config.admin_lang.description"),
            default=hconfig(ConfigEnum.admin_lang))
        # lang=wtf.SelectField(_("config.lang.label"),choices=[("en",_("lang.en")),("fa",_("lang.fa"))],description=_("config.lang.description"),default=hconfig(ConfigEnum.lang))
        country = wtf.SelectField(
            _("config.country.label"), choices=[("ir", _("Iran")), ("zh", _("China")), ("ru", _("Russia")),  ("other", "Others")],
            description=_("config.country.description"),
            default=hconfig(ConfigEnum.country))
        lang_submit = wtf.SubmitField(_('Submit'))

        def post(self, view):
            set_hconfig(ConfigEnum.lang, self.admin_lang.data)
            set_hconfig(ConfigEnum.admin_lang, self.admin_lang.data)
            set_hconfig(ConfigEnum.country, self.country.data)

            flask_babel.refresh()
            hutils.flask.flash((_('quicksetup.setlang.success')), 'success')

            return render_template(
                'quick_setup.html', form=view.current_form(next=True),
                # admin_link=admin_link(),
                # ipv4=hutils.network.get_ip_str(4),
                # ipv6=hutils.network.get_ip_str(6),
                show_domain_info=False)

    form = LangForm(None)if empty else LangForm()
    form.step.data = "1"
    return form


def get_password_form(empty=False):
    class PasswordForm(FlaskForm):
        step = wtf.HiddenField(default="1")
        admin_username = wtf.StringField(
            _("Username"),
            description=_("Used to log in to the admin panel."),
            default=(AdminUser.current_admin_or_owner().username or 'admin'),
            validators=[
                InputRequired(message=_("Username is required.")),
                Length(min=3, max=100, message=_("Username must be between 3 and 100 characters.")),
                validate_username_unique,
            ])
        admin_pass = wtf.PasswordField(
            _("user.password.title"),
            description=_("user.password.description"),
            default="admin",validators=[

                InputRequired(message=_("user.password.validation-required")),
                Length(min=3, message=_("user.password.validation-lenght"))

            ])
        password_submit = wtf.SubmitField(_('Submit'))

        def post(self, view):
            admin = AdminUser.current_admin_or_owner()
            admin.username = self.admin_username.data.strip()
            admin.update_password(self.admin_pass.data)

            return render_template(
                'quick_setup.html', form=view.current_form(next=True),
                admin_link=admin_link(),
                ipv4=hutils.network.get_ip_str(4),
                ipv6=hutils.network.get_ip_str(6),
                show_domain_info=False)

    form = PasswordForm(None)if empty else PasswordForm()
    form.step.data = "2"
    return form


def validate_username_unique(form, field):
    admin = AdminUser.current_admin_or_owner()
    # Query directly instead of temporarily assigning field.data onto the
    # live tracked `admin` instance - excluding admin.id here means this
    # only flags a genuine collision with a *different* admin, not the
    # unchanged value of this same one.
    with db.session.no_autoflush:
        existing = AdminUser.query.filter(
            AdminUser.username == field.data.strip(),
            AdminUser.id != admin.id,
        ).first()
    if existing:
        raise ValidationError(_("An admin with this username already exists."))


def get_proxy_form(empty=False):
    class ProxyForm(FlaskForm):
        step = wtf.HiddenField(default="3")

        def post(self, view):

            for k, vs in self.data.items():
                ek = ConfigEnum[k]
                if ek != ConfigEnum.not_found:
                    set_hconfig(ek, vs, commit=False)

            db.session.commit()
            # print(cat,vs)
            hutils.proxy.get_proxies.invalidate_all()
            if hutils.node.is_child():
                hutils.node.run_node_op_in_bg(hutils.node.child.sync_with_parent, *[hutils.node.child.SyncFields.hconfigs])

            from .Actions import Actions
            return Actions().reinstall(domain_changed=True)
    # Toggles we want pinned adjacent to each other regardless of DB
    # insertion order (e.g. WireGuard next to SSH Proxy); everything else
    # falls back to grouping by its ConfigCategory.
    pinned_order = [ConfigEnum.wireguard_enable, ConfigEnum.ssh_server_enable]

    def _proxy_toggle_sort_key(cf):
        if cf.key in pinned_order:
            return (0, pinned_order.index(cf.key))
        # ConfigEnum uses a custom FastEnum metaclass with no ordering
        # support (unlike a plain StrEnum) - cf.key.name is the same
        # member's plain string name, which sorts fine.
        return (1, cf.key.category, cf.key.name)

    boolconfigs = sorted(
        BoolConfig.query.filter(BoolConfig.child_id == Child.current().id).all(),
        key=_proxy_toggle_sort_key,
    )

    for cf in boolconfigs:
        if cf.key.category == 'hidden':
            continue
        if cf.key.startswith("sub_") or cf.key.startswith("mux_"):
            continue
        # wireguard_enable: retired in favor of AmneziaWG - forced off by
        # migration _v127, excluded here so there's no toggle to turn it
        # back on.
        if not cf.key.endswith("_enable") or cf.key in [ConfigEnum.hysteria_obfs_enable, ConfigEnum.tls_padding_enable, ConfigEnum.wireguard_enable]:
            continue
        
        field = SwitchField(_(f'config.{cf.key}.label'), default=cf.value, description=_(f'config.{cf.key}.description'))
        setattr(ProxyForm, f'{cf.key}', field)
    setattr(ProxyForm, "submit_global", wtf.fields.SubmitField(_('Submit')))
    form = ProxyForm(None) if empty else ProxyForm()
    form.step.data = "4"
    return form


def get_quick_setup_form(empty=False):
    def get_used_domains():
        configs = get_hconfigs()
        domains = []
        for c in configs:
            if "domain" in c:
                domains.append(configs[c])
        for d in Domain.query.all():
            domains.append(d.domain)
        return domains

    class BasicConfigs(FlaskForm):
        step = wtf.HiddenField(default="2")
        domain_regex = "^([A-Za-z0-9\\-\\.]+\\.[a-zA-Z]{2,})$"

        domain_validators = [
            wtf.validators.Regexp(domain_regex, re.IGNORECASE, _("config.Invalid_domain")),
            validate_domain,
            validate_domain_not_conflicting(DomainType.direct),
            wtf.validators.NoneOf([c.value.lower() for c in StrConfig.query.all() if "fakedomain" in c.key and c.key != ConfigEnum.decoy_domain], _("config.Domain_already_used"))]

        cdn_domain_validators = [
            wtf.validators.Regexp(f'({domain_regex})|(^$)', re.IGNORECASE, _("config.Invalid_domain")),
            validate_domain_cdn,
            validate_domain_not_conflicting(DomainType.cdn),
            wtf.validators.NoneOf([c.value.lower() for c in StrConfig.query.all() if "fakedomain" in c.key and c.key != ConfigEnum.decoy_domain], _("config.Domain_already_used"))]
        domain = wtf.StringField(
            _("domain.domain"),
            domain_validators,
            description=_("domain.description"),
            render_kw={
                "class": "ltr",
                "pattern": domain_validators[0].regex.pattern,
                "title": domain_validators[0].message,
                "required": "",
                "placeholder": "sub.domain.com"})

        cdn_domain = wtf.StringField(
            _("quicksetup.cdn_domain.label"),
            cdn_domain_validators,
            description=_("quicksetup.cdn_domain.description"),
            render_kw={
                "class": "ltr",
                "pattern": domain_validators[0].regex.pattern,
                "title": domain_validators[0].message,
                "placeholder": "sub.domain.com"})
        # enable_telegram = SwitchField(_("config.telegram_enable.label"), description=_("config.telegram_enable.description"), default=hconfig(ConfigEnum.telegram_enable))
        # enable_firewall = SwitchField(_("config.firewall.label"), description=_("config.firewall.description"), default=hconfig(ConfigEnum.firewall))
        block_iran_sites = SwitchField(_("config.block_iran_sites.label"), description=_(
            "config.block_iran_sites.description"), default=hconfig(ConfigEnum.block_iran_sites))
        # enable_vmess = SwitchField(_("config.vmess_enable.label"), description=_("config.vmess_enable.description"), default=hconfig(ConfigEnum.vmess_enable))
        decoy_domain = wtf.StringField(_("config.decoy_domain.label"), description=_("config.decoy_domain.description"), default=hconfig(
            ConfigEnum.decoy_domain), validators=[wtf.validators.Regexp(domain_regex, re.IGNORECASE, _("config.Invalid_domain")), hutils.flask.validate_domain_exist])
        preferred_domain = wtf.SelectField(
            _('quicksetup.preferred_domain.label'),
            choices=[('direct', _('quicksetup.preferred_domain.direct')), ('cdn', _('quicksetup.preferred_domain.cdn'))],
            description=_('quicksetup.preferred_domain.description'),
            default='direct')
        submit = wtf.SubmitField(_('Submit'))

        def post(self, view):
            Domain.query.filter(Domain.domain == f'{hutils.network.get_ip_str(4)}.sslip.io').delete()
            # Insert-if-missing rather than always-insert: a domain already
            # sitting here in the *same* mode is a harmless resubmission of
            # this same step (e.g. Quick Setup run more than once, or a
            # retried request after a slow/dropped connection) - the
            # validators above already reject a genuine conflict (the
            # domain existing in a *different* mode), so reaching this line
            # with an existing same-mode row means there's nothing to do.
            domain = self.domain.data.lower()
            if not Domain.query.filter(Domain.domain == domain).first():
                db.session.add(Domain(domain=domain, mode=DomainType.direct))
            if self.cdn_domain.data:
                cdn_domain = self.cdn_domain.data.lower()
                if not Domain.query.filter(Domain.domain == cdn_domain).first():
                    db.session.add(Domain(domain=cdn_domain, mode=DomainType.cdn))
            set_hconfig(ConfigEnum.block_iran_sites, self.block_iran_sites.data)
            set_hconfig(ConfigEnum.decoy_domain, self.decoy_domain.data)

            from flask import session as flask_session
            flask_session['qs_preferred_domain'] = self.preferred_domain.data

            return render_template(
                'quick_setup.html', form=view.current_form(next=True),
                admin_link=admin_link(),
                preferred_domain=self.preferred_domain.data,
                show_domain_info=False)

    form = BasicConfigs(None) if empty else BasicConfigs()
    form.step.data = "3"
    return form


def validate_domain_not_conflicting(mode):
    '''A domain already registered in `mode` is a harmless resubmission
    (Quick Setup run more than once, or a retried request) - only a domain
    registered under a *different* mode is a genuine conflict.'''
    def _validator(form, field):
        submitted = (field.data or '').lower()
        if not submitted:
            return
        existing = Domain.query.filter(Domain.domain == submitted).first()
        if existing and existing.mode != mode:
            raise ValidationError(_("config.Domain_already_used"))
    return _validator


def validate_domain(form, field):
    domain = field.data
    dip = hutils.network.get_domain_ip(domain)
    if dip is None:
        raise ValidationError(_("Domain can not be resolved! there is a problem in your domain"))

    myips = hutils.network.get_ips()
      # Fixed: Changed from get_ip(4) to get_ip(6)
    if dip not in myips:
        raise ValidationError(_("Domain (%(domain)s)-> IP=%(domain_ip)s is not matched with your ip=%(server_ip)s which is required in direct mode",
                              server_ip=myips, domain_ip=dip, domain=domain))


def validate_domain_cdn(form, field):
    domain = field.data
    if not domain:
        return
    dip = hutils.network.get_domain_ip(domain)
    if dip is None:
        raise ValidationError(_("Domain can not be resolved! there is a problem in your domain"))

    myips = hutils.network.get_ips()
    if dip in myips:
        raise ValidationError(_("In CDN mode, Domain IP=%(domain_ip)s should be different to your ip=%(server_ip)s",
                              server_ip=myips, domain_ip=dip, domain=domain))


def admin_link():
    domains = Domain.get_domains()
    return hiddify.get_admin_login_link(domains[0] if len(domains) else hutils.network.get_ip_str(4))
