from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from sqlalchemy import select

from app import create_app
from app.core.extensions import db
from app.users.models import User
from tests.conftest import AppFactory
from tests.contract import assert_matches_schema
from tests.factories import create_user

LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/refresh/"
PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def users(app: Flask) -> None:
    with app.app_context():
        create_user("alice")
        create_user("inactive", is_active=False)


def login(
    client: FlaskClient, username: str = "alice", password: str = PASSWORD
) -> Any:
    return client.post(LOGIN, json={"username": username, "password": password})


def claims(app: Flask, token: str) -> dict[str, Any]:
    with app.app_context():
        decoded: dict[str, Any] = decode_token(token)
        return decoded


def alice_id(app: Flask) -> int:
    with app.app_context():
        return db.session.scalars(select(User.id).where(User.username == "alice")).one()


# ---- login ------------------------------------------------------------------


def test_login_returns_an_access_and_a_refresh_token(
    app: Flask, client: FlaskClient
) -> None:
    response = login(client)

    assert response.status_code == 200
    body = response.json
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 15 * 60
    access, refresh = claims(app, body["access_token"]), claims(
        app, body["refresh_token"]
    )
    assert (access["type"], refresh["type"]) == ("access", "refresh")
    assert access["sub"] == refresh["sub"] == str(alice_id(app))
    assert access["exp"] - access["iat"] == 15 * 60
    assert refresh["exp"] - refresh["iat"] == 7 * 24 * 60 * 60
    assert_matches_schema(client, "TokenResponse", body)


def test_login_records_last_login(app: Flask, client: FlaskClient) -> None:
    before = datetime.now(UTC)

    login(client)

    with app.app_context():
        user = db.session.scalars(select(User).where(User.username == "alice")).one()
        assert user.last_login is not None and user.last_login >= before


@pytest.mark.parametrize(
    ("username", "password"),
    [("alice", "wrong password"), ("nobody", PASSWORD), ("inactive", PASSWORD)],
    ids=["wrong password", "unknown user", "inactive user"],
)
def test_failed_logins_get_the_same_401(
    client: FlaskClient, username: str, password: str
) -> None:
    response = login(client, username, password)

    assert response.status_code == 401
    # The same message for every failure: it doesn't reveal which usernames exist.
    assert response.json["error"] == {
        "code": "unauthorized",
        "message": "Invalid username or password.",
    }


@pytest.mark.parametrize("body", [{}, {"username": "alice"}, {"password": PASSWORD}])
def test_login_requires_both_fields(client: FlaskClient, body: dict[str, str]) -> None:
    assert client.post(LOGIN, json=body).status_code == 422


# ---- refresh ----------------------------------------------------------------


def test_refresh_returns_a_new_access_token(app: Flask, client: FlaskClient) -> None:
    refresh_token = login(client).json["refresh_token"]

    response = client.post(REFRESH, json={"refresh": refresh_token})

    assert response.status_code == 200
    body = response.json
    assert body is not None
    assert set(body) == {"access_token", "token_type", "expires_in"}
    new_access = claims(app, body["access_token"])
    assert new_access["type"] == "access"
    assert new_access["sub"] == str(alice_id(app))
    assert_matches_schema(client, "AccessTokenResponse", body)


def make_token(app: Flask, kind: str, **options: Any) -> str:
    with app.app_context():
        create = create_refresh_token if kind == "refresh" else create_access_token
        token: str = create(identity=str(alice_id(app)), **options)
        return token


@pytest.mark.parametrize(
    "token_factory",
    [
        lambda app: make_token(app, "access"),
        lambda app: make_token(app, "refresh", expires_delta=timedelta(seconds=-1)),
        lambda app: make_token(app, "refresh")[:-3] + "abc",
        lambda app: "not-a-token",
    ],
    ids=["access token", "expired", "tampered signature", "garbage"],
)
def test_refresh_rejects_unusable_tokens(
    app: Flask, client: FlaskClient, token_factory: Any
) -> None:
    response = client.post(REFRESH, json={"refresh": token_factory(app)})

    assert response.status_code == 401
    assert response.json is not None
    assert response.json["error"]["code"] == "unauthorized"


def test_refresh_rejects_a_token_signed_with_another_key(
    app: Flask, client: FlaskClient
) -> None:
    other = Flask(__name__)
    other.config["JWT_SECRET_KEY"] = "a-completely-different-key-for-signing-tokens"
    JWTManager(other)
    with other.app_context():
        forged = create_refresh_token(identity=str(alice_id(app)))

    assert client.post(REFRESH, json={"refresh": forged}).status_code == 401


def test_deactivated_users_cannot_refresh(app: Flask, client: FlaskClient) -> None:
    refresh_token = login(client).json["refresh_token"]
    with app.app_context():
        user = db.session.scalars(select(User).where(User.username == "alice")).one()
        user.is_active = False
        db.session.commit()

    assert client.post(REFRESH, json={"refresh": refresh_token}).status_code == 401


# ---- signing key ------------------------------------------------------------


@pytest.mark.parametrize("secret", [None, "", "too-short"])
def test_app_refuses_to_start_without_a_strong_secret(
    make_app: AppFactory, secret: str | None
) -> None:
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        make_app("production", JWT_SECRET_KEY=secret)


def test_testing_profile_has_its_own_secret() -> None:
    app = create_app(
        "testing", {"SQLALCHEMY_DATABASE_URI": "postgresql+psycopg2://x@y/z"}
    )

    assert len(app.config["JWT_SECRET_KEY"]) >= 32
