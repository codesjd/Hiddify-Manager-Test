from apiflask import abort, fields, Schema
from flask.views import MethodView
from flask import current_app as app, g
from flask_babel import lazy_gettext as _
from loguru import logger

from hiddifypanel.auth import login_required
from hiddifypanel.models import set_hconfig, ConfigEnum, PanelMode, Role
from hiddifypanel import hutils

from .schema import RegisterWithParentInputSchema


class RegisterWithParentApi(MethodView):
    decorators = [login_required({Role.super_admin})]

    @app.input(RegisterWithParentInputSchema, arg_name='data')  # type: ignore
    def post(self, data):
        import asyncio
        logger.info(f"Registering panel with parent called by {data['name']}")
        if hutils.node.is_parent() or hutils.node.is_child():
            logger.error("The panel is already a child or parent")
            abort(400, 'The panel is already a child or parent')

        domain, proxy_path, uuid = hutils.flask.extract_parent_info_from_url(data['parent_panel'])
        if not domain or not proxy_path or not uuid or not asyncio.run(hutils.node.is_panel_active(domain, proxy_path, uuid)):
            logger.error("Invalid parent panel URL")
            abort(400, _('parent.invalid-parent-url'))  # type: ignore

        set_hconfig(ConfigEnum.parent_domain, domain, commit=False)  # type: ignore
        set_hconfig(ConfigEnum.parent_admin_proxy_path, proxy_path, commit=False)  # type: ignore
        set_hconfig(ConfigEnum.parent_panel, data['parent_panel'])  # type: ignore

        if not asyncio.run(hutils.node.child.register_to_parent(data['name'], uuid)):
            logger.error("Child registration to parent failed")
            set_hconfig(ConfigEnum.parent_panel, '')  # type: ignore
            set_hconfig(ConfigEnum.parent_domain, '')  # type: ignore
            set_hconfig(ConfigEnum.parent_admin_proxy_path, '')  # type: ignore
            abort(400, _('child.register-failed'))  # type: ignore

        set_hconfig(ConfigEnum.panel_mode, PanelMode.child)  # type: ignore
        logger.info("Registered panel with parent, panel mode is now child")
        return {'status': 200, 'msg': 'ok'}
