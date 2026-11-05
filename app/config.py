import decouple


class Config:
    DEBUG = False
    TESTING = False

    # Flask-RESTX: don't append "did you mean ..." hints to 404 messages,
    # and don't advertise the X-Fields mask header in Swagger.
    RESTX_ERROR_404_HELP = False
    RESTX_MASK_SWAGGER = False

    REDIS_HOST: str = decouple.config("REDIS_HOST", default="localhost")
    REDIS_PORT: int = decouple.config("REDIS_PORT", default=6379, cast=int)
    REDIS_PASSWORD: str | None = decouple.config("REDIS_PASSWORD", default=None)


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    pass


class TestingConfig(Config):
    TESTING = True


config_by_name: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
