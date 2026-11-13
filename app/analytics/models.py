from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.extensions import db
from app.urls.models import URL, URL_MAX_LENGTH


class Click(db.Model):  # type: ignore[name-defined]
    """One visit to a short URL."""

    __tablename__ = "clicks"
    # Analytics always read one URL's clicks, usually over a time range.
    __table_args__ = (Index("ix_clicks_url_id_clicked_at", "url_id", "clicked_at"),)

    # BIGINT: clicks are the fastest-growing table.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    url_id: Mapped[int] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"))
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # PostgreSQL's IP address type, as used by Django's GenericIPAddressField.
    ip_address: Mapped[str] = mapped_column(INET)
    city: Mapped[str | None] = mapped_column(String(100))
    # ISO 3166-1 alpha-2 code, e.g. "RW".
    country: Mapped[str | None] = mapped_column(String(2))
    user_agent: Mapped[str] = mapped_column(Text, default="")
    referrer: Mapped[str | None] = mapped_column(String(URL_MAX_LENGTH))

    url: Mapped[URL] = relationship()
