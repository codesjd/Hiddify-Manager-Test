from loguru import logger
import socket
from flask_babel import gettext as _
from strenum import StrEnum
from celery import shared_task

from hiddifypanel.models import AdminUser, User, hconfig, ConfigEnum, ChildMode, Domain, Proxy, StrConfig, BoolConfig, Child, ChildMode
from hiddifypanel import hutils
from hiddifypanel.panel import hiddify
from hiddifypanel.panel import usage
from hiddifypanel.database import db
from hiddifypanel.cache import cache
from sqlalchemy.orm import joinedload

# import schemas
from hiddifypanel.panel.commercial.restapi.v2.parent.schema import *
from hiddifypanel.panel.commercial.restapi.v2.child.schema import *
from hiddifypanel.panel.commercial.restapi.v2.admin.schema import AdminSchema
from hiddifypanel.panel.commercial.restapi.v2.admin.schema import UserSchema

from .api_client import NodeApiClient, NodeApiErrorSchema
# region private


def __get_register_data_for_api(name: str, mode: ChildMode) -> RegisterInputSchema:

    register_data = RegisterInputSchema()
    register_data.unique_id = hconfig(ConfigEnum.unique_id)
    register_data.name = name  # type: ignore
    register_data.mode = mode  # type: ignore

    panel_data = RegisterDataSchema()  # type: ignore

    panel_data.admin_users = AdminSchema(many=True).load([admin_user.to_dict() for admin_user in AdminUser.query.all()])
    panel_data.users = UserSchema(many=True).load([user.to_dict(dump_id=True) for user in User.query.all()])
    panel_data.domains = DomainSchema(many=True).load([domain.to_dict() for domain in Domain.query.options(joinedload(Domain.child), joinedload(Domain.show_domains), joinedload(Domain.download_domain)).all()])
    panel_data.proxies = ProxySchema(many=True).load([proxy.to_dict() for proxy in Proxy.query.options(joinedload(Proxy.child)).all()])

    str_configs = HConfigSchema(many=True).load([u.to_dict() for u in StrConfig.query.options(joinedload(StrConfig.child)).all()])
    bool_configs = HConfigSchema(many=True).load([u.to_dict() for u in BoolConfig.query.options(joinedload(BoolConfig.child)).all()])
    panel_data.hconfigs = [*str_configs, *bool_configs]  # type: ignore
    register_data.panel_data = panel_data

    return register_data


class SyncFields(StrEnum):
    domains = 'domains'
    proxies = 'proxies'
    hconfigs = 'hconfigs'


def __get_sync_data_for_api(*fields: SyncFields) -> SyncInputSchema:
    sync_data = SyncInputSchema()

    def get_domains():
        return DomainSchema(many=True).load([domain.to_dict() for domain in Domain.query.options(joinedload(Domain.child), joinedload(Domain.show_domains), joinedload(Domain.download_domain)).all()])

    def get_proxies():
        return ProxySchema(many=True).load([proxy.to_dict() for proxy in Proxy.query.options(joinedload(Proxy.child)).all()])

    def get_hconfigs():
        str_configs = HConfigSchema(many=True).load([u.to_dict() for u in StrConfig.query.options(joinedload(StrConfig.child)).all()])
        bool_configs = HConfigSchema(many=True).load([u.to_dict() for u in BoolConfig.query.options(joinedload(BoolConfig.child)).all()])
        return [*str_configs, *bool_configs]

    if len(fields) == 0:
        sync_data.domains = get_domains()
        sync_data.proxies = get_proxies()
        sync_data.hconfigs = get_hconfigs()
    else:
        for f in fields:
            match f:
                case SyncFields.domains:
                    sync_data.domains = get_domains()
                case SyncFields.proxies:
                    sync_data.proxies = get_proxies()
                case SyncFields.hconfigs:
                    sync_data.hconfigs = get_hconfigs()

    return sync_data


def __get_parent_panel_url() -> str:
    url = 'https://' + f"{hconfig(ConfigEnum.parent_domain).removesuffix('/')}/{hconfig(ConfigEnum.parent_admin_proxy_path).removesuffix('/')}"
    return url

# endregion


def is_registered() -> bool:
    '''Checks if the current parent registered as a child'''
    try:
        logger.debug("Checking if current panel is registered with parent")
        base_url = __get_parent_panel_url()
        if not base_url:
            return False
        payload = ChildStatusInputSchema()
        payload.child_unique_id = hconfig(ConfigEnum.unique_id)

        res = NodeApiClient(base_url).post('/api/v2/parent/status/', payload, ChildStatusOutputSchema)
        if isinstance(res, NodeApiErrorSchema):
            logger.error(f"Error while checking if current panel is registered with parent: {res.msg}")
            return False

        if res['existance']:
            return True
        return False
    except Exception as e:
        logger.error(f"Error while checking if current panel is registered with parent")
        logger.exception(e)
        return False


def register_to_parent(name: str, apikey: str, mode: ChildMode = ChildMode.remote) -> bool:
    # get parent link its format is "https://panel.hiddify.com/<admin_proxy_path>/"
    p_url = __get_parent_panel_url()
    if not p_url:
        logger.error("Parent url is empty")
        return False

    payload = __get_register_data_for_api(name, mode)
    res = NodeApiClient(p_url, apikey).put('/api/v2/parent/register/', payload, RegisterOutputSchema)
    if isinstance(res, NodeApiErrorSchema):
        logger.error(f"Error while registering to parent: {res.msg}")
        return False

    # TODO: change the bulk_register and such methods to accept models instead of dict
    AdminUser.bulk_register(res['admin_users'], commit=False)
    User.bulk_register(res['users'], commit=False)

    # add new child as parent
    db.session.add(  # type: ignore
        Child(unique_id=res['parent_unique_id'], name=socket.gethostname() or res['parent_unique_id'], mode=ChildMode.parent)
    )

    db.session.commit()  # type: ignore

    logger.success("Successfully registered to parent")
    cache.invalidate_all_cached_functions()
    return True


@shared_task(
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,       # exponential: 1s, 2s, 4s, 8s, 16s...
    retry_backoff_max=600,    # capped at 10 minutes between attempts
    retry_jitter=True,        # avoid every child retrying in lockstep
    max_retries=5,
)
def periodic_full_resync_with_parent() -> None:
    """Plan 031 fix: sync_with_parent() (domains/proxies/hconfigs, plus
    usage as a side effect - see below) previously only ran on-demand, from
    admin actions that change config (DomainAdmin/ProxyAdmin/SettingAdmin/
    Actions). If the parent was unreachable during one of those triggers,
    nothing re-attempted the sync until some *unrelated* future config
    change happened to fire it again - unbounded staleness on the parent's
    view of this child, not just a slow retry. Usage sync self-heals from
    this because it pushes an absolute counter (a late catch-up sync
    recovers the whole gap in one delta) - but domain/proxy/config sync
    pushes current *state*, which has no equivalent self-healing property
    without something re-triggering it independently of admin activity.
    This periodic task is exactly that: the same bounded-staleness
    guarantee usage sync gets "for free" from its own periodicity, applied
    to the sync path that didn't have any. Retry-with-backoff (via the
    @shared_task options below) additionally shrinks staleness in the
    common transient-failure case, on top of the periodic floor.
    """
    if not hutils.node.is_child():
        return
    if not sync_with_parent():
        # sync_with_parent() already logs specifics; raise so the
        # @shared_task retry/backoff below actually engages - it only
        # triggers on a raised exception, not a False return, and
        # sync_with_parent()'s bool-return contract is relied on elsewhere
        # (DomainAdmin/ProxyAdmin/Actions), so it isn't changed here.
        raise RuntimeError("periodic_full_resync_with_parent: sync_with_parent() failed")


def sync_with_parent(*fields: SyncFields) -> bool:
    # sync usage first
    if not sync_users_usage_with_parent():
        logger.error("Error while syncing with parent: Failed to sync users usage")
        return False

    p_url = __get_parent_panel_url()
    if not p_url:
        logger.error("Error while syncing with parent: Parent url is empty")
        return False
    payload = __get_sync_data_for_api(*fields)
    res = NodeApiClient(p_url).put('/api/v2/parent/sync/', payload, SyncOutputSchema)
    if isinstance(res, NodeApiErrorSchema):
        logger.error(f"Error while syncing with parent: {res.msg}")
        return False
    AdminUser.bulk_register(res['admin_users'], commit=False, remove=True)
    User.bulk_register(res['users'], commit=False, remove=True)
    db.session.commit()  # type: ignore
    logger.success("Successfully synced with parent")
    cache.invalidate_all_cached_functions()
    return True


def sync_users_usage_with_parent() -> bool:
    p_url = __get_parent_panel_url()
    if not p_url:
        logger.error("Parent url is empty")
        return False

    payload = hutils.node.get_users_usage_data_for_api()
    if payload:
        res = NodeApiClient(p_url).put('/api/v2/parent/usage/', payload, UsageInputOutputSchema)  # type: ignore
        if isinstance(res, NodeApiErrorSchema):
            logger.error(f"Error while syncing users usage with parent: {res.msg}")
            return False

        # parse usages data
        res = hutils.node.convert_usage_api_response_to_dict(res)  # type: ignore
        usage.add_users_usage_uuid(res, hiddify.get_child(None), True)
        logger.success(f"Successfully synced users usage with parent: {res}")

    return True
