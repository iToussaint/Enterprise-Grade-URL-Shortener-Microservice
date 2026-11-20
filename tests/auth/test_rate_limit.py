import time
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from tests.conftest import AppFactory
from tests.factories import create_user

LOGIN = "/api/v1/auth/login/"
PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def alice(app: Flask) -> None:
    with app.app_context():
        create_user("alice")


def login(
    client: FlaskClient, password: str = PASSWORD, ip: str = "203.0.113.10"
) -> Any:
    return client.post(
        LOGIN,
        json={"username": "alice", "password": password},
        environ_base={"REMOTE_ADDR": ip},
    )


def test_sixth_attempt_in_a_minute_is_refused(client: FlaskClient) -> None:
    statuses = [login(client, "wrong password").status_code for _ in range(5)]

    response = login(client, "wrong password")

    assert statuses == [401] * 5
    assert response.status_code == 429
    assert response.json is not None
    assert response.json["error"] == {
        "code": "too_many_requests",
        "message": "Too many login attempts. Please wait and try again.",
    }
    assert int(response.headers["Retry-After"]) > 0


def test_the_right_password_is_also_refused_once_limited(client: FlaskClient) -> None:
    for _ in range(5):
        login(client, "wrong password")

    # Otherwise an attacker would keep guessing and only stop when it worked.
    assert login(client).status_code == 429


def test_successful_logins_count_too(client: FlaskClient) -> None:
    statuses = [login(client).status_code for _ in range(6)]

    assert statuses == [200] * 5 + [429]


def test_each_address_has_its_own_limit(client: FlaskClient) -> None:
    for _ in range(6):
        login(client, "wrong password", ip="203.0.113.10")

    assert login(client, ip="198.51.100.20").status_code == 200


def test_remaining_attempts_are_announced(client: FlaskClient) -> None:
    response = login(client)

    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "4"


def test_other_auth_endpoints_are_not_limited(client: FlaskClient) -> None:
    statuses = [
        client.post(
            "/api/v1/auth/refresh/",
            json={"refresh": "not-a-token"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        ).status_code
        for _ in range(7)
    ]

    assert statuses == [401] * 7


def test_attempts_are_allowed_again_after_the_window(make_app: AppFactory) -> None:
    app = make_app(LOGIN_RATE_LIMIT="2 per 1 second")
    client = app.test_client()
    login(client, "wrong password")
    login(client, "wrong password")
    assert login(client, "wrong password").status_code == 429

    time.sleep(1.1)

    assert login(client, "wrong password").status_code == 401
