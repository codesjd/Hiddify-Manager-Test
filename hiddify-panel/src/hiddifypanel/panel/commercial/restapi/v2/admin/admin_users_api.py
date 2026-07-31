from flask import current_app as app
from flask import g
from apiflask import abort
from flask.views import MethodView
from hiddifypanel.auth import login_required
from hiddifypanel.models.role import Role
from .admin_user_api import AdminSchema
from hiddifypanel.models import AdminUser, AdminMode
from apiflask import fields

class AdminUsersApi(MethodView):
    decorators = [login_required({Role.super_admin, Role.admin})]

    @app.output(list[AdminSchema])  # type: ignore
    def get(self):
        """Admin: Get all admins"""
        admins = AdminUser.query.filter(AdminUser.id.in_(g.account.recursive_sub_admins_ids())).all() or abort(404, "You have no admin")
        return [admin.to_schema() for admin in admins]  # type: ignore

    @app.input(AdminSchema, arg_name='data')  # type: ignore
    @app.output(AdminSchema)  # type: ignore
    def post(self, data):
        """Admin: Create an admin"""
        if not (g.account.mode == AdminMode.super_admin or g.account.can_add_admin):
            abort(403, "You don't have permission to add an admin")
        if 'uuid' in data and AdminUser.by_uuid(data['uuid']):
            abort(400, "The admin exists")

        parent = data.get('parent_admin_uuid')
        if parent:
            # A caller-supplied parent_admin_uuid must resolve to an admin
            # the caller actually owns (self or a sub-admin) - otherwise any
            # admin could create a sub-admin under a tree they don't control
            # just by guessing/knowing another admin's uuid. add_or_update()
            # itself only reads parent_admin_uuid, not added_by_uuid, and
            # applies no such check.
            target_admin = AdminUser.by_uuid(parent)
            if not target_admin or target_admin.id not in g.account.recursive_sub_admins_ids():
                abort(403, "You don't have permission to add an admin under this parent")

        admin = AdminUser.add_or_update(**data) or abort(502, "Unknown issue: Admin is not added")
        return admin
