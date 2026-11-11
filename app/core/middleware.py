import time

from flask import Flask, Response, current_app, g, request


def register_request_logging(app: Flask) -> None:
    @app.before_request
    def start_timer() -> None:
        # g lives for exactly one request, so concurrent requests never share it.
        g.request_start = time.perf_counter()

    @app.after_request
    def log_request(response: Response) -> Response:
        # Runs for error responses too, because every error becomes a response.
        # Query strings and bodies are not logged: they can contain sensitive data.
        duration_ms = (time.perf_counter() - g.request_start) * 1000
        current_app.logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )
        return response
