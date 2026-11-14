from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.errors import ConflictError
from app.core.extensions import db
from app.users.models import User

# Which field a unique-constraint violation on the users table refers to.
UNIQUE_FIELDS = {"uq_users_username": "username", "uq_users_email": "email"}

# Checked when the username does not exist, so an unknown username takes as long
# as a wrong password and response times don't reveal which usernames exist.
DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password")


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
            constraint = getattr(
                getattr(error.orig, "diag", None), "constraint_name", ""
            )
            field = UNIQUE_FIELDS.get(constraint)
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
