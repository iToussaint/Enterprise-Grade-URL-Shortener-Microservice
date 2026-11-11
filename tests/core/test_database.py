import pytest
from flask import Flask
from sqlalchemy import text

from app import create_app
from app.core.extensions import db


def test_app_connects_to_postgresql(app: Flask) -> None:
    with app.app_context():
        version = db.session.execute(text("SELECT version()")).scalar_one()

    assert version.startswith("PostgreSQL 18")


def test_migrations_have_been_applied(app: Flask) -> None:
    with app.app_context():
        version_table = db.session.execute(
            text("SELECT to_regclass('alembic_version')")
        ).scalar_one()

    assert version_table == "alembic_version"


def test_missing_database_url_stops_the_app() -> None:
    with pytest.raises(RuntimeError, match="SQLALCHEMY_DATABASE_URI"):
        create_app("testing", {"SQLALCHEMY_DATABASE_URI": None})
