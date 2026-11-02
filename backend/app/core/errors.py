class DomainError(Exception):
    """A business-rule violation. Message is shown to the user as-is, so keep it plain."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFound(DomainError):
    def __init__(self, what: str = "Record"):
        super().__init__(f"{what} not found.", 404)
