import os

import redis
from loguru import logger
from redis_cache import RedisCache, chunks, compact_dump

from hiddifypanel.hutils.safe_cache_codec import dumps, loads

redis_client = redis.from_url(os.environ.get("REDIS_URI_MAIN", "redis://127.0.0.1:6379"))
# print(os.environ["REDIS_URI_MAIN"])


class CustomRedisCache(RedisCache):
    def __init__(
        self,
        redis_client,
        prefix="rc",
        serializer=compact_dump,
        deserializer=loads,
        key_serializer=None,
        support_cluster=True,
        exception_handler=None,
    ):
        super().__init__(
            redis_client, prefix, serializer, deserializer, key_serializer, support_cluster, exception_handler
        )
        self.cached_functions = set()

    def cache(self, ttl=0, limit=0, namespace=None, exception_handler=None):
        res = super().cache(ttl, limit, namespace, exception_handler)
        # python-redis-cache's cached-function wrapper only fails open on
        # reads (a broken client.get() falls back to calling the real
        # function) - invalidate()/invalidate_all() have no exception
        # handling at all, so a Redis hiccup during any set_hconfig() (or
        # any other cache invalidation, anywhere in the app) crashes the
        # whole request with a raw ConnectionError instead of just leaving
        # a stale cache entry to expire on its own via ttl. Wrap both so a
        # flaky/restarting Redis (e.g. mid-install, when Quick Setup's
        # final step itself restarts every service including Redis) can't
        # take down the request that triggered it.
        real_invalidate = res.invalidate
        real_invalidate_all = res.invalidate_all

        def safe_invalidate(*args, **kwargs):
            try:
                return real_invalidate(*args, **kwargs)
            except Exception as err:
                with logger.contextualize(error=err):
                    logger.error(f"Failed to invalidate cache for {res.get_full_prefix()}")
                return False

        def safe_invalidate_all(*args, **kwargs):
            try:
                return real_invalidate_all(*args, **kwargs)
            except Exception as err:
                with logger.contextualize(error=err):
                    logger.error(f"Failed to invalidate_all cache for {res.get_full_prefix()}")
                return False

        res.invalidate = safe_invalidate
        res.invalidate_all = safe_invalidate_all
        self.cached_functions.add(res)
        return res

    def invalidate_all_cached_functions(self):
        try:
            for f in self.cached_functions:
                f.invalidate_all()
            logger.trace("Invalidating all cached functions")
            chunks_gen = chunks(f"{self.prefix}*", 5000)
            for keys in chunks_gen:
                self.client.delete(*keys)
            logger.trace("Successfully invalidated all cached functions")
            return True
        except Exception as err:
            with logger.contextualize(error=err):
                logger.error("Failed to invalidate all cached functions")
            return False


cache = CustomRedisCache(redis_client=redis_client, prefix="h", serializer=dumps, deserializer=loads)
