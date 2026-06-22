"""A catalog of illustrative d2ql / d2path sample programs.

This is the single source of truth for examples: the CLI help, the docs, the test corpus, and the
web playground all read `SAMPLES`. Every entry is parse-valid (a test asserts this), so the catalog
doubles as a conformance set. Sample source is version-agnostic d2ql/d2path text.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Sample(BaseModel):
    """One illustrative d2ql pipeline or d2path expression with metadata for display and testing."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    category: str
    language: Literal["d2ql", "d2path"]
    source: str
    description: str
    needs_profile: bool = True


def _q(id: str, title: str, category: str, source: str, description: str) -> Sample:
    """Build a d2ql sample (runs against a live profile)."""
    return Sample(id=id, title=title, category=category, language="d2ql", source=source, description=description)


def _p(id: str, title: str, source: str, description: str) -> Sample:
    """Build a d2path sample (evaluates over local JSON, no profile needed)."""
    return Sample(
        id=id,
        title=title,
        category="d2path",
        language="d2path",
        source=source,
        description=description,
        needs_profile=False,
    )


SAMPLES: list[Sample] = [
    # ---------------------------------------------------------------- basics
    _q("basics-all", "List a resource", "basics", "dataElements | limit 25", "Fetch the first rows of a resource."),
    _q("basics-select", "Select columns", "basics", "dataElements | select id, name", "Project id and name only."),
    _q("basics-count", "Count rows", "basics", "dataElements | count", "Return the number of matching rows."),
    _q("basics-page", "Page through rows", "basics", "dataElements | skip 50 | limit 25", "Offset then take."),
    _q(
        "basics-rename",
        "Rename a column",
        "basics",
        "dataElements | select id, name as label | limit 10",
        "Alias with `as`.",
    ),
    # ---------------------------------------------------------------- filtering
    _q(
        "filter-eq",
        "Filter by equality",
        "filtering",
        'dataElements | where domainType = "AGGREGATE"',
        "Pushed down to a DHIS2 `eq` filter.",
    ),
    _q(
        "filter-like",
        "Case-insensitive match",
        "filtering",
        'dataElements | where name ~ "ANC"',
        "`~` pushes down to `ilike`.",
    ),
    _q(
        "filter-and",
        "Combine with and",
        "filtering",
        'dataElements | where domainType = "AGGREGATE" and valueType = "NUMBER"',
        "Both clauses pushed down (AND).",
    ),
    _q(
        "filter-or",
        "Combine with or",
        "filtering",
        'dataElements | where name ~ "ANC" or name ~ "BCG"',
        "OR pushed down via rootJunction.",
    ),
    _q(
        "filter-in",
        "Membership",
        "filtering",
        'dataElements | where valueType in ["NUMBER", "INTEGER"]',
        "Pushed down to a DHIS2 `in` filter.",
    ),
    _q("filter-ne", "Not equal", "filtering", "indicators | where annualized != true", "Pushed down to `ne`."),
    _q(
        "filter-nested",
        "Filter on a nested field",
        "filtering",
        'dataElements | where categoryCombo.name = "default"',
        "Dotted path pushes down to `categoryCombo.name:eq:default`.",
    ),
    _q(
        "filter-compare",
        "Numeric comparison",
        "filtering",
        "organisationUnits | where level >= 3",
        "Pushed down to `ge`.",
    ),
    _q(
        "filter-inline",
        "Inline retrieve filter",
        "filtering",
        'dataElements[domainType = "AGGREGATE"] | limit 5',
        "`[predicate]` is a leading where.",
    ),
    _q(
        "filter-local",
        "Local-only predicate",
        "filtering",
        'dataElements | where name.substring(0, 3) = "ANC"',
        "Function predicate stays local (not pushed down).",
    ),
    # ---------------------------------------------------------------- projection
    _q(
        "project-nested",
        "Project a nested value",
        "projection",
        "dataElements | select id, name, categoryCombo.name as combo | limit 10",
        "Read a nested ref field.",
    ),
    _q(
        "project-computed",
        "Computed column",
        "projection",
        "dataElements | select id, name, name.upper() as upper | limit 10",
        "Call a d2path function in select.",
    ),
    _q(
        "project-prefix",
        "Substring column",
        "projection",
        "dataElements | select name, name.substring(0, 3) as prefix | limit 10",
        "String slicing in projection.",
    ),
    # ---------------------------------------------------------------- ordering
    _q(
        "order-asc",
        "Order ascending",
        "ordering",
        "dataElements | order name asc | limit 10",
        "Pushed down to `order=name:asc`.",
    ),
    _q(
        "order-multi",
        "Order by multiple keys",
        "ordering",
        "dataElements | order domainType asc, name desc | limit 10",
        "Multi-key ordering, pushed down.",
    ),
    # ---------------------------------------------------------------- transform
    _q(
        "transform-reshape",
        "Reshape rows",
        "transform",
        "dataElements | transform { code: id, label: name } | limit 10",
        "Build a new object per row.",
    ),
    _q(
        "transform-nested",
        "Nested object",
        "transform",
        "dataElements | transform { id: id, meta: { type: domainType, value: valueType } } | limit 10",
        "Nested object construction.",
    ),
    _q(
        "transform-array",
        "Array field",
        "transform",
        "dataElements | transform { id: id, tags: [domainType, valueType] } | limit 10",
        "Array construction.",
    ),
    _q(
        "transform-bool",
        "Computed boolean",
        "transform",
        'dataElements | transform { id: id, aggregate: domainType = "AGGREGATE" } | limit 10',
        "Boolean expression in a field.",
    ),
    # ---------------------------------------------------------------- fhir emit (generic transform; no FHIR dependency)
    _q(
        "fhir-observation",
        "Emit FHIR Observation shape",
        "fhir",
        'dataElements | where domainType = "AGGREGATE" | transform { resourceType: "Observation", status: "final", code: { coding: [ { system: "dhis2", code: id, display: name } ] } } | limit 10',  # noqa: E501
        "Transform DHIS2 metadata into a FHIR-shaped object (transform is generic).",
    ),
    _q(
        "fhir-concept",
        "Emit a code-system concept",
        "fhir",
        'dataElements | transform { system: "dhis2-dataElements", code: id, display: name } | limit 10',
        "Map data elements to terminology concepts.",
    ),
    # ---------------------------------------------------------------- definitions
    _q(
        "def-scalar",
        "Scalar definition",
        "definitions",
        "define MinLevel: 3\norganisationUnits | where level >= $MinLevel",
        "Reference a scalar `define` with `$`.",
    ),
    _q(
        "def-function",
        "Function definition",
        "definitions",
        'define function isAnc(de): $de.name ~ "ANC"\ndataElements | where isAnc($this) | select id, name',
        "A reusable predicate function.",
    ),
    _q(
        "def-named-query",
        "Named query reuse",
        "definitions",
        'define Aggregates: dataElements | where domainType = "AGGREGATE"\nAggregates | order name asc | limit 10',
        "Reference a named query as a source.",
    ),
    _q(
        "def-compose",
        "Compose definitions",
        "definitions",
        'define Aggregates: dataElements | where domainType = "AGGREGATE"\ndefine function big(n): $n > 0\nAggregates | select id, name | limit 5',  # noqa: E501
        "Several definitions in one program.",
    ),
    # ---------------------------------------------------------------- sinks
    _q(
        "sink-csv",
        "Write CSV",
        "sinks",
        'dataElements | select id, name >> "data-elements.csv"',
        "Write rows to a CSV file.",
    ),
    _q(
        "sink-json",
        "Write JSON",
        "sinks",
        'dataElements | where domainType = "AGGREGATE" | transform { code: id, label: name } >> "aggregates.json"',
        "Write transformed rows to JSON.",
    ),
    _q(
        "sink-ndjson",
        "Write NDJSON",
        "sinks",
        'dataElements | select id, name >> "elements.ndjson"',
        "Write newline-delimited JSON.",
    ),
    # ---------------------------------------------------------------- d2path
    _p(
        "path-official-family",
        "Official family name",
        'name.where(use = "official").family',
        "Filter a repeating element, then navigate.",
    ),
    _p("path-first-given", "First given name", "name.given.first()", "Flatten and take the first."),
    _p("path-count-given", "Count given names", "name.given.count()", "Aggregate a collection."),
    _p("path-gender", "Equality test", 'gender = "male"', "A boolean predicate."),
    _p("path-phone", "Filter by system", 'telecom.where(system = "phone").value', "where + navigation."),
    _p("path-arith", "Arithmetic", "(1 + 2) * 3", "Operator precedence."),
    _p(
        "path-identifier",
        "National identifier",
        'identifier.where(system = "national").value.first()',
        "Chained filtering.",
    ),
    _p("path-upper", "Uppercase family", "name.family.upper()", "String function."),
    _p("path-loinc", "LOINC code", 'code.coding.where(system = "http://loinc.org").code', "Navigate FHIR coding."),
    _p("path-and", "Compound predicate", 'active = true and gender = "female"', "Boolean logic."),
    _p("path-join", "Join given names", 'name.given.join(" ")', "Collection to string."),
    _p("path-in", "Status membership", 'status in ["active", "completed"]', "Membership operator."),
    _p("path-exists", "Existence check", 'name.where(use = "official").exists()', "Does any match exist?"),
    _p("path-iif", "Conditional value", 'iif(gender = "male", "M", "F")', "Inline conditional."),
]


def samples_by_category() -> dict[str, list[Sample]]:
    """Group the catalog by category, preserving definition order within each group."""
    grouped: dict[str, list[Sample]] = {}
    for sample in SAMPLES:
        grouped.setdefault(sample.category, []).append(sample)
    return grouped
