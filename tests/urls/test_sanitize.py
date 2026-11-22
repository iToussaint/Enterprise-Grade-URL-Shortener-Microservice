from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.users.models import Tier
from tests.factories import bearer, create_user

V1 = "/api/v1/urls/"

REFUSED = [
    ("https://example.com/a b", "spaces or invisible characters"),
    ("https://example.com/a\tb", "spaces or invisible characters"),
    ("https://example.com/\x00", "spaces or invisible characters"),
    ("https://example.com/​pay", "spaces or invisible characters"),  # zero-width
    ("https://example.com/‮gpj.exe", "spaces or invisible characters"),  # RTL
    ("https://user:secret@example.com/", "username or password"),
    ("https://user@example.com/", "username or password"),
    ("http://localhost/abc1234/", "this URL shortener"),
    ("http://LOCALHOST:80/abc1234/", "this URL shortener"),
    ("javascript:alert(1)", "URL scheme should be 'http' or 'https'"),
    ("ftp://example.com/file", "URL scheme should be 'http' or 'https'"),
]
REFUSED_IDS = [
    "space",
    "tab",
    "NUL",
    "zero-width space",
    "right-to-left override",
    "user and password",
    "user only",
    "own host",
    "own host, other spelling",
    "javascript scheme",
    "ftp scheme",
]


@pytest.fixture(autouse=True)
def alice(app: Flask) -> None:
    with app.app_context():
        create_user("alice", tier=Tier.PREMIUM, is_premium=True)


def submit(client: FlaskClient, endpoint: str, url: str) -> Any:
    """Send the URL to one of the three endpoints that accept URLs."""
    if endpoint == "module 5":
        return client.post("/api/urls", json={"url": url})
    headers = bearer(client, "alice")
    if endpoint == "create":
        return client.post(V1, json={"url": url}, headers=headers)
    created = client.post(V1, json={"url": "https://example.com/"}, headers=headers)
    assert created.json is not None
    code = created.json["short_code"]
    return client.put(f"{V1}{code}/", json={"url": url}, headers=headers)


ENDPOINTS = pytest.mark.parametrize("endpoint", ["module 5", "create", "update"])


@ENDPOINTS
@pytest.mark.parametrize(("url", "message"), REFUSED, ids=REFUSED_IDS)
def test_unsafe_urls_are_refused(
    client: FlaskClient, endpoint: str, url: str, message: str
) -> None:
    response = submit(client, endpoint, url)

    assert response.status_code == 422
    [detail] = response.json["error"]["details"]
    assert detail["field"] == "url"
    assert message in detail["message"]


@ENDPOINTS
@pytest.mark.parametrize(
    ("submitted", "stored"),
    [
        ("  https://example.com/page  ", "https://example.com/page"),
        ("https://BÜCHER.example/Path", "https://xn--bcher-kva.example/Path"),
        ("HTTPS://Example.COM/CaseKept", "https://example.com/CaseKept"),
        ("http://localhost:8080/other-service", "http://localhost:8080/other-service"),
    ],
    ids=[
        "surrounding spaces trimmed",
        "international domain",
        "scheme and host lower-cased",
        "same host, other port",
    ],
)
def test_valid_urls_are_cleaned_and_kept(
    client: FlaskClient, endpoint: str, submitted: str, stored: str
) -> None:
    response = submit(client, endpoint, submitted)

    assert response.status_code in (200, 201)
    assert response.json["original_url"] == stored
