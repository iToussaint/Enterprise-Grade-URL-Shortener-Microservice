from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.extensions import db


class Tier(StrEnum):
    FREE = "Free"
    PREMIUM = "Premium"
    ADMIN = "Admin"


# Tiers with Premium features: unlimited URLs, custom aliases, analytics.
PREMIUM_TIERS = frozenset({Tier.PREMIUM, Tier.ADMIN})

# A Free account may have at most this many active (not expired) URLs.
FREE_MAX_ACTIVE_URLS = 10


class User(db.Model):  # type: ignore[name-defined]
    """Application user: the fields of Django's AbstractUser plus `is_premium` and `tier`.

    `tier` is the source of truth for the account level; `is_premium` is kept
    because the specification requires it.
    """

    # "user" is a reserved word in PostgreSQL.
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    # A salted one-way hash, never the password itself.
    password: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(150), default="")
    last_name: Mapped[str] = mapped_column(String(150), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    is_staff: Mapped[bool] = mapped_column(default=False)
    is_superuser: Mapped[bool] = mapped_column(default=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_joined: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_premium: Mapped[bool] = mapped_column(default=False)
    # Stored as VARCHAR with a CHECK constraint, like a Django CharField with choices.
    tier: Mapped[Tier] = mapped_column(
        Enum(
            Tier,
            name="tier",
            native_enum=False,
            create_constraint=True,
            length=10,
            values_callable=lambda tiers: [tier.value for tier in tiers],
        ),
        default=Tier.FREE,
    )

    def set_password(self, raw_password: str) -> None:
        self.password = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password, raw_password)
