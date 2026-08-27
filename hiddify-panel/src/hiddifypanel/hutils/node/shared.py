import threading
from loguru import logger
from typing import Callable
from flask import copy_current_request_context

from hiddifypanel.models import hconfig, ConfigEnum, PanelMode, User
from hiddifypanel.cache import cache
from hiddifypanel.hutils.safe_cache_codec import dumps, loads
from hiddifypanel.panel.commercial.restapi.v2.parent.schema import UsageInputOutputSchema, UsageData
from hiddifypanel.panel.commercial.restapi.v2.panel.schema import PanelInfoOutputSchema
from .api_client import NodeApiClient, NodeApiErrorSchema


def is_child() -> bool:
    return hconfig(ConfigEnum.panel_mode) == PanelMode.child


def is_parent() -> bool:
    return hconfig(ConfigEnum.panel_mode) == PanelMode.parent

# region usage


def get_users_usage_data_for_api() -> UsageInputOutputSchema:
    res = UsageInputOutputSchema()
    res.usages = []  # type: ignore
    for u in User.query.all():
        usage_data = UsageData()
        usage_data.uuid = u.uuid
        usage_data.usage = u.current_usage
        usage_data.devices = u.devices
        res.usages.append(usage_data)  # type: ignore
    return res


def convert_usage_api_response_to_dict(data: dict) -> dict:
    converted = {}
    for i in data['usages']:  # type: ignore
        converted[str(i['uuid'])] = {
            'usage': i['usage'],
            'devices': ','.join(i['devices'])  # type: ignore
        }
    return converted

# endregion

# NodeApiClient is now async (aiohttp), so these can't use the sync
# @cache.cache decorator (it would cache the coroutine object, not the
# awaited result). Cache the result manually against Redis instead, keeping
# the same TTLs the sync-cached versions used. Both reads and writes fail
# open (a Redis hiccup just means a cache miss / no store, never an error),
# and the keys live under the same `h*` prefix so
# cache.invalidate_all_cached_functions() (run on apply/sync) still clears
# them alongside every other cached function.
def _node_cache_get(key: str):
    """Returns (hit, value). hit=False means "not cached" - distinct from a
    cached value that happens to be None/False (redis returns None only on a
    real miss; a stored serialized-None is not None)."""
    try:
        raw = cache.client.get(f"{cache.prefix}:nodeapi:{key}")
        if raw is not None:
            return True, loads(raw)
    except Exception as err:
        with logger.contextualize(error=err):
            logger.trace(f"node cache read failed for {key}")
    return False, None


def _node_cache_set(key: str, value, ttl: int) -> None:
    try:
        cache.client.set(f"{cache.prefix}:nodeapi:{key}", dumps(value), ex=ttl)
    except Exception as err:
        with logger.contextualize(error=err):
            logger.trace(f"node cache write failed for {key}")


async def is_panel_active(domain: str, proxy_path: str, apikey: str | None = None) -> bool:
    ckey = f"is_panel_active:{domain}:{proxy_path}:{apikey or ''}"
    hit, cached = _node_cache_get(ckey)
    if hit:
        return cached
    base_url = f'https://{domain}/{proxy_path}'
    res = await NodeApiClient(base_url, apikey).get('/api/v2/panel/ping/', dict)
    if isinstance(res, NodeApiErrorSchema):
        logger.error(f"Error while checking if panel is active: {res.msg}")
        return False
    active = bool('PONG' in res['msg'])
    logger.debug(f"Panel is {'active' if active else 'not active'}")
    _node_cache_set(ckey, active, ttl=150)
    return active


async def get_panel_info(domain: str, proxy_path: str, apikey: str | None = None) -> dict | None:
    ckey = f"get_panel_info:{domain}:{proxy_path}:{apikey or ''}"
    hit, cached = _node_cache_get(ckey)
    if hit:
        return cached
    base_url = f'https://{domain}/{proxy_path}'
    res = await NodeApiClient(base_url, apikey).get('/api/v2/panel/info/', PanelInfoOutputSchema)
    if isinstance(res, NodeApiErrorSchema):
        logger.error(f"Error while getting panel info from {domain}: {res.msg}")
        return None
    _node_cache_set(ckey, res, ttl=300)
    return res


def run_node_op_in_bg(op: Callable, *args, **kwargs):
    """Run a node operation in a background thread. `op` may be a coroutine
    function (the node client is async now) - in that case drive it to
    completion with asyncio.run inside the worker thread; a plain callable
    is just called."""
    import asyncio
    import inspect

    @copy_current_request_context
    def wrapped_op():
        if inspect.iscoroutinefunction(op):
            asyncio.run(op(*args, **kwargs))
        else:
            res = op(*args, **kwargs)
            if inspect.iscoroutine(res):
                asyncio.run(res)

    threading.Thread(target=wrapped_op).start()
