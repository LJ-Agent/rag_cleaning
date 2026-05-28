"""Redis cache client with distributed lock support."""
import time
from typing import Any
from uuid import uuid4

import redis
from redis import ConnectionPool

from common.config_loader import get_config
from common.util.logger import get_logger
from common.util.utils import json_dumps, json_loads

logger = get_logger()


class RedisClient:
    """Redis client for caching + distributed locking."""

    def __init__(self):
        cfg = get_config()["redis"]
        self._pool = ConnectionPool(
            host=cfg["host"],
            port=cfg["port"],
            password=cfg["password"] or None,
            db=cfg["database"],
            max_connections=cfg.get("pool_max_active", 20),
            socket_timeout=cfg.get("timeout_ms", 5000) / 1000,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        self._default_ttl = cfg.get("cache_ttl_seconds", 3600)
        self._lock_ttl = cfg.get("lock_ttl_seconds", 30)
        self._lock_retry = cfg.get("lock_retry_times", 3)
        self._lock_delay = cfg.get("lock_retry_delay_ms", 200) / 1000

    # ─── Basic cache operations ────────────────────────────

    def get(self, key: str) -> str | None:
        try:
            val = self._client.get(key)
            return val.decode() if val else None
        except redis.RedisError as e:
            logger.warning(f"Redis get failed: {key} — {e}")
            return None

    def set(self, key: str, value: str, ttl: int | None = None):
        try:
            self._client.setex(key, ttl or self._default_ttl, value)
        except redis.RedisError as e:
            logger.warning(f"Redis set failed: {key} — {e}")

    def get_json(self, key: str) -> Any | None:
        raw = self.get(key)
        return json_loads(raw) if raw else None

    def set_json(self, key: str, value: Any, ttl: int | None = None):
        self.set(key, json_dumps(value), ttl)

    def delete(self, key: str):
        try:
            self._client.delete(key)
        except redis.RedisError as e:
            logger.warning(f"Redis delete failed: {key} — {e}")

    def exists(self, key: str) -> bool:
        try:
            return bool(self._client.exists(key))
        except redis.RedisError:
            return False

    def incr(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        """Increment counter, returns new value."""
        try:
            val = self._client.incrby(key, amount)
            if ttl:
                self._client.expire(key, ttl)
            return val
        except redis.RedisError as e:
            logger.warning(f"Redis incr failed: {key} — {e}")
            return 0

    # ─── Distributed lock ──────────────────────────────────

    def acquire_lock(self, lock_key: str, ttl: int | None = None) -> str | None:
        """Acquire distributed lock. Returns lock token on success, None on failure."""
        token = str(uuid4())
        ttl = ttl or self._lock_ttl
        for _ in range(self._lock_retry):
            if self._client.set(lock_key, token, nx=True, ex=ttl):
                return token
            time.sleep(self._lock_delay)
        return None

    def release_lock(self, lock_key: str, token: str):
        """Release distributed lock using Lua script (atomic check-and-delete)."""
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            self._client.eval(script, 1, lock_key, token)
        except redis.RedisError as e:
            logger.warning(f"Redis unlock failed: {lock_key} — {e}")

    # ─── Counters & rate limiting ─────────────────────────

    def cache_task_status(self, task_id: str, status: str, ttl: int = 86400):
        """Cache task status for quick lookup."""
        self.set(f"cleaning:task:{task_id}:status", status, ttl)

    def get_task_status(self, task_id: str) -> str | None:
        return self.get(f"cleaning:task:{task_id}:status")

    def mark_task_processed(self, task_id: str, ttl: int = 86400):
        """Mark task as processed for idempotency check."""
        self.set(f"cleaning:task:{task_id}:processed", "1", ttl)

    def is_task_processed(self, task_id: str) -> bool:
        return self.exists(f"cleaning:task:{task_id}:processed")

    def close(self):
        self._pool.disconnect()

    @property
    def client(self) -> redis.Redis:
        return self._client


_redis_client: RedisClient | None = None


def get_redis_client() -> RedisClient:
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client
