class Config:
    DEBUG = False
    TESTING = False

    # Flask-RESTX: don't append "did you mean ..." hints to 404 messages,
    # and don't advertise the X-Fields mask header in Swagger.
    RESTX_ERROR_404_HELP = False
    RESTX_MASK_SWAGGER = False


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
