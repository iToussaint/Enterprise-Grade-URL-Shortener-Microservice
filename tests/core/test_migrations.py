import pytest
from flask_migrate import check, downgrade, upgrade
from sqlalchemy import inspect

from app.core.extensions import db

pytestmark = pytest.mark.usefixtures("app_context")


def table_names() -> set[str]:
    return set(inspect(db.engine).get_table_names())


def test_all_migrations_can_be_reverted_and_reapplied() -> None:
    db.session.remove()

    downgrade(revision="base")
    assert table_names() == {"alembic_version"}

    upgrade()
    assert "users" in table_names()


def test_models_and_migrations_are_in_sync() -> None:
    # Fails if a model changed without a matching migration.
    check()
