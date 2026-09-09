"""Application factory (standard Flask MVC-style entrypoint)."""
from flask import Flask

from app.controllers.items_controller import bp as items_bp


def create_app():
    app = Flask(__name__)
    app.register_blueprint(items_bp)
    return app
