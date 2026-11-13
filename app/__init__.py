import logging
from collections.abc import Mapping
from typing import Any

import decouple
from flask import Flask
from flask_injector import FlaskInjector
from injector import Injector

from app import models  # noqa: F401  (registers every table with SQLAlchemy)
from app.api import api_bp
from app.core.config import config_by_name
from app.core.dependencies import RedisModule
from app.core.errors import register_app_error_handlers
from app.core.extensions import db, migrate
from app.core.middleware import register_request_logging


def create_app(
    config_name: str | None = None, overrides: Mapping[str, Any] | None = None
) -> Flask:
    """Build the application.

    `overrides` replaces settings before the extensions start; the tests use it
    to point the app at their own PostgreSQL container.
    """
    if config_name is None:
        # Default to production so a missing APP_ENV never enables debug mode.
        config_name = decouple.config("APP_ENV", default="production")

    if config_name not in config_by_name:
        allowed = ", ".join(config_by_name)
        raise ValueError(f"Unknown APP_ENV '{config_name}'. Use one of: {allowed}")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])
    if overrides:
        app.config.update(overrides)
    # Without this, Python's default WARNING level hides INFO logs under Gunicorn.
    app.logger.setLevel(logging.INFO)

    db.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(api_bp)
    register_app_error_handlers(app)
    register_request_logging(app)

    # Must come last: FlaskInjector only wraps views that are already registered.
    injector = Injector([RedisModule()])
    FlaskInjector(app=app, injector=injector)
    app.extensions["injector"] = injector

    return app
