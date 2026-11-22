import logging
from collections.abc import Mapping
from typing import Any

import decouple
from flask import Flask
from flask_injector import FlaskInjector
from injector import Injector
from werkzeug.middleware.proxy_fix import ProxyFix

from app import models  # noqa: F401  (registers every table with SQLAlchemy)
from app.analytics.geoip import GeoIPModule
from app.api import api_bp
from app.core.config import config_by_name
from app.core.errors import register_app_error_handlers
from app.core.extensions import db, jwt, migrate
from app.core.middleware import register_request_logging
from app.urls.redirects import redirects_bp
from app.users.commands import users_cli

MIN_JWT_SECRET_LENGTH = 32


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

    proxies = app.config["TRUSTED_PROXY_COUNT"]
    if proxies:
        # Behind N trusted proxies: take the client IP, scheme and host from
        # their X-Forwarded-* headers. Off by default, because clients can fake them.
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies
        )

    secret = app.config.get("JWT_SECRET_KEY") or ""
    if len(secret) < MIN_JWT_SECRET_LENGTH:
        # A missing or short key would let anyone forge tokens: refuse to start.
        raise RuntimeError(
            f"Set JWT_SECRET_KEY to a random value of at least {MIN_JWT_SECRET_LENGTH}"
            " characters (see .env.example)."
        )

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    app.register_blueprint(api_bp)
    app.register_blueprint(redirects_bp)
    app.cli.add_command(users_cli)
    register_app_error_handlers(app)
    register_request_logging(app)

    # Must come last: FlaskInjector only wraps views that are already registered.
    # Services are built from their constructors; modules configure the rest.
    injector = Injector([GeoIPModule()])
    FlaskInjector(app=app, injector=injector)
    app.extensions["injector"] = injector

    return app
