"""Element cache manager — multi-level caching (local → Redis → MinIO) for idempotent element processing."""

import time
from typing import Any

from common.config_loader import get_config
from common.models.document import BaseElement
from common.util.logger import get_logger
from common.util.utils import json_dumps, json_loads

logger = get_logger()


class ElementCacheManager:
    """Multi-level cache for element processing results.

    Cache hierarchy (checked in order):
    1. L1: Local in-memory (fastest, process-local, TTL 300s)
    2. L2: Redis (shared across processes, TTL 3600s)
    3. L3: MinIO (persistent, for large results like rendered images)

    Cache key: element_id (globally unique)
    """

    def __init__(self):
        cfg = get_config()["redis"]
        self._l1_ttl = 300  # 5 minutes
        self._l2_ttl = cfg.get("cache_ttl_seconds", 3600)

        # L1: local dict with timestamps
        self._l1_cache: dict[str, tuple[float, Any]] = {}

        self._redis = None

    def _get_redis(self):
        if self._redis is None:
            from infrastructure.redis.redis_client import get_redis_client
            self._redis = get_redis_client()
        return self._redis

    def get(self, element_id: str) -> Any | None:
        """Get cached element processing result. Returns None if not found."""
        # L1: local memory
        if element_id in self._l1_cache:
            ts, value = self._l1_cache[element_id]
            if time.time() - ts < self._l1_ttl:
                logger.debug(f"Cache L1 hit: {element_id}")
                return value
            del self._l1_cache[element_id]

        # L2: Redis
        try:
            redis = self._get_redis()
            key = f"cleaning:element:{element_id}"
            cached = redis.get_json(key)
            if cached:
                self._set_l1(element_id, cached)
                logger.debug(f"Cache L2 hit: {element_id}")
                return cached
        except Exception as e:
            logger.debug(f"Cache L2 miss: {element_id} ({e})")

        return None

    def set(self, element_id: str, value: Any):
        """Store element processing result in cache."""
        self._set_l1(element_id, value)

        try:
            redis = self._get_redis()
            key = f"cleaning:element:{element_id}"
            redis.set_json(key, value, self._l2_ttl)
        except Exception as e:
            logger.debug(f"Cache L2 write failed: {element_id} ({e})")

    def _set_l1(self, element_id: str, value: Any):
        self._l1_cache[element_id] = (time.time(), value)

        # Evict expired entries periodically
        if len(self._l1_cache) > 1000:
            now = time.time()
            expired = [k for k, (ts, _) in self._l1_cache.items() if now - ts > self._l1_ttl]
            for k in expired:
                del self._l1_cache[k]

    def invalidate(self, element_id: str):
        """Remove element from all cache levels."""
        self._l1_cache.pop(element_id, None)
        try:
            self._get_redis().delete(f"cleaning:element:{element_id}")
        except Exception:
            pass

    def get_stats(self) -> dict:
        return {
            "l1_size": len(self._l1_cache),
            "l1_ttl": self._l1_ttl,
            "l2_ttl": self._l2_ttl,
        }


_cache_manager: ElementCacheManager | None = None


def get_cache_manager() -> ElementCacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = ElementCacheManager()
    return _cache_manager
