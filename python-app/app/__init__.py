"""Application factory (MVC entrypoint) - FastAPI edition.

FastAPI auto-generates interactive API docs from the routes/schemas
registered below:
  - Swagger UI: /docs
  - ReDoc:      /redoc
  - raw schema: /openapi.json
That's the "easy UI" - interns can browse endpoints and fire GET/POST
requests from the browser instead of curl.
"""
from fastapi import FastAPI

from app.controllers.items_controller import router as items_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Caching Demo API",
        description="Python MVC (FastAPI) server used to teach app-level "
        "(Redis) and reverse-proxy (NGINX) caching.",
        version="1.0.0",
    )
    app.include_router(items_router)
    return app
