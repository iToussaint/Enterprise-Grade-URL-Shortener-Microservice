from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    Table,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.extensions import db

if TYPE_CHECKING:
    from app.users.models import User

URL_MAX_LENGTH = 2083
SHORT_CODE_MAX_LENGTH = 10
CUSTOM_ALIAS_MAX_LENGTH = 50

# Link table for the URL <-> Tag many-to-many relationship: one row per pairing.
url_tags = Table(
    "url_tags",
    db.metadata,
    Column("url_id", ForeignKey("urls.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class URL(db.Model):  # type: ignore[name-defined]
    __tablename__ = "urls"
    # Like Django's PositiveIntegerField on PostgreSQL.
    __table_args__ = (CheckConstraint("click_count >= 0", name="click_count_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    original_url: Mapped[str] = mapped_column(String(URL_MAX_LENGTH))
    short_code: Mapped[str] = mapped_column(
        String(SHORT_CODE_MAX_LENGTH), unique=True, index=True
    )
    custom_alias: Mapped[str | None] = mapped_column(
        String(CUSTOM_ALIAS_MAX_LENGTH), unique=True
    )
    # Nullable: URLs created through the anonymous Module 5 endpoint have no owner.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(1000))
    favicon: Mapped[str | None] = mapped_column(String(URL_MAX_LENGTH))
    click_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    owner: Mapped["User | None"] = relationship()
    tags: Mapped[list["Tag"]] = relationship(
        secondary=url_tags, back_populates="urls", passive_deletes=True
    )


class Tag(db.Model):  # type: ignore[name-defined]
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

    urls: Mapped[list[URL]] = relationship(
        secondary=url_tags, back_populates="tags", passive_deletes=True
    )
