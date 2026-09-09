"""
Controller layer: wires HTTP routes to model calls and view rendering.
No Redis calls and no response formatting here - just orchestration.
"""
from flask import Blueprint, request

from app.models import items_model
from app.views import items_view

bp = Blueprint("items", __name__)


@bp.route("/healthz")
def healthz():
    return items_view.render_health()


@bp.route("/api/items", methods=["GET"])
def list_items():
    """List overview - cached (app-level via Redis, and reverse-proxy level
    via NGINX in front of this app)."""
    overview, cache_status = items_model.get_overview_cached()
    return items_view.render_overview(overview, cache_status)


@bp.route("/api/items", methods=["POST"])
def create_item():
    """Create - never cached, and busts the list overview cache so the
    next GET reflects this write immediately."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "unnamed-item")
    item = items_model.create_item(name)
    return items_view.render_created(item)
