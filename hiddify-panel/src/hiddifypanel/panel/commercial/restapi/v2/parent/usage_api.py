from apiflask import abort
from flask import current_app as app
from flask import g
from flask.views import MethodView
from loguru import logger

from hiddifypanel.auth import login_required
from hiddifypanel.models import Child
from hiddifypanel.panel.usage import add_users_usage_uuid

from .schema import UsageInputOutputSchema


class UsageApi(MethodView):
    decorators = [login_required(node_auth=True)]

    @app.input(UsageInputOutputSchema, arg_name="data")  # type: ignore
    @app.output(UsageInputOutputSchema)  # type: ignore
    def put(self, data):
        from hiddifypanel import hutils

        child = Child.query.filter(Child.unique_id == Child.node.unique_id).first()
        if not child:
            logger.error("The child does not exist")
            abort(400, "The child does not exist")

        # parse request data
        logger.debug(f"Received Usage data from child: {data}")
        child_usages_data = hutils.node.convert_usage_api_response_to_dict(data)

        # get current usage
        logger.debug("Getting current usage data from parent")
        parent_current_usages_data = hutils.node.convert_usage_api_response_to_dict(UsageInputOutputSchema().dump(hutils.node.get_users_usage_data_for_api()))  # type: ignore

        # calculate usages
        logger.debug("Calculating increased usages")
        increased_usages = self.__calculate_parent_increased_usages(child_usages_data, parent_current_usages_data)
        logger.debug(f"Increased usages: {increased_usages}")

        # add users usage
        if increased_usages:
            logger.info(f"Adding increased usages to parent: {increased_usages}")
            add_users_usage_uuid(increased_usages, child.id)

        return hutils.node.get_users_usage_data_for_api()

    def __calculate_parent_increased_usages(self, child_usages_data: dict, parent_usages_data: dict) -> dict:
        # Iterating parent_usages_data means any uuid the child sent that
        # the parent doesn't recognize is never visited at all - previously
        # silently dropped with no trace, which can hide real node
        # data-corruption or child/parent sync drift. Surface it instead of
        # rejecting the whole batch (a child a few users ahead of a sync is
        # a normal transient state, not necessarily corruption).
        unknown_uuids = set(child_usages_data) - set(parent_usages_data)
        if unknown_uuids:
            logger.warning(
                f"Child sent usage for {len(unknown_uuids)} uuid(s) unknown to parent (ignored): {unknown_uuids}"
            )
        res = {}
        for p_uuid, p_usage in parent_usages_data.items():
            if child_usage := child_usages_data.get(p_uuid):
                if child_usage["usage"] > 0:
                    usage_data = {
                        "usage": child_usage["usage"] - p_usage["usage"],
                        "devices": child_usage["devices"],
                    }
                    if usage_data["usage"] > 0:
                        res[p_uuid] = usage_data
        return res
