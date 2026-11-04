from flask import Blueprint
from flask_restx import Api

shortener_bp = Blueprint("shortener", __name__, url_prefix="/api")

api = Api(
    shortener_bp,
    title="URL Shortener API",
    version="1.0",
    description="Shorten long URLs and redirect short codes to the original URL.",
    doc="/docs",
)
