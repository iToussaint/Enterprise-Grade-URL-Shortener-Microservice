import pytest
from flask import Flask
from sqlalchemy import select

from app.core.extensions import db
from app.users.models import Tier, User
from tests.factories import create_user


@pytest.fixture(autouse=True)
def alice(app: Flask) -> None:
    with app.app_context():
        create_user("alice")


def stored(app: Flask) -> tuple[Tier, bool]:
    with app.app_context():
        user = db.session.scalars(select(User).where(User.username == "alice")).one()
        return user.tier, user.is_premium


@pytest.mark.parametrize(
    ("argument", "tier", "is_premium"),
    [
        ("premium", Tier.PREMIUM, True),
        ("Admin", Tier.ADMIN, True),
        ("free", Tier.FREE, False),
    ],
)
def test_set_tier_updates_tier_and_is_premium(
    app: Flask, argument: str, tier: Tier, is_premium: bool
) -> None:
    result = app.test_cli_runner().invoke(args=["users", "set-tier", "alice", argument])

    assert result.exit_code == 0, result.output
    assert f"tier={tier.value}" in result.output
    assert stored(app) == (tier, is_premium)


def test_unknown_user_is_an_error(app: Flask) -> None:
    result = app.test_cli_runner().invoke(args=["users", "set-tier", "nobody", "free"])

    assert result.exit_code == 1
    assert "No user named 'nobody'" in result.output


def test_unknown_tier_is_rejected(app: Flask) -> None:
    result = app.test_cli_runner().invoke(args=["users", "set-tier", "alice", "gold"])

    assert result.exit_code == 2  # usage error
    assert stored(app) == (Tier.FREE, False)
