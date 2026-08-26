import os
from redis_cache import RedisCache, chunks, compact_dump
import redis
from hiddifypanel.hutils.safe_cache_codec import dumps, loads
from loguru import logger

redis_client = redis.from_url(os.environ.get("REDIS_URI_MAIN", "redis://127.0.0.1:6379"))
# print(os.environ["REDIS_URI_MAIN"])

class CustomRedisCache(RedisCache):
    def __init__(self, redis_client, prefix="rc", serializer=compact_dump, deserializer=loads, key_serializer=None, support_cluster=True, exception_handler=None):
        super().__init__(redis_client, prefix, serializer, deserializer, key_serializer, support_cluster, exception_handler)
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

    def dynamic_ttl_cache(self, ttl_func):
        """
        A decorator that dynamically sets the TTL of a cached function based on its arguments.
        Thread-safe version that creates a new CacheDecorator instance per call.
        """
        def decorator(func):
            import functools
            # Register the base function with 0 TTL to get it tracked in self.cached_functions
            base_cached_func = self.cache(ttl=0)(func)

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Fail-open: the dynamic-TTL path reaches into python-redis-cache's
                # internals (CacheDecorator), so any incompatibility there must
                # degrade to "just run the function uncached" rather than break
                # the caller (this wraps a user-facing path - short links). A
                # Redis hiccup is likewise swallowed by CacheDecorator itself.
                try:
                    ttl = ttl_func(*args, **kwargs)
                    from redis_cache import CacheDecorator
                    cache_decorator = CacheDecorator(
                        redis_client=self.client,
                        prefix=self.prefix,
                        serializer=self.serializer,
                        deserializer=self.deserializer,
                        key_serializer=self.key_serializer,
                        ttl=ttl,
                        limit=0,
                        namespace=f'{func.__module__}.{func.__qualname__}',
                        support_cluster=self.support_cluster,
                        exception_handler=self.exception_handler
                    )
                    return cache_decorator(func)(*args, **kwargs)
                except Exception as err:
                    with logger.contextualize(error=err):
                        logger.warning(f"dynamic_ttl_cache falling back to uncached call for {func.__qualname__}")
                    return func(*args, **kwargs)

            wrapper.invalidate = base_cached_func.invalidate
            wrapper.invalidate_all = base_cached_func.invalidate_all
            return wrapper
        return decorator

    def invalidate_all_cached_functions(self):
        try:
            for f in self.cached_functions:
                f.invalidate_all()
            logger.trace("Invalidating all cached functions")
            chunks_gen = chunks(f'{self.prefix}*', 5000)
            for keys in chunks_gen:
                self.client.delete(*keys)
            logger.trace("Successfully invalidated all cached functions")
            return True
        except Exception as err:
            with logger.contextualize(error=err):
                logger.error("Failed to invalidate all cached functions")
            return False


cache = CustomRedisCache(redis_client=redis_client, prefix="h", serializer=dumps, deserializer=loads)
