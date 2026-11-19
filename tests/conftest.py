from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_migrate import upgrade
from sqlalchemy import event, text
from testcontainers.community.postgres import PostgresContainer

from app import create_app
from app.core.config import TestingConfig
from app.core.extensions import db

POSTGRES_IMAGE = "postgres:18-alpine"

AppFactory = Callable[..., Flask]


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Start one throwaway PostgreSQL for the test run and apply all migrations."""
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg2") as postgres:
        url = postgres.get_connection_url()
        app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": url})
        with app.app_context():
            upgrade()
            db.engine.dispose()
        yield url


def empty_all_tables() -> None:
    tables = ", ".join(f'"{table.name}"' for table in db.metadata.sorted_tables)
    if tables:
        db.session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        db.session.commit()


@pytest.fixture
def make_app(database_url: str) -> Iterator[AppFactory]:
    """Build apps connected to the test database; close their connections after."""
    created: list[Flask] = []

    def factory(config_name: str | None = "testing", **settings: Any) -> Flask:
        defaults = {
            "SQLALCHEMY_DATABASE_URI": database_url,
            # Every profile needs a signing key; only TestingConfig defines one.
            "JWT_SECRET_KEY": TestingConfig.JWT_SECRET_KEY,
        }
        app = create_app(config_name, {**defaults, **settings})
        created.append(app)
        return app

    yield factory

    for app in created:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


@pytest.fixture
def app(make_app: AppFactory) -> Iterator[Flask]:
    app = make_app()
    yield app
    # Every test starts from empty tables.
    with app.app_context():
        empty_all_tables()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def app_context(app: Flask) -> Iterator[None]:
    """Run the test inside an application context, so `db.session` is usable."""
    with app.app_context():
        yield


StatementRecorder = Callable[[], AbstractContextManager[list[str]]]


@pytest.fixture
def sql_statements(app: Flask) -> StatementRecorder:
    """Record every SQL statement the app sends while the `with` block runs.

    with sql_statements() as statements:
        client.get(...)
    assert len(statements) == 3
    """
    with app.app_context():
        engine = db.engine

    @contextmanager
    def record() -> Iterator[list[str]]:
        statements: list[str] = []

        def on_execute(*args: Any) -> None:
            statements.append(args[2])  # (conn, cursor, statement, ...)

        event.listen(engine, "before_cursor_execute", on_execute)
        try:
            yield statements
        finally:
            event.remove(engine, "before_cursor_execute", on_execute)

    return record
