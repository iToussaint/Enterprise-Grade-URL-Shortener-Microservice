from flask import Blueprint
from flask_restx import Api

from app.errors import register_error_handlers
from app.shortener.routes import ns

shortener_bp = Blueprint("shortener", __name__, url_prefix="/api")

api = Api(
    shortener_bp,
    title="URL Shortener API",
    version="1.0",
    description="Shorten long URLs and redirect short codes to the original URL.",
    doc="/docs",
)
api.add_namespace(ns)
register_error_handlers(api)
