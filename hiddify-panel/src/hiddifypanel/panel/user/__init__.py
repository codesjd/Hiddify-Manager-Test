from .user import UserView
from flask import send_from_directory
from flask import Blueprint
from hiddifypanel.database import db

# from .resources import ProductItemResource, ProductResource
from .user import *
from apiflask import APIBlueprint
bp = APIBlueprint("client", __name__, url_prefix="/<proxy_path>/client/", template_folder="templates", enable_openapi=False)


def send_static(path):
    return send_from_directory('static/assets', path)


def init_app(app):
    @app.route('/<proxy_path>/<user_secret>')
    @app.route('/<proxy_path>/<user_secret>/')
    @app.doc(hide=True)
    def backward_compatibality(user_secret):
        from flask import request, redirect, render_template, g

        # proxy_path is stripped from the view args by the app's
        # url_value_preprocessor and stashed on g.proxy_path instead.
        proxy_path = g.proxy_path

        # Handle non-browser requests by redirecting directly to the client route
        if not g.user_agent.get('is_browser', False):
            return redirect(f"/{proxy_path}/client/")

        # We redirect the browser to the new client UI but first show a link to copy the URL
        user_link = request.url_root.replace('http://', 'https://').rstrip('/') + f"/{proxy_path}/client/"
        return render_template('redirect_to_user.html', user_link=user_link)

    UserView.register(bp, route_base="/")

    # bp.add_url_rule("/", view_func=index)
    # bp.add_url_rule("/<lang>", view_func=index)
    # bp.add_url_rule("/clash/<meta_or_normal>/<mode>.yml", view_func=clash_config)
    # bp.add_url_rule("/clash/<mode>.yml", view_func=clash_config)
    # bp.add_url_rule("/clash/<meta_or_normal>/proxies.yml", view_func=clash_proxies)
    # bp.add_url_rule("/clash/proxies.yml", view_func=clash_proxies)
    # bp.add_url_rule("/all.txt", view_func=all_configs)
    # bp.add_url_rule('/static/<path:path>',view_func=send_static)
    app.register_blueprint(bp)
    app.register_blueprint(bp, name=f"child_{bp.name}", url_prefix="/<proxy_path>/<int:child_id>/")
    app.register_blueprint(bp, name=f"{bp.name}_uuid", url_prefix="/<proxy_path>/<uuid:secret_uuid>/")
    app.register_blueprint(bp, name=f"child_{bp.name}_uuid", url_prefix="/<proxy_path>/<int:child_id>/<uuid:secret_uuid>/")
