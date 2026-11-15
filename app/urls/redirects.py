"""The public short link: GET /<code>/ redirects to the original URL.

It lives outside the /api blueprint (and outside Swagger) because it is the
link people share, not an API call.
"""

from flask import Blueprint, redirect, request
from injector import inject
from werkzeug.wrappers import Response

from app.analytics.service import ClickService, Visit
from app.urls.service import UrlShortenerService

redirects_bp = Blueprint("redirects", __name__)


def follow_short_link(
    code: str, service: UrlShortenerService, clicks: ClickService
) -> Response:
    """Resolve a code or alias, record the click and redirect (shared by both routes).

    404 if unknown, 410 if deactivated or expired; neither is counted as a click.
    """
    url = service.resolve(code)
    original_url = url.original_url
    clicks.record(url.id, Visit.from_request(request))
    # 302, not 301: browsers cache a 301 and would stop coming back, so later
    # clicks could not be counted.
    return redirect(original_url, code=302)


@redirects_bp.route("/<string:code>/", strict_slashes=False)
@inject
def follow(code: str, service: UrlShortenerService, clicks: ClickService) -> Response:
    return follow_short_link(code, service, clicks)
