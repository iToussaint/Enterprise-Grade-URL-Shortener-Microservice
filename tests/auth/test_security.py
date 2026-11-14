import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from app.auth.security import current_user, login_required
from tests.factories import create_user

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
        create_user("inactive", is_active=False)
    return app.test_client()


def test_valid_credentials_reach_the_view_as_that_user(probe: FlaskClient) -> None:
    response = probe.get("/probe", auth=("alice", PASSWORD))

    assert response.status_code == 200
    assert response.json == {"username": "alice"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer some-token"},
        {"Authorization": "Basic not-base64!"},
    ],
    ids=["no header", "other scheme", "malformed"],
)
def test_missing_or_unusable_credentials_get_401(
    probe: FlaskClient, headers: dict[str, str]
) -> None:
    response = probe.get("/probe", headers=headers)

    assert_unauthorized(response)


@pytest.mark.parametrize(
    "credentials",
    [("alice", "wrong password"), ("nobody", PASSWORD), ("inactive", PASSWORD)],
    ids=["wrong password", "unknown user", "inactive user"],
)
def test_rejected_credentials_get_401(
    probe: FlaskClient, credentials: tuple[str, str]
) -> None:
    assert_unauthorized(probe.get("/probe", auth=credentials))


def assert_unauthorized(response: TestResponse) -> None:
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == 'Basic realm="URL Shortener"'
    assert response.json is not None
    assert response.json["error"]["code"] == "unauthorized"
