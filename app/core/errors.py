from typing import Any

from flask import Flask, current_app
from flask_restx import Api
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.exceptions import HTTPException

HandlerResult = tuple[dict[str, Any], int]


class ShortCodeNotFoundError(Exception):
    def __init__(self, short_code: str) -> None:
        super().__init__(f"Short code '{short_code}' was not found.")
        self.short_code = short_code


class ShortCodeGenerationError(Exception):
    """Raised when no unused short code could be found after several attempts."""


class LinkGoneError(Exception):
    """The short URL exists but no longer redirects: deactivated or expired."""


class ForbiddenError(Exception):
    """The caller is known but not allowed to do this, e.g. a Free user."""


class ConflictError(Exception):
    """The request is valid but clashes with existing data, e.g. a taken username."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def violated_constraint(error: IntegrityError) -> str:
    """The name of the database constraint that rejected a write, e.g. "uq_users_email"."""
    diagnostics = getattr(error.orig, "diag", None)
    return getattr(diagnostics, "constraint_name", None) or ""


# These models define the error format once: error_body() builds every error
# response through them, and Swagger documents them.
class ErrorDetail(BaseModel):
    field: str = Field(description="The invalid field, or 'body' for the whole body.")
    message: str = Field(description="Why the value was rejected.")


class ErrorBody(BaseModel):
    code: str = Field(description="Machine-readable error code, e.g. 'not_found'.")
    message: str = Field(description="Human-readable explanation.")
    details: list[ErrorDetail] = Field(
        default=[], description="Field-level problems (validation errors only)."
    )


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": [
                        {
                            "field": "url",
                            "message": "URL scheme should be 'http' or 'https'",
                        }
                    ],
                }
            }
        }
    )

    error: ErrorBody


def error_body(
    code: str, message: str, details: list[ErrorDetail] | None = None
) -> dict[str, Any]:
    body = ErrorBody(code=code, message=message, details=details or [])
    # exclude_defaults drops "details" when it is empty.
    return ErrorResponse(error=body).model_dump(exclude_defaults=True)


def handle_validation_error(error: ValidationError) -> HandlerResult:
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in item["loc"]) or "body",
            message=item["msg"],
        )
        for item in error.errors()
    ]
    return error_body("validation_error", "Request validation failed.", details), 422


def handle_not_found(error: ShortCodeNotFoundError) -> HandlerResult:
    return error_body("not_found", str(error)), 404


def handle_gone(error: LinkGoneError) -> HandlerResult:
    return error_body("gone", str(error)), 410


def handle_forbidden(error: ForbiddenError) -> HandlerResult:
    return error_body("forbidden", str(error)), 403


def handle_conflict(error: ConflictError) -> HandlerResult:
    details = [ErrorDetail(field=error.field, message=error.message)]
    return (
        error_body("conflict", "The request conflicts with existing data.", details),
        409,
    )


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


def handle_generation_error(error: ShortCodeGenerationError) -> HandlerResult:
    message = "Could not generate a short code. Please try again."
    return error_body("service_unavailable", message), 503


def handle_storage_error(error: OperationalError) -> HandlerResult:
    # OperationalError: the database could not be reached or the connection failed.
    message = "The storage service is temporarily unavailable. Please try again."
    return error_body("service_unavailable", message), 503


def handle_unexpected_error(error: Exception) -> HandlerResult:
    return error_body("internal_server_error", "An unexpected error occurred."), 500


def handle_unexpected_app_error(error: Exception) -> HandlerResult:
    # Outside Flask-RESTX nothing logs a handled exception, so we do it here.
    current_app.logger.exception("Unhandled exception: %s", error)
    return handle_unexpected_error(error)


def handle_storage_app_error(error: OperationalError) -> HandlerResult:
    current_app.logger.exception("Storage unavailable: %s", error)
    return handle_storage_error(error)


def register_error_handlers(api: Api) -> None:
    """Handlers for errors raised inside Flask-RESTX routes.

    Flask-RESTX uses the first registered handler whose exception class matches,
    so specific exceptions must come before the catch-all Exception handler.
    """
    api.errorhandler(ValidationError)(handle_validation_error)
    api.errorhandler(ShortCodeNotFoundError)(handle_not_found)
    api.errorhandler(LinkGoneError)(handle_gone)
    api.errorhandler(ForbiddenError)(handle_forbidden)
    api.errorhandler(ConflictError)(handle_conflict)
    api.errorhandler(ShortCodeGenerationError)(handle_generation_error)
    api.errorhandler(OperationalError)(handle_storage_error)
    api.errorhandler(HTTPException)(handle_http_exception)
    api.errorhandler(Exception)(handle_unexpected_error)


def register_app_error_handlers(app: Flask) -> None:
    """Handlers for errors outside Flask-RESTX: the public redirect, unknown paths."""
    app.register_error_handler(ShortCodeNotFoundError, handle_not_found)
    app.register_error_handler(LinkGoneError, handle_gone)
    app.register_error_handler(OperationalError, handle_storage_app_error)
    app.register_error_handler(HTTPException, handle_http_exception)
    app.register_error_handler(Exception, handle_unexpected_app_error)
