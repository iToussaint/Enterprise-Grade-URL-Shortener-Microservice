from sqlalchemy import Select, func, or_, select

from app.urls.models import URL

URLQuery = Select[URL]


class URLManager:
    """Reusable URL queries, like a Django manager.

    Each method returns a query (a `Select`) without running it, so it can be
    combined with another method or refined with `.where()`, `.order_by()` or
    `.options()` before being executed with `db.session.scalars(...)`.
    Pass an existing query to build on it, e.g. `popular_urls(active_urls())`.
    """

    def active_urls(self, query: URLQuery | None = None) -> URLQuery:
        """Active URLs that have not expired (no expiry date, or one in the future)."""
        return self._base(query).where(
            URL.is_active,
            or_(URL.expires_at.is_(None), URL.expires_at > func.now()),
        )

    def expired_urls(self, query: URLQuery | None = None) -> URLQuery:
        """URLs whose expiry date has passed, whether or not they are active."""
        return self._base(query).where(
            URL.expires_at.is_not(None), URL.expires_at <= func.now()
        )

    def popular_urls(self, query: URLQuery | None = None) -> URLQuery:
        """URLs ordered by click count, most clicked first; ties newest first."""
        return self._base(query).order_by(
            URL.click_count.desc(), URL.created_at.desc(), URL.id.desc()
        )

    def _base(self, query: URLQuery | None) -> URLQuery:
        return query if query is not None else select(URL)
