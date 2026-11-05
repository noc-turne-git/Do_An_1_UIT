class ApplicationError(Exception):
    """Shared component failure; implementations must translate provider/DB errors.

    Invalid model input/output raises Pydantic ValidationError instead.
    Retry decisions belong to the future orchestrator, never to protocols.
    """

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)
