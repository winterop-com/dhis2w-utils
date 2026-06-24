"""Pydantic AST for d2ql: expressions, pipeline stages, sources, sinks, and library definitions.

Every node is a frozen `BaseModel` tagged with a `kind` discriminator so the recursive
expression and stage unions validate and round-trip without a separate transform layer.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- expressions


class _Node(BaseModel):
    """Common config for every AST node."""

    model_config = ConfigDict(frozen=True)


class LiteralExpr(_Node):
    """A literal value: string, number, boolean, date/datetime, or null."""

    kind: Literal["literal"] = "literal"
    value: str | int | float | bool | None
    literal_type: Literal["string", "integer", "decimal", "boolean", "date", "datetime", "null"]


class NameExpr(_Node):
    """A bare identifier — a navigation root or a leading member name (e.g. `name`, `categoryCombo`)."""

    kind: Literal["name"] = "name"
    name: str


class VariableExpr(_Node):
    """A `$`-prefixed variable: `$this`, `$index`, a function parameter, or a define reference."""

    kind: Literal["variable"] = "variable"
    name: str


class MemberExpr(_Node):
    """Member navigation `target.name` (e.g. `categoryCombo.name`)."""

    kind: Literal["member"] = "member"
    target: Expr
    name: str


class IndexExpr(_Node):
    """Indexing `target[index]` (e.g. `dataSetElements[0]`)."""

    kind: Literal["index"] = "index"
    target: Expr
    index: Expr


class CallExpr(_Node):
    """A function or method call; `target` is None for a free function like `today()`."""

    kind: Literal["call"] = "call"
    target: Expr | None
    name: str
    args: list[Expr] = Field(default_factory=list)


class UnaryExpr(_Node):
    """A prefix unary operation (`-x`, `not x`)."""

    kind: Literal["unary"] = "unary"
    op: str
    operand: Expr


class BinaryExpr(_Node):
    """A binary operation (`a = b`, `a ~ b`, `a and b`, `a + b`, `a in b`)."""

    kind: Literal["binary"] = "binary"
    op: str
    left: Expr
    right: Expr


class ObjectField(_Node):
    """One `key: value` entry inside an object constructor / transform template."""

    name: str
    value: Expr


class ObjectExpr(_Node):
    """An object constructor `{ key: expr, ... }` — also the body of a `transform` stage."""

    kind: Literal["object"] = "object"
    fields: list[ObjectField] = Field(default_factory=list)


class ArrayExpr(_Node):
    """An array constructor `[ expr, ... ]`."""

    kind: Literal["array"] = "array"
    items: list[Expr] = Field(default_factory=list)


Expr = Annotated[
    LiteralExpr
    | NameExpr
    | VariableExpr
    | MemberExpr
    | IndexExpr
    | CallExpr
    | UnaryExpr
    | BinaryExpr
    | ObjectExpr
    | ArrayExpr,
    Field(discriminator="kind"),
]

# --------------------------------------------------------------------------- sources / stages / sinks


class NameSource(_Node):
    """A pipeline source named by identifier — a DHIS2 resource or a `define` reference.

    `inline_filter` carries an optional `[predicate]` retrieve shorthand
    (e.g. `dataElements[domainType = AGGREGATE]`).
    """

    kind: Literal["name"] = "name"
    name: str
    inline_filter: Expr | None = None


class ReadSource(_Node):
    """A pipeline source reading items from a JSON/NDJSON file: `read("path.json")`."""

    kind: Literal["read"] = "read"
    path: str


class ExprSource(_Node):
    """A pipeline source that is a scalar expression (e.g. `define Total: 1 + 2`)."""

    kind: Literal["expr"] = "expr"
    expr: Expr


class CallSource(_Node):
    """A source written as a named call with keyword arguments (e.g. `analytics(dx: "...", pe: "...")`)."""

    kind: Literal["call"] = "call"
    name: str
    args: list[ObjectField] = Field(default_factory=list)


Source = Annotated[NameSource | ReadSource | ExprSource | CallSource, Field(discriminator="kind")]


class SelectItem(_Node):
    """One projected column in a `select` stage, with an optional `as` alias."""

    expr: Expr
    alias: str | None = None


class OrderKey(_Node):
    """One sort key in an `order` stage."""

    expr: Expr
    descending: bool = False


class WhereStage(_Node):
    """Filter the stream to items where the predicate is truthy."""

    kind: Literal["where"] = "where"
    predicate: Expr


class SelectStage(_Node):
    """Project each item to the listed expressions, keyed by name or alias."""

    kind: Literal["select"] = "select"
    items: list[SelectItem]


class TransformStage(_Node):
    """Reshape each item via the template — an object literal `{ … }` or an expression yielding one."""

    kind: Literal["transform"] = "transform"
    template: Expr


class OrderStage(_Node):
    """Sort the stream by one or more keys."""

    kind: Literal["order"] = "order"
    keys: list[OrderKey]


class LimitStage(_Node):
    """Keep at most `count` items."""

    kind: Literal["limit"] = "limit"
    count: int


class SkipStage(_Node):
    """Drop the first `count` items."""

    kind: Literal["skip"] = "skip"
    count: int


class CountStage(_Node):
    """Replace the stream with a single integer: its length."""

    kind: Literal["count"] = "count"


class AggregateStage(_Node):
    """Group rows by a key expression and reduce each group with aggregate expressions.

    `group by <group> { total: sum(value), n: count() }` — each aggregation expression is
    evaluated against the group's rows, so `value` gathers that field across the group.
    """

    kind: Literal["aggregate"] = "aggregate"
    group: Expr
    aggregations: ObjectExpr


class FoldStage(_Node):
    """Collapse the whole stream into a single object (e.g. a FHIR Bundle or GeoJSON FeatureCollection).

    `fold { resourceType: "Bundle", entry: $rows }` — the template is built once with the entire
    stream in focus; `$rows` is the stream as a list, and aggregate/`select` functions see all rows.
    """

    kind: Literal["fold"] = "fold"
    template: ObjectExpr


Stage = Annotated[
    WhereStage
    | SelectStage
    | TransformStage
    | OrderStage
    | LimitStage
    | SkipStage
    | CountStage
    | AggregateStage
    | FoldStage,
    Field(discriminator="kind"),
]


class StdoutSink(_Node):
    """Sink rendering the result to stdout; `format` (from `as`) picks json/ndjson/csv, else the default."""

    kind: Literal["stdout"] = "stdout"
    format: Literal["json", "ndjson", "csv"] | None = None


class FileSink(_Node):
    """Sink writing the result to a file; format inferred from extension when None."""

    kind: Literal["file"] = "file"
    path: str
    format: Literal["json", "ndjson", "csv"] | None = None


Sink = Annotated[StdoutSink | FileSink, Field(discriminator="kind")]


class Pipeline(_Node):
    """A source feeding a chain of stages, optionally ending in a sink."""

    source: Source
    stages: list[Stage] = Field(default_factory=list)
    sink: Sink | None = None


# --------------------------------------------------------------------------- library


class Define(_Node):
    """A named query definition: `define NAME: <pipeline>`."""

    kind: Literal["define"] = "define"
    name: str
    body: Pipeline


class DefineFunction(_Node):
    """A named function definition: `define function NAME(params): <expr>`."""

    kind: Literal["define_function"] = "define_function"
    name: str
    params: list[str] = Field(default_factory=list)
    body: Expr


Definition = Annotated[Define | DefineFunction, Field(discriminator="kind")]


class Library(_Node):
    """A whole d2ql program: zero or more definitions plus an optional terminal pipeline."""

    definitions: list[Definition] = Field(default_factory=list)
    terminal: Pipeline | None = None


for _model in (
    MemberExpr,
    IndexExpr,
    CallExpr,
    UnaryExpr,
    BinaryExpr,
    ObjectField,
    ObjectExpr,
    ArrayExpr,
    NameSource,
    ExprSource,
    CallSource,
    SelectItem,
    OrderKey,
    WhereStage,
    SelectStage,
    TransformStage,
    OrderStage,
    AggregateStage,
    FoldStage,
    Pipeline,
    Define,
    DefineFunction,
    Library,
):
    _model.model_rebuild()
