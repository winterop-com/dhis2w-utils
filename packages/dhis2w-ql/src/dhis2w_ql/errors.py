"""Error types for the d2ql language engine, carrying source position where known."""

from __future__ import annotations


class D2qlError(Exception):
    """Base class for every d2ql language error."""


class LexError(D2qlError):
    """Raised when the tokenizer hits a character it cannot start a token with."""

    def __init__(self, message: str, *, position: int, line: int, column: int) -> None:
        """Record the offending message and its source position."""
        super().__init__(f"{message} (line {line}, column {column})")
        self.message = message
        self.position = position
        self.line = line
        self.column = column


class ParseError(D2qlError):
    """Raised when the parser cannot build an AST from the token stream."""

    def __init__(self, message: str, *, position: int, line: int, column: int) -> None:
        """Record the offending message and its source position."""
        super().__init__(f"{message} (line {line}, column {column})")
        self.message = message
        self.position = position
        self.line = line
        self.column = column


class SemanticError(D2qlError):
    """Raised when a parsed program is well-formed but cannot be resolved or planned."""


class EvaluationError(D2qlError):
    """Raised when evaluating an expression or executing a pipeline fails at runtime."""
