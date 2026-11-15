from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import Request
from injector import inject
from sqlalchemy import distinct, func, select, text, update

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


# Clicks per day/week/month in UTC. generate_series lists every interval of the
# period, so intervals without clicks appear with 0 instead of being missing.
# Times are converted to UTC ("AT TIME ZONE 'UTC'") so the buckets do not depend
# on the database session's time zone.
TIME_SERIES_SQL = text("""
    WITH buckets AS (
        SELECT generate_series(
            date_trunc(:interval, CAST(:start AS timestamptz) AT TIME ZONE 'UTC'),
            date_trunc(:interval, CAST(:end AS timestamptz) AT TIME ZONE 'UTC'),
            CAST('1 ' || :interval AS interval)
        ) AS bucket
    )
    SELECT buckets.bucket AT TIME ZONE 'UTC' AS period_start,
           count(clicks.id) AS clicks
    FROM buckets
    LEFT JOIN clicks
        ON clicks.url_id = :url_id
        AND clicks.clicked_at BETWEEN :start AND :end
        AND date_trunc(:interval, clicks.clicked_at AT TIME ZONE 'UTC') = buckets.bucket
    GROUP BY buckets.bucket
    ORDER BY buckets.bucket
""")

TOP_REFERRERS = 10


class AnalyticsService:
    def report(self, url: URL, days: int, interval: str) -> dict[str, Any]:
        """Click statistics for one URL over the last `days` days.

        Every figure is computed by PostgreSQL (COUNT ... GROUP BY), the
        equivalent of Django's values(...).annotate(Count(...)).
        """
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        in_period = (
            Click.url_id == url.id,
            Click.clicked_at.between(start, end),
        )

        clicks, unique_visitors = db.session.execute(
            select(func.count(), func.count(distinct(Click.ip_address))).where(
                *in_period
            )
        ).one()

        clicks_per_interval = db.session.execute(
            TIME_SERIES_SQL,
            {"interval": interval, "start": start, "end": end, "url_id": url.id},
        ).all()

        clicks_column = func.count().label("clicks")
        by_country = db.session.execute(
            select(Click.country, clicks_column)
            .where(*in_period)
            .group_by(Click.country)
            .order_by(clicks_column.desc(), Click.country)
        ).all()
        top_referrers = db.session.execute(
            select(Click.referrer, clicks_column)
            .where(*in_period)
            .group_by(Click.referrer)
            .order_by(clicks_column.desc(), Click.referrer)
            .limit(TOP_REFERRERS)
        ).all()

        return {
            "short_code": url.short_code,
            "total_clicks": url.click_count,
            "period": {"start": start, "end": end, "interval": interval},
            "clicks": clicks,
            "unique_visitors": unique_visitors,
            "time_series": [
                {"period_start": row.period_start, "clicks": row.clicks}
                for row in clicks_per_interval
            ],
            "by_country": [
                {"country": row.country, "clicks": row.clicks} for row in by_country
            ],
            "top_referrers": [
                {"referrer": row.referrer, "clicks": row.clicks}
                for row in top_referrers
            ],
        }
