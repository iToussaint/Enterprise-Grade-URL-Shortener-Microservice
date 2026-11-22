"""JWT authentication for protected endpoints.

The client logs in at /api/v1/auth/login/ and sends the access token with each
request: `Authorization: Bearer <access_token>`. Only the signature and expiry
are checked per request, never the password.
"""

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import ExpiredSignatureError, PyJWTError
from werkzeug.datastructures import WWWAuthenticate
from werkzeug.exceptions import Unauthorized

from app.core.extensions import db
from app.users.models import User

P = ParamSpec("P")
R = TypeVar("R")


def unauthorized(message: str) -> Unauthorized:
    # WWW-Authenticate tells clients (and Swagger UI) to send a Bearer token.
    return Unauthorized(
        message, www_authenticate=WWWAuthenticate("bearer", {"realm": "URL Shortener"})
    )


def authenticate_request() -> User:
    """Return the user of the request's access token, or raise 401."""
    try:
        # Reads "Authorization: Bearer <token>", checks signature and expiry, and
        # refuses refresh tokens (they are only for /api/v1/auth/refresh/).
        verify_jwt_in_request()
    except ExpiredSignatureError:
        raise unauthorized("The access token has expired; refresh it.") from None
    except (PyJWTError, JWTExtendedException):
        raise unauthorized(
            "A valid access token is required: 'Authorization: Bearer <token>'."
        ) from None

    # The token can outlive the account: deleted or deactivated users are refused.
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or not user.is_active:
        raise unauthorized("This account no longer exists or is inactive.")
    return user


def login_required(view: Callable[P, R]) -> Callable[P, R]:
    """Allow the view to run only for an authenticated user, available as current_user()."""

    @wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        g.current_user = authenticate_request()
        return view(*args, **kwargs)

    return wrapper


def current_user() -> User:
    user: User = g.current_user
    return user
