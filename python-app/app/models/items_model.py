"""
Model layer: owns the "database" (a Redis list, standing in for a real
DB table) AND the cache (a separate Redis string key) for the list
overview. Controllers never talk to Redis directly - only through here.

Key design point for the lesson:
  - `items:store` = the source of truth ("the database").
  - `items:overview:cache` = a cached, precomputed overview of that data,
    with a TTL. It's invalidated immediately on every write, which is the
    "write-through invalidation" pattern: don't just wait for the TTL to
    expire, actively bust the cache the moment the underlying data changes.
"""
import json
import os
import time
import uuid
from datetime import datetime, timezone

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "15"))

STORE_KEY = "items:store"
OVERVIEW_CACHE_KEY = "items:overview:cache"

# Short timeouts so a Redis outage fails fast instead of hanging requests.
_redis_client = redis.Redis.from_url(
    REDIS_URL,
    socket_connect_timeout=1,
    socket_timeout=1,
    decode_responses=True,
)


def _safe_redis_call(fn, default=None):
    try:
        return fn()
    except redis.RedisError as exc:
        print(f"Redis call failed, failing open: {exc}")
        return default


def create_item(name):
    """Write path: persist the new item, then bust the overview cache.

    This is a real write - it is never cached, and it's the reason the
    cached overview needs to be invalidated (not just left to expire).
    """
    item = {
        "id": str(uuid.uuid4()),
        "name": name,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    _safe_redis_call(lambda: _redis_client.rpush(STORE_KEY, json.dumps(item)))
    # Invalidate: delete the cached overview so the very next GET recomputes
    # fresh data instead of serving a stale list missing this new item.
    _safe_redis_call(lambda: _redis_client.delete(OVERVIEW_CACHE_KEY))
    return item


def _compute_overview():
    """Simulates an expensive aggregation over the "database" (0.75s)."""
    time.sleep(0.75)
    raw_items = _safe_redis_call(lambda: _redis_client.lrange(STORE_KEY, 0, -1), default=[])
    items = [json.loads(raw) for raw in raw_items]
    return {
        "items": items,
        "count": len(items),
        "computedAt": datetime.now(timezone.utc).isoformat(),
    }


def get_overview_cached():
    """
    Cache-aside read path for GET /api/items:
      1. Try the cache.
      2. On miss, recompute and repopulate the cache with a TTL.
    Returns (overview_dict, cache_status) where cache_status is 'HIT' or 'MISS'.
    """
    cached = _safe_redis_call(lambda: _redis_client.get(OVERVIEW_CACHE_KEY))
    if cached:
        return json.loads(cached), "HIT"

    overview = _compute_overview()
    _safe_redis_call(
        lambda: _redis_client.set(OVERVIEW_CACHE_KEY, json.dumps(overview), ex=CACHE_TTL_SECONDS)
    )
    return overview, "MISS"
