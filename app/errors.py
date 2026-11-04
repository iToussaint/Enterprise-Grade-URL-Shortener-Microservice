class ShortCodeNotFoundError(Exception):
    def __init__(self, short_code: str) -> None:
        super().__init__(f"Short code '{short_code}' was not found.")
        self.short_code = short_code


class ShortCodeGenerationError(Exception):
    """Raised when no unused short code could be found after several attempts."""
