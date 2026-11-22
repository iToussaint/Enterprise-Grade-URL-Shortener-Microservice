from dataclasses import dataclass
from datetime import UTC, datetime

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.errors import AuthenticationError, ConflictError, violated_constraint
from app.core.extensions import db
from app.users.models import User

# Which field a unique-constraint violation on the users table refers to.
UNIQUE_FIELDS = {"uq_users_username": "username", "uq_users_email": "email"}

# Checked when the username does not exist, so an unknown username takes as long
# as a wrong password and response times don't reveal which usernames exist.
DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password")


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_in: int  # seconds until the access token expires


class AuthService:
    def register(self, username: str, email: str, password: str) -> User:
        user = User(username=username, email=email.lower())
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError as error:
            # The unique constraints decide, so two simultaneous registrations
            # with the same name cannot both succeed.
            db.session.rollback()
            field = UNIQUE_FIELDS.get(violated_constraint(error))
            if field is None:
                raise
            raise ConflictError(field, f"This {field} is already registered.") from None
        return user

    def authenticate(self, username: str, password: str) -> User | None:
        """Return the active user these credentials belong to, or None."""
        user: User | None = db.session.scalar(
            select(User).where(User.username == username)
        )
        if user is None:
            check_password_hash(DUMMY_PASSWORD_HASH, password)
            return None
        if not user.check_password(password) or not user.is_active:
            return None
        return user

    def login(self, username: str, password: str) -> Tokens:
        """Check the password once and issue an access and a refresh token."""
        user = self.authenticate(username, password)
        if user is None:
            # One message for every failure: it doesn't reveal which usernames exist.
            raise AuthenticationError("Invalid username or password.")
        user.last_login = datetime.now(UTC)
        db.session.commit()
        identity = str(user.id)
        return Tokens(
            access_token=create_access_token(identity=identity),
            refresh_token=create_refresh_token(identity=identity),
            expires_in=self._access_token_lifetime(),
        )

    def refresh(self, refresh_token: str) -> Tokens:
        """A new access token, if the refresh token is valid and its user active."""
        try:
            claims = decode_token(refresh_token)
        except (PyJWTError, JWTExtendedException):
            raise AuthenticationError("Invalid or expired refresh token.") from None
        if claims.get("type") != "refresh":
            raise AuthenticationError("A refresh token is required.")

        user = db.session.get(User, int(claims["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("Invalid or expired refresh token.")
        return Tokens(
            access_token=create_access_token(identity=str(user.id)),
            refresh_token=None,
            expires_in=self._access_token_lifetime(),
        )

    @staticmethod
    def _access_token_lifetime() -> int:
        return int(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds())
