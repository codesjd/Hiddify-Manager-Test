from typing import Optional, Union, Type
from apiflask import Schema, fields
import asyncio
import traceback
import aiohttp
from loguru import logger
from hiddifypanel.models import hconfig, ConfigEnum


class NodeApiErrorSchema(Schema):
    msg = fields.String(required=True)
    stacktrace = fields.String(required=True)
    code = fields.Integer(required=True)
    reason = fields.String(required=True)


class NodeApiClient():
    def __init__(self, base_url: str, apikey: Optional[str] = None, max_retry: int = 3):
        self.base_url = base_url if base_url.endswith('/') else base_url+'/'
        self.max_retry = max_retry
        self.headers = {'Hiddify-API-Key': apikey or hconfig(ConfigEnum.unique_id)}

    async def __call(self, method: str, path: str, payload: Optional[Schema], output_schema: Type[Union[Schema, dict]]) -> Union[dict, NodeApiErrorSchema]:  # type: ignore
        retry_count = 1
        full_url = self.base_url + path.removeprefix('/')
        timeout = aiohttp.ClientTimeout(total=5)
        # One session per call (matches the old per-request model). The
        # session must be created inside the running loop this coroutine
        # is driven by (asyncio.run at the sync call sites, or the enclosing
        # asyncio.gather).
        async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
            while True:
                # status/reason are only known once a response actually came
                # back; on a pure connection error there is no response, so
                # start them at 0/'' instead of touching an undefined
                # response object (a latent bug in the old requests version).
                status_code = 0
                reason = ''
                try:
                    logger.trace(f"Attempting {method} request to node at {full_url}")

                    kwargs = {}
                    if payload:
                        kwargs['json'] = payload.dump(payload)

                    async with session.request(method, full_url, **kwargs) as response:
                        status_code = response.status
                        reason = response.reason or ''
                        response.raise_for_status()
                        resp = await response.json()

                    if not resp:
                        err = NodeApiErrorSchema()
                        err.msg = 'Empty response'  # type: ignore
                        err.stacktrace = ''  # type: ignore
                        err.code = status_code  # type: ignore
                        err.reason = reason  # type: ignore
                        with logger.contextualize(payload=payload):
                            logger.warning(f"Received empty response from {full_url} with method {method}")
                        return err

                    logger.trace(f"Successfully received response from {full_url}")
                    return resp if output_schema is dict else output_schema().load(resp)  # type: ignore

                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if retry_count >= self.max_retry:
                        stack_trace = traceback.format_exc()
                        # aiohttp response errors carry .status/.message; a
                        # plain connection/timeout error does not, so fall
                        # back to whatever we captured above.
                        code = getattr(e, 'status', status_code) or status_code
                        rsn = getattr(e, 'message', None) or reason or str(e)
                        err = NodeApiErrorSchema()
                        err.msg = str(e)  # type: ignore
                        err.stacktrace = stack_trace  # type: ignore
                        err.code = code  # type: ignore
                        err.reason = rsn  # type: ignore
                        with logger.contextualize(status_code=code, reason=rsn, stack_trace=stack_trace, payload=payload):
                            logger.error(f"HTTP error after {self.max_retry} retries")
                            logger.exception(e)
                        return err

                    logger.warning(f"Error occurred: {e} from {full_url} with method {method}, retrying... ({retry_count}/{self.max_retry})")
                    retry_count += 1
                    await asyncio.sleep(1)

    async def get(self, path: str, output: Type[Union[Schema, dict]]) -> Union[dict, NodeApiErrorSchema]:
        return await self.__call("GET", path, None, output)

    async def post(self, path: str, payload: Optional[Schema], output: Type[Union[Schema, dict]]) -> Union[dict, NodeApiErrorSchema]:
        return await self.__call("POST", path, payload, output)

    async def put(self, path: str, payload: Optional[Schema], output: Type[Union[Schema, dict]]) -> Union[dict, NodeApiErrorSchema]:
        return await self.__call("PUT", path, payload, output)
