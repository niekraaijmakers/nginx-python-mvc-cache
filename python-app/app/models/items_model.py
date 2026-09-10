"""
Business logic in front of the real database (db.py). With only one cache
in this system (NGINX, sitting in front of the whole app - see
nginx/nginx.conf), this layer has no caching concerns of its own: it just
reads from and writes to the database.
"""
import time
import uuid
from datetime import datetime, timezone

from app.models import db


def create_item(name):
    """Write path: persist the new item to the real database.

    This is a real write - it must never be cached, which is why
    nginx/nginx.conf restricts caching to GET/HEAD only. There is no
    cache to invalidate here (there's no app-level cache anymore) - the
    only cache in the whole system is NGINX, and it can't be reached from
    application code, only expired via its own TTL.
    """
    item = {
        "id": str(uuid.uuid4()),
        "name": name,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    db.insert_item(item)
    return item


def get_overview():
    """Read path for GET /api/items: simulates a slow query (0.75s
    artificial delay) against the real database. No app-level caching -
    every call to this function does the full work. NGINX is what makes
    repeated requests fast, by caching the HTTP response in front of this
    entirely."""
    time.sleep(0.75)
    items = db.fetch_all_items()
    return {
        "items": items,
        "count": len(items),
        "computedAt": datetime.now(timezone.utc).isoformat(),
    }
