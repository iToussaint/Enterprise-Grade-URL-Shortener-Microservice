import decouple
from flask import Flask

from app.config import config_by_name
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

    app.register_blueprint(shortener_bp)

    return app
