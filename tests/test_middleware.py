import logging
import re

import pytest
from flask.testing import FlaskClient

from app import create_app


def request_log_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.module == "middleware"
    ]


def test_successful_request_is_logged_with_status_and_duration(
    client: FlaskClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        client.post("/api/urls", json={"url": "https://example.com"})

    lines = request_log_lines(caplog)
    assert len(lines) == 1
    assert re.fullmatch(r"POST /api/urls 201 \d+\.\dms", lines[0])


@pytest.mark.parametrize(
    ("method", "path", "json", "status"),
    [
        ("GET", "/api/missing", None, 404),
        ("POST", "/api/urls", {"url": "not-a-url"}, 422),
        ("GET", "/foo", None, 404),
    ],
)
def test_error_responses_are_logged(
    client: FlaskClient,
    caplog: pytest.LogCaptureFixture,
    method: str,
    path: str,
    json: dict[str, str] | None,
    status: int,
) -> None:
    with caplog.at_level(logging.INFO):
        client.open(path, method=method, json=json)

    assert request_log_lines(caplog)[0].startswith(f"{method} {path} {status} ")


def test_query_string_is_not_logged(
    client: FlaskClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        client.get("/api/missing?token=secret-value")

    assert "secret-value" not in " ".join(request_log_lines(caplog))


def test_app_logger_emits_info_in_production() -> None:
    # Guards against INFO logs silently disappearing under Gunicorn.
    app = create_app("production")

    assert app.logger.isEnabledFor(logging.INFO)
