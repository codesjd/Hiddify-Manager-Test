from apiflask import APIBlueprint

from .login import LoginView

bp = APIBlueprint("common_bp", __name__, url_prefix="/<proxy_path>/", template_folder="templates", enable_openapi=False)


def init_app(app):
    LoginView.register(bp, route_base="/")
    app.register_blueprint(bp)
    app.register_blueprint(bp, name=f"child_{bp.name}", url_prefix="/<proxy_path>/<int:child_id>/")
