"""
Controller layer: wires HTTP routes to model calls and view (schema)
rendering. No Redis calls and no response-shape decisions here - just
orchestration. FastAPI's automatic OpenAPI docs (/docs) are generated
straight from these route + schema declarations, giving interns a
clickable UI to exercise GET/POST without curl.
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
    summary="List overview (cached)",
)
def list_items(response: Response):
    """List overview - cached (app-level via Redis, and reverse-proxy level
    via NGINX in front of this app)."""
    overview, cache_status = items_model.get_overview_cached()
    response.headers["X-App-Cache"] = cache_status
    response.headers["Cache-Control"] = f"public, max-age={items_model.CACHE_TTL_SECONDS}"
    return overview


@router.post(
    "/api/items",
    response_model=Item,
    status_code=201,
    tags=["items"],
    summary="Create item (never cached)",
)
def create_item(body: CreateItemRequest, response: Response):
    """Create - never cached, and busts the list overview cache so the
    next GET reflects this write immediately."""
    item = items_model.create_item(body.name)
    response.headers["Cache-Control"] = "no-store"
    return item
