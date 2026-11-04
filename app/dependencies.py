from flask import Flask
from injector import Module, provider, singleton
from redis import Redis


class RedisModule(Module):
    @singleton
    @provider
    def provide_redis(self, app: Flask) -> Redis:
        # One client per process: it owns a connection pool shared by all requests.
        return Redis(
            host=app.config["REDIS_HOST"],
            port=app.config["REDIS_PORT"],
            password=app.config["REDIS_PASSWORD"],
            decode_responses=True,
        )
