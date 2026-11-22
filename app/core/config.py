from datetime import timedelta
from urllib.parse import quote

import decouple


class Config:
    DEBUG = False
    TESTING = False

    # Flask-RESTX: don't append "did you mean ..." hints to 404 messages,
    # don't add its own top-level "message" key to our error bodies,
    # and don't advertise the X-Fields mask header in Swagger.
    RESTX_ERROR_404_HELP = False
    ERROR_INCLUDE_MESSAGE = False
    RESTX_MASK_SWAGGER = False

    # postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DATABASE
    SQLALCHEMY_DATABASE_URI: str | None = decouple.config("DATABASE_URL", default=None)
    # Test each pooled connection before use, so a restarted database
    # does not turn the first requests afterwards into errors.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # DB-IP "IP to City Lite" database for click locations (optional: without
    # the file, clicks are recorded without city and country).
    GEOIP_DATABASE_PATH: str = decouple.config(
        "GEOIP_DATABASE_PATH", default="geoip/dbip-city-lite.mmdb"
    )
    # Number of trusted reverse proxies in front of the app. When > 0, the client
    # IP is taken from X-Forwarded-For; 0 ignores that header, which clients can fake.
    TRUSTED_PROXY_COUNT: int = decouple.config(
        "TRUSTED_PROXY_COUNT", default=0, cast=int
    )

    # Signs the JWT access and refresh tokens. Required (at least 32 characters):
    # anyone who knows it can forge tokens, so it only lives in .env.
    JWT_SECRET_KEY: str | None = decouple.config("JWT_SECRET_KEY", default=None)
    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)

    REDIS_HOST: str = decouple.config("REDIS_HOST", default="localhost")
    REDIS_PORT: int = decouple.config("REDIS_PORT", default=6379, cast=int)
    REDIS_PASSWORD: str | None = decouple.config("REDIS_PASSWORD", default=None)

    # Rate limiting (Flask-Limiter). Counters live in Redis, so every Gunicorn
    # worker shares them; if Redis is unreachable, each worker falls back to
    # in-memory counters instead of switching limits off.
    RATELIMIT_STORAGE_URI = (
        "redis://"
        + (f":{quote(REDIS_PASSWORD, safe='')}@" if REDIS_PASSWORD else "")
        + f"{REDIS_HOST}:{REDIS_PORT}/0"
    )
    RATELIMIT_STRATEGY = "moving-window"  # any 60 seconds, not per clock minute
    RATELIMIT_HEADERS_ENABLED = True  # X-RateLimit-* and Retry-After headers
    RATELIMIT_SWALLOW_ERRORS = True
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = True
    LOGIN_RATE_LIMIT = "5 per minute"


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    pass


class TestingConfig(Config):
    TESTING = True
    JWT_SECRET_KEY = "test-only-secret-key-that-is-long-enough-for-hs256"
    RATELIMIT_STORAGE_URI = "memory://"


config_by_name: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
