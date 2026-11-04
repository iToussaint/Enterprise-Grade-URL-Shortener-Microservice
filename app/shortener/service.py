import secrets
import string

from injector import inject
from redis import Redis

from app.errors import ShortCodeGenerationError, ShortCodeNotFoundError

CODE_ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7
MAX_ATTEMPTS = 5
KEY_PREFIX = "url:"


def generate_short_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class UrlShortenerService:
    @inject
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    def shorten(self, original_url: str) -> str:
        for _ in range(MAX_ATTEMPTS):
            short_code = generate_short_code()
            # NX stores the key only if it doesn't exist yet, so checking for a
            # collision and saving happen in one atomic Redis operation.
            if self._redis.set(KEY_PREFIX + short_code, original_url, nx=True):
                return short_code

        raise ShortCodeGenerationError(
            f"Could not generate a unique short code after {MAX_ATTEMPTS} attempts."
        )

    def resolve(self, short_code: str) -> str:
        original_url = self._redis.get(KEY_PREFIX + short_code)
        if original_url is None:
            raise ShortCodeNotFoundError(short_code)
        return str(original_url)
