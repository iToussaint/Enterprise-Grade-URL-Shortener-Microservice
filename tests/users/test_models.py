from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.users.models import Tier, User

pytestmark = pytest.mark.usefixtures("app_context")


def make_user(**fields: Any) -> User:
    values = {"username": "alice", "email": "alice@example.com", **fields}
    user = User(**values)
    user.set_password("correct horse battery staple")
    return user


def save(user: User) -> User:
    db.session.add(user)
    db.session.commit()
    return user


def test_new_user_gets_spec_defaults() -> None:
    user = save(make_user())
    db.session.refresh(user)

    assert user.tier is Tier.FREE
    assert user.is_premium is False
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.last_login is None
    # Set by PostgreSQL (server default now()), with a time zone.
    assert user.date_joined is not None
    assert user.date_joined.tzinfo is not None


def test_password_is_stored_as_a_hash() -> None:
    user = save(make_user())

    assert user.password != "correct horse battery staple"
    assert user.password.startswith("scrypt:")
    assert user.check_password("correct horse battery staple")
    assert not user.check_password("wrong password")


@pytest.mark.parametrize(
    "duplicate",
    [
        {"username": "bob", "email": "alice@example.com"},
        {"username": "alice", "email": "bob@example.com"},
    ],
    ids=["same email", "same username"],
)
def test_email_and_username_must_be_unique(duplicate: dict[str, str]) -> None:
    save(make_user())

    with pytest.raises(IntegrityError):
        save(make_user(**duplicate))


def test_email_is_required() -> None:
    with pytest.raises(IntegrityError):
        save(make_user(email=None))


def test_tier_is_stored_as_the_spec_text() -> None:
    save(make_user(tier=Tier.PREMIUM))

    stored = db.session.execute(text("SELECT tier FROM users")).scalar_one()

    assert stored == "Premium"


def test_database_rejects_an_unknown_tier() -> None:
    # Bypass the Python enum to prove the CHECK constraint protects the column.
    with pytest.raises(IntegrityError, match="ck_users_tier"):
        db.session.execute(
            text(
                "INSERT INTO users (username, email, password, first_name, last_name,"
                " is_active, is_staff, is_superuser, is_premium, tier)"
                " VALUES ('eve', 'eve@example.com', 'x', '', '',"
                " true, false, false, false, 'Gold')"
            )
        )
