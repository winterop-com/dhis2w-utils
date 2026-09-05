"""Parser guards shared by the FHIRPath and CQL front ends."""

from typing import Any

from antlr4 import Token  # type: ignore[import-untyped]
from antlr4.error.ErrorListener import ErrorListener  # type: ignore[import-untyped]

from .exceptions import FHIRPathError


def require_end_of_input(parser: Any, error_type: type[FHIRPathError]) -> None:
    """Refuse an expression the parser stopped short of the end of.

    The `expression` rule is not anchored at EOF, so ANTLR happily parses `1 +` as `1` and leaves the
    `+` unread. Reading the token the parser stopped on turns that silence into a syntax error with a
    position, spelled the way the listener spells one so a caller reads both the same way.
    """
    token: Any = parser.getCurrentToken()
    if token is None or token.type == Token.EOF:
        return
    raise error_type(
        f"Syntax error at line {token.line}:{token.column}: extraneous input '{token.text}' expecting end of expression"
    )


class ThrowingErrorListener(ErrorListener):
    """ANTLR error listener that raises the engine's error type rather than writing to stderr."""

    error_type: type[FHIRPathError] = FHIRPathError

    def syntaxError(
        self,
        recognizer: Any,
        offendingSymbol: Any,
        line: int,
        column: int,
        msg: str,
        e: Any,
    ) -> None:
        """Turn a lexer or parser recognition error into an engine error."""
        raise self.error_type(f"Syntax error at line {line}:{column}: {msg}")

    def reportAmbiguity(
        self,
        recognizer: Any,
        dfa: Any,
        startIndex: int,
        stopIndex: int,
        exact: bool,
        ambigAlts: Any,
        configs: Any,
    ) -> None:
        """Ignore an ambiguity report; the alternative the grammar picked is the answer."""

    def reportAttemptingFullContext(
        self,
        recognizer: Any,
        dfa: Any,
        startIndex: int,
        stopIndex: int,
        conflictingAlts: Any,
        configs: Any,
    ) -> None:
        """Ignore a full-context attempt report."""

    def reportContextSensitivity(
        self,
        recognizer: Any,
        dfa: Any,
        startIndex: int,
        stopIndex: int,
        prediction: int,
        configs: Any,
    ) -> None:
        """Ignore a context-sensitivity report."""
