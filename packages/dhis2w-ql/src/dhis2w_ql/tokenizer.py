"""Tokenizer for d2ql: turns source text into a flat list of positioned tokens."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from dhis2w_ql.errors import LexError


class TokenKind(StrEnum):
    """The lexical category of a token."""

    IDENT = "ident"
    KEYWORD = "keyword"
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATETIME = "datetime"
    VARIABLE = "variable"
    OP = "op"
    PIPE = "pipe"
    SINK = "sink"
    LPAREN = "lparen"
    RPAREN = "rparen"
    LBRACKET = "lbracket"
    RBRACKET = "rbracket"
    LBRACE = "lbrace"
    RBRACE = "rbrace"
    COMMA = "comma"
    COLON = "colon"
    DOT = "dot"
    EOF = "eof"


KEYWORDS: frozenset[str] = frozenset(
    {
        "define",
        "function",
        "where",
        "select",
        "transform",
        "order",
        "limit",
        "skip",
        "count",
        "aggregate",
        "by",
        "read",
        "as",
        "asc",
        "desc",
        "and",
        "or",
        "xor",
        "implies",
        "in",
        "is",
        "contains",
        "div",
        "mod",
        "true",
        "false",
        "null",
    }
)

# Multi-character operators are matched before single-character ones so `>=` does not lex as `>` `=`.
_MULTI_OPS: tuple[str, ...] = (">>", ">=", "<=", "!=", "!~")
_SINGLE_OPS: frozenset[str] = frozenset({"=", "~", "<", ">", "+", "-", "*", "/"})


class Token(BaseModel):
    """A single lexed token with its source position."""

    model_config = ConfigDict(frozen=True)

    kind: TokenKind
    value: str
    position: int
    line: int
    column: int


def tokenize(source: str) -> list[Token]:
    """Lex d2ql source text into a list of tokens terminated by an EOF token."""
    return _Lexer(source).run()


class _Lexer:
    """Single-pass character scanner producing positioned tokens."""

    def __init__(self, source: str) -> None:
        """Bind the source text and reset scan state."""
        self._source = source
        self._length = len(source)
        self._index = 0
        self._line = 1
        self._column = 1
        self._tokens: list[Token] = []

    def run(self) -> list[Token]:
        """Scan the whole source and return the token list with a trailing EOF."""
        while self._index < self._length:
            char = self._source[self._index]
            if char in " \t\r\n":
                self._advance()
                continue
            if char == "/" and self._peek(1) == "/":
                self._skip_line_comment()
                continue
            if char == "@":
                self._lex_datetime()
                continue
            if char in "'\"":
                self._lex_string(char)
                continue
            if char.isdigit():
                self._lex_number()
                continue
            if char == "$":
                self._lex_variable()
                continue
            if char.isalpha() or char == "_":
                self._lex_word()
                continue
            if self._lex_punct_or_op():
                continue
            raise LexError(f"unexpected character {char!r}", position=self._index, line=self._line, column=self._column)
        self._tokens.append(
            Token(kind=TokenKind.EOF, value="", position=self._index, line=self._line, column=self._column)
        )
        return self._tokens

    def _peek(self, offset: int = 0) -> str:
        target = self._index + offset
        return self._source[target] if target < self._length else ""

    def _advance(self) -> str:
        char = self._source[self._index]
        self._index += 1
        if char == "\n":
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return char

    def _skip_line_comment(self) -> None:
        while self._index < self._length and self._source[self._index] != "\n":
            self._advance()

    def _emit(self, kind: TokenKind, value: str, start: int, line: int, column: int) -> None:
        self._tokens.append(Token(kind=kind, value=value, position=start, line=line, column=column))

    def _lex_string(self, quote: str) -> None:
        start, line, column = self._index, self._line, self._column
        self._advance()  # opening quote
        chars: list[str] = []
        while self._index < self._length:
            char = self._source[self._index]
            if char == "\\":
                self._advance()
                chars.append(self._read_escape())
                continue
            if char == quote:
                self._advance()
                self._emit(TokenKind.STRING, "".join(chars), start, line, column)
                return
            chars.append(self._advance())
        raise LexError("unterminated string literal", position=start, line=line, column=column)

    def _read_escape(self) -> str:
        if self._index >= self._length:
            raise LexError("unterminated escape sequence", position=self._index, line=self._line, column=self._column)
        char = self._advance()
        return {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "/": "/"}.get(char, char)

    def _lex_number(self) -> None:
        start, line, column = self._index, self._line, self._column
        digits: list[str] = []
        is_decimal = False
        while self._index < self._length:
            char = self._source[self._index]
            if char.isdigit():
                digits.append(self._advance())
            elif char == "." and self._peek(1).isdigit() and not is_decimal:
                is_decimal = True
                digits.append(self._advance())
            else:
                break
        kind = TokenKind.DECIMAL if is_decimal else TokenKind.INTEGER
        self._emit(kind, "".join(digits), start, line, column)

    def _lex_datetime(self) -> None:
        start, line, column = self._index, self._line, self._column
        self._advance()  # @
        chars: list[str] = []
        while self._index < self._length and (
            self._source[self._index].isdigit() or self._source[self._index] in "-:T+Z."
        ):
            chars.append(self._advance())
        if not chars:
            raise LexError("expected a date or datetime after '@'", position=start, line=line, column=column)
        self._emit(TokenKind.DATETIME, "".join(chars), start, line, column)

    def _lex_variable(self) -> None:
        start, line, column = self._index, self._line, self._column
        self._advance()  # $
        chars: list[str] = []
        while self._index < self._length and (self._source[self._index].isalnum() or self._source[self._index] == "_"):
            chars.append(self._advance())
        if not chars:
            raise LexError("expected a name after '$'", position=start, line=line, column=column)
        self._emit(TokenKind.VARIABLE, "".join(chars), start, line, column)

    def _lex_word(self) -> None:
        start, line, column = self._index, self._line, self._column
        chars: list[str] = []
        while self._index < self._length and (self._source[self._index].isalnum() or self._source[self._index] == "_"):
            chars.append(self._advance())
        text = "".join(chars)
        kind = TokenKind.KEYWORD if text in KEYWORDS else TokenKind.IDENT
        self._emit(kind, text, start, line, column)

    def _lex_punct_or_op(self) -> bool:
        start, line, column = self._index, self._line, self._column
        for op in _MULTI_OPS:
            if self._source.startswith(op, self._index):
                for _ in op:
                    self._advance()
                kind = TokenKind.SINK if op == ">>" else TokenKind.OP
                self._emit(kind, op, start, line, column)
                return True
        char = self._source[self._index]
        simple = {
            "(": TokenKind.LPAREN,
            ")": TokenKind.RPAREN,
            "[": TokenKind.LBRACKET,
            "]": TokenKind.RBRACKET,
            "{": TokenKind.LBRACE,
            "}": TokenKind.RBRACE,
            ",": TokenKind.COMMA,
            ":": TokenKind.COLON,
            ".": TokenKind.DOT,
            "|": TokenKind.PIPE,
        }
        if char in simple:
            self._advance()
            self._emit(simple[char], char, start, line, column)
            return True
        if char in _SINGLE_OPS:
            self._advance()
            self._emit(TokenKind.OP, char, start, line, column)
            return True
        return False
