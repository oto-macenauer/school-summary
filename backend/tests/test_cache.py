"""Tests for DataCache service."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.services.cache import DataCache


class TestDataCache:
    """Tests for DataCache class."""

    @pytest.fixture
    def cache(self) -> DataCache:
        """Create a DataCache instance."""
        return DataCache()

    def test_set_and_get(self, cache: DataCache) -> None:
        """Test setting and getting a cached value."""
        cache.set("key1", "value1", ttl=60)
        assert cache.get("key1") == "value1"

    def test_get_missing_key_returns_none(self, cache: DataCache) -> None:
        """Test getting a non-existent key returns None."""
        assert cache.get("nonexistent") is None

    def test_get_expired_returns_none(self, cache: DataCache) -> None:
        """Test that expired entries return None."""
        cache.set("key1", "value1", ttl=1)

        # Patch time.monotonic to simulate expiry
        original_monotonic = time.monotonic
        cache._store["key1"].expires_at = time.monotonic() - 1

        assert cache.get("key1") is None

    def test_set_overwrites_existing(self, cache: DataCache) -> None:
        """Test that setting the same key overwrites the old value."""
        cache.set("key1", "value1", ttl=60)
        cache.set("key1", "value2", ttl=60)
        assert cache.get("key1") == "value2"

    def test_invalidate(self, cache: DataCache) -> None:
        """Test removing a specific key from cache."""
        cache.set("key1", "value1", ttl=60)
        cache.set("key2", "value2", ttl=60)

        cache.invalidate("key1")

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_invalidate_nonexistent_key(self, cache: DataCache) -> None:
        """Test that invalidating a non-existent key does not raise."""
        cache.invalidate("nonexistent")  # Should not raise

    def test_clear(self, cache: DataCache) -> None:
        """Test clearing all cached values."""
        cache.set("key1", "value1", ttl=60)
        cache.set("key2", "value2", ttl=60)

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_keys(self, cache: DataCache) -> None:
        """Test getting list of non-expired keys."""
        cache.set("key1", "value1", ttl=60)
        cache.set("key2", "value2", ttl=60)

        keys = cache.keys()
        assert sorted(keys) == ["key1", "key2"]

    def test_keys_excludes_expired(self, cache: DataCache) -> None:
        """Test that keys() excludes expired entries."""
        cache.set("key1", "value1", ttl=60)
        cache.set("key2", "value2", ttl=1)

        # Manually expire key2
        cache._store["key2"].expires_at = time.monotonic() - 1

        keys = cache.keys()
        assert keys == ["key1"]

    def test_various_value_types(self, cache: DataCache) -> None:
        """Test caching different value types."""
        cache.set("string", "hello", ttl=60)
        cache.set("int", 42, ttl=60)
        cache.set("list", [1, 2, 3], ttl=60)
        cache.set("dict", {"a": 1}, ttl=60)
        cache.set("none", None, ttl=60)

        assert cache.get("string") == "hello"
        assert cache.get("int") == 42
        assert cache.get("list") == [1, 2, 3]
        assert cache.get("dict") == {"a": 1}
        assert cache.get("none") is None  # None value looks like missing
