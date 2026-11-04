from typing import Any

from flask_restx import Api
from pydantic import ValidationError


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


def register_error_handlers(api: Api) -> None:
    @api.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError) -> tuple[dict[str, Any], int]:
        details = [
            {
                "field": ".".join(str(part) for part in item["loc"]) or "body",
                "message": item["msg"],
            }
            for item in error.errors()
        ]
        return (
            error_body("validation_error", "Request validation failed.", details),
            422,
        )

    @api.errorhandler(ShortCodeNotFoundError)
    def handle_not_found(error: ShortCodeNotFoundError) -> tuple[dict[str, Any], int]:
        return error_body("not_found", str(error)), 404
