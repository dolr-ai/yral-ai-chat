
import pickle
from unittest.mock import AsyncMock, patch

import pytest

from src.core.cache import RedisCache, cache_key, cached


@pytest.fixture
def mock_redis():
    with patch("redis.asyncio.from_url") as mock_from_url:
        redis_instance = AsyncMock()
        mock_from_url.return_value = redis_instance
        yield redis_instance

@pytest.mark.asyncio
async def test_redis_cache_set_get(mock_redis):
    """Test basic set/get operations with mocking"""
    cache = RedisCache("redis://localhost:6379/0")
    test_key = "test_key"
    test_value = {"data": "hello"}
    
    # Test Set
    await cache.set(test_key, test_value)
    mock_redis.set.assert_called_once()
    args, kwargs = mock_redis.set.call_args
    assert args[0] == test_key
    assert pickle.loads(args[1]) == test_value  # noqa: S301
    assert kwargs["ex"] == 300  # Default TTL
    
    # Test Get
    mock_redis.get.return_value = pickle.dumps(test_value)
    result = await cache.get(test_key)
    assert result == test_value
    mock_redis.get.assert_called_with(test_key)

@pytest.mark.asyncio
async def test_redis_cache_error_handling(mock_redis):
    """Test that cache handles connection errors gracefully without crashing"""
    cache = RedisCache("redis://localhost:6379/0")
    mock_redis.get.side_effect = Exception("Connection refused")
    
    # Should return None and log error instead of raising
    result = await cache.get("any_key")
    assert result is None

@pytest.mark.asyncio
async def test_cached_decorator(mock_redis):
    """Test the @cached decorator logic"""
    # Create a fresh cache instance to avoid global state issues in tests
    # But @cached uses the global 'cache' instance from src.core.cache.
    # We need to patch the global cache or use monkeypatch.
    
    with patch("src.core.cache.cache") as mock_global_cache:
        mock_global_cache.get = AsyncMock(return_value=None)
        mock_global_cache.set = AsyncMock()
        
        call_count = 0
        
        @cached(ttl=100, key_prefix="test")
        async def my_func(a, b):
            nonlocal call_count
            call_count += 1
            return a + b
            
        # First call: Cache miss
        res1 = await my_func(1, 2)
        assert res1 == 3
        assert call_count == 1
        mock_global_cache.get.assert_called_once()
        mock_global_cache.set.assert_called_once()
        
        # Second call: Cache hit
        mock_global_cache.get.return_value = 3
        res2 = await my_func(1, 2)
        assert res2 == 3
        assert call_count == 1  # Should not have incremented

def test_cache_key_consistency():
    """Ensure cache keys are deterministic"""
    key1 = cache_key(1, 2, name="test")
    key2 = cache_key(1, 2, name="test")
    key3 = cache_key(2, 1, name="test")
    
    assert key1 == key2
    assert key1 != key3

@pytest.mark.asyncio
async def test_redis_cache_delete(mock_redis):
    """Test delete operation"""
    cache = RedisCache("redis://localhost:6379/0")
    await cache.delete("delete_me")
    mock_redis.delete.assert_called_with("delete_me")

@pytest.mark.asyncio
async def test_redis_cache_clear(mock_redis):
    """Test clear (flushdb) operation"""
    cache = RedisCache("redis://localhost:6379/0")
    await cache.clear()
    mock_redis.flushdb.assert_called_once()

@pytest.mark.asyncio
async def test_redis_cache_invalidate_pattern(mock_redis):
    """Test pattern invalidation using scan/delete"""
    cache = RedisCache("redis://localhost:6379/0")
    
    # Mock scan results (cursor, keys)
    # First call returns some keys and a second cursor, second call returns no more keys
    mock_redis.scan.side_effect = [
        (b"1", [b"key:1", b"key:2"]),
        (b"0", [b"key:3"])
    ]
    
    await cache.invalidate_pattern("key")
    
    assert mock_redis.scan.call_count == 2
    assert mock_redis.delete.call_count == 2
    mock_redis.delete.assert_any_call(b"key:1", b"key:2")
    mock_redis.delete.assert_any_call(b"key:3")
