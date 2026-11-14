from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.users.models import Tier


class RegisterRequest(BaseModel):
    """Account details. The rules follow Django's defaults for users."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "alice",
                "email": "alice@example.com",
                "password": "correct horse battery staple",
            }
        }
    )

    username: str = Field(
        min_length=1,
        max_length=150,
        pattern=r"^[\w.@+-]+$",
        description="Letters, digits and @ . + - _ only.",
    )
    email: EmailStr = Field(max_length=254, description="Stored in lowercase.")
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    """A user's public details. The password hash is never returned."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "username": "alice",
                "email": "alice@example.com",
                "tier": "Free",
                "is_premium": False,
                "date_joined": "2026-11-15T10:30:00+00:00",
            }
        },
    )

    id: int
    username: str
    email: str
    tier: Tier
    is_premium: bool
    date_joined: datetime
