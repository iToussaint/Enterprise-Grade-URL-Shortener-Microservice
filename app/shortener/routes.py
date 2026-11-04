from typing import Any

from flask import redirect
from flask_restx import Namespace, Resource
from injector import inject
from werkzeug.wrappers import Response

from app.shortener.schemas import ShortenRequest, ShortenResponse
from app.shortener.service import UrlShortenerService

ns = Namespace("urls", path="/", description="Create short URLs and follow them")

# Swagger shows the JSON Schema that Pydantic generates, so the documented
# schema and the validation rules always come from the same model.
shorten_request_model = ns.schema_model(
    "ShortenRequest", ShortenRequest.model_json_schema()
)
shorten_response_model = ns.schema_model(
    "ShortenResponse", ShortenResponse.model_json_schema()
)


@ns.route("/urls")
class ShortUrlCollection(Resource):
    @inject
    def __init__(self, service: UrlShortenerService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = service

    @ns.expect(shorten_request_model)
    @ns.response(201, "Short URL created", shorten_response_model)
    @ns.response(422, "The URL is missing or invalid")
    def post(self) -> tuple[dict[str, str], int, dict[str, str]]:
        payload = ShortenRequest.model_validate(ns.payload)
        original_url = str(payload.url)
        short_code = self._service.shorten(original_url)
        # _external=True builds an absolute URL from the current request's host.
        short_url: str = self.api.url_for(
            ShortUrlRedirect, short_code=short_code, _external=True
        )

        body = ShortenResponse(
            short_code=short_code, short_url=short_url, original_url=original_url
        )
        return body.model_dump(), 201, {"Location": short_url}


@ns.route("/<string:short_code>")
@ns.param("short_code", "The code returned when the short URL was created")
class ShortUrlRedirect(Resource):
    @inject
    def __init__(self, service: UrlShortenerService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = service

    @ns.response(302, "Redirects to the original URL")
    @ns.response(404, "The short code does not exist")
    def get(self, short_code: str) -> Response:
        return redirect(self._service.resolve(short_code), code=302)
