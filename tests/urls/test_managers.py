from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql

from app.core.extensions import db
from app.urls.managers import URLManager, URLQuery
from app.urls.models import URL
from tests.factories import create_url

pytestmark = pytest.mark.usefixtures("app_context")

manager = URLManager()


def codes(query: URLQuery) -> list[str]:
    return [url.short_code for url in db.session.scalars(query)]


@pytest.fixture
def urls_of_every_kind(app_context: None) -> None:
    now = datetime.now(UTC)
    create_url("forever")
    create_url("future", expires_at=now + timedelta(days=1))
    create_url("expired", expires_at=now - timedelta(days=1))
    create_url("off", is_active=False)
    create_url("offexp", is_active=False, expires_at=now - timedelta(days=1))


@pytest.mark.usefixtures("urls_of_every_kind")
def test_active_urls_are_active_and_not_expired() -> None:
    assert set(codes(manager.active_urls())) == {"forever", "future"}


@pytest.mark.usefixtures("urls_of_every_kind")
def test_expired_urls_are_past_their_expiry_date_even_if_inactive() -> None:
    assert set(codes(manager.expired_urls())) == {"expired", "offexp"}


def test_popular_urls_are_ordered_by_click_count_then_newest() -> None:
    create_url("few", click_count=2)
    create_url("tie_old", click_count=10)
    create_url("tie_new", click_count=10)
    create_url("most", click_count=50)

    assert codes(manager.popular_urls()) == ["most", "tie_new", "tie_old", "few"]


def test_methods_combine_like_querysets() -> None:
    yesterday = datetime.now(UTC) - timedelta(days=1)
    create_url("live", click_count=5)
    create_url("hot", click_count=99, expires_at=yesterday)
    create_url("warm", click_count=20)

    assert codes(manager.popular_urls(manager.active_urls())) == ["warm", "live"]


def test_queries_can_be_refined_before_they_run() -> None:
    create_url("mine")
    create_url("theirs")

    query = manager.active_urls().where(URL.short_code == "mine")

    assert codes(query) == ["mine"]


@pytest.mark.parametrize(
    ("method", "expected_sql"),
    [
        ("active_urls", "urls.expires_at IS NULL OR urls.expires_at > now()"),
        ("expired_urls", "urls.expires_at <= now()"),
        ("popular_urls", "ORDER BY urls.click_count DESC"),
    ],
)
def test_generated_sql(method: str, expected_sql: str) -> None:
    # Run with `pytest -s` to print the SQL each method produces.
    sql = str(getattr(manager, method)().compile(dialect=postgresql.dialect()))
    print(f"\n-- {method}()\n{sql}")

    assert expected_sql in sql
