"""Tests for performance optimization utilities."""

import asyncio
import pickle
import time
from unittest.mock import MagicMock, patch

import pytest

from hiddifypanel.hutils.performance import (
    BatchProcessor,
    async_timed,
    cache_result,
    optimize_db_query,
    timed,
)


class TestTimedDecorator:
    """Tests for the timed decorator."""

    def test_timed_sync_function(self):
        """Test timing a synchronous function."""
        with patch("hiddifypanel.hutils.performance.current_app") as mock_app:
            mock_app.logger = MagicMock()

            @timed
            def slow_function():
                time.sleep(0.1)
                return 42

            result = slow_function()

            assert result == 42
            mock_app.logger.info.assert_called_once()
            call_args = mock_app.logger.info.call_args[0][0]
            assert "slow_function" in call_args
            assert "took" in call_args

    @pytest.mark.asyncio
    async def test_timed_async_function(self):
        """Test timing an asynchronous function."""
        with patch("hiddifypanel.hutils.performance.current_app") as mock_app:
            mock_app.logger = MagicMock()

            @async_timed
            async def async_slow_function():
                await asyncio.sleep(0.1)
                return 42

            result = await async_slow_function()

            assert result == 42
            mock_app.logger.info.assert_called_once()
            call_args = mock_app.logger.info.call_args[0][0]
            assert "async_slow_function" in call_args


class TestCacheResultDecorator:
    """Tests for the cache_result decorator."""

    def test_cache_result_hit(self):
        """Test cache hit scenario."""
        with patch("hiddifypanel.hutils.performance.redis_client") as mock_redis:
            mock_redis.get.return_value = pickle.dumps(42)

            call_count = 0

            @cache_result(key_prefix="test", ttl=300)
            def cached_function(x):
                nonlocal call_count
                call_count += 1
                return x * 2

            result1 = cached_function(21)
            result2 = cached_function(21)

            assert result1 == 42
            assert result2 == 42
            assert call_count == 0  # Function never called due to cache
            mock_redis.get.assert_called()

    def test_cache_result_miss(self):
        """Test cache miss scenario."""
        with patch("hiddifypanel.hutils.performance.redis_client") as mock_redis:
            mock_redis.get.return_value = None

            call_count = 0

            @cache_result(key_prefix="test", ttl=300)
            def cached_function(x):
                nonlocal call_count
                call_count += 1
                return x * 2

            result = cached_function(21)

            assert result == 42
            assert call_count == 1
            mock_redis.setex.assert_called_once()


class TestBatchProcessor:
    """Tests for BatchProcessor class."""

    def test_process_batches(self):
        """Test batch processing of items."""
        processor = BatchProcessor(batch_size=10)
        items = list(range(100))

        def batch_processor(batch):
            return [x * 2 for x in batch]

        results = processor.process(items, batch_processor)

        assert len(results) == 100
        assert results[0] == 0
        assert results[-1] == 198

    def test_process_small_batch(self):
        """Test batch processing with fewer items than batch size."""
        processor = BatchProcessor(batch_size=10)
        items = list(range(5))

        def batch_processor(batch):
            return [x * 2 for x in batch]

        results = processor.process(items, batch_processor)

        assert len(results) == 5
        assert results == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_process_async_batches(self):
        """Test async batch processing."""
        processor = BatchProcessor(batch_size=10)
        items = list(range(100))

        async def async_batch_processor(batch):
            await asyncio.sleep(0.01)
            return [x * 2 for x in batch]

        results = await processor.process_async(items, async_batch_processor)

        assert len(results) == 100
        assert results[0] == 0
        assert results[-1] == 198


class TestOptimizeDbQuery:
    """Tests for optimize_db_query decorator."""

    def test_fast_query_no_warning(self):
        """Test that fast queries don't trigger warnings."""
        with patch("hiddifypanel.hutils.performance.current_app") as mock_app:
            mock_app.debug = True
            mock_app.logger = MagicMock()

            @optimize_db_query
            def fast_query():
                time.sleep(0.01)
                return []

            result = fast_query()

            assert result == []
            mock_app.logger.warning.assert_not_called()

    def test_slow_query_triggers_warning(self):
        """Test that slow queries trigger warnings."""
        with patch("hiddifypanel.hutils.performance.current_app") as mock_app:
            mock_app.debug = True
            mock_app.logger = MagicMock()

            @optimize_db_query
            def slow_query():
                time.sleep(1.1)
                return []

            result = slow_query()

            assert result == []
            mock_app.logger.warning.assert_called_once()

    def test_non_debug_mode(self):
        """Test that decorator doesn't log in non-debug mode."""
        with patch("hiddifypanel.hutils.performance.current_app") as mock_app:
            mock_app.debug = False
            mock_app.logger = MagicMock()

            @optimize_db_query
            def any_query():
                return [1, 2, 3]

            result = any_query()

            assert result == [1, 2, 3]
            mock_app.logger.warning.assert_not_called()
