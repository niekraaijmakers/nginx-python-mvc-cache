"""
Controller layer: wires HTTP routes to model calls and view (schema)
rendering. No caching logic here - the only cache in this system is
NGINX, sitting in front of the whole app (see nginx/nginx.conf). FastAPI's
automatic OpenAPI docs (/docs) are generated straight from these route +
schema declarations, giving interns a clickable UI to exercise GET/POST
without curl.
"""
from fastapi import APIRouter, Response

from app.models import items_model
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
    summary="Create item (never cached)",
)
def create_item(body: CreateItemRequest, response: Response):
    """Create - never cached. `proxy_cache_methods GET HEAD` in
    nginx.conf guarantees NGINX never caches this response."""
    item = items_model.create_item(body.name)
    response.headers["Cache-Control"] = "no-store"
    return item
