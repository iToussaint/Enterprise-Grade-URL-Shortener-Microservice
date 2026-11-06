from typing import Any

from flask import Flask, current_app
from flask_restx import Api
from pydantic import ValidationError
from redis.exceptions import RedisError
from werkzeug.exceptions import HTTPException

ErrorResponse = tuple[dict[str, Any], int]


class ShortCodeNotFoundError(Exception):
    def __init__(self, short_code: str) -> None:
        super().__init__(f"Short code '{short_code}' was not found.")
        self.short_code = short_code


class ShortCodeGenerationError(Exception):
    """Raised when no unused short code could be found after several attempts."""


def error_body(
    code: str, message: str, details: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error}


def handle_validation_error(error: ValidationError) -> ErrorResponse:
    details = [
        {
            "field": ".".join(str(part) for part in item["loc"]) or "body",
            "message": item["msg"],
        }
        for item in error.errors()
    ]
    return error_body("validation_error", "Request validation failed.", details), 422


def handle_not_found(error: ShortCodeNotFoundError) -> ErrorResponse:
    return error_body("not_found", str(error)), 404


def handle_http_exception(
    error: HTTPException,
) -> tuple[dict[str, Any], int, dict[str, str]]:
    status = error.code or 500
    code = (error.name or "error").lower().replace(" ", "_")
    # Keep headers such as "Allow" on 405 responses; we set our own content type.
    headers = {
        name: value
        for name, value in error.get_headers()
        if name.lower() != "content-type"
    }
    return error_body(code, error.description or code), status, headers


# The 5xx handlers below don't log: Flask-RESTX already logs every response
# with status >= 500, including the traceback. Responses never include the
# real cause, so hostnames and internals are not exposed to clients.


def handle_generation_error(error: ShortCodeGenerationError) -> ErrorResponse:
    message = "Could not generate a short code. Please try again."
    return error_body("service_unavailable", message), 503


def handle_storage_error(error: RedisError) -> ErrorResponse:
    message = "The storage service is temporarily unavailable. Please try again."
    return error_body("service_unavailable", message), 503


def handle_unexpected_error(error: Exception) -> ErrorResponse:
    return error_body("internal_server_error", "An unexpected error occurred."), 500


def handle_unexpected_app_error(error: Exception) -> ErrorResponse:
    # Outside Flask-RESTX nothing logs a handled exception, so we do it here.
    current_app.logger.exception("Unhandled exception: %s", error)
    return handle_unexpected_error(error)


def register_error_handlers(api: Api) -> None:
    """Handlers for errors raised inside Flask-RESTX routes.

    Flask-RESTX uses the first registered handler whose exception class matches,
    so specific exceptions must come before the catch-all Exception handler.
    """
    api.errorhandler(ValidationError)(handle_validation_error)
    api.errorhandler(ShortCodeNotFoundError)(handle_not_found)
    api.errorhandler(ShortCodeGenerationError)(handle_generation_error)
    api.errorhandler(RedisError)(handle_storage_error)
    api.errorhandler(HTTPException)(handle_http_exception)
    api.errorhandler(Exception)(handle_unexpected_error)


def register_app_error_handlers(app: Flask) -> None:
    """Handlers for errors outside Flask-RESTX, e.g. paths no route matches."""
    app.register_error_handler(HTTPException, handle_http_exception)
    app.register_error_handler(Exception, handle_unexpected_app_error)
