
import os

import pytest
from redis import asyncio as aioredis

from src.core.cache import RedisCache

# This test requires a running Redis instance.
# It will skip if Redis is not available at the configured URL.
REDIS_TEST_URL = os.getenv("REDIS_TEST_URL", "redis://localhost:6379/0")

async def is_redis_available(url: str) -> bool:
    """Helper to check if Redis is reachable"""
    try:
        client = aioredis.from_url(url)
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False

@pytest.mark.asyncio
async def test_redis_real_integration():
    """Actual integration test against a live Redis server"""
    if not await is_redis_available(REDIS_TEST_URL):
        pytest.skip(f"Redis not available at {REDIS_TEST_URL}")

    cache = RedisCache(REDIS_TEST_URL)
    test_key = "integration_test_key"
    test_data = {"status": "ok", "nested": [1, 2, 3]}

    try:
        # 1. Clean up first
        await cache.delete(test_key)
        
        # 2. Set value
        await cache.set(test_key, test_data, ttl=10)
        
        # 3. Get value
        result = await cache.get(test_key)
        assert result == test_data
        
        # 4. Verify directly with raw redis client (optional but good for 'actual' integration)
        raw_client = aioredis.from_url(REDIS_TEST_URL)
        raw_val = await raw_client.get(test_key)
        assert raw_val is not None # Should be bytes because we use pickle and decode_responses=False
        
        # 5. Delete
        await cache.delete(test_key)
        result_after_del = await cache.get(test_key)
        assert result_after_del is None
        
        await raw_client.aclose()
        
    finally:
        # Cleanup
        await cache.delete(test_key)

@pytest.mark.asyncio
async def test_redis_pattern_invalidation_real(monkeypatch):
    """Test pattern invalidation against a live Redis server"""
    if not await is_redis_available(REDIS_TEST_URL):
        pytest.skip(f"Redis not available at {REDIS_TEST_URL}")

    # The autouse fixture in conftest.py mocks the global cache.
    # We need to patch it back to a real RedisCache for this integration test.
    from src.core.cache import RedisCache, invalidate_cache_pattern
    real_cache = RedisCache(REDIS_TEST_URL)
    monkeypatch.setattr("src.core.cache.cache", real_cache)
    
    # We use a unique prefix for this test to avoid messing with other keys
    prefix = "it_pattern"
    keys = [f"{prefix}:1", f"{prefix}:2", "other:key"]
    
    try:
        for k in keys:
            await real_cache.set(k, "val")
            
        # Invalidate by pattern
        await invalidate_cache_pattern(prefix)
        
        assert await real_cache.get(f"{prefix}:1") is None
        assert await real_cache.get(f"{prefix}:2") is None
        assert await real_cache.get("other:key") == "val" # Should NOT be deleted
        
    finally:
        for k in keys:
            await real_cache.delete(k)
