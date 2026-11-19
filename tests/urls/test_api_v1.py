from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import func, select

from app.core.extensions import db
from app.urls.models import URL, Tag
from app.users.models import User
from tests.conftest import StatementRecorder
from tests.contract import assert_matches_schema
from tests.factories import bearer, create_url, create_user

URLS = "/api/v1/urls/"
LONG_URL = "https://www.example.com/spring-sale"
PASSWORD = "correct horse battery staple"
ALICE = "alice"


@pytest.fixture(autouse=True)
def users(app: Flask) -> None:
    with app.app_context():
        create_user("alice")
        create_user("bob")


def user_id(app: Flask, username: str) -> int:
    with app.app_context():
        return db.session.scalars(
            select(User.id).where(User.username == username)
        ).one()


def create(client: FlaskClient, user: str = ALICE, **fields: Any) -> Any:
    return client.post(
        URLS, json={"url": LONG_URL, **fields}, headers=bearer(client, user)
    )


def get(client: FlaskClient, path: str, user: str = ALICE) -> Any:
    return client.get(path, headers=bearer(client, user))


def future(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


# ---- authentication ---------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", URLS), ("post", URLS), ("get", f"{URLS}abc1234/")],
)
def test_endpoints_require_authentication(
    client: FlaskClient, method: str, path: str
) -> None:
    response = getattr(client, method)(path, json={"url": LONG_URL})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")


# ---- create -----------------------------------------------------------------


def test_create_returns_201_with_details_and_location(client: FlaskClient) -> None:
    response = create(client)

    assert response.status_code == 201
    body = response.json
    code = body["short_code"]
    assert body["owner"] == "alice"
    assert body["original_url"] == LONG_URL
    assert body["short_url"] == f"http://localhost/{code}/"  # the public link
    assert body["tags"] == []
    assert body["is_active"] is True
    assert body["click_count"] == 0
    assert body["title"] is None
    assert response.headers["Location"] == f"http://localhost{URLS}{code}/"
    assert_matches_schema(client, "UrlResponse", body)


def test_create_with_alias_expiry_and_tags(app: Flask, client: FlaskClient) -> None:
    with app.app_context():
        db.session.add(Tag(name="Marketing"))
        db.session.commit()
    expires_at = future()

    response = create(
        client,
        custom_alias="spring-sale",
        expires_at=expires_at,
        tags=["marketing", "Brand New", "BRAND NEW"],
    )

    assert response.status_code == 201
    body = response.json
    assert body["custom_alias"] == "spring-sale"
    assert body["short_url"] == "http://localhost/spring-sale/"  # alias link
    assert datetime.fromisoformat(body["expires_at"]) == datetime.fromisoformat(
        expires_at
    )
    # "marketing" reuses the existing tag; duplicate names are ignored.
    assert body["tags"] == ["Brand New", "Marketing"]
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(Tag)) == 2


def test_alias_must_be_unique(client: FlaskClient) -> None:
    create(client, custom_alias="spring-sale")

    response = create(client, user="bob", custom_alias="spring-sale")

    assert response.status_code == 409
    assert response.json["error"]["details"][0]["field"] == "custom_alias"


def test_alias_cannot_equal_an_existing_short_code(client: FlaskClient) -> None:
    code = create(client).json["short_code"]

    response = create(client, custom_alias=code)

    assert response.status_code == 409


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"expires_at": "2020-01-01T00:00:00Z"}, "expires_at"),
        ({"expires_at": "2030-01-01T00:00:00"}, "expires_at"),
        ({"custom_alias": "has space"}, "custom_alias"),
        ({"custom_alias": "ab"}, "custom_alias"),
        ({"tags": [f"tag{n}" for n in range(11)]}, "tags"),
        ({"url": "not-a-url"}, "url"),
    ],
    ids=[
        "past expiry",
        "expiry without time zone",
        "alias with space",
        "alias too short",
        "too many tags",
        "invalid url",
    ],
)
def test_create_validates_fields(
    client: FlaskClient, fields: dict[str, Any], field: str
) -> None:
    response = create(client, **fields)

    assert response.status_code == 422
    assert response.json["error"]["details"][0]["field"] == field


# ---- list -------------------------------------------------------------------


def test_list_shows_only_my_urls(client: FlaskClient) -> None:
    mine = create(client).json["short_code"]
    create(client, user="bob")

    response = get(client, URLS)

    assert response.status_code == 200
    body = response.json
    assert [item["short_code"] for item in body["items"]] == [mine]
    assert (body["total"], body["page"], body["page_size"]) == (1, 1, 20)
    assert_matches_schema(client, "UrlListResponse", body)


def test_list_filters_by_status_and_sorts_by_popularity(
    app: Flask, client: FlaskClient
) -> None:
    alice_id = user_id(app, "alice")
    with app.app_context():
        yesterday = datetime.now(UTC) - timedelta(days=1)
        create_url("quiet", owner_id=alice_id, click_count=1)
        create_url("busy", owner_id=alice_id, click_count=9)
        create_url("gone", owner_id=alice_id, click_count=50, expires_at=yesterday)

    def codes(query: str) -> list[str]:
        items = get(client, f"{URLS}?{query}").json["items"]
        return [item["short_code"] for item in items]

    assert codes("status=active&sort=popular") == ["busy", "quiet"]
    assert codes("status=expired") == ["gone"]
    assert codes("sort=popular") == ["gone", "busy", "quiet"]
    assert codes("") == ["gone", "busy", "quiet"]  # newest first


def test_list_pages_through_results(app: Flask, client: FlaskClient) -> None:
    alice_id = user_id(app, "alice")
    with app.app_context():
        for number in range(5):
            create_url(f"code{number}", owner_id=alice_id)

    body = get(client, f"{URLS}?page=3&page_size=2").json

    assert [item["short_code"] for item in body["items"]] == ["code0"]
    assert body["total"] == 5


@pytest.mark.parametrize(
    "query", ["page=0", "page_size=101", "status=deleted", "sort=oldest"]
)
def test_list_rejects_invalid_parameters(client: FlaskClient, query: str) -> None:
    response = get(client, f"{URLS}?{query}")

    assert response.status_code == 422


# ---- retrieve ---------------------------------------------------------------


def test_get_returns_my_url(client: FlaskClient) -> None:
    code = create(client, tags=["Social"]).json["short_code"]

    response = get(client, f"{URLS}{code}/")

    assert response.status_code == 200
    assert response.json["short_code"] == code
    assert response.json["tags"] == ["Social"]


@pytest.mark.parametrize("owner", ["bob", None], ids=["other user", "unknown"])
def test_get_other_or_unknown_url_is_not_found(
    client: FlaskClient, owner: str | None
) -> None:
    code = "zzzzzzz"
    if owner is not None:
        code = create(client, user=owner).json["short_code"]

    response = get(client, f"{URLS}{code}/")

    # 404, not 403: the response does not reveal that someone else owns the code.
    assert response.status_code == 404


# ---- N+1 prevention ---------------------------------------------------------


def create_tagged_urls(app: Flask, count: int) -> None:
    alice_id = user_id(app, "alice")
    with app.app_context():
        tags = [Tag(name=name) for name in ("Marketing", "Social", "Event")]
        for number in range(count):
            create_url(f"code{number:03}", owner_id=alice_id, tags=tags)


@pytest.mark.parametrize("count", [1, 10])
def test_list_runs_a_fixed_number_of_queries(
    app: Flask, client: FlaskClient, sql_statements: StatementRecorder, count: int
) -> None:
    create_tagged_urls(app, count)

    headers = bearer(client, ALICE)  # outside the block: only the app's queries count
    with sql_statements() as statements:
        body = client.get(URLS, headers=headers).json

    assert body is not None

    assert len(body["items"]) == count
    assert all(
        item["tags"] == ["Event", "Marketing", "Social"] for item in body["items"]
    )
    # 1 authentication, 1 COUNT for the total, 1 for URLs joined with their owner,
    # 1 for all their tags: the same 4 queries for 1 URL or 10.
    assert len(statements) == 4
    urls_query, tags_query = statements[2], statements[3]
    assert "LEFT OUTER JOIN users" in urls_query  # joinedload = select_related
    assert "url_tags" in tags_query and " IN (" in tags_query  # selectinload


def test_without_eager_loading_queries_grow_with_the_rows(
    app: Flask, sql_statements: StatementRecorder
) -> None:
    # The N+1 problem the list endpoint avoids: one more query per URL for its tags.
    create_tagged_urls(app, 10)

    with app.app_context(), sql_statements() as statements:
        for url in db.session.scalars(select(URL)):
            assert url.owner is not None
            _ = (url.owner.username, [tag.name for tag in url.tags])

    # 1 for the URLs + 1 for their (shared) owner + 10 for the tags of each URL.
    assert len(statements) == 12


# ---- update (PUT) -----------------------------------------------------------


def put(client: FlaskClient, code: str, user: str = ALICE, **body: Any) -> Any:
    return client.put(f"{URLS}{code}/", json=body, headers=bearer(client, user))


def test_put_replaces_every_editable_field(client: FlaskClient) -> None:
    code = create(client, tags=["Social"]).json["short_code"]
    expires_at = future(days=60)

    response = put(
        client,
        code,
        url="https://www.example.com/summer-sale",
        custom_alias="summer-sale",
        expires_at=expires_at,
        tags=["Marketing", "Launch"],
        is_active=False,
    )

    assert response.status_code == 200
    body = response.json
    assert body["short_code"] == code  # never changes
    assert body["original_url"] == "https://www.example.com/summer-sale"
    assert body["custom_alias"] == "summer-sale"
    assert datetime.fromisoformat(body["expires_at"]) == datetime.fromisoformat(
        expires_at
    )
    assert body["tags"] == ["Launch", "Marketing"]
    assert body["is_active"] is False
    assert_matches_schema(client, "UrlResponse", body)


def test_put_resets_optional_fields_that_are_left_out(client: FlaskClient) -> None:
    code = create(
        client, custom_alias="spring-sale", expires_at=future(), tags=["Social"]
    ).json["short_code"]
    client.delete(f"{URLS}{code}/", headers=bearer(client, ALICE))

    body = put(client, code, url=LONG_URL).json

    assert body["custom_alias"] is None
    assert body["expires_at"] is None
    assert body["tags"] == []
    assert body["is_active"] is True  # also how a deactivated URL is reactivated


def test_put_can_keep_its_own_alias(client: FlaskClient) -> None:
    code = create(client, custom_alias="spring-sale").json["short_code"]

    response = put(client, code, url=LONG_URL, custom_alias="spring-sale")

    assert response.status_code == 200


def test_put_cannot_take_another_urls_alias_or_code(client: FlaskClient) -> None:
    other = create(client, user="bob", custom_alias="bobs-link").json
    code = create(client).json["short_code"]

    for alias in ("bobs-link", other["short_code"]):
        response = put(client, code, url=LONG_URL, custom_alias=alias)
        assert response.status_code == 409


def test_put_validates_like_create(client: FlaskClient) -> None:
    code = create(client).json["short_code"]

    response = put(client, code, url=LONG_URL, expires_at="2020-01-01T00:00:00Z")

    assert response.status_code == 422


def test_put_keeps_click_history(app: Flask, client: FlaskClient) -> None:
    alice_id = user_id(app, "alice")
    with app.app_context():
        create_url("counted", owner_id=alice_id, click_count=7)

    body = put(client, "counted", url="https://www.example.com/new-target").json

    assert body["click_count"] == 7


# ---- deactivate (DELETE) ----------------------------------------------------


def test_delete_deactivates_but_keeps_the_url(client: FlaskClient) -> None:
    code = create(client).json["short_code"]

    response = client.delete(f"{URLS}{code}/", headers=bearer(client, ALICE))

    assert response.status_code == 204
    assert response.get_data() == b""
    details = get(client, f"{URLS}{code}/").json
    assert details["is_active"] is False
    listed = get(client, URLS).json["items"]
    assert [item["short_code"] for item in listed] == [code]
    assert get(client, f"{URLS}?status=active").json["items"] == []


def test_delete_twice_is_harmless(client: FlaskClient) -> None:
    code = create(client).json["short_code"]
    client.delete(f"{URLS}{code}/", headers=bearer(client, ALICE))

    assert (
        client.delete(f"{URLS}{code}/", headers=bearer(client, ALICE)).status_code
        == 204
    )


# ---- ownership and authentication for PUT / DELETE --------------------------


@pytest.mark.parametrize("method", ["put", "delete"])
def test_cannot_change_another_users_url(client: FlaskClient, method: str) -> None:
    code = create(client, user="bob").json["short_code"]

    response = getattr(client, method)(
        f"{URLS}{code}/", json={"url": LONG_URL}, headers=bearer(client, ALICE)
    )

    assert response.status_code == 404
    bobs = client.get(f"{URLS}{code}/", headers=bearer(client, "bob")).json
    assert bobs is not None and bobs["is_active"] is True


@pytest.mark.parametrize("method", ["put", "delete"])
def test_put_and_delete_require_authentication(
    client: FlaskClient, method: str
) -> None:
    response = getattr(client, method)(f"{URLS}abc1234/", json={"url": LONG_URL})

    assert response.status_code == 401
