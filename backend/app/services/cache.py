"""In-memory cache with TTL support."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger("bakalari.cache")


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class DataCache:
    """Simple in-memory cache with TTL support."""

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        """Get a cached value, returning None if expired or missing."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set a cached value with TTL in seconds."""
        self._store[key] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + ttl,
        )

    def invalidate(self, key: str) -> None:
        """Remove a specific key from cache."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Clear all cached values."""
        self._store.clear()
        _LOGGER.debug("Cache cleared")

    def keys(self) -> list[str]:
        """Return all non-expired keys."""
        now = time.monotonic()
        return [k for k, v in self._store.items() if now <= v.expires_at]
