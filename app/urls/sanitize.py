"""Clean-up and checks for every URL a user submits.

`SafeHttpUrl` adds these rules to Pydantic's `HttpUrl` (which already requires
http/https, lower-cases the host and converts international domain names):

1. Surrounding whitespace is removed.
2. Spaces and invisible characters inside the URL are refused. Pydantic would
   silently encode or drop them, so the stored link would differ from what the
   user typed, and invisible characters can disguise a link.
3. Credentials (`https://user:password@host/`) are refused: they would be
   stored and shown to everyone who can read the URL.
4. Links to this service itself are refused: a short link to a short link can
   loop. The service's address comes from the validation context.
"""

import unicodedata
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import AfterValidator, BeforeValidator, HttpUrl, ValidationInfo
from pydantic_core import PydanticCustomError

DEFAULT_PORTS = {"http": 80, "https": 443}


def strip_and_refuse_hidden_characters(value: Any) -> Any:
    if not isinstance(value, str):
        return value  # HttpUrl reports the wrong type
    value = value.strip()
    # Category "C" = control, format (e.g. zero-width space, right-to-left
    # override), surrogate, private-use and unassigned characters.
    if any(char.isspace() or unicodedata.category(char)[0] == "C" for char in value):
        raise PydanticCustomError(
            "url_hidden_characters",
            "URL must not contain spaces or invisible characters.",
        )
    return value


def refuse_credentials(url: HttpUrl) -> HttpUrl:
    if url.username or url.password:
        raise PydanticCustomError(
            "url_credentials", "URL must not contain a username or password."
        )
    return url


def refuse_own_links(url: HttpUrl, info: ValidationInfo) -> HttpUrl:
    service_url = (info.context or {}).get("service_url")
    if service_url:
        own = urlsplit(service_url)
        own_port = own.port or DEFAULT_PORTS.get(own.scheme)
        if url.host == own.hostname and url.port == own_port:
            raise PydanticCustomError(
                "url_self_link", "URL must not point to this URL shortener."
            )
    return url


SafeHttpUrl = Annotated[
    HttpUrl,
    BeforeValidator(strip_and_refuse_hidden_characters),
    AfterValidator(refuse_credentials),
    AfterValidator(refuse_own_links),
]


def validation_context(service_url: str) -> dict[str, str]:
    """Context for model_validate(): the address this service is reached at."""
    return {"service_url": service_url}
