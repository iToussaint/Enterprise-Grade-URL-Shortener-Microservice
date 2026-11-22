from datetime import timedelta
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import create_access_token, create_refresh_token
from sqlalchemy import select
from werkzeug.test import TestResponse

from app.auth.security import current_user, login_required
from app.core.extensions import db
from app.users.models import User
from tests.factories import bearer, create_user

PASSWORD = "correct horse battery staple"


@pytest.fixture
def probe(app: Flask) -> FlaskClient:
    """A test-only route protected the same way the real endpoints are."""

    @app.route("/probe")
    @login_required
    def probe_view() -> dict[str, str]:
        return {"username": current_user().username}

    with app.app_context():
        create_user("alice")
    return app.test_client()


def token_for(app: Flask, kind: str = "access", **options: Any) -> str:
    with app.app_context():
        user_id = db.session.scalars(
            select(User.id).where(User.username == "alice")
        ).one()
        create = create_refresh_token if kind == "refresh" else create_access_token
        token: str = create(identity=str(user_id), **options)
        return token


def test_a_valid_access_token_reaches_the_view_as_that_user(
    probe: FlaskClient,
) -> None:
    response = probe.get("/probe", headers=bearer(probe, "alice"))

    assert response.status_code == 200
    assert response.json == {"username": "alice"}


def test_a_token_from_login_works(probe: FlaskClient) -> None:
    login = probe.post(
        "/api/v1/auth/login/", json={"username": "alice", "password": PASSWORD}
    )
    assert login.json is not None
    token = login.json["access_token"]

    response = probe.get("/probe", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic YWxpY2U6Y29ycmVjdA=="},  # Basic auth no longer works
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer not-a-token"},
    ],
    ids=["no header", "basic credentials", "empty bearer", "garbage token"],
)
def test_missing_or_unusable_credentials_get_401(
    probe: FlaskClient, headers: dict[str, str]
) -> None:
    assert_unauthorized(probe.get("/probe", headers=headers))


@pytest.mark.parametrize(
    ("kind", "options", "message"),
    [
        ("access", {"expires_delta": timedelta(seconds=-1)}, "expired"),
        ("refresh", {}, "valid access token"),
    ],
    ids=["expired access token", "refresh token used as access token"],
)
def test_rejected_tokens_get_401(
    app: Flask, probe: FlaskClient, kind: str, options: dict[str, Any], message: str
) -> None:
    token = token_for(app, kind, **options)

    response = probe.get("/probe", headers={"Authorization": f"Bearer {token}"})

    assert_unauthorized(response)
    assert response.json is not None
    assert message in response.json["error"]["message"]


def test_a_tampered_token_gets_401(app: Flask, probe: FlaskClient) -> None:
    token = token_for(app)[:-3] + "abc"

    assert_unauthorized(
        probe.get("/probe", headers={"Authorization": f"Bearer {token}"})
    )


@pytest.mark.parametrize("change", ["deactivate", "delete"])
def test_tokens_of_inactive_or_deleted_users_get_401(
    app: Flask, probe: FlaskClient, change: str
) -> None:
    headers = bearer(probe, "alice")
    with app.app_context():
        user = db.session.scalars(select(User).where(User.username == "alice")).one()
        if change == "deactivate":
            user.is_active = False
        else:
            db.session.delete(user)
        db.session.commit()

    assert_unauthorized(probe.get("/probe", headers=headers))


def assert_unauthorized(response: TestResponse) -> None:
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == 'Bearer realm="URL Shortener"'
    assert response.json is not None
    assert response.json["error"]["code"] == "unauthorized"
