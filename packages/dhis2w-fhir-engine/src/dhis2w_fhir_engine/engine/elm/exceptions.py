"""ELM-specific exceptions."""


class ELMError(Exception):
    """Base exception for ELM errors."""

    def __init__(self, message: str, locator: str | None = None):
        self.locator = locator
        if locator:
            message = f"{message} at {locator}"
        super().__init__(message)


class ELMValidationError(ELMError):
    """Error during ELM validation or parsing."""

    pass


class ELMExecutionError(ELMError):
    """Error during ELM expression execution."""

    pass


class ELMTypeError(ELMError):
    """Type-related error in ELM evaluation."""

    pass


class ELMReferenceError(ELMError):
    """Error resolving a reference (definition, function, parameter, etc.)."""

    pass
