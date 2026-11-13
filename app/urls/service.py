import secrets
import string

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import ShortCodeGenerationError, ShortCodeNotFoundError
from app.core.extensions import db
from app.urls.models import URL

CODE_ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7
MAX_ATTEMPTS = 5


def generate_short_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class UrlShortenerService:
    def shorten(self, original_url: str) -> str:
        for _ in range(MAX_ATTEMPTS):
            short_code = generate_short_code()
            # ON CONFLICT DO NOTHING inserts only if the code is still free, so
            # checking for a collision and saving happen in one atomic statement.
            inserted_id = db.session.execute(
                insert(URL)
                .values(short_code=short_code, original_url=original_url)
                .on_conflict_do_nothing(index_elements=[URL.short_code])
                .returning(URL.id)
            ).scalar_one_or_none()
            if inserted_id is not None:
                db.session.commit()
                return short_code

        raise ShortCodeGenerationError(
            f"Could not generate a unique short code after {MAX_ATTEMPTS} attempts."
        )

    def resolve(self, short_code: str) -> str:
        original_url = db.session.scalar(
            select(URL.original_url).where(URL.short_code == short_code)
        )
        if original_url is None:
            raise ShortCodeNotFoundError(short_code)
        return original_url
