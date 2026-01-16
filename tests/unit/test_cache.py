"""
Unit tests for LRU cache with TTL support
"""

import time

from src.core.cache import LRUCache, cache_key


class TestLRUCache:
    """Test LRU cache functionality"""

    def test_basic_set_get(self):
        """Test basic cache operations"""
        cache = LRUCache(max_size=10, default_ttl=60)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        """Test that items expire after TTL"""
        cache = LRUCache(max_size=10, default_ttl=1)

        cache.set("key1", "value1", ttl=1)
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        """Test LRU eviction when max size is reached"""
        cache = LRUCache(max_size=3, default_ttl=60)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # All items should be present
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

        # Add fourth item, should evict oldest (key1)
        cache.set("key4", "value4")

        assert cache.get("key1") is None  # Evicted
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_lru_access_order(self):
        """Test that accessing an item updates its LRU position"""
        cache = LRUCache(max_size=3, default_ttl=60)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1, making it most recently used
        cache.get("key1")

        # Add key4, should evict key2 (oldest unused)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"  # Still present
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_update_existing_key(self):
        """Test updating an existing key"""
        cache = LRUCache(max_size=10, default_ttl=60)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

    def test_delete(self):
        """Test deleting a key"""
        cache = LRUCache(max_size=10, default_ttl=60)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        cache.delete("key1")
        assert cache.get("key1") is None

    def test_clear(self):
        """Test clearing all cache items"""
        cache = LRUCache(max_size=10, default_ttl=60)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None
        assert cache.get_stats().total_items == 0

    def test_cleanup_expired(self):
        """Test cleanup of expired items"""
        cache = LRUCache(max_size=10, default_ttl=1)

        cache.set("key1", "value1", ttl=1)
        cache.set("key2", "value2", ttl=60)

        # Wait for key1 to expire
        time.sleep(1.1)

        removed = cache.cleanup_expired()

        assert removed == 1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_stats(self):
        """Test cache statistics"""
        cache = LRUCache(max_size=100, default_ttl=60)

        # Add some items
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Get one item (hit)
        cache.get("key1")

        # Try to get non-existent item (miss)
        cache.get("key3")

        stats = cache.get_stats()

        assert stats.total_items == 2
        assert stats.active_items == 2
        assert stats.max_size == 100
        assert stats.hits == 1
        assert stats.misses == 1
        assert stats.hit_rate == 0.5
        assert (stats.total_items / stats.max_size * 100) == 2.0

    def test_eviction_count(self):
        """Test that evictions are tracked"""
        cache = LRUCache(max_size=2, default_ttl=60)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should evict key1

        stats = cache.get_stats()
        assert stats.evictions == 1

        cache.set("key4", "value4")  # Should evict key2

        stats = cache.get_stats()
        assert stats.evictions == 2

    def test_cache_with_complex_values(self):
        """Test caching complex data types"""
        cache = LRUCache(max_size=10, default_ttl=60)

        # Test with dict
        cache.set("dict_key", {"name": "test", "value": 123})
        assert cache.get("dict_key") == {"name": "test", "value": 123}

        # Test with list
        cache.set("list_key", [1, 2, 3, 4, 5])
        assert cache.get("list_key") == [1, 2, 3, 4, 5]

        # Test with nested structures
        cache.set("nested", {"users": [{"id": 1}, {"id": 2}]})
        assert cache.get("nested") == {"users": [{"id": 1}, {"id": 2}]}


class TestCacheKeyGeneration:
    """Test cache key generation"""

    def test_cache_key_with_args(self):
        """Test cache key generation with positional args"""
        key1 = cache_key("arg1", "arg2")
        key2 = cache_key("arg1", "arg2")
        key3 = cache_key("arg1", "arg3")

        assert key1 == key2
        assert key1 != key3

    def test_cache_key_with_kwargs(self):
        """Test cache key generation with keyword args"""
        key1 = cache_key(param1="value1", param2="value2")
        key2 = cache_key(param1="value1", param2="value2")
        key3 = cache_key(param1="value1", param2="value3")

        assert key1 == key2
        assert key1 != key3

    def test_cache_key_order_independence(self):
        """Test that kwargs order doesn't affect key"""
        key1 = cache_key(a=1, b=2, c=3)
        key2 = cache_key(c=3, b=2, a=1)

        assert key1 == key2

    def test_cache_key_with_mixed_args(self):
        """Test cache key with both args and kwargs"""
        key1 = cache_key("pos1", "pos2", kwarg1="val1", kwarg2="val2")
        key2 = cache_key("pos1", "pos2", kwarg2="val2", kwarg1="val1")

        assert key1 == key2


class TestCacheIntegration:
    """Integration tests for cache usage patterns"""

    def test_full_cache_lifecycle(self):
        """Test complete cache lifecycle"""
        cache = LRUCache(max_size=5, default_ttl=2)

        # Phase 1: Fill cache
        for i in range(5):
            cache.set(f"key{i}", f"value{i}")

        stats = cache.get_stats()
        assert stats.total_items == 5
        assert (stats.total_items / stats.max_size * 100) == 100.0

        # Phase 2: Trigger eviction
        cache.set("key5", "value5")
        assert cache.get("key0") is None  # Evicted

        # Get stats after eviction
        stats = cache.get_stats()
        assert stats.evictions >= 1

        # Phase 3: Wait for expiration
        time.sleep(2.1)
        cleaned = cache.cleanup_expired()
        assert cleaned > 0

        # Phase 4: Clear
        cache.clear()
        stats = cache.get_stats()
        assert stats.total_items == 0
