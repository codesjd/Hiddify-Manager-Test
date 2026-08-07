from apiflask import APIBlueprint

bp = APIBlueprint("api_user", __name__, url_prefix="/<proxy_path>/api/v2/user/", enable_openapi=True)

bp_uuid = APIBlueprint(
    "api_user_by_uuid", __name__, url_prefix="/<proxy_path>/<uuid:secret_uuid>/api/v2/user/", enable_openapi=True
)


def init_app(app):
    with app.app_context():
        from .apps_api import AppAPI
        from .configs_api import AllConfigsAPI
        from .info_api import InfoAPI
        from .mtproxies import MTProxiesAPI
        from .short_api import ShortAPI

        bp.add_url_rule("/me/", view_func=InfoAPI)
        bp.add_url_rule("/mtproxies/", view_func=MTProxiesAPI)
        bp.add_url_rule("/all-configs/", view_func=AllConfigsAPI)
        bp.add_url_rule("/short/", view_func=ShortAPI)
        bp.add_url_rule("/apps/", view_func=AppAPI)

        bp_uuid.add_url_rule("/me/", view_func=InfoAPI)
        bp_uuid.add_url_rule("/mtproxies/", view_func=MTProxiesAPI)
        bp_uuid.add_url_rule("/all-configs/", view_func=AllConfigsAPI)
        bp_uuid.add_url_rule("/short/", view_func=ShortAPI)
        bp_uuid.add_url_rule("/apps/", view_func=AppAPI)

    app.register_blueprint(bp)
    app.register_blueprint(bp_uuid)
