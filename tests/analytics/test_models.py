import pytest
from sqlalchemy import select
from sqlalchemy.exc import DataError

from app.analytics.models import Click
from app.core.extensions import db
from tests.factories import create_url

pytestmark = pytest.mark.usefixtures("app_context")


def save_click(**fields: object) -> Click:
    click = Click(**{"url": create_url(), "ip_address": "203.0.113.7", **fields})
    db.session.add(click)
    db.session.commit()
    return click


def test_click_records_visit_details() -> None:
    click = save_click(
        city="Kigali",
        country="RW",
        user_agent="Mozilla/5.0",
        referrer="https://news.example.org/",
    )
    db.session.refresh(click)

    assert click.url.short_code == "abc1234"
    assert click.ip_address == "203.0.113.7"
    assert (click.city, click.country) == ("Kigali", "RW")
    # auto_now_add: set by PostgreSQL when the row is inserted.
    assert click.clicked_at.tzinfo is not None


def test_optional_fields_default_to_empty() -> None:
    click = save_click()

    assert click.city is None
    assert click.country is None
    assert click.referrer is None
    assert click.user_agent == ""


def test_ip_address_accepts_ipv6() -> None:
    assert save_click(ip_address="2001:db8::1").ip_address == "2001:db8::1"


def test_ip_address_rejects_invalid_values() -> None:
    # PostgreSQL's INET type validates the address.
    with pytest.raises(DataError):
        save_click(ip_address="not-an-ip")


def test_deleting_a_url_deletes_its_clicks() -> None:
    click = save_click()

    db.session.delete(click.url)
    db.session.commit()

    assert db.session.scalars(select(Click)).all() == []
