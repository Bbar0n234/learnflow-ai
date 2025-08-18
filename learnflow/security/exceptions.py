"""Security-related exceptions for LearnFlow AI."""


class SecurityValidationError(Exception):
    """Raised when security validation fails."""
    
    def __init__(self, message: str, original_content: str = None):
        super().__init__(message)
        self.original_content = original_content