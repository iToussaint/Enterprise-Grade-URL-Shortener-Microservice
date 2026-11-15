from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from app.analytics.geoip import GeoIPLocator, Location
from app.analytics.models import Click
from app.core.extensions import db
from app.urls.models import URL
from tests.conftest import AppFactory
from tests.factories import create_url, create_user

TARGET = "https://www.example.com/landing"
KIGALI_IP = "41.186.0.1"


class FakeLocator:
    """Stands in for the DB-IP database: one known public IP."""

    def locate(self, ip: str) -> Location:
        return Location("Kigali", "RW") if ip == KIGALI_IP else Location()


def use_fake_locator(app: Flask) -> None:
    app.extensions["injector"].binder.bind(GeoIPLocator, to=FakeLocator())


@pytest.fixture(autouse=True)
def links(app: Flask) -> None:
    use_fake_locator(app)
    yesterday = datetime.now(UTC) - timedelta(days=1)
    with app.app_context():
        owner = create_user("alice")
        create_url("live123", original_url=TARGET, owner=owner, custom_alias="promo")
        create_url("off1234", original_url=TARGET, is_active=False)
        create_url("old1234", original_url=TARGET, expires_at=yesterday)


def clicks(app: Flask) -> list[Click]:
    with app.app_context():
        return list(db.session.scalars(select(Click)))


def click_count(app: Flask, code: str) -> int:
    with app.app_context():
        return db.session.scalars(
            select(URL.click_count).where(URL.short_code == code)
        ).one()


# ---- redirecting ------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/live123/", "/live123", "/promo/", "/api/live123", "/api/promo"],
    ids=["code", "code without slash", "alias", "api code", "api alias"],
)
def test_redirects_with_302(client: FlaskClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 302
    assert response.headers["Location"] == TARGET


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/nothing/", 404, "not_found"),
        ("/off1234/", 410, "gone"),
        ("/old1234/", 410, "gone"),
        ("/api/off1234", 410, "gone"),
    ],
    ids=["unknown", "deactivated", "expired", "api deactivated"],
)
def test_unknown_or_unavailable_links_are_not_redirected(
    app: Flask, client: FlaskClient, path: str, status: int, code: str
) -> None:
    response = client.get(path)

    assert response.status_code == status
    assert response.json is not None
    assert response.json["error"]["code"] == code
    assert clicks(app) == []  # only successful redirects count


def test_gone_message_says_why(client: FlaskClient) -> None:
    deactivated = client.get("/off1234/").json
    expired = client.get("/old1234/").json

    assert deactivated is not None and "deactivated" in deactivated["error"]["message"]
    assert expired is not None and "expired" in expired["error"]["message"]


# ---- click tracking ---------------------------------------------------------


def test_each_redirect_records_a_click(app: Flask, client: FlaskClient) -> None:
    client.get(
        "/promo/",
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://news.example.org/"},
    )

    [click] = clicks(app)
    assert click.ip_address == "127.0.0.1"
    assert click.user_agent == "Mozilla/5.0"
    assert click.referrer == "https://news.example.org/"
    # A local address has no location.
    assert (click.city, click.country) == (None, None)
    assert click_count(app, "live123") == 1


def test_click_count_counts_simultaneous_clicks(app: Flask) -> None:
    def visit(_: int) -> int:
        return int(app.test_client().get("/live123/").status_code)

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(visit, range(20)))

    assert statuses == [302] * 20
    assert click_count(app, "live123") == 20
    assert len(clicks(app)) == 20


def test_very_long_user_agents_are_capped(app: Flask, client: FlaskClient) -> None:
    client.get("/live123/", headers={"User-Agent": "x" * 5000})

    assert len(clicks(app)[0].user_agent) == 1000


# ---- client IP and proxies --------------------------------------------------


def test_forwarded_for_is_ignored_without_trusted_proxies(
    app: Flask, client: FlaskClient
) -> None:
    # Anyone can send this header; trusting it by default would let clients
    # fake their address.
    client.get("/live123/", headers={"X-Forwarded-For": KIGALI_IP})

    assert clicks(app)[0].ip_address == "127.0.0.1"


def test_behind_a_trusted_proxy_the_forwarded_ip_is_located(
    make_app: AppFactory, app: Flask
) -> None:
    proxied = make_app(TRUSTED_PROXY_COUNT=1)
    use_fake_locator(proxied)

    proxied.test_client().get("/live123/", headers={"X-Forwarded-For": KIGALI_IP})

    [click] = clicks(app)
    assert click.ip_address == KIGALI_IP
    assert (click.city, click.country) == ("Kigali", "RW")


# ---- reserved aliases -------------------------------------------------------


@pytest.mark.parametrize("alias", ["api", "Static", "swaggerui"])
def test_aliases_cannot_shadow_other_routes(client: FlaskClient, alias: str) -> None:
    body: dict[str, Any] = {"url": TARGET, "custom_alias": alias}

    response = client.post(
        "/api/v1/urls/", json=body, auth=("alice", "correct horse battery staple")
    )

    assert response.status_code == 422
