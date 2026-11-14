from typing import Any

import jsonschema
import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from app.core.extensions import db
from app.users.models import User

REGISTER = "/api/v1/auth/register/"
ACCOUNT = {
    "username": "alice",
    "email": "alice@example.com",
    "password": "correct horse battery staple",
}


def register(client: FlaskClient, **changes: str) -> Any:
    return client.post(REGISTER, json={**ACCOUNT, **changes})


def test_register_creates_a_free_account(app: Flask, client: FlaskClient) -> None:
    response = register(client)

    assert response.status_code == 201
    body = response.json
    assert set(body) == {"id", "username", "email", "tier", "is_premium", "date_joined"}
    assert body["username"] == "alice"
    assert body["tier"] == "Free"
    assert body["is_premium"] is False
    with app.app_context():
        user = db.session.scalars(select(User)).one()
        assert user.check_password("correct horse battery staple")


def test_register_response_matches_the_published_schema(client: FlaskClient) -> None:
    spec = client.get("/api/swagger.json").json
    assert spec is not None
    schema = {"$ref": "#/definitions/UserResponse", "definitions": spec["definitions"]}

    jsonschema.validate(register(client).json, schema)


def test_register_stores_the_email_in_lowercase(client: FlaskClient) -> None:
    response = register(client, email="Alice@Example.COM")

    assert response.json["email"] == "alice@example.com"


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"email": "bob@example.com"}, "username"),
        ({"username": "bob", "email": "ALICE@example.com"}, "email"),
    ],
    ids=["taken username", "taken email in another case"],
)
def test_register_rejects_a_taken_username_or_email(
    client: FlaskClient, changes: dict[str, str], field: str
) -> None:
    register(client)

    response = register(client, **changes)

    assert response.status_code == 409
    error = response.json["error"]
    assert error["code"] == "conflict"
    assert error["details"][0]["field"] == field


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"email": "not-an-email"}, "email"),
        ({"password": "short"}, "password"),
        ({"username": "al ice"}, "username"),
        ({"username": ""}, "username"),
    ],
)
def test_register_validates_the_fields(
    client: FlaskClient, changes: dict[str, str], field: str
) -> None:
    response = register(client, **changes)

    assert response.status_code == 422
    assert [detail["field"] for detail in response.json["error"]["details"]] == [field]


def test_register_never_returns_the_password(client: FlaskClient) -> None:
    body = register(client).get_data(as_text=True)

    assert "password" not in body
    assert "scrypt" not in body
