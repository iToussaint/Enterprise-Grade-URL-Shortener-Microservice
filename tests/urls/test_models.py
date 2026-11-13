import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.urls.models import URL, Tag
from tests.factories import create_url, create_user

pytestmark = pytest.mark.usefixtures("app_context")


def test_new_url_gets_spec_defaults() -> None:
    url = create_url()
    db.session.refresh(url)

    assert url.is_active is True
    assert url.click_count == 0
    assert url.owner is None
    assert url.custom_alias is None
    assert url.expires_at is None
    assert url.tags == []
    assert url.created_at.tzinfo is not None


def test_url_belongs_to_its_owner() -> None:
    owner = create_user()
    url = create_url(owner=owner)

    assert url.owner_id == owner.id
    assert url.owner is owner


def test_urls_and_tags_link_in_both_directions() -> None:
    marketing, social = Tag(name="Marketing"), Tag(name="Social")
    url = create_url(tags=[marketing, social])

    assert {tag.name for tag in url.tags} == {"Marketing", "Social"}
    assert marketing.urls == [url]


def test_deleting_a_user_deletes_their_urls() -> None:
    owner = create_user()
    create_url(owner=owner)

    db.session.delete(owner)
    db.session.commit()

    assert db.session.scalars(select(URL)).all() == []


def test_deleting_a_url_unlinks_its_tags_but_keeps_them() -> None:
    url = create_url(tags=[Tag(name="Marketing")])

    db.session.delete(url)
    db.session.commit()

    tag = db.session.scalars(select(Tag)).one()
    assert tag.name == "Marketing"
    assert tag.urls == []


@pytest.mark.parametrize(
    "duplicate",
    [{"short_code": "abc1234"}, {"short_code": "xyz9876", "custom_alias": "promo"}],
    ids=["same short_code", "same custom_alias"],
)
def test_short_code_and_custom_alias_must_be_unique(duplicate: dict[str, str]) -> None:
    create_url(custom_alias="promo")

    with pytest.raises(IntegrityError):
        create_url(**duplicate)


def test_many_urls_can_have_no_custom_alias() -> None:
    create_url("abc1234")
    create_url("xyz9876")

    assert len(db.session.scalars(select(URL)).all()) == 2


def test_tag_names_must_be_unique() -> None:
    db.session.add_all([Tag(name="Social"), Tag(name="Social")])

    with pytest.raises(IntegrityError):
        db.session.commit()


def test_click_count_cannot_be_negative() -> None:
    with pytest.raises(IntegrityError, match="ck_urls_click_count_positive"):
        create_url(click_count=-1)


def test_spec_indexes_exist() -> None:
    indexes = {index["name"]: index for index in inspect(db.engine).get_indexes("urls")}

    assert indexes["ix_urls_short_code"]["unique"] is True
    assert indexes["ix_urls_short_code"]["column_names"] == ["short_code"]
    assert indexes["ix_urls_created_at"]["column_names"] == ["created_at"]
