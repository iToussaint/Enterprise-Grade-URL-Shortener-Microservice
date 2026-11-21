from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.urls.models import CUSTOM_ALIAS_MAX_LENGTH, URL
from app.urls.sanitize import SafeHttpUrl

# Path segments used by other routes; an alias must not shadow them.
RESERVED_CODES = frozenset({"api", "static", "swaggerui"})


class ShortenRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"url": "https://www.example.com/articles/2026/flask-guide"}
        }
    )

    url: SafeHttpUrl = Field(
        description="The long URL to shorten: http or https, no spaces, no credentials, "
        "not a link to this service."
    )


class ShortenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "short_code": "aB3xY9z",
                "short_url": "http://localhost:8000/api/aB3xY9z",
                "original_url": "https://www.example.com/articles/2026/flask-guide",
            }
        }
    )

    short_code: str = Field(description="The generated 7-character code.")
    short_url: str = Field(description="The full short URL that redirects.")
    original_url: str = Field(description="The stored (normalized) original URL.")


# ---- /api/v1/urls (authenticated) -------------------------------------------

TagName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


class CreateUrlRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://www.example.com/spring-sale",
                "custom_alias": "spring-sale",
                "expires_at": "2026-12-31T23:59:59Z",
                "tags": ["Marketing", "Social"],
            }
        }
    )

    url: SafeHttpUrl = Field(
        description="The long URL to shorten: http or https, no spaces, no credentials, "
        "not a link to this service."
    )
    custom_alias: str | None = Field(
        default=None,
        min_length=3,
        max_length=CUSTOM_ALIAS_MAX_LENGTH,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Optional memorable name: letters, digits, _ and - only.",
    )
    expires_at: AwareDatetime | None = Field(
        default=None, description="Optional expiry, with a time zone; must be future."
    )
    tags: list[TagName] = Field(
        default=[],
        max_length=10,
        description="Tag names. Existing tags match case-insensitively; "
        "new names create new tags.",
    )

    @field_validator("custom_alias")
    @classmethod
    def must_not_be_reserved(cls, value: str | None) -> str | None:
        if value is not None and value.lower() in RESERVED_CODES:
            raise ValueError("is reserved, choose another alias")
        return value

    @field_validator("expires_at")
    @classmethod
    def must_be_in_the_future(cls, value: datetime | None) -> datetime | None:
        if value is not None and value <= datetime.now(UTC):
            raise ValueError("must be in the future")
        return value


class UpdateUrlRequest(CreateUrlRequest):
    """PUT replaces the URL's editable fields; anything optional left out resets."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://www.example.com/summer-sale",
                "custom_alias": "summer-sale",
                "expires_at": None,
                "tags": ["Marketing"],
                "is_active": True,
            }
        }
    )

    is_active: bool = Field(
        default=True, description="false deactivates the link; true reactivates it."
    )


class UrlResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "short_code": "aB3xY9z",
                "short_url": "http://localhost:8000/api/aB3xY9z",
                "original_url": "https://www.example.com/spring-sale",
                "custom_alias": "spring-sale",
                "owner": "alice",
                "tags": ["Marketing", "Social"],
                "is_active": True,
                "expires_at": "2026-12-31T23:59:59Z",
                "click_count": 0,
                "created_at": "2026-11-15T10:30:00Z",
                "title": None,
                "description": None,
                "favicon": None,
            }
        }
    )

    short_code: str
    short_url: str = Field(description="The full short URL that redirects.")
    original_url: str
    custom_alias: str | None
    owner: str | None = Field(
        description="The owner's username; null for anonymous (Module 5) URLs."
    )
    tags: list[str]
    is_active: bool
    expires_at: datetime | None
    click_count: int
    created_at: datetime
    title: str | None = Field(description="Filled by the preview service (Module 9).")
    description: str | None = Field(
        description="Filled by the preview service (Module 9)."
    )
    favicon: str | None = Field(description="Filled by the preview service (Module 9).")

    @classmethod
    def from_url(cls, url: URL, short_url: str) -> "UrlResponse":
        return cls(
            short_code=url.short_code,
            short_url=short_url,
            original_url=url.original_url,
            custom_alias=url.custom_alias,
            owner=url.owner.username if url.owner else None,
            tags=sorted(tag.name for tag in url.tags),
            is_active=url.is_active,
            expires_at=url.expires_at,
            click_count=url.click_count,
            created_at=url.created_at,
            title=url.title,
            description=url.description,
            favicon=url.favicon,
        )


class ListUrlsParams(BaseModel):
    """Query parameters of GET /api/v1/urls/."""

    status: Literal["all", "active", "expired"] = "all"
    sort: Literal["newest", "popular"] = "newest"
    tag: TagName | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class UrlListResponse(BaseModel):
    items: list[UrlResponse]
    page: int
    page_size: int
    total: int = Field(description="Number of URLs matching the filter, all pages.")
