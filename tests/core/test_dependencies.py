from flask import Blueprint, Flask
from flask_injector import FlaskInjector
from flask_restx import Api, Resource
from injector import inject

from app.urls.service import UrlShortenerService


def test_injector_builds_the_service(app: Flask) -> None:
    service = app.extensions["injector"].get(UrlShortenerService)

    assert isinstance(service, UrlShortenerService)


def test_flask_restx_resource_receives_injected_service() -> None:
    # Confirms Flask-Injector can inject into Flask-RESTX Resources,
    # which the endpoints depend on.
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
    FlaskInjector(app=app)

    response = app.test_client().get("/probe")

    assert response.status_code == 200
    assert response.json == {"service": "UrlShortenerService"}
