from fakeredis import FakeRedis
from flask import Blueprint, Flask
from flask_injector import FlaskInjector
from flask_restx import Api, Resource
from injector import Binder, Injector, inject
from redis import Redis

from app.dependencies import RedisModule
from app.shortener.service import UrlShortenerService


def test_injector_builds_service_with_redis(
    app: Flask, redis_client: FakeRedis
) -> None:
    service = app.extensions["injector"].get(UrlShortenerService)

    assert isinstance(service, UrlShortenerService)
    short_code = service.shorten("https://example.com")
    assert redis_client.get(f"url:{short_code}") == "https://example.com"


def test_redis_client_is_a_singleton_built_from_config() -> None:
    app = Flask(__name__)
    app.config.update(REDIS_HOST="redis", REDIS_PORT=6380, REDIS_PASSWORD="secret")
    injector = Injector([RedisModule()])
    FlaskInjector(app=app, injector=injector)

    first = injector.get(Redis)
    second = injector.get(Redis)

    assert first is second
    connection_kwargs = first.connection_pool.connection_kwargs
    assert connection_kwargs["host"] == "redis"
    assert connection_kwargs["port"] == 6380
    assert connection_kwargs["password"] == "secret"


def test_flask_restx_resource_receives_injected_service() -> None:
    # Confirms Flask-Injector can inject into Flask-RESTX Resources,
    # which the endpoints in the next stage depend on.
    app = Flask(__name__)
    blueprint = Blueprint("probe", __name__)
    api = Api(blueprint)

    @api.route("/probe")
    class Probe(Resource):
        @inject
        def __init__(self, service: UrlShortenerService, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.service = service

        def get(self) -> dict[str, str]:
            return {"service": type(self.service).__name__}

    app.register_blueprint(blueprint)

    def use_fake_redis(binder: Binder) -> None:
        binder.bind(Redis, to=FakeRedis(decode_responses=True))

    FlaskInjector(app=app, modules=[use_fake_redis])

    response = app.test_client().get("/probe")

    assert response.status_code == 200
    assert response.json == {"service": "UrlShortenerService"}
