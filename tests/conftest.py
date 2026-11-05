import pytest
from fakeredis import FakeRedis
from flask import Flask
from flask.testing import FlaskClient
from redis import Redis

from app import create_app


@pytest.fixture
def redis_client() -> FakeRedis:
    return FakeRedis(decode_responses=True)


@pytest.fixture
def app(redis_client: FakeRedis) -> Flask:
    app = create_app("testing")
    # Replace the real Redis binding so tests never need a running Redis server.
    app.extensions["injector"].binder.bind(Redis, to=redis_client)
    return app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()
