import pytest
from fakeredis import FakeRedis

from app.errors import ShortCodeGenerationError, ShortCodeNotFoundError
from app.shortener import service as service_module
from app.shortener.service import (
    CODE_ALPHABET,
    CODE_LENGTH,
    MAX_ATTEMPTS,
    UrlShortenerService,
)

LONG_URL = "https://example.com/some/very/long/path?with=query"


@pytest.fixture
def service(redis_client: FakeRedis) -> UrlShortenerService:
    return UrlShortenerService(redis_client)


def test_shorten_returns_code_of_expected_length_and_alphabet(
    service: UrlShortenerService,
) -> None:
    short_code = service.shorten(LONG_URL)

    assert len(short_code) == CODE_LENGTH
    assert all(char in CODE_ALPHABET for char in short_code)


def test_shorten_stores_url_under_prefixed_key(
    service: UrlShortenerService, redis_client: FakeRedis
) -> None:
    short_code = service.shorten(LONG_URL)

    assert redis_client.get(f"url:{short_code}") == LONG_URL


def test_shorten_same_url_twice_gives_different_codes(
    service: UrlShortenerService,
) -> None:
    assert service.shorten(LONG_URL) != service.shorten(LONG_URL)


def test_resolve_returns_original_url(service: UrlShortenerService) -> None:
    short_code = service.shorten(LONG_URL)

    assert service.resolve(short_code) == LONG_URL


def test_resolve_unknown_code_raises_not_found(service: UrlShortenerService) -> None:
    with pytest.raises(ShortCodeNotFoundError) as exc_info:
        service.resolve("missing")

    assert exc_info.value.short_code == "missing"


def test_shorten_retries_when_code_is_taken(
    service: UrlShortenerService,
    redis_client: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client.set("url:taken01", "https://existing.example")
    codes = iter(["taken01", "free001"])
    monkeypatch.setattr(service_module, "generate_short_code", lambda: next(codes))

    short_code = service.shorten(LONG_URL)

    assert short_code == "free001"
    # The existing mapping must not be overwritten.
    assert redis_client.get("url:taken01") == "https://existing.example"


def test_shorten_gives_up_after_max_attempts(
    service: UrlShortenerService,
    redis_client: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client.set("url:taken01", "https://existing.example")
    calls: list[str] = []

    def always_taken() -> str:
        calls.append("taken01")
        return "taken01"

    monkeypatch.setattr(service_module, "generate_short_code", always_taken)

    with pytest.raises(ShortCodeGenerationError):
        service.shorten(LONG_URL)
    assert len(calls) == MAX_ATTEMPTS
