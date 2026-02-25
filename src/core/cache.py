"""
Caching utilities with in-memory fallback
LRU cache with TTL support and bounded size
"""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from functools import wraps

from loguru import logger

from src.models.internal import CacheStats


class LRUCache:
    """LRU cache with TTL support and maximum size limit"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        Initialize cache

        Args:
            max_size: Maximum number of items in cache (default: 1000)
            default_ttl: Default time-to-live in seconds (default: 300)
        """
        self._cache: OrderedDict[str, tuple[object, float]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, key: str) -> asyncio.Lock:
        """Get or create an asyncio Lock for a specific cache key"""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def cleanup_lock(self, key: str):
        """Remove a lock if it's no longer needed"""
        if key in self._locks and not self._locks[key].locked():
            del self._locks[key]

    def get(self, key: str) -> object | None:
        """
        Get value from cache (LRU: moves to end)

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        if key not in self._cache:
            self._misses += 1
            return None

        value, expiry = self._cache[key]

        if time.time() > expiry:
            del self._cache[key]
            self._misses += 1
            return None

        self._cache.move_to_end(key)
        self._hits += 1
        return value

    def set(self, key: str, value: object, ttl: int | None = None):
        """
        Set value in cache with TTL and LRU eviction

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (None for default)
        """
        ttl = ttl or self._default_ttl
        expiry = time.time() + ttl

        if key in self._cache:
            del self._cache[key]

        self._cache[key] = (value, expiry)

        while len(self._cache) > self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._evictions += 1
            logger.debug(f"Cache evicted LRU item: {oldest_key}")

    def delete(self, key: str):
        """Delete key from cache"""
        if key in self._cache:
            del self._cache[key]

    def clear(self):
        """Clear all cached items"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def cleanup_expired(self) -> int:
        """
        Remove expired items from cache

        Returns:
            Number of items removed
        """
        now = time.time()
        expired_keys = [key for key, (_, expiry) in self._cache.items() if now > expiry]
        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def get_stats(self) -> CacheStats:
        """Get cache statistics"""
        now = time.time()
        active_items = sum(1 for _, expiry in self._cache.values() if now <= expiry)
        hit_rate = self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0.0

        return CacheStats(
            total_items=len(self._cache),
            active_items=active_items,
            expired_items=len(self._cache) - active_items,
            max_size=self._max_size,
            hits=self._hits,
            misses=self._misses,
            hit_rate=round(hit_rate, 3),
            evictions=self._evictions,
        )


cache = LRUCache(max_size=250, default_ttl=300)


def cache_key(*args, **kwargs) -> str:
    """
    Generate cache key from function arguments

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Hashed cache key
    """
    key_data = {"args": args, "kwargs": kwargs}
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

            # 1. Fast path: check if we already have it
            cached_value = cache.get(key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {key}")
                return cached_value

            # 2. Cache miss -> Stampede Protection
            # Get a unique lock for this specific key
            lock = cache.get_lock(key)

            async with lock:
                # 3. Double-check pattern
                # If another request was also waiting for the lock, it might have
                # already populated the cache while we were waiting.
                cached_value = cache.get(key)
                if cached_value is not None:
                    logger.debug(f"Cache hit (after await): {key}")
                    cache.cleanup_lock(key)
                    return cached_value

                # 4. We are the first one, do the expensive work
                logger.debug(f"Cache miss (executing): {key}")
                try:
                    result = await func(*args, **kwargs)
                    cache.set(key, result, ttl=ttl)
                    return result
                finally:
                    # Clean up the lock object when done protecting this refresh
                    cache.cleanup_lock(key)

        def invalidate_all():
            """Invalidate all cache entries for this function"""
            invalidate_cache_pattern(f"{key_prefix}:{func.__name__}")

        wrapper.invalidate_all = invalidate_all  # type: ignore[attr-defined]

        return wrapper

    return decorator


def invalidate_cache_pattern(pattern: str):
    """
    Invalidate cache entries matching a pattern

    Args:
        pattern: Pattern to match (simple prefix matching)
    """
    keys_to_delete = [key for key in cache._cache if key.startswith(pattern)]

    for key in keys_to_delete:
        cache.delete(key)

    if keys_to_delete:
        logger.debug(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")
