"""
Controller layer: wires HTTP routes to model calls and view (schema)
rendering. The only cache in this system is NGINX, sitting in front of
the whole app (see nginx/nginx.conf). FastAPI's automatic OpenAPI docs
(/docs) are generated straight from these route + schema declarations,
giving interns a clickable UI to exercise GET/POST without curl.

On this branch (demo/cache-busting), POST actively busts the NGINX cache
entry for GET /api/items by deleting its on-disk cache file - see
app/models/cache_buster.py for how and why, and its trade-offs.
"""
from fastapi import APIRouter, Response

from app.models import cache_buster, items_model
from app.views.items_view import CreateItemRequest, HealthStatus, Item, ItemsOverview

router = APIRouter()


@router.get("/healthz", response_model=HealthStatus, tags=["health"])
def healthz(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok"}


@router.get(
    "/api/items",
    response_model=ItemsOverview,
    tags=["items"],
    summary="List overview (cacheable by NGINX)",
)
def list_items():
    """List overview. This route itself does no caching - it's cacheable
    *by NGINX* (see nginx/nginx.conf's `proxy_cache` block for /api/items),
    which is the only cache in this system."""
    return items_model.get_overview()


@router.post(
    "/api/items",
    response_model=Item,
    status_code=201,
    tags=["items"],
    summary="Create item (never cached, busts the GET cache)",
)
def create_item(body: CreateItemRequest, response: Response):
    """Create - never cached itself (`proxy_cache_methods GET HEAD` in
    nginx.conf guarantees that), and additionally actively purges the
    cached GET /api/items response on disk so the very next read is
    guaranteed fresh, regardless of how long is left on its TTL."""
    item = items_model.create_item(body.name)
    purged = cache_buster.purge_items_overview_cache()
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Cache-Purged"] = "true" if purged else "nothing-cached"
    return item
