"""
View layer: turns model data into HTTP responses (JSON envelope + headers).
Kept separate from the controller so response formatting can change (e.g.
add HTML templates) without touching request-handling logic.
"""
from flask import jsonify

from app.models.items_model import CACHE_TTL_SECONDS


def render_overview(overview, cache_status):
    response = jsonify(overview)
    response.headers["X-App-Cache"] = cache_status
    # Tells any well-behaved downstream cache (browser, NGINX, CDN) it may
    # also cache this GET response for the same TTL as the app cache.
    response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL_SECONDS}"
    return response


def render_created(item):
    response = jsonify(item)
    response.status_code = 201
    # Writes must never be cached anywhere.
    response.headers["Cache-Control"] = "no-store"
    return response


def render_health():
    response = jsonify({"status": "ok"})
    response.headers["Cache-Control"] = "no-store"
    return response
