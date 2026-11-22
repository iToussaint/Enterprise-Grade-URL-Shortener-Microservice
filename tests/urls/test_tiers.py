from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from app.core.extensions import db
from app.users.models import FREE_MAX_ACTIVE_URLS, Tier, User
from tests.factories import bearer, create_url, create_user

URLS = "/api/v1/urls/"
LONG_URL = "https://www.example.com/landing"


@pytest.fixture(autouse=True)
def users(app: Flask) -> None:
    with app.app_context():
        create_user("free")
        create_user("premium", tier=Tier.PREMIUM, is_premium=True)
        create_user("admin", tier=Tier.ADMIN, is_premium=True)


def owner(app: Flask, username: str) -> User:
    with app.app_context():
        return db.session.scalars(select(User).where(User.username == username)).one()


def give_urls(app: Flask, username: str, count: int, **fields: Any) -> None:
    user_id = owner(app, username).id
    with app.app_context():
        for number in range(count):
            create_url(f"{username[:3]}{number:04}", owner_id=user_id, **fields)


def create(client: FlaskClient, user: str = "free", **fields: Any) -> Any:
    return client.post(
        URLS, json={"url": LONG_URL, **fields}, headers=bearer(client, user)
    )


def put(client: FlaskClient, code: str, user: str = "free", **body: Any) -> Any:
    return client.put(f"{URLS}{code}/", json=body, headers=bearer(client, user))


def assert_forbidden(response: Any, message_part: str) -> None:
    assert response.status_code == 403
    assert response.json["error"]["code"] == "forbidden"
    assert message_part in response.json["error"]["message"]


# ---- active URL limit -------------------------------------------------------


def test_free_accounts_can_have_ten_active_urls(
    app: Flask, client: FlaskClient
) -> None:
    give_urls(app, "free", FREE_MAX_ACTIVE_URLS - 1)

    assert create(client).status_code == 201  # the 10th
    assert_forbidden(create(client), "at most 10 active URLs")  # the 11th


def test_deactivated_and_expired_urls_do_not_count(
    app: Flask, client: FlaskClient
) -> None:
    yesterday = datetime.now(UTC) - timedelta(days=1)
    give_urls(app, "free", 8)
    with app.app_context():
        user_id = owner(app, "free").id
        create_url("off0001", owner_id=user_id, is_active=False)
        create_url("old0001", owner_id=user_id, expires_at=yesterday)

    assert create(client).status_code == 201  # 9 active
    assert create(client).status_code == 201  # 10 active
    assert create(client).status_code == 403


def test_deactivating_frees_a_slot(app: Flask, client: FlaskClient) -> None:
    give_urls(app, "free", FREE_MAX_ACTIVE_URLS)
    assert create(client).status_code == 403

    client.delete(f"{URLS}fre0000/", headers=bearer(client, "free"))

    assert create(client).status_code == 201


def test_premium_accounts_are_unlimited(app: Flask, client: FlaskClient) -> None:
    give_urls(app, "premium", FREE_MAX_ACTIVE_URLS + 5)

    assert create(client, user="premium").status_code == 201


def test_reactivating_counts_against_the_limit(app: Flask, client: FlaskClient) -> None:
    give_urls(app, "free", FREE_MAX_ACTIVE_URLS)
    with app.app_context():
        create_url("off0001", owner_id=owner(app, "free").id, is_active=False)

    assert_forbidden(
        put(client, "off0001", url=LONG_URL, is_active=True), "at most 10 active URLs"
    )


def test_removing_an_expiry_counts_as_reactivating(
    app: Flask, client: FlaskClient
) -> None:
    yesterday = datetime.now(UTC) - timedelta(days=1)
    give_urls(app, "free", FREE_MAX_ACTIVE_URLS)
    with app.app_context():
        create_url("old0001", owner_id=owner(app, "free").id, expires_at=yesterday)

    # PUT without expires_at clears it, which would make the URL live again.
    assert put(client, "old0001", url=LONG_URL).status_code == 403


def test_editing_an_active_url_at_the_limit_is_allowed(
    app: Flask, client: FlaskClient
) -> None:
    give_urls(app, "free", FREE_MAX_ACTIVE_URLS)

    assert put(client, "fre0000", url="https://example.org/new").status_code == 200


def test_simultaneous_creates_cannot_exceed_the_limit(app: Flask) -> None:
    give_urls(app, "free", FREE_MAX_ACTIVE_URLS - 2)
    headers = bearer(app.test_client(), "free")

    def attempt(_: int) -> int:
        response = app.test_client().post(URLS, json={"url": LONG_URL}, headers=headers)
        return int(response.status_code)

    with ThreadPoolExecutor(max_workers=5) as pool:
        statuses = sorted(pool.map(attempt, range(5)))

    # The row lock makes the requests count one after another: only 2 fit.
    assert statuses == [201, 201, 403, 403, 403]


# ---- custom aliases ---------------------------------------------------------


def test_free_accounts_cannot_set_an_alias(client: FlaskClient) -> None:
    assert_forbidden(create(client, custom_alias="my-link"), "Premium account")


def test_premium_accounts_can_set_an_alias(client: FlaskClient) -> None:
    response = create(client, user="premium", custom_alias="my-link")

    assert response.status_code == 201
    assert response.json["custom_alias"] == "my-link"


def test_free_accounts_cannot_add_an_alias_with_put(
    app: Flask, client: FlaskClient
) -> None:
    give_urls(app, "free", 1)

    assert_forbidden(
        put(client, "fre0000", url=LONG_URL, custom_alias="my-link"), "Premium"
    )


def test_downgraded_accounts_keep_existing_aliases(
    app: Flask, client: FlaskClient
) -> None:
    # The alias was set while Premium; the account is Free now.
    give_urls(app, "free", 1, custom_alias="kept-alias")

    response = put(
        client, "fre0000", url="https://example.org/new", custom_alias="kept-alias"
    )

    assert response.status_code == 200
    assert response.json["custom_alias"] == "kept-alias"


# ---- admins -----------------------------------------------------------------


def test_admins_moderating_a_free_users_url_are_not_limited(
    app: Flask, client: FlaskClient
) -> None:
    give_urls(app, "free", FREE_MAX_ACTIVE_URLS)
    with app.app_context():
        create_url("off0001", owner_id=owner(app, "free").id, is_active=False)

    response = put(
        client,
        "off0001",
        user="admin",
        url=LONG_URL,
        custom_alias="moderated",
        is_active=True,
    )

    assert response.status_code == 200
