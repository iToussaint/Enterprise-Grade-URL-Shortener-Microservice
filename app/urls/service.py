import secrets
import string
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal, NoReturn

from injector import inject
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.core.errors import (
    ConflictError,
    ShortCodeGenerationError,
    ShortCodeNotFoundError,
    violated_constraint,
)
from app.core.extensions import db
from app.urls.managers import URLManager, URLQuery
from app.urls.models import URL, Tag
from app.users.models import User

CODE_ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7
MAX_ATTEMPTS = 5


def generate_short_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class UrlShortenerService:
    @inject
    def __init__(self, urls: URLManager) -> None:
        self._urls = urls

    # ---- Module 5: anonymous short URLs -------------------------------------

    def shorten(self, original_url: str) -> str:
        _, short_code = self._insert_with_new_code(original_url=original_url)
        db.session.commit()
        return short_code

    def resolve(self, short_code: str) -> str:
        original_url = db.session.scalar(
            select(URL.original_url).where(URL.short_code == short_code)
        )
        if original_url is None:
            raise ShortCodeNotFoundError(short_code)
        return original_url

    # ---- Module 6: URLs owned by a user -------------------------------------

    def create_for(
        self,
        owner: User,
        original_url: str,
        custom_alias: str | None = None,
        expires_at: datetime | None = None,
        tag_names: Sequence[str] = (),
    ) -> URL:
        if custom_alias is not None:
            self._ensure_alias_is_free(custom_alias)
        try:
            url_id, _ = self._insert_with_new_code(
                original_url=original_url,
                owner_id=owner.id,
                custom_alias=custom_alias,
                expires_at=expires_at,
            )
        except IntegrityError as error:
            self._raise_alias_conflict(error)

        url = db.session.get_one(URL, url_id)
        url.tags = self._tags_named(tag_names)
        db.session.commit()
        return url

    def list_for(
        self,
        owner: User,
        status: Literal["all", "active", "expired"] = "all",
        sort: Literal["newest", "popular"] = "newest",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[URL], int]:
        """One page of the owner's URLs, and how many match in total."""
        query = select(URL).where(URL.owner_id == owner.id)
        if status == "active":
            query = self._urls.active_urls(query)
        elif status == "expired":
            query = self._urls.expired_urls(query)

        total = db.session.scalar(select(func.count()).select_from(query.subquery()))

        if sort == "popular":
            query = self._urls.popular_urls(query)
        else:
            query = query.order_by(URL.created_at.desc(), URL.id.desc())
        query = (
            self._with_owner_and_tags(query)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return list(db.session.scalars(query)), total or 0

    def get_for(self, owner: User, short_code: str) -> URL:
        """The owner's URL with this code. Other users' URLs are "not found"."""
        url: URL | None = db.session.scalar(
            self._with_owner_and_tags(
                select(URL).where(
                    URL.short_code == short_code, URL.owner_id == owner.id
                )
            )
        )
        if url is None:
            raise ShortCodeNotFoundError(short_code)
        return url

    def update_for(
        self,
        owner: User,
        short_code: str,
        original_url: str,
        custom_alias: str | None,
        expires_at: datetime | None,
        tag_names: Sequence[str],
        is_active: bool,
    ) -> URL:
        """Replace the editable fields of the owner's URL (PUT semantics).

        The short code never changes: it is the link people already shared.
        """
        url = self.get_for(owner, short_code)
        if custom_alias is not None and custom_alias != url.custom_alias:
            self._ensure_alias_is_free(custom_alias, ignore_url_id=url.id)

        url.original_url = original_url
        url.custom_alias = custom_alias
        url.expires_at = expires_at
        url.is_active = is_active
        url.tags = self._tags_named(tag_names)
        try:
            db.session.commit()
        except IntegrityError as error:
            self._raise_alias_conflict(error)
        return url

    def deactivate_for(self, owner: User, short_code: str) -> None:
        """Soft delete: the row and its clicks stay, the link stops working."""
        url = self.get_for(owner, short_code)
        url.is_active = False
        db.session.commit()

    # ---- helpers ------------------------------------------------------------

    def _insert_with_new_code(self, **values: Any) -> tuple[int, str]:
        """Insert a URL row under a new random code; return its id and code."""
        for _ in range(MAX_ATTEMPTS):
            short_code = generate_short_code()
            # ON CONFLICT DO NOTHING inserts only if the code is still free, so
            # checking for a collision and saving happen in one atomic statement.
            url_id = db.session.execute(
                insert(URL)
                .values(short_code=short_code, **values)
                .on_conflict_do_nothing(index_elements=[URL.short_code])
                .returning(URL.id)
            ).scalar_one_or_none()
            if url_id is not None:
                return url_id, short_code

        raise ShortCodeGenerationError(
            f"Could not generate a unique short code after {MAX_ATTEMPTS} attempts."
        )

    def _ensure_alias_is_free(
        self, alias: str, ignore_url_id: int | None = None
    ) -> None:
        # An alias must not equal any alias or short code, so a link is never ambiguous.
        query = select(URL.id).where(
            or_(URL.custom_alias == alias, URL.short_code == alias)
        )
        if ignore_url_id is not None:
            query = query.where(URL.id != ignore_url_id)
        if db.session.scalar(query) is not None:
            raise ConflictError("custom_alias", "This alias is already taken.")

    def _raise_alias_conflict(self, error: IntegrityError) -> NoReturn:
        """Turn a lost race for an alias into 409; re-raise anything else."""
        db.session.rollback()
        if violated_constraint(error) == "uq_urls_custom_alias":
            # Another request took the alias between the check and the write.
            raise ConflictError(
                "custom_alias", "This alias is already taken."
            ) from None
        raise error

    def _tags_named(self, names: Sequence[str]) -> list[Tag]:
        """Existing tags matched case-insensitively; unknown names become new tags."""
        wanted: dict[str, str] = {}
        for name in names:
            wanted.setdefault(name.lower(), name)
        if not wanted:
            return []

        existing = {
            tag.name.lower(): tag
            for tag in db.session.scalars(
                select(Tag).where(func.lower(Tag.name).in_(wanted))
            )
        }
        return [existing.get(key) or Tag(name=name) for key, name in wanted.items()]

    @staticmethod
    def _with_owner_and_tags(query: URLQuery) -> URLQuery:
        # Avoid N+1 queries when the owner and tags are read for every URL:
        # joinedload  = Django select_related: owner comes in the same query (JOIN).
        # selectinload = Django prefetch_related: one extra query loads all tags.
        return query.options(joinedload(URL.owner), selectinload(URL.tags))
