from flask.views import MethodView
from flask import current_app as app, g
from apiflask import abort
from hiddifypanel.auth import login_required
from hiddifypanel.models.role import Role
from hiddifypanel.panel import hiddify
from hiddifypanel.drivers import user_driver
from hiddifypanel.models import AdminUser, User
from .user_api import UserSchema, PostUserSchema
from . import has_permission
from apiflask import fields

class UsersApi(MethodView):
    decorators = [login_required({Role.super_admin, Role.admin, Role.agent})]

    @app.output(list[UserSchema])  # type: ignore
    def get(self):
        """User: List users of current admin"""

        users = User.query.filter(User.added_by.in_(g.account.recursive_sub_admins_ids())).all() or abort(404, "You have no user")
        return [user.to_schema() for user in users]  # type: ignore

    @app.input(PostUserSchema, arg_name="data")  # type: ignore
    @app.output(UserSchema)  # type: ignore
    def post(self, data):
        """User: Create a user"""

        if data.get("uuid") and User.by_uuid(data['uuid']):
            abort(400, 'The user exists')

        if not data.get('added_by_uuid'):
            data['added_by_uuid'] = g.account.uuid
        else:
            # A caller-supplied added_by_uuid must resolve to an admin the
            # caller actually owns (self or a sub-admin) - otherwise any
            # admin could create users under a tree they don't control just
            # by guessing/knowing another admin's uuid.
            target_admin = AdminUser.by_uuid(data['added_by_uuid'])
            if not target_admin or target_admin.id not in g.account.recursive_sub_admins_ids():
                abort(403, "You don't have permission to add a user for this admin")

        dbuser = User.add_or_update(**data) or abort(502, "Unknown issue: User is not added")
        user_driver.add_client(dbuser)
        hiddify.quick_apply_users()
        return dbuser.to_schema()
