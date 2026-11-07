from typing import Any

from flask import redirect
from flask_restx import Namespace, Resource
from injector import inject
from pydantic import BaseModel
from werkzeug.wrappers import Response

from app.errors import ErrorResponse
from app.shortener.schemas import ShortenRequest, ShortenResponse
from app.shortener.service import UrlShortenerService

ns = Namespace("urls", path="/", description="Create short URLs and follow them")


def inline_references(node: Any, definitions: dict[str, Any]) -> Any:
    """Replace every {"$ref": "#/$defs/Name"} with the definition it points to."""
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            return inline_references(definitions[name], definitions)
        return {
            key: inline_references(value, definitions) for key, value in node.items()
        }
    if isinstance(node, list):
        return [inline_references(item, definitions) for item in node]
    return node


def register_schema(model: type[BaseModel]) -> Any:
    """Register a Pydantic model's JSON Schema as a Swagger definition.

    Swagger shows the schema Pydantic generates, so the documented schema and the
    validation rules come from the same model. Nested models are inlined because
    Flask-RESTX only publishes models that are referenced directly; it does not
    follow "$ref"s inside a raw JSON Schema.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    return ns.schema_model(model.__name__, inline_references(schema, definitions))


shorten_request_model = register_schema(ShortenRequest)
shorten_response_model = register_schema(ShortenResponse)
error_model = register_schema(ErrorResponse)


@ns.route("/urls")
class ShortUrlCollection(Resource):
    @inject
    def __init__(self, service: UrlShortenerService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = service

    @ns.expect(shorten_request_model)
    @ns.response(
        201,
        "Short URL created.",
        shorten_response_model,
        headers={"Location": "The full short URL (same as short_url)."},
    )
    @ns.response(400, "The request body is not valid JSON.", error_model)
    @ns.response(415, "The Content-Type is not application/json.", error_model)
    @ns.response(422, "The URL is missing or invalid.", error_model)
    @ns.response(503, "The storage service is temporarily unavailable.", error_model)
    def post(self) -> tuple[dict[str, str], int, dict[str, str]]:
        """Create a short URL.

        Validates the URL (absolute http/https, at most 2083 characters), stores it
        under a new random 7-character code and returns the full short URL.
        Every request creates a new code, even for a URL shortened before.
        """
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

    @ns.response(
        302,
        "Found. Redirects to the original URL.",
        headers={"Location": "The original URL."},
    )
    @ns.response(404, "The short code does not exist.", error_model)
    @ns.response(503, "The storage service is temporarily unavailable.", error_model)
    def get(self, short_code: str) -> Response:
        """Redirect to the original URL.

        Open the short URL in a browser to follow the redirect. Swagger UI's
        "Try it out" usually shows "Failed to fetch" for an existing code: the
        browser follows the redirect to another site and then blocks reading
        its response (CORS). Unknown codes return a 404 error body.
        """
        return redirect(self._service.resolve(short_code), code=302)
