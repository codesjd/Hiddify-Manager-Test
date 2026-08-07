from apiflask import Schema, abort, fields
from flask import current_app as app
from flask import g
from flask.views import MethodView
from flask_babel import lazy_gettext as _
from loguru import logger

from hiddifypanel import hutils
from hiddifypanel.auth import login_required
from hiddifypanel.models import ConfigEnum, PanelMode, Role, set_hconfig

from .schema import RegisterWithParentInputSchema


class RegisterWithParentApi(MethodView):
    decorators = [login_required({Role.super_admin})]

    # TODO: incomplete (not used)
    @app.input(RegisterWithParentInputSchema, arg_name="data")  # type: ignore
    def post(self, data):
        logger.info(f"Registering panel with parent called by {data['parent_unique_id']}")
        if hutils.node.is_parent() or hutils.node.is_child():
            logger.error("The panel is not in standalone mode nor in child")
            abort(400, "The panel is not in standalone mode nor in child")

        set_hconfig(ConfigEnum.parent_panel, data["parent_panel"])  # type: ignore

        if not hutils.node.child.register_to_parent(data["name"], data["apikey"]):
            logger.error("Child registration to parent failed")
            set_hconfig(ConfigEnum.parent_panel, "")  # type: ignore
            abort(400, _("child.register-failed"))  # type: ignore

        set_hconfig(ConfigEnum.panel_mode, PanelMode.child)  # type: ignore
        logger.info("Registered panel with parent, panel mode is now child")
        return {"status": 200, "msg": "ok"}
