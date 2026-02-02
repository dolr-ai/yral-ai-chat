from __future__ import annotations

import hashlib
import json
import pickle
from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from loguru import logger
from redis import asyncio as aioredis

from src.config import settings
from src.models.internal import CacheStats


class RedisCache:
    """Redis cache implementation"""

    def __init__(self, redis_url: str, default_ttl: int = 300):
        """
        Initialize Redis cache
        
        Args:
            redis_url: Redis connection URL
            default_ttl: Default time-to-live in seconds (default: 300)
        """
        self._redis = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=False)
        self._default_ttl = default_ttl

    async def _run_safe(self, operation: str, method_or_func: str | Callable, *args, **kwargs):
        """Helper to run Redis operations with error handling"""
        try:
            func = getattr(self._redis, method_or_func) if isinstance(method_or_func, str) else method_or_func
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Redis {operation} failed: {e}")
            return None

    async def get(self, key: str) -> object | None:
        """Get value from cache"""
        value = await self._run_safe(f"get {key}", "get", key)
        return pickle.loads(value) if value else None  # noqa: S301

    async def set(self, key: str, value: object, ttl: int | None = None):
        """Set value in cache with TTL"""
        packed_value = pickle.dumps(value)
        await self._run_safe(f"set {key}", "set", key, packed_value, ex=ttl or self._default_ttl)

    async def delete(self, key: str):
        """Delete key from cache"""
        await self._run_safe(f"delete {key}", "delete", key)

    async def clear(self):
        """Clear all cached items"""
        await self._run_safe("flushdb", "flushdb")

    async def cleanup_expired(self) -> int:
        """
        Remove expired items from cache
        (Redis handles this automatically, so this is a no-op or manual scan-del)
        """
        return 0

    async def get_stats(self) -> CacheStats:
        """Get cache statistics"""
        # Note: Getting accurate global stats from Redis is expensive (full scan or info)
        # We'll return basic info if available or placeholders
        try:
            info = await self._redis.info()
            return CacheStats(
                total_items=await self._redis.dbsize(),
                active_items=0, # Hard to track without scan
                expired_items=info.get("expired_keys", 0),
                max_size=0,
                hits=info.get("keyspace_hits", 0),
                misses=info.get("keyspace_misses", 0),
                hit_rate=0.0,
                evictions=info.get("evicted_keys", 0)
            )
        except Exception as e:
            logger.error(f"Redis info failed: {e}")
            return CacheStats(
                total_items=0, active_items=0, expired_items=0, max_size=0,
                hits=0, misses=0, hit_rate=0.0, evictions=0
            )

    async def invalidate_pattern(self, pattern: str):
        """
        Invalidate cache entries matching a pattern
        
        Args:
            pattern: Pattern to match (e.g., 'user:*')
        """
        async def _do_invalidate():
            cur = b"0"
            while True:
                cur, keys = await self._redis.scan(cursor=cur, match=f"*{pattern}*", count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cur in (b"0", 0):
                    break
            return True

        await self._run_safe(f"invalidate_pattern {pattern}", _do_invalidate)

    async def lpush(self, key: str, *values: object):
        """Prepend values to a list"""
        packed_values = [pickle.dumps(v) for v in values]
        await self._run_safe(f"lpush {key}", "lpush", key, *packed_values)

    async def lrange(self, key: str, start: int, end: int) -> list[object]:
        """Get range of values from list"""
        items = await self._run_safe(f"lrange {key}", "lrange", key, start, end)
        if not items:
            return []
        return [pickle.loads(item) for item in items]  # noqa: S301

    async def expire(self, key: str, ttl: int):
        """Set expiration on a key"""
        await self._run_safe(f"expire {key}", "expire", key, ttl)


cache = RedisCache(redis_url=settings.redis_url, default_ttl=300)


def cache_key(*args, **kwargs) -> str:
    """
    Generate cache key from function arguments
    
    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Hashed cache key
    """
    key_data = {
        "args": args,
        "kwargs": kwargs
    }
    key_str = json.dumps(key_data, sort_keys=True, default=str)
    return hashlib.sha256(key_str.encode()).hexdigest()


def cached(ttl: int = 300, key_prefix: str = ""):
    """
    Decorator to cache function results
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
        
    Example:
        @cached(ttl=600, key_prefix="influencers")
        async def list_influencers(limit: int, offset: int):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = f"{key_prefix}:{func.__name__}:{cache_key(*args, **kwargs)}"

            # Redis get is async
            cached_value = await cache.get(key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {key}")
                return cached_value

            logger.debug(f"Cache miss: {key}")
            result = await func(*args, **kwargs)
            
            # Redis set is async
            await cache.set(key, result, ttl=ttl)

            return result

        return wrapper
    return decorator



