from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ShortenRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"url": "https://www.example.com/articles/2026/flask-guide"}
        }
    )

    url: HttpUrl = Field(description="The long URL to shorten. Must be http or https.")


class ShortenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "short_code": "aB3xY9z",
                "short_url": "http://localhost:8000/api/aB3xY9z",
                "original_url": "https://www.example.com/articles/2026/flask-guide",
            }
        }
    )

    short_code: str = Field(description="The generated 7-character code.")
    short_url: str = Field(description="The full short URL that redirects.")
    original_url: str = Field(description="The stored (normalized) original URL.")
