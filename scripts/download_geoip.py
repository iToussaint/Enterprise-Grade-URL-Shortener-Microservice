"""Download the free DB-IP "IP to City Lite" database used for click locations.

Usage:  poetry run python scripts/download_geoip.py [destination]
Default destination: geoip/dbip-city-lite.mmdb

DB-IP publishes a new file each month; if this month's is not out yet, the
previous month's is used. Licence: CC BY 4.0, attribution "IP Geolocation by
DB-IP" (https://db-ip.com) is required wherever the data is shown.
"""

import gzip
import shutil
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError

URL_TEMPLATE = "https://download.db-ip.com/free/dbip-city-lite-{month}.mmdb.gz"
DEFAULT_DESTINATION = Path("geoip/dbip-city-lite.mmdb")
USER_AGENT = "url-shortener-geoip-download/1.0"


def candidate_months(today: datetime) -> list[str]:
    """This month, then last month (the day before the 1st is in last month)."""
    first_of_month = today.replace(day=1)
    last_month = first_of_month - timedelta(days=1)
    return [first_of_month.strftime("%Y-%m"), last_month.strftime("%Y-%m")]


def download(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    for month in candidate_months(datetime.now(UTC)):
        url = URL_TEMPLATE.format(month=month)
        print(f"Downloading {url} ...")
        # DB-IP refuses Python's default "Python-urllib" user agent (403).
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                temporary = destination.with_suffix(".part")
                with gzip.GzipFile(fileobj=response) as unzipped:
                    with temporary.open("wb") as file:
                        shutil.copyfileobj(unzipped, file)
                temporary.replace(destination)
        except HTTPError as error:
            print(f"  not available ({error.code}), trying the previous month")
            continue
        size_mb = destination.stat().st_size / 1_000_000
        print(f"Saved {destination} ({size_mb:.0f} MB)")
        return
    sys.exit("No DB-IP database could be downloaded.")


if __name__ == "__main__":
    download(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DESTINATION)
