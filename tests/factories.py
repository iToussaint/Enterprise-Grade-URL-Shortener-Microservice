"""Small helpers that create and save rows for tests."""

from typing import Any

from flask.testing import FlaskClient
from flask_jwt_extended import create_access_token
from sqlalchemy import select

from app.core.extensions import db
from app.urls.models import URL
from app.users.models import User


def create_user(username: str = "alice", **fields: Any) -> User:
    user = User(username=username, email=f"{username}@example.com", **fields)
    user.set_password("correct horse battery staple")
    db.session.add(user)
    db.session.commit()
    return user


def create_url(short_code: str = "abc1234", **fields: Any) -> URL:
    values = {"original_url": "https://example.com/", **fields}
    url = URL(short_code=short_code, **values)
    db.session.add(url)
    db.session.commit()
    return url


def bearer(client: FlaskClient, username: str) -> dict[str, str]:
    """An Authorization header with a fresh access token for an existing user."""
    with client.application.app_context():
        user_id = db.session.scalars(
            select(User.id).where(User.username == username)
        ).one()
        token = create_access_token(identity=str(user_id))
    return {"Authorization": f"Bearer {token}"}
