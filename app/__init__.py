import logging

import decouple
from flask import Flask
from flask_injector import FlaskInjector
from injector import Injector

from app.config import config_by_name
from app.dependencies import RedisModule
from app.errors import register_app_error_handlers
from app.middleware import register_request_logging
from app.shortener import shortener_bp


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        # Default to production so a missing APP_ENV never enables debug mode.
        config_name = decouple.config("APP_ENV", default="production")

    if config_name not in config_by_name:
        allowed = ", ".join(config_by_name)
        raise ValueError(f"Unknown APP_ENV '{config_name}'. Use one of: {allowed}")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])
    # Without this, Python's default WARNING level hides INFO logs under Gunicorn.
    app.logger.setLevel(logging.INFO)

    app.register_blueprint(shortener_bp)
    register_app_error_handlers(app)
    register_request_logging(app)

    # Must come last: FlaskInjector only wraps views that are already registered.
    injector = Injector([RedisModule()])
    FlaskInjector(app=app, injector=injector)
    app.extensions["injector"] = injector

    return app
