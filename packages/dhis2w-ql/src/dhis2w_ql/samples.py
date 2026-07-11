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


def _r(id: str, title: str, category: str, source: str, description: str) -> Sample:
    """Build a d2ql sample that reads a local file (`read(...)`), so it needs no profile."""
    return Sample(
        id=id,
        title=title,
        category=category,
        language="d2ql",
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
    # ---------------------------------------------------------------- organisation units
    _q(
        "ou-by-level",
        "Org units at a level",
        "orgunits",
        "organisationUnits | where level = 2 | select id, name, level | order name asc | limit 20",
        "Filter the hierarchy by level (pushed down).",
    ),
    _q(
        "ou-parent",
        "Parent name",
        "orgunits",
        "organisationUnits | where level = 3 | select id, name, parent.name as district | limit 20",
        "Navigate the parent association.",
    ),
    _q(
        "ou-path-filter",
        "Subtree by path",
        "orgunits",
        'organisationUnits | where path ~ "/ImspTQPwCqd" | select id, name, level | limit 20',
        "Everything under a root org unit (path contains its UID).",
    ),
    _q(
        "ou-leaf-facilities",
        "Leaf facilities",
        "orgunits",
        "organisationUnits | where level = 4 | count",
        "Count facilities at the leaf level.",
    ),
    _q(
        "ou-geometry-passthrough",
        "Keep GeoJSON geometry",
        "orgunits",
        "organisationUnits | where level = 2 | transform { id: id, name: name, geometry: geometry } | limit 10",
        "Pass the whole GeoJSON geometry object through unchanged (treat it as opaque).",
    ),
    _q(
        "ou-geometry-type",
        "Filter by geometry type",
        "orgunits",
        'organisationUnits | where geometry.type = "Point" | select id, name | limit 20',
        "A nested geometry path is not a DHIS2 filter property (BUGS.md #48), so this predicate runs locally over fetched rows, not pushed down.",  # noqa: E501
    ),
    _q(
        "ou-as-feature",
        "Emit a GeoJSON Feature",
        "orgunits",
        'organisationUnits | where geometry.type = "Polygon" | transform { type: "Feature", geometry: geometry, properties: { id: id, name: name, level: level } } | limit 10',  # noqa: E501
        "Reshape org units into GeoJSON Features (geometry passed through, attributes lifted to properties).",
    ),
    _q(
        "ou-with-groups",
        "Org units with group refs",
        "orgunits",
        "organisationUnits | where level = 4 | select id, name, organisationUnitGroups.name as groups | limit 10",
        "Collect a repeating association into a list.",
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
    # ---------------------------------------------------------------- aggregate data
    _q(
        "agg-metadata-count",
        "Group + count metadata",
        "aggregate",
        "dataElements | group by domainType { n: count() } | order n desc",
        "Group rows by a key and reduce each group (works over any source).",
    ),
    _q(
        "agg-analytics-source",
        "Analytics source",
        "aggregate",
        'analytics(dx: "fbfJHSPpUQD;cYeuwXTCPkU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd") | select dx, pe, value | limit 12',  # noqa: E501
        "Read aggregated values from /api/analytics; rows are keyed by dimension (dx/pe/ou/value).",
    ),
    _q(
        "agg-analytics-rollup",
        "Roll up analytics by dimension",
        "aggregate",
        'analytics(dx: "fbfJHSPpUQD;cYeuwXTCPkU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd") | where value > 1000 | group by dx { total: sum(value), periods: count() } | order total desc',  # noqa: E501
        "Filter then sum analytics values per data element.",
    ),
    _q(
        "agg-datavalues-source",
        "Aggregate data values",
        "aggregate",
        'dataValues(dataSet: "BfMAe6Itzgt", period: "202401", orgUnit: "ImspTQPwCqd") | transform { de: dataElement, ou: orgUnit, v: value } | limit 10',  # noqa: E501
        "Read raw aggregate data values from /api/dataValueSets.",
    ),
    # ---------------------------------------------------------------- explore (cross-resource)
    _q(
        "explore-indicators",
        "Indicators with type",
        "explore",
        "indicators | select id, name, indicatorType.name as type | order name asc | limit 20",
        "List indicators with their indicator type (nested ref).",
    ),
    _q(
        "explore-indicator-expr",
        "Indicator numerators",
        "explore",
        "indicators | select name, numerator, denominator | limit 10",
        "Inspect raw indicator expressions.",
    ),
    _q(
        "explore-programs",
        "Programs by type",
        "explore",
        "programs | group by programType { n: count() } | order n desc",
        "How many programs are with vs. without registration.",
    ),
    _q(
        "explore-datasets",
        "Data sets by period type",
        "explore",
        "dataSets | group by periodType { n: count() } | order n desc",
        "Group data sets by reporting frequency.",
    ),
    _q(
        "explore-optionsets",
        "Option sets with options",
        "explore",
        "optionSets | select id, name, options.name as options | limit 10",
        "Collect each option set's option names into a list.",
    ),
    _q(
        "explore-analytics-by-period",
        "Analytics summed by period",
        "explore",
        'analytics(dx: "fbfJHSPpUQD", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd") | group by pe { total: sum(value) } | order pe asc',  # noqa: E501
        "Total an indicator across org units, per month.",
    ),
    _q(
        "explore-de-groups",
        "Data element group sizes",
        "explore",
        "dataElementGroups | select name, dataElements.name as members | limit 10",
        "List each group's member data elements.",
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
    # ---------------------------------------------------------------- read (local files, no profile)
    _r(
        "read-json-array",
        "Read a JSON array",
        "read",
        'read("examples/d2ql/data/orgunits.json") | where level = 2 | select id, name, parent.name as parent | order name asc',  # noqa: E501
        "Use a local JSON file as the source instead of a DHIS2 resource; the top-level array becomes the rows.",
    ),
    _r(
        "read-ndjson",
        "Read newline-delimited JSON",
        "read",
        'read("examples/d2ql/data/facilities.ndjson") | select id, name, lastUpdated | order lastUpdated desc',
        "A `.ndjson` file is parsed one JSON object per line; all stages run locally over the file.",
    ),
    _r(
        "read-group-by",
        "Group a local file",
        "read",
        'read("examples/d2ql/data/orgunits.json") | group by level { n: count() } | order level asc',
        "`group by` + `count` works over any source, including a local `read(...)` file.",
    ),
    _r(
        "read-transform",
        "Reshape local file rows",
        "read",
        'read("examples/d2ql/data/orgunits.json") | where level = 2 | transform { id: id, name: name, childCount: children.count() } | order name asc',  # noqa: E501
        "Nested navigation (`children.count()`) works the same over local data as over DHIS2 metadata.",
    ),
    # ---------------------------------------------------------------- dates
    _q(
        "date-modified-since",
        "Modified since a date",
        "dates",
        "dataElements | where lastUpdated >= @2024-01-01 | select id, name, lastUpdated | order lastUpdated desc | limit 25",  # noqa: E501
        "A plain `@`-date literal renders into a native `lastUpdated:ge:` filter (pushed down); ISO dates compare correctly.",  # noqa: E501
    ),
    _q(
        "date-created-window",
        "Created-date window",
        "dates",
        "dataElements | where created >= @2020-01-01 and created <= @2024-12-31 | select id, name, created | order created asc | limit 25",  # noqa: E501
        "Two `@`-date literals AND'd into a window; both clauses push down as native `created:ge:`/`created:le:` filters.",  # noqa: E501
    ),
    _r(
        "date-datetime-literal",
        "Datetime literal filter",
        "dates",
        'read("examples/d2ql/data/facilities.ndjson") | where lastUpdated >= @2024-01-01T00:00:00 | select name, lastUpdated | order lastUpdated asc',  # noqa: E501
        "A `@`-datetime literal (with a time part) compares as an ISO string; over a local file it stays local.",
    ),
    # ---------------------------------------------------------------- strings
    _q(
        "string-label",
        "Compose a display label",
        "strings",
        'dataElements | transform { id: id, label: "[" + valueType + "] " + name } | order name asc | limit 25',
        "`+` between strings concatenates fields and literals into one composed column.",
    ),
    _q(
        "string-join-codes",
        "Join a collection to a string",
        "strings",
        'optionSets | transform { name: name, codes: options.code.join(", ") } | order name asc | limit 25',
        "`join(sep)` turns a repeating association into one delimited string (the inverse of `split`).",
    ),
    _q(
        "string-tostring-cast",
        "Cast a number for concatenation",
        "strings",
        'organisationUnits | where level = 2 | transform { label: name + " (level " + level.toString() + ")" } | order name asc | limit 25',  # noqa: E501
        "`toString()` casts a number so `+` can concatenate it into a label.",
    ),
    # ---------------------------------------------------------------- subset (collection ends / dedup)
    _q(
        "subset-first-last",
        "First and last of a collection",
        "subset",
        "organisationUnits | where level = 2 | transform { name: name, firstChild: children.name.first(), lastChild: children.name.last() } | order name asc | limit 25",  # noqa: E501
        "`first()`/`last()` pick the ends of a nested collection; a single-element collection collapses to a scalar.",
    ),
    _q(
        "subset-tail",
        "All but the first",
        "subset",
        "organisationUnits | where level = 2 | transform { name: name, otherChildren: children.name.tail() } | order name asc | limit 25",  # noqa: E501
        "`tail()` returns everything after the first element (the complement of `first()`).",
    ),
    _q(
        "subset-distinct",
        "Dedupe and test distinctness",
        "subset",
        "dataElementGroups | transform { name: name, valueTypes: dataElements.valueType.distinct(), allTypesDistinct: dataElements.valueType.isDistinct() } | order name asc | limit 25",  # noqa: E501
        "`distinct()` dedupes a collection; `isDistinct()` reports whether it had no duplicates.",
    ),
    # ---------------------------------------------------------------- convert (string -> number)
    _r(
        "convert-rate",
        "Computed rate from string inputs",
        "convert",
        'read("examples/d2ql/data/readings.ndjson") | transform { facility: facility, per1000: ((cases.toDecimal() / population.toDecimal()) * 1000).round(1) } | order per1000 desc',  # noqa: E501
        "Cast text columns with `toDecimal()`, divide/scale, and `round(1)` — a per-1000 rate from raw string inputs.",
    ),
    # ---------------------------------------------------------------- regex filter
    _q(
        "filter-matches",
        "Regex predicate",
        "filtering",
        'dataElements | where code.matches("^[A-Z]{2}") | select id, name, code | order name asc | limit 25',
        "`matches(pattern)` is a local regex predicate (never pushed down); a missing `code` fails the match.",
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
    _p("path-geometry-type", "GeoJSON geometry type", "geometry.type", "Read the type of a GeoJSON geometry."),
    _p(
        "path-first-coordinate",
        "First coordinate pair",
        "geometry.coordinates.first()",
        "Drill into a GeoJSON coordinate array (navigation flattens one level).",
    ),
]


def samples_by_category() -> dict[str, list[Sample]]:
    """Group the catalog by category, preserving definition order within each group."""
    grouped: dict[str, list[Sample]] = {}
    for sample in SAMPLES:
        grouped.setdefault(sample.category, []).append(sample)
    return grouped
