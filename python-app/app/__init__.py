"""Application factory (MVC entrypoint) - FastAPI edition.

View layer = Jinja2 templates in app/templates/ (server-rendered HTML)
plus static assets in app/static/ (CSS/JS), instead of a JSON API. FastAPI
still exposes /docs, but the actual UI interns use is the rendered page
itself at "/".
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.controllers.items_controller import router as items_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Caching Demo",
        description="Python MVC (FastAPI) server rendering HTML, used to "
        "teach reverse-proxy (NGINX) caching of pages and static assets.",
        version="1.0.0",
    )
    app.include_router(items_router)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    return app
