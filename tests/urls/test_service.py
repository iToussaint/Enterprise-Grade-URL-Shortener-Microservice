import pytest
from sqlalchemy import select

from app.core.errors import ShortCodeGenerationError, ShortCodeNotFoundError
from app.core.extensions import db
from app.urls import service as service_module
from app.urls.managers import URLManager
from app.urls.models import URL
from app.urls.service import (
    CODE_ALPHABET,
    CODE_LENGTH,
    MAX_ATTEMPTS,
    UrlShortenerService,
)
from tests.factories import create_url

LONG_URL = "https://example.com/some/very/long/path?with=query"

pytestmark = pytest.mark.usefixtures("app_context")


@pytest.fixture
def service() -> UrlShortenerService:
    return UrlShortenerService(URLManager())


def stored_url(short_code: str) -> URL:
    return db.session.scalars(select(URL).where(URL.short_code == short_code)).one()


def test_shorten_returns_code_of_expected_length_and_alphabet(
    service: UrlShortenerService,
) -> None:
    short_code = service.shorten(LONG_URL)

    assert len(short_code) == CODE_LENGTH
    assert all(char in CODE_ALPHABET for char in short_code)


def test_shorten_stores_an_anonymous_url_row(service: UrlShortenerService) -> None:
    short_code = service.shorten(LONG_URL)

    url = stored_url(short_code)
    assert url.original_url == LONG_URL
    assert url.owner_id is None
    assert url.is_active is True
    assert url.click_count == 0


def test_shorten_same_url_twice_gives_different_codes(
    service: UrlShortenerService,
) -> None:
    assert service.shorten(LONG_URL) != service.shorten(LONG_URL)


def test_resolve_returns_original_url(service: UrlShortenerService) -> None:
    short_code = service.shorten(LONG_URL)

    assert service.resolve(short_code).original_url == LONG_URL


def test_resolve_unknown_code_raises_not_found(service: UrlShortenerService) -> None:
    with pytest.raises(ShortCodeNotFoundError) as exc_info:
        service.resolve("missing")

    assert exc_info.value.short_code == "missing"


def test_shorten_retries_when_code_is_taken(
    service: UrlShortenerService, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_url("taken01", original_url="https://existing.example")
    codes = iter(["taken01", "free001"])
    monkeypatch.setattr(service_module, "generate_short_code", lambda: next(codes))

    short_code = service.shorten(LONG_URL)

    assert short_code == "free001"
    # The existing row must not be overwritten.
    assert stored_url("taken01").original_url == "https://existing.example"


def test_shorten_gives_up_after_max_attempts(
    service: UrlShortenerService, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_url("taken01")
    calls: list[str] = []

    def always_taken() -> str:
        calls.append("taken01")
        return "taken01"

    monkeypatch.setattr(service_module, "generate_short_code", always_taken)

    with pytest.raises(ShortCodeGenerationError):
        service.shorten(LONG_URL)
    assert len(calls) == MAX_ATTEMPTS
