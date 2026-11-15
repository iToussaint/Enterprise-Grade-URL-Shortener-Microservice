import ipaddress
import logging
from dataclasses import dataclass
from typing import Any

import maxminddb
from flask import Flask
from injector import Module, provider, singleton

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Location:
    city: str | None = None
    country: str | None = None  # ISO 3166-1 alpha-2, e.g. "RW"


class GeoIPLocator:
    """Finds the city and country of an IP address in a local DB-IP database.

    The file is opened once and shared by every request of the worker. If it is
    missing, every lookup returns an empty Location, so clicks are still recorded.
    """

    def __init__(self, database_path: str) -> None:
        self._reader: maxminddb.Reader | None = None
        try:
            self._reader = maxminddb.open_database(database_path)
        except (OSError, maxminddb.InvalidDatabaseError) as error:
            logger.warning(
                "GeoIP database not available (%s); clicks are recorded without "
                "city and country. Run scripts/download_geoip.py to download it.",
                error,
            )

    def locate(self, ip: str) -> Location:
        if self._reader is None:
            return Location()
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return Location()
        # Private and local addresses (127.0.0.1, Docker's 172.x) have no location.
        if not address.is_global:
            return Location()

        record = self._reader.get(address)
        if not isinstance(record, dict):
            return Location()
        city = _english_name(record.get("city"))
        country = _get(record.get("country"), "iso_code")
        return Location(
            city=city[:100] if isinstance(city, str) else None,
            country=country if isinstance(country, str) else None,
        )


def _get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _english_name(value: Any) -> Any:
    return _get(_get(value, "names"), "en")


class GeoIPModule(Module):
    """Tells Flask-Injector how to build the locator: once per worker, from config."""

    @singleton
    @provider
    def provide_locator(self, app: Flask) -> GeoIPLocator:
        return GeoIPLocator(app.config["GEOIP_DATABASE_PATH"])
