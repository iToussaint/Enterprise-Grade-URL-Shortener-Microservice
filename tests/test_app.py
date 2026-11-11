import decouple
import pytest
from flask.testing import FlaskClient

from app import create_app
from tests.conftest import AppFactory


@pytest.mark.parametrize(
    ("config_name", "expected_debug", "expected_testing"),
    [
        ("development", True, False),
        ("production", False, False),
        ("testing", False, True),
    ],
)
def test_create_app_applies_selected_config(
    make_app: AppFactory,
    config_name: str,
    expected_debug: bool,
    expected_testing: bool,
) -> None:
    app = make_app(config_name)

    assert app.config["DEBUG"] is expected_debug
    assert app.config["TESTING"] is expected_testing


def test_create_app_reads_app_env(
    make_app: AppFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "development")

    assert make_app(None).config["DEBUG"] is True


def test_create_app_defaults_to_production(
    make_app: AppFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Ignore any local .env file so only the code default applies.
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setattr(decouple, "config", decouple.Config(decouple.RepositoryEmpty()))

    assert make_app(None).config["DEBUG"] is False


def test_create_app_rejects_unknown_config() -> None:
    with pytest.raises(ValueError, match="Unknown APP_ENV"):
        create_app("staging")


def test_swagger_spec_is_served(client: FlaskClient) -> None:
    response = client.get("/api/swagger.json")

    assert response.status_code == 200
    assert response.json is not None
    assert response.json["info"]["title"] == "URL Shortener API"


def test_swagger_ui_is_served(client: FlaskClient) -> None:
    response = client.get("/api/docs")

    assert response.status_code == 200
