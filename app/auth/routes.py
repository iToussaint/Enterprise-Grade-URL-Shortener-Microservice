from typing import Any

from flask import current_app
from flask_restx import Namespace, Resource
from injector import inject

from app.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.auth.service import AuthService
from app.core.errors import ErrorResponse
from app.core.extensions import limiter
from app.core.swagger import register_schema

ns = Namespace(
    "auth",
    path="/v1/auth",
    description="Create an account, log in for JWT tokens, refresh the access token",
)

register_request_model = register_schema(ns, RegisterRequest)
user_response_model = register_schema(ns, UserResponse)
login_request_model = register_schema(ns, LoginRequest)
token_response_model = register_schema(ns, TokenResponse)
refresh_request_model = register_schema(ns, RefreshRequest)
access_token_model = register_schema(ns, AccessTokenResponse)
error_model = register_schema(ns, ErrorResponse)


class AuthResource(Resource):
    @inject
    def __init__(self, service: AuthService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = service


@ns.route("/register/")
class Register(AuthResource):
    @ns.expect(register_request_model)
    @ns.response(201, "Account created.", user_response_model)
    @ns.response(400, "The request body is not valid JSON.", error_model)
    @ns.response(409, "The username or email is already registered.", error_model)
    @ns.response(415, "The Content-Type is not application/json.", error_model)
    @ns.response(422, "A field is missing or invalid.", error_model)
    @ns.response(503, "The storage service is temporarily unavailable.", error_model)
    def post(self) -> tuple[dict[str, Any], int]:
        """Create an account.

        New accounts start on the Free tier. The password is stored as a
        salted hash and is never returned.
        """
        payload = RegisterRequest.model_validate(ns.payload)
        user = self._service.register(
            payload.username, str(payload.email), payload.password
        )
        return UserResponse.model_validate(user).model_dump(mode="json"), 201


@ns.route("/login/")
class Login(AuthResource):
    @ns.expect(login_request_model)
    @ns.response(200, "Logged in.", token_response_model)
    @ns.response(400, "The request body is not valid JSON.", error_model)
    @ns.response(401, "Invalid username or password.", error_model)
    @ns.response(415, "The Content-Type is not application/json.", error_model)
    @ns.response(422, "A field is missing or invalid.", error_model)
    @ns.response(
        429,
        "Too many login attempts from this address (5 per minute).",
        error_model,
        headers={"Retry-After": "Seconds to wait before trying again."},
    )
    @ns.response(503, "The storage service is temporarily unavailable.", error_model)
    # Counts every attempt from the client's IP, successful or not, against
    # brute-force password guessing.
    @limiter.limit(
        lambda: str(current_app.config["LOGIN_RATE_LIMIT"]),
        error_message="Too many login attempts. Please wait and try again.",
    )
    def post(self) -> dict[str, Any]:
        """Log in and receive an access token and a refresh token.

        The access token expires after 15 minutes; send it as
        `Authorization: Bearer <access_token>`. The refresh token (7 days)
        gets new access tokens from /refresh/.
        """
        payload = LoginRequest.model_validate(ns.payload)
        tokens = self._service.login(payload.username, payload.password)
        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token or "",
            expires_in=tokens.expires_in,
        ).model_dump()


@ns.route("/refresh/")
class Refresh(AuthResource):
    @ns.expect(refresh_request_model)
    @ns.response(200, "A new access token.", access_token_model)
    @ns.response(400, "The request body is not valid JSON.", error_model)
    @ns.response(401, "The refresh token is invalid or expired.", error_model)
    @ns.response(415, "The Content-Type is not application/json.", error_model)
    @ns.response(422, "The refresh field is missing.", error_model)
    @ns.response(503, "The storage service is temporarily unavailable.", error_model)
    def post(self) -> dict[str, Any]:
        """Get a new access token with a refresh token."""
        payload = RefreshRequest.model_validate(ns.payload)
        tokens = self._service.refresh(payload.refresh)
        return AccessTokenResponse(
            access_token=tokens.access_token, expires_in=tokens.expires_in
        ).model_dump()
