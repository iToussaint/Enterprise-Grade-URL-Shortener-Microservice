from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Interval = Literal["day", "week", "month"]


class AnalyticsParams(BaseModel):
    """Query parameters of GET /api/v1/analytics/<short_code>/."""

    days: int = Field(default=30, ge=1, le=365)
    interval: Interval = "day"


class Period(BaseModel):
    start: datetime
    end: datetime
    interval: Interval


class TimeBucket(BaseModel):
    period_start: datetime = Field(description="Start of the day, week or month (UTC).")
    clicks: int


class CountryClicks(BaseModel):
    country: str | None = Field(description="ISO country code; null if unknown.")
    clicks: int


class ReferrerClicks(BaseModel):
    referrer: str | None = Field(description="Referring page; null for direct visits.")
    clicks: int


class AnalyticsResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "short_code": "aB3xY9z",
                "total_clicks": 120,
                "period": {
                    "start": "2026-10-16T10:00:00Z",
                    "end": "2026-11-15T10:00:00Z",
                    "interval": "day",
                },
                "clicks": 42,
                "unique_visitors": 31,
                "time_series": [
                    {"period_start": "2026-11-14T00:00:00Z", "clicks": 0},
                    {"period_start": "2026-11-15T00:00:00Z", "clicks": 7},
                ],
                "by_country": [
                    {"country": "RW", "clicks": 25},
                    {"country": None, "clicks": 3},
                ],
                "top_referrers": [
                    {"referrer": "https://news.example.org/", "clicks": 9},
                    {"referrer": None, "clicks": 33},
                ],
            }
        }
    )

    short_code: str
    total_clicks: int = Field(description="All clicks since the URL was created.")
    period: Period
    clicks: int = Field(description="Clicks in the period.")
    unique_visitors: int = Field(description="Distinct IP addresses in the period.")
    time_series: list[TimeBucket] = Field(
        description="Clicks per interval; intervals without clicks are included as 0."
    )
    by_country: list[CountryClicks]
    top_referrers: list[ReferrerClicks] = Field(description="At most 10.")
