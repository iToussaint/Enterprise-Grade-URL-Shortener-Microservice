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


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"username": "alice", "password": "correct horse battery staple"}
        }
    )

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"refresh": "<refresh_token from login>"}}
    )

    refresh: str = Field(min_length=1, description="The refresh token from login.")


class AccessTokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "Bearer",
                "expires_in": 900,
            }
        }
    )

    access_token: str = Field(description="Send as 'Authorization: Bearer <token>'.")
    token_type: str = "Bearer"
    expires_in: int = Field(description="Seconds until the access token expires.")


class TokenResponse(AccessTokenResponse):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "Bearer",
                "expires_in": 900,
            }
        }
    )

    refresh_token: str = Field(description="Use with /refresh/ for new access tokens.")
