"""/api/v1/urls: each authenticated user manages their own short URLs."""

from typing import Any

from flask import Response, request, url_for
from flask_restx import Namespace, Resource
from injector import inject

from app.auth.permissions import IsOwnerOrReadOnly
from app.auth.security import current_user, login_required
from app.core.errors import ErrorResponse
from app.core.swagger import register_schema
from app.urls.models import URL
from app.urls.schemas import (
    CreateUrlRequest,
    ListUrlsParams,
    UpdateUrlRequest,
    UrlListResponse,
    UrlResponse,
)
from app.urls.service import UrlShortenerService

ns = Namespace(
    "my-urls",
    path="/v1/urls",
    description="Manage your own short URLs (JWT access token)",
)

create_request_model = register_schema(ns, CreateUrlRequest)
update_request_model = register_schema(ns, UpdateUrlRequest)
url_response_model = register_schema(ns, UrlResponse)
url_list_model = register_schema(ns, UrlListResponse)
error_model = register_schema(ns, ErrorResponse)

LIST_PARAMS = {
    "status": {
        "in": "query",
        "type": "string",
        "enum": ["all", "active", "expired"],
        "default": "all",
        "description": "active: active and not expired; expired: past expires_at.",
    },
    "sort": {
        "in": "query",
        "type": "string",
        "enum": ["newest", "popular"],
        "default": "newest",
        "description": "popular: most clicked first.",
    },
    "page": {"in": "query", "type": "integer", "default": 1, "minimum": 1},
    "page_size": {
        "in": "query",
        "type": "integer",
        "default": 20,
        "minimum": 1,
        "maximum": 100,
    },
}


class OwnUrlResource(Resource):
    """Base for the endpoints below: login required, service injected."""

    method_decorators = [login_required]

    @inject
    def __init__(self, service: UrlShortenerService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = service

    def to_response(self, url: URL) -> dict[str, Any]:
        # The public link people share: the alias if there is one.
        short_url = url_for(
            "redirects.follow", code=url.custom_alias or url.short_code, _external=True
        )
        return UrlResponse.from_url(url, short_url).model_dump(mode="json")


@ns.route("/")
@ns.doc(security="bearerAuth")
@ns.response(401, "Missing or invalid credentials.", error_model)
@ns.response(503, "The storage service is temporarily unavailable.", error_model)
class OwnUrlCollection(OwnUrlResource):
    @ns.doc(params=LIST_PARAMS)
    @ns.response(200, "One page of your URLs.", url_list_model)
    @ns.response(422, "A query parameter is invalid.", error_model)
    def get(self) -> dict[str, Any]:
        """List your short URLs.

        Filter with `status`, order with `sort`, and page through the results.
        Each URL's owner and tags are loaded with a fixed number of queries,
        however many URLs the page holds.
        """
        params = ListUrlsParams.model_validate(request.args.to_dict())
        urls, total = self._service.list_for(
            current_user(), params.status, params.sort, params.page, params.page_size
        )
        return {
            "items": [self.to_response(url) for url in urls],
            "page": params.page,
            "page_size": params.page_size,
            "total": total,
        }

    @ns.expect(create_request_model)
    @ns.response(
        201,
        "Short URL created.",
        url_response_model,
        headers={"Location": "The URL of the new resource's details."},
    )
    @ns.response(400, "The request body is not valid JSON.", error_model)
    @ns.response(409, "The custom alias is already taken.", error_model)
    @ns.response(415, "The Content-Type is not application/json.", error_model)
    @ns.response(422, "A field is missing or invalid.", error_model)
    def post(self) -> tuple[dict[str, Any], int, dict[str, str]]:
        """Create a short URL that you own.

        Optionally set a custom alias, an expiry date and tags.
        """
        payload = CreateUrlRequest.model_validate(ns.payload)
        url = self._service.create_for(
            current_user(),
            str(payload.url),
            custom_alias=payload.custom_alias,
            expires_at=payload.expires_at,
            tag_names=payload.tags,
        )
        location: str = self.api.url_for(
            OwnUrlItem, short_code=url.short_code, _external=True
        )
        return self.to_response(url), 201, {"Location": location}


@ns.route("/<string:short_code>/")
@ns.param("short_code", "The URL's short code")
@ns.doc(security="bearerAuth")
@ns.response(401, "Missing or invalid credentials.", error_model)
@ns.response(404, "No URL has this code.", error_model)
@ns.response(503, "The storage service is temporarily unavailable.", error_model)
class OwnUrlItem(OwnUrlResource):
    permission = IsOwnerOrReadOnly()

    def url_for_request(self, short_code: str) -> URL:
        """Load the URL (404 if unknown), then check IsOwnerOrReadOnly (403)."""
        url = self._service.get(short_code)
        self.permission.check(request.method, current_user(), url)
        return url

    @ns.response(200, "The URL's details.", url_response_model)
    def get(self, short_code: str) -> dict[str, Any]:
        """Retrieve a short URL's details.

        Any logged-in user may read any URL; only its owner or an Admin may
        change it (IsOwnerOrReadOnly).
        """
        return self.to_response(self.url_for_request(short_code))

    @ns.expect(update_request_model)
    @ns.response(200, "The updated URL.", url_response_model)
    @ns.response(400, "The request body is not valid JSON.", error_model)
    @ns.response(403, "Only the owner or an Admin may change this URL.", error_model)
    @ns.response(409, "The custom alias is already taken.", error_model)
    @ns.response(415, "The Content-Type is not application/json.", error_model)
    @ns.response(422, "A field is missing or invalid.", error_model)
    def put(self, short_code: str) -> dict[str, Any]:
        """Replace one of your short URLs (Admins: any URL).

        Send every field you want to keep: optional fields left out are reset
        (no alias, no expiry, no tags, active). The short code never changes.
        Set `is_active` to true to reactivate a deactivated URL.
        """
        url = self.url_for_request(short_code)
        payload = UpdateUrlRequest.model_validate(ns.payload)
        url = self._service.update(
            url,
            str(payload.url),
            custom_alias=payload.custom_alias,
            expires_at=payload.expires_at,
            tag_names=payload.tags,
            is_active=payload.is_active,
        )
        return self.to_response(url)

    @ns.response(204, "Deactivated. The URL and its clicks are kept.")
    @ns.response(403, "Only the owner or an Admin may change this URL.", error_model)
    def delete(self, short_code: str) -> Response:
        """Deactivate one of your short URLs (Admins: any URL).

        The link stops redirecting, but the URL and its click history are kept;
        it still appears in your list and can be reactivated with PUT.
        Deleting an already deactivated URL also returns 204.
        """
        self._service.deactivate(self.url_for_request(short_code))
        return Response(status=204)
