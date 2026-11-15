from dataclasses import dataclass

from flask import Request
from injector import inject
from sqlalchemy import update

from app.analytics.geoip import GeoIPLocator
from app.analytics.models import Click
from app.core.extensions import db
from app.urls.models import URL, URL_MAX_LENGTH

USER_AGENT_MAX_LENGTH = 1000


@dataclass(frozen=True)
class Visit:
    """What we record about one visit to a short URL."""

    ip_address: str
    user_agent: str
    referrer: str | None

    @classmethod
    def from_request(cls, request: Request) -> "Visit":
        return cls(
            # With TRUSTED_PROXY_COUNT set, ProxyFix has already put the real
            # client IP from X-Forwarded-For here.
            ip_address=request.remote_addr or "0.0.0.0",
            # Capped, so a client cannot store megabytes per click.
            user_agent=request.user_agent.string[:USER_AGENT_MAX_LENGTH],
            referrer=request.referrer[:URL_MAX_LENGTH] if request.referrer else None,
        )


class ClickService:
    @inject
    def __init__(self, locator: GeoIPLocator) -> None:
        self._locator = locator

    def record(self, url_id: int, visit: Visit) -> None:
        """Save the click and add one to the URL's counter, in one transaction."""
        location = self._locator.locate(visit.ip_address)
        db.session.add(
            Click(
                url_id=url_id,
                ip_address=visit.ip_address,
                city=location.city,
                country=location.country,
                user_agent=visit.user_agent,
                referrer=visit.referrer,
            )
        )
        # Computed by PostgreSQL (click_count = click_count + 1), so simultaneous
        # clicks are all counted; reading, adding 1 in Python and saving would not.
        db.session.execute(
            update(URL).where(URL.id == url_id).values(click_count=URL.click_count + 1)
        )
        db.session.commit()
