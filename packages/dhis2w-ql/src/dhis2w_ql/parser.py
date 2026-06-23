"""Recursive-descent parser for d2ql: token stream to Pydantic AST.

Grammar (informal):

    library      := definition* terminal?
    definition   := "define" ( "function" IDENT "(" params ")" ":" expr
                             |  IDENT ":" pipeline )
    pipeline     := source ("|" stage)* ( ">>" sink )?
    source       := "read" "(" STRING ")"
                 |  IDENT ( "[" expr "]" )?        # name source, optional inline filter
                 |  expr                            # scalar expression source
    stage        := "where" expr
                 |  "select" selectItem ("," selectItem)*
                 |  "transform" object
                 |  "order" orderKey ("," orderKey)*
                 |  "limit" INTEGER | "skip" INTEGER | "count"
    sink         := STRING | "stdout"

The pipeline `|` is the stage separator; FHIRPath collection union is the `union()` function,
so `|` is never ambiguous between the two layers.
"""

from __future__ import annotations

from typing import Literal

from dhis2w_ql.ast import (
    AggregateStage,
    ArrayExpr,
    BinaryExpr,
    CallExpr,
    CallSource,
    Define,
    DefineFunction,
    Definition,
    Expr,
    ExprSource,
    FileSink,
    IndexExpr,
    Library,
    LimitStage,
    LiteralExpr,
    MemberExpr,
    NameExpr,
    NameSource,
    ObjectExpr,
    ObjectField,
    OrderKey,
    OrderStage,
    Pipeline,
    ReadSource,
    SelectItem,
    SelectStage,
    Sink,
    SkipStage,
    Source,
    Stage,
    StdoutSink,
    TransformStage,
    UnaryExpr,
    VariableExpr,
    WhereStage,
)
from dhis2w_ql.errors import ParseError
from dhis2w_ql.tokenizer import Token, TokenKind, tokenize

_EQUALITY_OPS = frozenset({"=", "!=", "~", "!~"})
_COMPARISON_OPS = frozenset({"<", "<=", ">", ">="})
_FORMAT_BY_EXT: dict[str, Literal["json", "ndjson", "csv"]] = {"json": "json", "ndjson": "ndjson", "csv": "csv"}


def parse(source: str) -> Library:
    """Parse d2ql source text into a `Library` AST."""
    return _Parser(tokenize(source)).parse_library()


def parse_pipeline(source: str) -> Pipeline:
    """Parse a single pipeline (no definitions) into a `Pipeline` AST."""
    library = parse(source)
    if library.definitions or library.terminal is None:
        raise ParseError("expected a single pipeline", position=0, line=1, column=1)
    return library.terminal


def parse_expression(source: str) -> Expr:
    """Parse a single bare expression (the FHIRPath-compatible expression surface)."""
    parser = _Parser(tokenize(source))
    expr = parser.parse_expr()
    parser.expect_eof()
    return expr


class _Parser:
    """Hand-written recursive-descent parser over a fixed token list."""

    def __init__(self, tokens: list[Token]) -> None:
        """Bind the token stream and reset the cursor."""
        self._tokens = tokens
        self._index = 0

    # ------------------------------------------------------------------ cursor helpers

    def _peek(self, offset: int = 0) -> Token:
        target = self._index + offset
        return self._tokens[target] if target < len(self._tokens) else self._tokens[-1]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        if token.kind is not TokenKind.EOF:
            self._index += 1
        return token

    def _at(self, kind: TokenKind) -> bool:
        return self._peek().kind is kind

    def _at_keyword(self, *words: str) -> bool:
        token = self._peek()
        return token.kind is TokenKind.KEYWORD and token.value in words

    def _at_op(self, *ops: str) -> bool:
        token = self._peek()
        return token.kind is TokenKind.OP and token.value in ops

    def _error(self, message: str) -> ParseError:
        token = self._peek()
        return ParseError(message, position=token.position, line=token.line, column=token.column)

    def _expect(self, kind: TokenKind, label: str) -> Token:
        if not self._at(kind):
            raise self._error(f"expected {label}, found {self._peek().value or self._peek().kind.value!r}")
        return self._advance()

    def _expect_keyword(self, word: str) -> None:
        if not self._at_keyword(word):
            raise self._error(f"expected {word!r}")
        self._advance()

    def expect_eof(self) -> None:
        """Raise unless the cursor is at the end of the token stream."""
        if not self._at(TokenKind.EOF):
            raise self._error(f"unexpected trailing input {self._peek().value!r}")

    # ------------------------------------------------------------------ library / definitions

    def parse_library(self) -> Library:
        """Parse a sequence of definitions followed by an optional terminal pipeline."""
        definitions: list[Definition] = []
        while self._at_keyword("define"):
            definitions.append(self._parse_definition())
        terminal: Pipeline | None = None
        if not self._at(TokenKind.EOF):
            terminal = self._parse_pipeline()
        self.expect_eof()
        return Library(definitions=definitions, terminal=terminal)

    def _parse_definition(self) -> Definition:
        self._advance()  # define
        if self._at_keyword("function"):
            return self._parse_define_function()
        name = self._expect(TokenKind.IDENT, "definition name").value
        self._expect(TokenKind.COLON, "':'")
        return Define(name=name, body=self._parse_pipeline())

    def _parse_define_function(self) -> DefineFunction:
        self._advance()  # function
        name = self._expect(TokenKind.IDENT, "function name").value
        self._expect(TokenKind.LPAREN, "'('")
        params: list[str] = []
        if not self._at(TokenKind.RPAREN):
            params.append(self._expect(TokenKind.IDENT, "parameter name").value)
            while self._at(TokenKind.COMMA):
                self._advance()
                params.append(self._expect(TokenKind.IDENT, "parameter name").value)
        self._expect(TokenKind.RPAREN, "')'")
        self._expect(TokenKind.COLON, "':'")
        return DefineFunction(name=name, params=params, body=self.parse_expr())

    # ------------------------------------------------------------------ pipeline

    def _parse_pipeline(self) -> Pipeline:
        source = self._parse_source()
        stages: list[Stage] = []
        while self._at(TokenKind.PIPE):
            self._advance()
            stages.append(self._parse_stage())
        sink: Sink | None = None
        if self._at(TokenKind.SINK):
            self._advance()
            sink = self._parse_sink()
        return Pipeline(source=source, stages=stages, sink=sink)

    def _parse_source(self) -> Source:
        if self._at_keyword("read"):
            self._advance()
            self._expect(TokenKind.LPAREN, "'('")
            path = self._expect(TokenKind.STRING, "a quoted file path").value
            self._expect(TokenKind.RPAREN, "')'")
            return ReadSource(path=path)
        if self._at(TokenKind.IDENT):
            following = self._peek(1).kind
            if following is TokenKind.LPAREN:
                return self._parse_call_source()
            if following is TokenKind.LBRACKET:
                name = self._advance().value
                self._advance()  # [
                predicate = self.parse_expr()
                self._expect(TokenKind.RBRACKET, "']'")
                return NameSource(name=name, inline_filter=predicate)
            if following in (TokenKind.PIPE, TokenKind.SINK, TokenKind.EOF) or self._peek(1).value == "define":
                return NameSource(name=self._advance().value)
        return ExprSource(expr=self.parse_expr())

    def _parse_call_source(self) -> CallSource:
        name = self._advance().value
        self._expect(TokenKind.LPAREN, "'('")
        args: list[ObjectField] = []
        if not self._at(TokenKind.RPAREN):
            args.append(self._parse_object_field())
            while self._at(TokenKind.COMMA):
                self._advance()
                if self._at(TokenKind.RPAREN):
                    break
                args.append(self._parse_object_field())
        self._expect(TokenKind.RPAREN, "')'")
        return CallSource(name=name, args=args)

    def _parse_stage(self) -> Stage:
        if self._at_keyword("where"):
            self._advance()
            return WhereStage(predicate=self.parse_expr())
        if self._at_keyword("select"):
            self._advance()
            return SelectStage(items=self._parse_select_items())
        if self._at_keyword("transform"):
            self._advance()
            return TransformStage(template=self._parse_object())
        if self._at_keyword("order"):
            self._advance()
            return OrderStage(keys=self._parse_order_keys())
        if self._at_keyword("limit"):
            self._advance()
            return LimitStage(count=self._parse_integer("a row count after 'limit'"))
        if self._at_keyword("skip"):
            self._advance()
            return SkipStage(count=self._parse_integer("a row count after 'skip'"))
        if self._at_keyword("count"):
            self._advance()
            from dhis2w_ql.ast import CountStage  # noqa: PLC0415 — local import avoids a long top import line

            return CountStage()
        if self._at_keyword("aggregate"):
            self._advance()
            self._expect_keyword("by")
            group = self.parse_expr()
            return AggregateStage(group=group, aggregations=self._parse_object())
        raise self._error("expected a stage keyword (where/select/transform/order/limit/skip/count/aggregate)")

    def _parse_select_items(self) -> list[SelectItem]:
        items = [self._parse_select_item()]
        while self._at(TokenKind.COMMA):
            self._advance()
            items.append(self._parse_select_item())
        return items

    def _parse_select_item(self) -> SelectItem:
        expr = self.parse_expr()
        alias: str | None = None
        if self._at_keyword("as"):
            self._advance()
            alias = self._expect(TokenKind.IDENT, "an alias after 'as'").value
        return SelectItem(expr=expr, alias=alias)

    def _parse_order_keys(self) -> list[OrderKey]:
        keys = [self._parse_order_key()]
        while self._at(TokenKind.COMMA):
            self._advance()
            keys.append(self._parse_order_key())
        return keys

    def _parse_order_key(self) -> OrderKey:
        expr = self.parse_expr()
        descending = False
        if self._at_keyword("asc"):
            self._advance()
        elif self._at_keyword("desc"):
            self._advance()
            descending = True
        return OrderKey(expr=expr, descending=descending)

    def _parse_integer(self, label: str) -> int:
        return int(self._expect(TokenKind.INTEGER, label).value)

    def _parse_sink(self) -> Sink:
        if self._at(TokenKind.STRING):
            path = self._advance().value
            extension = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            return FileSink(path=path, format=_FORMAT_BY_EXT.get(extension))
        if self._at(TokenKind.IDENT) and self._peek().value == "stdout":
            self._advance()
            return StdoutSink()
        raise self._error("expected a quoted file path or 'stdout' after '>>'")

    # ------------------------------------------------------------------ expressions

    def parse_expr(self) -> Expr:
        """Parse a full expression honouring d2ql operator precedence."""
        return self._parse_implies()

    def _parse_implies(self) -> Expr:
        left = self._parse_or()
        while self._at_keyword("implies"):
            self._advance()
            left = BinaryExpr(op="implies", left=left, right=self._parse_or())
        return left

    def _parse_or(self) -> Expr:
        left = self._parse_and()
        while self._at_keyword("or", "xor"):
            op = self._advance().value
            left = BinaryExpr(op=op, left=left, right=self._parse_and())
        return left

    def _parse_and(self) -> Expr:
        left = self._parse_equality()
        while self._at_keyword("and"):
            self._advance()
            left = BinaryExpr(op="and", left=left, right=self._parse_equality())
        return left

    def _parse_equality(self) -> Expr:
        left = self._parse_relational()
        while self._at_op(*_EQUALITY_OPS):
            op = self._advance().value
            left = BinaryExpr(op=op, left=left, right=self._parse_relational())
        return left

    def _parse_relational(self) -> Expr:
        left = self._parse_additive()
        while True:
            if self._at_op(*_COMPARISON_OPS) or self._at_keyword("in", "contains", "is"):
                op = self._advance().value
                left = BinaryExpr(op=op, left=left, right=self._parse_additive())
            else:
                return left

    def _parse_additive(self) -> Expr:
        left = self._parse_multiplicative()
        while self._at_op("+", "-"):
            op = self._advance().value
            left = BinaryExpr(op=op, left=left, right=self._parse_multiplicative())
        return left

    def _parse_multiplicative(self) -> Expr:
        left = self._parse_unary()
        while self._at_op("*", "/") or self._at_keyword("div", "mod"):
            op = self._advance().value
            left = BinaryExpr(op=op, left=left, right=self._parse_unary())
        return left

    def _parse_unary(self) -> Expr:
        if self._at_op("-", "+"):
            op = self._advance().value
            return UnaryExpr(op=op, operand=self._parse_unary())
        return self._parse_postfix()

    def _parse_postfix(self) -> Expr:
        expr = self._parse_primary()
        while True:
            if self._at(TokenKind.DOT):
                self._advance()
                name = self._member_name()
                if self._at(TokenKind.LPAREN):
                    expr = CallExpr(target=expr, name=name, args=self._parse_call_args())
                else:
                    expr = MemberExpr(target=expr, name=name)
            elif self._at(TokenKind.LBRACKET):
                self._advance()
                index = self.parse_expr()
                self._expect(TokenKind.RBRACKET, "']'")
                expr = IndexExpr(target=expr, index=index)
            else:
                return expr

    def _member_name(self) -> str:
        token = self._peek()
        if token.kind in (TokenKind.IDENT, TokenKind.KEYWORD):
            return self._advance().value
        raise self._error("expected a member or method name after '.'")

    def _parse_call_args(self) -> list[Expr]:
        self._expect(TokenKind.LPAREN, "'('")
        args: list[Expr] = []
        if not self._at(TokenKind.RPAREN):
            args.append(self.parse_expr())
            while self._at(TokenKind.COMMA):
                self._advance()
                args.append(self.parse_expr())
        self._expect(TokenKind.RPAREN, "')'")
        return args

    def _parse_primary(self) -> Expr:
        token = self._peek()
        if token.kind is TokenKind.LPAREN:
            self._advance()
            expr = self.parse_expr()
            self._expect(TokenKind.RPAREN, "')'")
            return expr
        if token.kind is TokenKind.LBRACE:
            return self._parse_object()
        if token.kind is TokenKind.LBRACKET:
            return self._parse_array()
        if token.kind is TokenKind.STRING:
            return LiteralExpr(value=self._advance().value, literal_type="string")
        if token.kind is TokenKind.INTEGER:
            return LiteralExpr(value=int(self._advance().value), literal_type="integer")
        if token.kind is TokenKind.DECIMAL:
            return LiteralExpr(value=float(self._advance().value), literal_type="decimal")
        if token.kind is TokenKind.DATETIME:
            text = self._advance().value
            return LiteralExpr(value=text, literal_type="datetime" if "T" in text else "date")
        if token.kind is TokenKind.VARIABLE:
            return VariableExpr(name=self._advance().value)
        if token.kind is TokenKind.KEYWORD and token.value in ("true", "false"):
            return LiteralExpr(value=self._advance().value == "true", literal_type="boolean")
        if token.kind is TokenKind.KEYWORD and token.value == "null":
            self._advance()
            return LiteralExpr(value=None, literal_type="null")
        if token.kind is TokenKind.KEYWORD and self._peek(1).kind is TokenKind.LPAREN:
            # A reserved word that doubles as a function (e.g. `count()`, `exists()`) in expression position.
            name = self._advance().value
            return CallExpr(target=None, name=name, args=self._parse_call_args())
        if token.kind is TokenKind.IDENT:
            name = self._advance().value
            if self._at(TokenKind.LPAREN):
                return CallExpr(target=None, name=name, args=self._parse_call_args())
            return NameExpr(name=name)
        raise self._error(f"unexpected token {token.value or token.kind.value!r} in expression")

    def _parse_object(self) -> ObjectExpr:
        self._expect(TokenKind.LBRACE, "'{'")
        fields: list[ObjectField] = []
        if not self._at(TokenKind.RBRACE):
            fields.append(self._parse_object_field())
            while self._at(TokenKind.COMMA):
                self._advance()
                if self._at(TokenKind.RBRACE):
                    break
                fields.append(self._parse_object_field())
        self._expect(TokenKind.RBRACE, "'}'")
        return ObjectExpr(fields=fields)

    def _parse_object_field(self) -> ObjectField:
        token = self._peek()
        if token.kind in (TokenKind.IDENT, TokenKind.KEYWORD, TokenKind.STRING):
            name = self._advance().value
        else:
            raise self._error("expected an object key")
        self._expect(TokenKind.COLON, "':'")
        return ObjectField(name=name, value=self.parse_expr())

    def _parse_array(self) -> ArrayExpr:
        self._expect(TokenKind.LBRACKET, "'['")
        items: list[Expr] = []
        if not self._at(TokenKind.RBRACKET):
            items.append(self.parse_expr())
            while self._at(TokenKind.COMMA):
                self._advance()
                if self._at(TokenKind.RBRACKET):
                    break
                items.append(self.parse_expr())
        self._expect(TokenKind.RBRACKET, "']'")
        return ArrayExpr(items=items)
