from collections.abc import Callable, Iterator

import pytest
from fakeredis import FakeRedis
from flask import Flask
from flask.testing import FlaskClient
from flask_migrate import upgrade
from redis import Redis
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

from app import create_app
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

    def factory(config_name: str | None = "testing") -> Flask:
        app = create_app(config_name, {"SQLALCHEMY_DATABASE_URI": database_url})
        created.append(app)
        return app

    yield factory

    for app in created:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


@pytest.fixture
def redis_client() -> FakeRedis:
    return FakeRedis(decode_responses=True)


@pytest.fixture
def app(make_app: AppFactory, redis_client: FakeRedis) -> Iterator[Flask]:
    app = make_app()
    # Replace the real Redis binding so tests never need a running Redis server.
    app.extensions["injector"].binder.bind(Redis, to=redis_client)
    yield app
    # Every test starts from empty tables.
    with app.app_context():
        empty_all_tables()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()
