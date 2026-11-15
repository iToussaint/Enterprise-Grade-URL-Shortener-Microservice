import logging
from pathlib import Path
from typing import Any

import pytest

from app.analytics.geoip import GeoIPLocator, Location

DATABASE = Path("geoip/dbip-city-lite.mmdb")


class FakeReader:
    """Returns records shaped like DB-IP's, without the 130 MB file."""

    def __init__(self, record: Any) -> None:
        self.record = record

    def get(self, address: object) -> Any:
        return self.record


def locator_with(record: Any) -> GeoIPLocator:
    locator = GeoIPLocator("missing.mmdb")
    locator._reader = FakeReader(record)  # type: ignore[assignment]
    return locator


def test_reads_city_and_country_from_the_record() -> None:
    record = {"city": {"names": {"en": "Kigali"}}, "country": {"iso_code": "RW"}}

    assert locator_with(record).locate("41.186.0.1") == Location("Kigali", "RW")


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "172.20.0.1", "192.168.1.5", "::1", "not-an-ip"]
)
def test_private_or_invalid_addresses_have_no_location(ip: str) -> None:
    record = {"city": {"names": {"en": "Kigali"}}, "country": {"iso_code": "RW"}}

    assert locator_with(record).locate(ip) == Location()


@pytest.mark.parametrize("record", [None, {}, {"city": "unexpected shape"}])
def test_unknown_or_unexpected_records_have_no_location(record: Any) -> None:
    assert locator_with(record).locate("8.8.8.8") == Location()


def test_missing_database_logs_a_warning_and_locates_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        locator = GeoIPLocator("does/not/exist.mmdb")

    assert locator.locate("41.186.0.1") == Location()
    assert "download_geoip.py" in caplog.text


@pytest.mark.skipif(not DATABASE.exists(), reason="run scripts/download_geoip.py")
def test_real_database_lookup() -> None:
    locator = GeoIPLocator(str(DATABASE))

    assert locator.locate("41.186.0.1").country == "RW"
    assert locator.locate("196.201.214.1").country == "KE"
