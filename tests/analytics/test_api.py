from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.analytics.models import Click
from app.core.extensions import db
from app.users.models import Tier
from tests.conftest import StatementRecorder
from tests.contract import assert_matches_schema
from tests.factories import bearer, create_url, create_user

PASSWORD = "correct horse battery staple"
PREMIUM = "alice"
NEWS = "https://news.example.org/"


@pytest.fixture(autouse=True)
def data(app: Flask) -> None:
    """alice (Premium) owns "stats01"; bob (Free) and carol (Premium) own nothing."""
    now = datetime.now(UTC)
    with app.app_context():
        alice = create_user("alice", tier=Tier.PREMIUM, is_premium=True)
        create_user("bob")
        create_user("carol", tier=Tier.PREMIUM, is_premium=True)
        url = create_url("stats01", owner=alice, click_count=6)
        visits = [
            # (when, ip, country, referrer)
            (now - timedelta(hours=1), "41.186.0.1", "RW", NEWS),
            (now - timedelta(hours=2), "41.186.0.1", "RW", None),
            (now - timedelta(days=1), "41.186.0.2", "RW", NEWS),
            (now - timedelta(days=2), "196.201.214.1", "KE", None),
            (now - timedelta(days=2), "172.20.0.1", None, None),
            (now - timedelta(days=40), "8.8.8.8", "US", None),  # outside 30 days
        ]
        db.session.add_all(
            Click(
                url=url, clicked_at=when, ip_address=ip, country=country, referrer=ref
            )
            for when, ip, country, ref in visits
        )
        db.session.commit()


def analytics(client: FlaskClient, query: str = "", user: str | None = PREMIUM) -> Any:
    headers = bearer(client, user) if user else {}
    return client.get(f"/api/v1/analytics/stats01/?{query}", headers=headers)


def test_report_counts_clicks_in_sql(client: FlaskClient) -> None:
    response = analytics(client)

    assert response.status_code == 200
    body = response.json
    assert body["short_code"] == "stats01"
    assert body["total_clicks"] == 6  # all time, including the 40-day-old click
    assert body["clicks"] == 5  # last 30 days
    assert body["unique_visitors"] == 4  # 41.186.0.1 clicked twice
    assert body["by_country"] == [
        {"country": "RW", "clicks": 3},
        {"country": "KE", "clicks": 1},
        {"country": None, "clicks": 1},
    ]
    assert body["top_referrers"] == [
        {"referrer": None, "clicks": 3},
        {"referrer": NEWS, "clicks": 2},
    ]
    assert body["period"]["interval"] == "day"
    assert_matches_schema(client, "AnalyticsResponse", body)


def test_daily_series_is_zero_filled(client: FlaskClient) -> None:
    series = analytics(client, "days=5").json["time_series"]

    starts = [datetime.fromisoformat(bucket["period_start"]) for bucket in series]
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    assert starts == [today - timedelta(days=n) for n in range(5, -1, -1)]
    assert sum(bucket["clicks"] for bucket in series) == 5
    assert 0 in [bucket["clicks"] for bucket in series]  # empty days are present


@pytest.mark.parametrize(
    ("interval", "is_bucket_start"),
    [
        ("week", lambda start: start.weekday() == 0),  # Mondays
        ("month", lambda start: start.day == 1),
    ],
)
def test_weekly_and_monthly_buckets(
    client: FlaskClient, interval: str, is_bucket_start: Any
) -> None:
    series = analytics(client, f"interval={interval}&days=90").json["time_series"]

    starts = [datetime.fromisoformat(bucket["period_start"]) for bucket in series]
    assert all(is_bucket_start(start) and start.hour == 0 for start in starts)
    assert starts == sorted(starts)
    # The 40-day-old click is inside a 90-day period.
    assert sum(bucket["clicks"] for bucket in series) == 6


def test_free_accounts_get_403(client: FlaskClient) -> None:
    response = analytics(client, user="bob")

    assert response.status_code == 403
    assert response.json["error"]["code"] == "forbidden"


def test_other_users_urls_are_not_found(client: FlaskClient) -> None:
    assert analytics(client, user="carol").status_code == 404


def test_requires_authentication(client: FlaskClient) -> None:
    assert analytics(client, user=None).status_code == 401


@pytest.mark.parametrize("query", ["days=0", "days=366", "interval=year"])
def test_rejects_invalid_parameters(client: FlaskClient, query: str) -> None:
    assert analytics(client, query).status_code == 422


def test_query_count_does_not_grow_with_clicks(
    app: Flask, client: FlaskClient, sql_statements: StatementRecorder
) -> None:
    headers = bearer(
        client, PREMIUM
    )  # outside the blocks: only the app's queries count
    url = "/api/v1/analytics/stats01/"
    with sql_statements() as before:
        client.get(url, headers=headers)

    with app.app_context():
        url_id = db.session.scalars(db.select(Click.url_id)).first()
        db.session.add_all(
            Click(url_id=url_id, ip_address=f"41.186.1.{n}", country="RW")
            for n in range(50)
        )
        db.session.commit()

    with sql_statements() as after:
        body = client.get(url, headers=headers).json

    assert body is not None

    assert body["clicks"] == 55
    # authentication, URL lookup, totals, time series, countries, referrers
    assert len(before) == len(after) == 6
