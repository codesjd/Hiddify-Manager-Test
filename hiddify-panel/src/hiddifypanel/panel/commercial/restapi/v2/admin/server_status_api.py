from apiflask import Schema, abort
from apiflask.fields import Dict
from flask import current_app as app
from flask import g, request
from flask.views import MethodView

from hiddifypanel import hutils
from hiddifypanel.auth import login_required
from hiddifypanel.models import DailyUsage, Role
from hiddifypanel.models.usage import DailyUsage
from hiddifypanel.panel import hiddify


class ServerStatusOutputSchema(Schema):
    stats = Dict(required=True, metadata={"description": "System stats"})
    usage_history = Dict(required=True, metadata={"description": "System usage history"})


class AdminServerStatusApi(MethodView):
    decorators = [login_required({Role.super_admin, Role.admin, Role.agent})]

    @app.output(ServerStatusOutputSchema)  # type: ignore
    def get(self):
        """System: ServerStatus"""
        dto = ServerStatusOutputSchema()
        top5 = hutils.system.top_processes()
        dto.stats = {  # type: ignore
            "system": hutils.system.system_stats(cpu_percent=top5.get("system_cpu_percent")),
            "top5": top5,
        }
        # Dashboard.py's equivalent view enforces this same subtree check
        # before querying usage history - this REST endpoint didn't, so any
        # admin/agent could read another admin's usage history just by
        # passing their admin_id (which is guessable/sequential).
        admin_id = hutils.convert.to_int(request.args.get("admin_id")) or g.account.id
        if admin_id not in g.account.recursive_sub_admins_ids():
            abort(403, "Access Denied!")
        dto.usage_history = DailyUsage.get_daily_usage_stats(admin_id)  # type: ignore
        return dto
