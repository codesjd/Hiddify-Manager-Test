"""Performance optimization utilities for Hiddify Panel."""

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

from flask import current_app
from werkzeug.local import LocalProxy

redis_client = LocalProxy(lambda: getattr(current_app, "redis", None)) if current_app else None

T = TypeVar("T")


def timed(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to measure execution time of a function."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        current_app.logger.info(f"{func.__name__} took {end - start:.4f}s")
        return result

    return wrapper


def async_timed(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to measure execution time of an async function."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        end = time.perf_counter()
        current_app.logger.info(f"{func.__name__} took {end - start:.4f}s")
        return result

    return wrapper


def cache_result(key_prefix: str, ttl: int = 300) -> Callable[..., Any]:
    """Decorator to cache function results in Redis.

    Args:
        key_prefix: Prefix for Redis cache key
        ttl: Time-to-live in seconds (default: 300)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Generate cache key from function name and arguments
            arg_str = "_".join(str(a) for a in args)
            cache_key = f"{key_prefix}:{func.__name__}:{arg_str}"

            # Try to get from cache
            if redis_client:
                try:
                    cached = redis_client.get(cache_key)
                    if cached:
                        import pickle

                        return pickle.loads(cached)
                except Exception:
                    pass

            # Execute function and cache result
            result = func(*args, **kwargs)

            if redis_client:
                try:
                    import pickle

                    redis_client.setex(cache_key, ttl, pickle.dumps(result))
                except Exception:
                    pass

            return result

        return wrapper

    return decorator


async def async_cache_result(key_prefix: str, ttl: int = 300) -> Callable[..., Any]:
    """Async decorator to cache function results in Redis."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            arg_str = "_".join(str(a) for a in args)
            cache_key = f"{key_prefix}:{func.__name__}:{arg_str}"

            if redis_client:
                try:
                    cached = await redis_client.get(cache_key)
                    if cached:
                        import pickle

                        return pickle.loads(cached)
                except Exception:
                    pass

            result = await func(*args, **kwargs)

            if redis_client:
                try:
                    import pickle

                    await redis_client.setex(cache_key, ttl, pickle.dumps(result))
                except Exception:
                    pass

            return result

        return wrapper

    return decorator


class BatchProcessor:
    """Process items in batches to optimize database operations."""

    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size

    def process(self, items: list[Any], processor: Callable[[list[Any]], Any]) -> list[Any]:
        """Process items in batches."""
        results = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]
            result = processor(batch)
            if result:
                results.extend(result if isinstance(result, list) else [result])
        return results

    async def process_async(self, items: list[Any], processor: Callable[[list[Any]], Any]) -> list[Any]:
        """Process items in batches asynchronously."""
        results = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]
            result = await processor(batch)
            if result:
                results.extend(result if isinstance(result, list) else [result])
        return results


def optimize_db_query(query_func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to add query optimization hints."""

    @functools.wraps(query_func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        # Enable query logging in debug mode
        if current_app.debug:
            start = time.perf_counter()
            result = query_func(*args, **kwargs)
            duration = time.perf_counter() - start
            if duration > 1.0:  # Log slow queries (>1s)
                current_app.logger.warning(f"Slow query detected: {query_func.__name__} took {duration:.2f}s")
            return result
        return query_func(*args, **kwargs)

    return wrapper
