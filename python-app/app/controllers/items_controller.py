"""
Controller layer: wires HTTP routes to model calls and view (template)
rendering. The only cache in this system is NGINX, sitting in front of
the whole app (see nginx/nginx.conf) - and on this branch, what it
caches is server-rendered HTML (GET /) and static assets (/static/*),
not a JSON API.

On this branch (demo/cache-busting), POST actively busts the NGINX cache
entry for GET / by deleting its on-disk cache file - see
app/models/cache_buster.py for how and why, and its trade-offs.
"""
from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.models import cache_buster, items_model

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/healthz")
def healthz(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok"}


@router.get("/", tags=["items"], summary="Item list page (cacheable by NGINX)")
def index(request: Request):
    """Renders the full HTML page, including the item list. This route
    itself does no caching - it's cacheable *by NGINX* (see
    nginx/nginx.conf's `proxy_cache` block for `/`), which is the only
    cache in this system. No Cache-Control is set here on purpose, so
    NGINX's `proxy_cache_valid` is the single source of truth."""
    overview = items_model.get_overview()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "items": overview["items"],
            "count": overview["count"],
            "computed_at": overview["computedAt"],
        },
    )


@router.post(
    "/items",
    tags=["items"],
    summary="Create item (never cached, busts the page cache)",
)
def create_item(name: str = Form(...)):
    """Create - a real write, never cached itself
    (`Cache-Control: no-store` plus `proxy_cache_methods GET HEAD` in
    nginx.conf, which structurally can't cache a POST anyway), and
    additionally actively purges the cached GET / page on disk so the
    very next read is guaranteed fresh, regardless of how long is left
    on its TTL. Redirects back to `/` afterwards - by the time the
    browser follows that redirect, the purge has already happened.

    Header note: when an endpoint returns its own Response subclass (like
    RedirectResponse here) FastAPI ignores headers set on an injected
    `Response` param - they have to be set directly on the object that's
    actually returned."""
    items_model.create_item(name)
    purged = cache_buster.purge_index_page_cache()
    redirect = RedirectResponse(url="/", status_code=303)
    redirect.headers["Cache-Control"] = "no-store"
    redirect.headers["X-Cache-Purged"] = "true" if purged else "nothing-cached"
    return redirect
