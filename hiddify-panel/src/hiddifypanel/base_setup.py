from flask import request, g
import redis
# from hiddifypanel.cache import cache
from hiddifypanel.models import *

import flask_bootstrap
from flask_babel import Babel
from flask_session import Session

import datetime

from dotenv import dotenv_values
import os
import sys
from werkzeug.middleware.proxy_fix import ProxyFix
from loguru import logger
from sonora.wsgi import grpcWSGI



def init_app(app):
        from hiddifypanel import auth
        app.config["PREFERRED_URL_SCHEME"] = "https"
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1,
        )
        

        secret_file = '/opt/hiddify-manager/hiddify-panel/secret.key'
        try:
            with open(secret_file, 'r') as f:
                app.secret_key = f.read().strip()
        except FileNotFoundError:
            app.secret_key = os.urandom(32).hex()
            try:
                with open(secret_file, 'w') as f:
                    f.write(app.secret_key)
            except Exception:
                pass

        app.servers = {
            'name': 'current',
            'url': '',
        }  # type: ignore
        app.info = {
            'description': 'Hiddify is a free and open source software. It is as it is.',
            'termsOfService': 'https://hiddify.com',
            'contact': {
                'name': 'API Support',
                'url': 'https://www.hiddify.com/support',
                'email': 'panel@hiddify.com'
            },
            'license': {
                'name': 'Creative Commons Zero v1.0 Universal',
                'url': 'https://github.com/hiddify/Hiddify-Manager/blob/main/LICENSE'
            }
        }
        # setup flask server-side session
        # app.config['APPLICATION_ROOT'] = './'
        # app.config['SESSION_COOKIE_DOMAIN'] = '/'
        

        app.jinja_env.line_statement_prefix = '%'
        from hiddifypanel import hutils
        app.jinja_env.filters['b64encode'] = hutils.encode.do_base_64
        app.jinja_env.filters['sanitize_html'] = hutils.encode.sanitize_html
        # raw_csrf_token(): exposes Flask-WTF's session-tied token generator
        # to every template, independent of whether a given view uses a
        # FlaskForm (which already gets CSRF via its own hidden field) - the
        # admin blueprint's raw <form method="post"> actions (see
        # panel/admin/__init__.py's before_request CSRF check) need it too.
        #
        # Deliberately NOT named "csrf_token": flask_adminlte3's vendored
        # flask-admin/adminlte/forms.html renders every ModelView form
        # (DomainAdmin, OutboundAdmin, ...) through form_body(), which does
        # `{% if form.hidden_tag is defined %} ... {% else %} {% if
        # csrf_token %}<input name="csrf_token" .../>{% endif %} ...`.
        # AdminLTEModelView's forms use flask_admin's SecureForm, which has
        # no hidden_tag (that's a FlaskForm-only method), so that branch
        # always runs - and a truthy bare `csrf_token` global made it inject
        # a second, bogus `name="csrf_token"` field ahead of SecureForm's own
        # real one in the same <form>. Both get submitted under the same
        # name, the server reads the first (wrong) value, and SecureForm's
        # own CSRF check fails silently (hidden field, no visible error) -
        # every Domain/Outbound/RoutingRule/... create or edit just
        # redisplayed the form with no indication why. A distinct global
        # name leaves the ambient `csrf_token` undefined again for that
        # vendored template, restoring SecureForm's own token as the only
        # one rendered.
        from flask_wtf.csrf import generate_csrf
        app.jinja_env.globals['raw_csrf_token'] = generate_csrf
        app.view_functions['admin.static'] = {}  # fix bug in apiflask
        flask_bootstrap.Bootstrap4(app)

        def get_locale():
            # Put your logic here. Application can store locale in
            # user profile, cookie, session, etc.
            if "admin" in request.base_url:
                g.locale = hconfig(ConfigEnum.admin_lang) or 'en'
            else:
                g.locale = auth.current_account.lang or hconfig(ConfigEnum.lang) or 'en'
            return g.locale
        app.jinja_env.globals['get_locale'] = get_locale

        @app.context_processor
        def inject_now_year():
            # admin-layout.html's sidebar footer shows this on every admin
            # page, not just the Dashboard (which passes it explicitly) -
            # a context processor avoids every other view needing to
            # remember to pass it in too.
            return {'now_year': datetime.datetime.now().year}
        babel = Babel(app, locale_selector=get_locale)
        
        app.config['SESSION_TYPE'] = 'redis'
        
        app.config['SESSION_REDIS'] = redis.from_url(os.environ['REDIS_URI_MAIN'])
        app.config['SESSION_PERMANENT'] = True
        app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=10)
        app.security_schemes = {  # equals to use config SECURITY_SCHEMES
            'Hiddify-API-Key': {
                'type': 'apiKey',
                'in': 'header',
                'name': 'Hiddify-API-Key',
            }
        }
        Session(app)
        app.wsgi_app = grpcWSGI(app.wsgi_app)