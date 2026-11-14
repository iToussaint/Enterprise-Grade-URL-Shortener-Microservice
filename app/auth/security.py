"""HTTP Basic authentication for protected endpoints.

The client sends `Authorization: Basic base64(username:password)` with every
request. Only use it over HTTPS: the password is encoded, not encrypted.
"""

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from flask import g, request
from werkzeug.datastructures import WWWAuthenticate
from werkzeug.exceptions import Unauthorized

from app.auth.service import AuthService
from app.users.models import User

P = ParamSpec("P")
R = TypeVar("R")


def authenticate_request() -> User:
    """Return the user identified by the request's Basic credentials, or raise 401."""
    credentials = request.authorization
    user = None
    if credentials is not None and credentials.type == "basic":
        user = AuthService().authenticate(
            credentials.username or "", credentials.password or ""
        )
    if user is None:
        raise Unauthorized(
            "Valid username and password required (HTTP Basic authentication).",
            # Tells clients (browsers, Swagger UI) how to authenticate.
            www_authenticate=WWWAuthenticate("basic", {"realm": "URL Shortener"}),
        )
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
