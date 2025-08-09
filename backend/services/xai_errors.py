class XAIQuotaError(Exception):
    """
    Raised when XAI reports that all available credits are used
    or the monthly spending limit has been reached.
    """
    def __init__(self, status: int = None, message: str = ""):
        super().__init__(message)
        self.status = status


class XAIRateLimitError(Exception):
    """
    Raised when XAI returns 429 Too Many Requests due to request rate limiting.
    """
    pass
