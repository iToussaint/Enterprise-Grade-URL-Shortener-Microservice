from typing import Any

from flask_restx import Namespace, Resource
from injector import inject

from app.auth.schemas import RegisterRequest, UserResponse
from app.auth.service import AuthService
from app.core.errors import ErrorResponse
from app.core.swagger import register_schema

ns = Namespace(
    "auth",
    path="/v1/auth",
    description="Create an account. Protected endpoints use HTTP Basic "
    "authentication (Authorize button); JWT login arrives in Module 7.",
)

register_request_model = register_schema(ns, RegisterRequest)
user_response_model = register_schema(ns, UserResponse)
error_model = register_schema(ns, ErrorResponse)


@ns.route("/register/")
class Register(Resource):
    @inject
    def __init__(self, service: AuthService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = service

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
