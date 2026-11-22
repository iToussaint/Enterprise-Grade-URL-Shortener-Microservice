from typing import Any

from flask import request
from flask_restx import Namespace, Resource
from injector import inject

from app.analytics.schemas import AnalyticsParams, AnalyticsResponse
from app.analytics.service import AnalyticsService
from app.auth.security import current_user, login_required
from app.core.errors import ErrorResponse, ForbiddenError
from app.core.swagger import register_schema
from app.urls.service import UrlShortenerService
from app.users.models import PREMIUM_TIERS

ns = Namespace(
    "analytics",
    path="/v1/analytics",
    description="Click analytics for your URLs (Premium accounts)",
)

analytics_model = register_schema(ns, AnalyticsResponse)
error_model = register_schema(ns, ErrorResponse)

PARAMS = {
    "days": {
        "in": "query",
        "type": "integer",
        "default": 30,
        "minimum": 1,
        "maximum": 365,
        "description": "Length of the period, ending now.",
    },
    "interval": {
        "in": "query",
        "type": "string",
        "enum": ["day", "week", "month"],
        "default": "day",
        "description": "Size of each time-series bucket (UTC).",
    },
}


@ns.route("/<string:short_code>/")
@ns.param("short_code", "The URL's short code")
@ns.doc(security="bearerAuth")
class UrlAnalytics(Resource):
    method_decorators = [login_required]

    @inject
    def __init__(
        self, urls: UrlShortenerService, analytics: AnalyticsService, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self._urls = urls
        self._analytics = analytics

    @ns.doc(params=PARAMS)
    @ns.response(200, "Click statistics for the period.", analytics_model)
    @ns.response(401, "Missing or invalid credentials.", error_model)
    @ns.response(403, "Analytics require a Premium account.", error_model)
    @ns.response(404, "You have no URL with this code.", error_model)
    @ns.response(422, "A query parameter is invalid.", error_model)
    @ns.response(503, "The storage service is temporarily unavailable.", error_model)
    def get(self, short_code: str) -> dict[str, Any]:
        """Click analytics for one of your URLs.

        Clicks over time (zero-filled), per country and per referrer, plus
        unique visitors, all computed in the database. Premium and Admin only.
        """
        user = current_user()
        if user.tier not in PREMIUM_TIERS:
            raise ForbiddenError("Analytics require a Premium account.")
        params = AnalyticsParams.model_validate(request.args.to_dict())
        url = self._urls.get_for(user, short_code, with_details=False)
        report = self._analytics.report(url, params.days, params.interval)
        return AnalyticsResponse.model_validate(report).model_dump(mode="json")
