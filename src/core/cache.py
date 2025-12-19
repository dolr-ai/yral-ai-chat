"""
Caching utilities with in-memory fallback
LRU cache with TTL support and bounded size
"""
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from functools import wraps
from typing import Any

from loguru import logger


class LRUCache:
    """
    LRU cache with TTL support and maximum size limit
    
    Combines Least Recently Used eviction with time-based expiry.
    Thread-safe for async operations through OrderedDict.
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        Initialize cache
        
        Args:
            max_size: Maximum number of items in cache (default: 1000)
            default_ttl: Default time-to-live in seconds (default: 300)
        """
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> Any | None:
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

        # Check if expired
        if time.time() > expiry:
            del self._cache[key]
            self._misses += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl: int | None = None):
        """
        Set value in cache with TTL and LRU eviction
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (None for default)
        """
        ttl = ttl or self._default_ttl
        expiry = time.time() + ttl

        # If key exists, remove it first to re-add at end
        if key in self._cache:
            del self._cache[key]

        self._cache[key] = (value, expiry)

        # Enforce max size with LRU eviction
        while len(self._cache) > self._max_size:
            # Remove oldest (first) item
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
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if now > expiry
        ]
        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        now = time.time()
        active_items = sum(1 for _, expiry in self._cache.values() if now <= expiry)
        hit_rate = self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0.0

        return {
            "total_items": len(self._cache),
            "active_items": active_items,
            "expired_items": len(self._cache) - active_items,
            "max_size": self._max_size,
            "usage_percent": (len(self._cache) / self._max_size * 100) if self._max_size > 0 else 0,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 3),
            "evictions": self._evictions
        }


# Global cache instance with 1000 item limit
cache = LRUCache(max_size=1000, default_ttl=300)


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
    return hashlib.md5(key_str.encode()).hexdigest()


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
            # Generate cache key
            key = f"{key_prefix}:{func.__name__}:{cache_key(*args, **kwargs)}"

            # Try to get from cache
            cached_value = cache.get(key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {key}")
                return cached_value

            # Call function and cache result
            logger.debug(f"Cache miss: {key}")
            result = await func(*args, **kwargs)
            cache.set(key, result, ttl=ttl)

            return result

        return wrapper
    return decorator


def invalidate_cache_pattern(pattern: str):
    """
    Invalidate cache entries matching a pattern
    
    Args:
        pattern: Pattern to match (simple prefix matching)
    """
    keys_to_delete = [
        key for key in cache._cache
        if key.startswith(pattern)
    ]

    for key in keys_to_delete:
        cache.delete(key)

    if keys_to_delete:
        logger.debug(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")
