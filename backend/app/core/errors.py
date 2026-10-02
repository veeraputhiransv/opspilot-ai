"""Application errors mapped to HTTP responses by the API layer."""


class OpsPilotError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(OpsPilotError):
    status = 404
    code = "not_found"


class ConflictError(OpsPilotError):
    status = 409
    code = "conflict"


class PolicyViolation(OpsPilotError):
    status = 403
    code = "policy_violation"


class UnknownTool(PolicyViolation):
    code = "unknown_tool"


class RateLimitError(OpsPilotError):
    status = 429
    code = "rate_limited"

    def __init__(self, message: str, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class UnauthorizedError(OpsPilotError):
    status = 401
    code = "unauthorized"


class ForbiddenError(OpsPilotError):
    status = 403
    code = "forbidden"
