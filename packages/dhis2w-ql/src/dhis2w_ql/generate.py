"""Combinatorial generator for large d2ql / d2path example corpora.

The curated `SAMPLES` catalog is the showcase set; this generator produces the bulk corpus (many
thousands of programs) used to populate the web playground and to stress-test the parser/engine
against live instances. It expands a `SchemaSpec` (resource -> fields, with value pools) into
parse-valid programs. Feed it a schema scraped from a live DHIS2 instance to get programs that are
valid against that exact version; the built-in `DEFAULT_SCHEMA` lets it run offline.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from itertools import combinations
from typing import Literal

from pydantic import BaseModel, ConfigDict


class FieldSpec(BaseModel):
    """A field on a resource, with a small pool of example values and a coarse kind."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: Literal["text", "enum", "number", "boolean"] = "text"
    values: list[str] = []


class ResourceSpec(BaseModel):
    """A DHIS2 resource and the fields the generator may build programs from."""

    model_config = ConfigDict(frozen=True)

    name: str
    fields: list[FieldSpec]


class SchemaSpec(BaseModel):
    """A set of resources the generator expands into example programs."""

    model_config = ConfigDict(frozen=True)

    resources: list[ResourceSpec]


class GeneratedExample(BaseModel):
    """One generated d2ql pipeline or d2path expression."""

    model_config = ConfigDict(frozen=True)

    id: str
    category: str
    language: Literal["d2ql", "d2path"]
    source: str


_TEXT_NAMES = ["ANC", "BCG", "Malaria", "TB", "Measles"]


def _f(name: str, kind: Literal["text", "enum", "number", "boolean"] = "text", values: Iterable[str] = ()) -> FieldSpec:
    return FieldSpec(name=name, kind=kind, values=list(values))


DEFAULT_SCHEMA = SchemaSpec(
    resources=[
        ResourceSpec(
            name="dataElements",
            fields=[
                _f("name", "text", _TEXT_NAMES),
                _f("shortName", "text", _TEXT_NAMES),
                _f("code", "text", ["DE_ANC", "DE_BCG"]),
                _f("domainType", "enum", ["AGGREGATE", "TRACKER"]),
                _f("valueType", "enum", ["NUMBER", "INTEGER", "TEXT", "BOOLEAN"]),
                _f("aggregationType", "enum", ["SUM", "AVERAGE", "COUNT"]),
                _f("categoryCombo.name", "text", ["default"]),
            ],
        ),
        ResourceSpec(
            name="indicators",
            fields=[
                _f("name", "text", _TEXT_NAMES),
                _f("shortName", "text", _TEXT_NAMES),
                _f("code", "text", ["IND_ANC"]),
                _f("annualized", "boolean", ["true", "false"]),
                _f("indicatorType.name", "text", ["Percentage"]),
            ],
        ),
        ResourceSpec(
            name="organisationUnits",
            fields=[
                _f("name", "text", ["Sierra Leone", "Bo", "Bombali"]),
                _f("code", "text", ["OU_001"]),
                _f("level", "number", ["1", "2", "3", "4"]),
                _f("path", "text", ["/ImspTQPwCqd"]),
                _f("parent.name", "text", ["Bo", "Bombali"]),
                _f("geometry.type", "enum", ["Point", "Polygon", "MultiPolygon"]),
            ],
        ),
        ResourceSpec(
            name="dataSets",
            fields=[
                _f("name", "text", ["ANC", "Reporting"]),
                _f("code", "text", ["DS_ANC"]),
                _f("periodType", "enum", ["Monthly", "Weekly", "Daily"]),
            ],
        ),
        ResourceSpec(
            name="programs",
            fields=[
                _f("name", "text", ["Child", "Maternal", "TB"]),
                _f("shortName", "text", ["Child"]),
                _f("programType", "enum", ["WITH_REGISTRATION", "WITHOUT_REGISTRATION"]),
            ],
        ),
        ResourceSpec(
            name="categoryOptions",
            fields=[_f("name", "text", ["Male", "Female", "<1y"]), _f("code", "text", ["CO_M"])],
        ),
        ResourceSpec(
            name="optionSets",
            fields=[_f("name", "text", ["Yes/No", "Severity"]), _f("valueType", "enum", ["TEXT", "INTEGER"])],
        ),
        ResourceSpec(
            name="trackedEntityAttributes",
            fields=[_f("name", "text", ["First name", "Last name"]), _f("valueType", "enum", ["TEXT", "DATE"])],
        ),
        ResourceSpec(
            name="validationRules",
            fields=[_f("name", "text", ["ANC check"]), _f("importance", "enum", ["HIGH", "MEDIUM", "LOW"])],
        ),
        ResourceSpec(
            name="dataElementGroups",
            fields=[_f("name", "text", ["ANC", "EPI"]), _f("code", "text", ["DEG_ANC"])],
        ),
    ]
)

_LIMITS = (10, 25, 50)


def generate(schema: SchemaSpec = DEFAULT_SCHEMA) -> list[GeneratedExample]:
    """Expand a schema into a large list of parse-valid d2ql/d2path example programs."""
    examples: list[GeneratedExample] = []
    counter = _Counter()
    for resource in schema.resources:
        _gen_basics(resource, examples, counter)
        _gen_filters(resource, examples, counter)
        _gen_compound(resource, examples, counter)
        _gen_select(resource, examples, counter)
        _gen_order(resource, examples, counter)
        _gen_transform(resource, examples, counter)
        _gen_path(resource, examples, counter)
    return examples


class _Counter:
    def __init__(self) -> None:
        self._n = 0

    def next(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n:05d}"


def _add(
    out: list[GeneratedExample], counter: _Counter, category: str, language: Literal["d2ql", "d2path"], source: str
) -> None:
    out.append(GeneratedExample(id=counter.next(category), category=category, language=language, source=source))


def _gen_basics(resource: ResourceSpec, out: list[GeneratedExample], counter: _Counter) -> None:
    name = resource.name
    for limit in _LIMITS:
        _add(out, counter, "basics", "d2ql", f"{name} | limit {limit}")
    _add(out, counter, "basics", "d2ql", f"{name} | count")
    _add(out, counter, "basics", "d2ql", f"{name} | skip 25 | limit 25")


def _gen_filters(resource: ResourceSpec, out: list[GeneratedExample], counter: _Counter) -> None:
    for field in resource.fields:
        for value in field.values:
            literal = _literal(field, value)
            for op in _ops_for(field):
                _add(
                    out, counter, "filtering", "d2ql", f"{resource.name} | where {field.name} {op} {literal} | limit 10"
                )
        if field.kind in ("enum", "text") and len(field.values) >= 2:
            members = ", ".join(_literal(field, value) for value in field.values[:3])
            _add(out, counter, "filtering", "d2ql", f"{resource.name} | where {field.name} in [{members}] | limit 10")


def _gen_compound(resource: ResourceSpec, out: list[GeneratedExample], counter: _Counter) -> None:
    usable = [field for field in resource.fields if field.values]
    for left, right in combinations(usable, 2):
        left_clause = f"{left.name} {_ops_for(left)[0]} {_literal(left, left.values[0])}"
        right_clause = f"{right.name} {_ops_for(right)[0]} {_literal(right, right.values[0])}"
        _add(out, counter, "filtering", "d2ql", f"{resource.name} | where {left_clause} and {right_clause} | limit 10")
        _add(out, counter, "filtering", "d2ql", f"{resource.name} | where {left_clause} or {right_clause} | limit 10")


def _gen_select(resource: ResourceSpec, out: list[GeneratedExample], counter: _Counter) -> None:
    names = ["id", "name", *[field.name for field in resource.fields if "." not in field.name]]
    for field in resource.fields:
        _add(out, counter, "projection", "d2ql", f"{resource.name} | select id, {field.name} | limit 10")
    for left, right in combinations(names[:5], 2):
        _add(out, counter, "projection", "d2ql", f"{resource.name} | select {left}, {right} as alias | limit 10")


def _gen_order(resource: ResourceSpec, out: list[GeneratedExample], counter: _Counter) -> None:
    for field in resource.fields:
        if "." in field.name:
            continue
        _add(out, counter, "ordering", "d2ql", f"{resource.name} | order {field.name} asc | limit 10")
        _add(out, counter, "ordering", "d2ql", f"{resource.name} | order {field.name} desc | limit 10")


def _gen_transform(resource: ResourceSpec, out: list[GeneratedExample], counter: _Counter) -> None:
    _add(out, counter, "transform", "d2ql", f"{resource.name} | transform {{ code: id, label: name }} | limit 10")
    for field in resource.fields:
        safe = field.name.replace(".", "_")
        _add(
            out,
            counter,
            "transform",
            "d2ql",
            f"{resource.name} | transform {{ id: id, {safe}: {field.name} }} | limit 10",
        )


def _gen_path(resource: ResourceSpec, out: list[GeneratedExample], counter: _Counter) -> None:
    for field in resource.fields:
        if field.kind == "text":
            _add(out, counter, "d2path", "d2path", f"{field.name}.upper()")
            for value in field.values[:1]:
                _add(out, counter, "d2path", "d2path", f'{field.name} ~ "{value}"')
        elif field.kind == "number":
            _add(out, counter, "d2path", "d2path", f"{field.name} >= {field.values[0] if field.values else 1}")


def _ops_for(field: FieldSpec) -> Sequence[str]:
    if field.kind == "number":
        return (">=", "<=", ">", "<", "=")
    if field.kind == "boolean":
        return ("=", "!=")
    if field.kind == "enum":
        return ("=", "!=")
    return ("=", "~", "!=")


def _literal(field: FieldSpec, value: str) -> str:
    if field.kind == "number":
        return value
    if field.kind == "boolean":
        return value
    return f'"{value}"'
