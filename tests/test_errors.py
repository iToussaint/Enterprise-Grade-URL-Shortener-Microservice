from typing import Any

import pytest
from fakeredis import FakeRedis
from flask import Flask
from flask.testing import FlaskClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.errors import ShortCodeGenerationError
from app.shortener.service import UrlShortenerService


def assert_error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    assert response.is_json
    assert set(response.json) == {"error"}
    error: dict[str, Any] = response.json["error"]
    assert error["code"] == code
    assert error["message"]
    return error


def test_malformed_json_returns_400(client: FlaskClient) -> None:
    response = client.post(
        "/api/urls", data="{not json", content_type="application/json"
    )

    assert_error(response, 400, "bad_request")


def test_non_json_body_returns_415(client: FlaskClient) -> None:
    response = client.post("/api/urls", data="url=https://example.com")

    assert_error(response, 415, "unsupported_media_type")


def test_wrong_method_returns_405_with_allow_header(client: FlaskClient) -> None:
    response = client.delete("/api/urls")

    assert_error(response, 405, "method_not_allowed")
    assert "POST" in response.headers["Allow"]


@pytest.mark.parametrize("path", ["/foo", "/api/a/b"])
def test_unknown_path_returns_404_json(client: FlaskClient, path: str) -> None:
    response = client.get(path)

    assert_error(response, 404, "not_found")


def test_unexpected_exception_returns_generic_500_and_logs(
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(self: UrlShortenerService, original_url: str) -> str:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(UrlShortenerService, "shorten", broken)

    response = client.post("/api/urls", json={"url": "https://example.com"})

    error = assert_error(response, 500, "internal_server_error")
    assert "secret internal detail" not in error["message"]
    assert "secret internal detail" in caplog.text


def test_unexpected_exception_outside_api_returns_500_json_and_logs(
    app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    def broken_view() -> str:
        raise RuntimeError("failure outside the API")

    app.add_url_rule("/broken", view_func=broken_view)

    response = app.test_client().get("/broken")

    assert_error(response, 500, "internal_server_error")
    assert len([record for record in caplog.records if record.exc_info]) == 1


def test_redis_unavailable_returns_503_without_leaking_details(
    client: FlaskClient,
    redis_client: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def unavailable(*args: object, **kwargs: object) -> None:
        raise RedisConnectionError("Error connecting to redis:6379")

    monkeypatch.setattr(redis_client, "get", unavailable)

    response = client.get("/api/abc1234")

    error = assert_error(response, 503, "service_unavailable")
    assert "redis:6379" not in error["message"]
    assert "redis:6379" in caplog.text
    # Logged exactly once (by Flask-RESTX), with the traceback attached.
    assert len([record for record in caplog.records if record.exc_info]) == 1


def test_code_generation_failure_returns_503(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def exhausted(self: UrlShortenerService, original_url: str) -> str:
        raise ShortCodeGenerationError("no free code")

    monkeypatch.setattr(UrlShortenerService, "shorten", exhausted)

    response = client.post("/api/urls", json={"url": "https://example.com"})

    assert_error(response, 503, "service_unavailable")
