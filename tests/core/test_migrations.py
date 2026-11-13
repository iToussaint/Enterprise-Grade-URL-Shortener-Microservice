import pytest
from flask_migrate import check, downgrade, upgrade
from sqlalchemy import inspect, select

from app.core.extensions import db
from app.urls.models import Tag

pytestmark = pytest.mark.usefixtures("app_context")

# The revision just before the tag seed (create urls, tags and clicks tables).
BEFORE_SEED = "43ca2d65d774"
DEFAULT_TAGS = {"Marketing", "Social", "Newsletter", "Product", "Event"}


def table_names() -> set[str]:
    return set(inspect(db.engine).get_table_names())


def tag_names() -> set[str]:
    return set(db.session.scalars(select(Tag.name)))


def migrate_to(revision: str) -> None:
    # Close the session first, so migrations never wait on its open transaction.
    db.session.remove()
    if revision == "head":
        upgrade()
    else:
        downgrade(revision=revision)


def test_all_migrations_can_be_reverted_and_reapplied() -> None:
    migrate_to("base")
    assert table_names() == {"alembic_version"}

    migrate_to("head")
    assert table_names() == {
        "alembic_version",
        "users",
        "urls",
        "tags",
        "url_tags",
        "clicks",
    }


def test_models_and_migrations_are_in_sync() -> None:
    # Fails if a model changed without a matching migration.
    check()


def test_data_migration_seeds_the_default_tags() -> None:
    migrate_to(BEFORE_SEED)
    assert tag_names() == set()

    migrate_to("head")
    assert tag_names() == DEFAULT_TAGS


def test_seeding_keeps_tags_that_already_exist() -> None:
    migrate_to(BEFORE_SEED)
    db.session.add(Tag(name="Social"))
    db.session.commit()

    migrate_to("head")

    assert tag_names() == DEFAULT_TAGS
    assert len(db.session.scalars(select(Tag)).all()) == len(DEFAULT_TAGS)


def test_reverting_the_seed_removes_only_the_default_tags() -> None:
    migrate_to("head")
    db.session.add(Tag(name="Custom"))
    db.session.commit()

    migrate_to(BEFORE_SEED)
    assert tag_names() == {"Custom"}

    migrate_to("head")
