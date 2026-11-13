"""Small helpers that create and save rows for tests."""

from typing import Any

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
