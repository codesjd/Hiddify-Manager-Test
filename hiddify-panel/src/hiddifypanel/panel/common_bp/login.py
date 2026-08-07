import datetime
import re

import wtforms as wtf
from apiflask import abort
from flask import current_app as app
from flask import flash, g, jsonify, redirect, render_template, request, session
from flask_babel import lazy_gettext as _
from flask_classful import FlaskView, route
from flask_wtf import FlaskForm

import hiddifypanel.panel.hiddify as hiddify
from hiddifypanel import hutils
from hiddifypanel.auth import current_account, login_by_username_or_uuid, login_required, login_user, logout_user
from hiddifypanel.hutils.flask import hurl_for
from hiddifypanel.models import *


class LoginForm(FlaskForm):
    secret_textbox = wtf.fields.StringField(
        _("Username"), default="", description=_("Enter your username"), render_kw={"required": ""}
    )

    password_textbox = wtf.fields.PasswordField(
        _(f"login.password.label"), default="", description=_(f"login.password.description"), render_kw={}
    )
    remember_me = wtf.fields.BooleanField(_("Remember me"), default=True)
    submit = wtf.fields.SubmitField(_("login.button"))


class LoginView(FlaskView):

    # @route("/")
    def index(self, force=None, next=None):
        force_arg = request.args.get("force")
        redirect_arg = request.args.get("redirect")
        username_arg = (request.args.get("user") or "").split("?")[0]
        if not current_account:
            form = LoginForm()
            form.secret_textbox.data = form.secret_textbox.data or username_arg
            return render_template("login.html", form=form, now_year=datetime.datetime.now().year)

            # abort(401, "Unauthorized1")

        if hutils.flask.is_safe_redirect_target(redirect_arg):
            return redirect(redirect_arg)
        if hutils.flask.is_admin_proxy_path() and g.account.role in {Role.super_admin, Role.admin, Role.agent}:
            return redirect(hurl_for("admin.Dashboard:index"))
        # if g.user_agent['is_browser'] and hutils.flask.is_client_proxy_path():
        #     return redirect(hurl_for('client.UserView:index'))

        from hiddifypanel.panel.user import UserView

        return UserView().auto_sub()

    def post(self):
        form = LoginForm()
        if form.validate_on_submit():
            uuid = form.secret_textbox.data.strip()
            if login_by_username_or_uuid(uuid, form.password_textbox.data, hutils.flask.is_admin_proxy_path()):
                # SESSION_PERMANENT defaults every session to a 10-day
                # lifetime already, so "remember me" only has a real effect
                # when explicitly unchecked: falls back to a browser-session
                # cookie that clears on close, instead of persisting 10 days.
                session.permanent = form.remember_me.data
                return redirect(f"/{g.proxy_path}/")
        hutils.flask.flash(_("config.invalid_username_or_password"), "danger")  # type: ignore
        return render_template("login.html", form=LoginForm(), now_year=datetime.datetime.now().year)

    @route("/l/<path:path>/")
    @route("/l/<path:path>")
    @route("/l/")
    @route("/l")
    def basic(self, path=None):
        if path:
            redirect_arg = f"/{g.proxy_path}/{path}"
        else:
            redirect_arg = request.args.get("next")

        if not current_account or (not request.headers.get("Authorization")):
            username = request.authorization.username if request.authorization else g.uuid

            loginurl = hurl_for("common_bp.LoginView:index", next=redirect_arg, user=username)
            if (
                g.user_agent["is_browser"]
                and request.headers.get("Authorization")
                or (current_account and len(username) > 0 and current_account.username != username)
            ):
                hutils.flask.flash(_("Incorrect Password"), "error")  # type: ignore
                logout_user()
                g.__account_store = None
                # hutils.flask.flash(request.authorization.username, 'error')
                return redirect(loginurl)

            return render_template("redirect.html", url=loginurl), 401
            # abort(401, "Unauthorized1")
        if hutils.flask.is_safe_redirect_target(redirect_arg):
            return redirect(redirect_arg)

        if hutils.flask.is_admin_proxy_path() and g.account.role in {Role.super_admin, Role.admin, Role.agent}:
            return redirect(hurl_for("admin.Dashboard:index"))

        if g.user_agent["is_browser"] and hutils.flask.is_client_proxy_path():
            return redirect(hurl_for("client.UserView:index"))

        from hiddifypanel.panel.user import UserView

        # return redirect(url_for("user.")) UserView().auto_sub()

    # @route('/<uuid:uuid>/<path:path>')
    # @route('/<uuid:uuid>/')

    # def uuid(self, uuid, path=''):
    #     proxy_path = hiddify.flask.get_proxy_path_from_url(request.url)
    #     g.__account_store = None
    #     uuid = str(uuid)
    #     if proxy_path == hconfig(ConfigEnum.proxy_path_client):
    #         g.__account_store = User.by_uuid(uuid)
    #         path = f'client/{path}'
    #     elif proxy_path == hconfig(ConfigEnum.proxy_path_admin):
    #         g.__account_store = AdminUser.by_uuid(uuid)
    #     if not g.account:
    #         abort(403)
    #     if not g.user_agent['is_browser'] and proxy_path == hconfig(ConfigEnum.proxy_path_client):
    #         userview = UserView()
    #         if "all.txt" in path:
    #             return userview.all_configs()
    #         if 'singbox.json' in path:
    #             return userview.singbox()
    #         if 'full-singbox.json' in path:
    #             return userview.full_singbox()
    #         if 'clash' in path:
    #             splt = path.split("/")
    #             meta_or_normal = 'meta' if splt[-2] == 'meta' else 'normal'
    #             typ = splt[-1].split('.yml')[0]
    #             return userview.clash_config(meta_or_normal=meta_or_normal, typ=typ)
    #         return userview.force_sub()

    #     login_user(g.account, force=True)

    #     return redirect(f"/{proxy_path}/{path}")

    @route("/logout")
    def logout(self):
        logout_user()
        return redirect(hurl_for("common_bp.LoginView:index"))

    @route("/<secret_uuid>/manifest.webmanifest")
    def create_pwa_manifest(self):
        domain = request.host
        admin_call = hutils.flask.is_admin_panel_call()
        account = AdminUser.by_uuid(g.uuid) if admin_call else User.by_uuid(g.uuid)
        if not admin_call and not account:
            abort(404)
        name = domain if admin_call else account.name
        return jsonify(
            {
                "name": f"Hiddify {name}",
                "short_name": f"{name}"[:12],
                "theme_color": "#f2f4fb",
                "background_color": "#1a1b21",
                "display": "standalone",
                "scope": f"/",
                "start_url": hiddify.get_account_panel_link(account, domain) + "?pwa=true",
                "description": "Hiddify, for a free Internet",
                "orientation": "any",
                "icons": [
                    {
                        "src": hutils.flask.static_url_for(filename="images/hiddify-dark.png"),
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "maskable any",
                    }
                ],
            }
        )
