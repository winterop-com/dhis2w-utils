# d2ql cookbook

Working recipes, grouped by what you're trying to do. Each one is a committed program in
[`examples/d2ql/`](https://github.com/winterop-com/dhis2w-utils/tree/main/examples/d2ql) — run any
with `d2w query run examples/d2ql/<name>.d2ql` (add `--profile <name>` / `--json`).

## Explore metadata

**Data elements by value type** — profile the dictionary (`metadata-elements-by-value-type.d2ql`):

```
dataElements | group by valueType { n: count() } | order n desc
```

**ANC aggregate elements** (`metadata-anc-elements.d2ql`):

```
dataElements | where domainType = "AGGREGATE" and name like "ANC" | select id, name, valueType | order name asc
```

**Indicators with their type** — a nested reference (`metadata-indicators.d2ql`):

```
indicators | select id, name, indicatorType.name as type | order name asc | limit 25
```

**Option sets with their options** — a repeating association collected into a list
(`metadata-option-sets.d2ql`):

```
optionSets | select id, name, options.name as options | limit 25
```

## Joins (nested relationships)

d2ql has one source per pipeline — there's no `join`/`from a, b`. But you rarely need one: DHIS2
metadata **embeds** relationships, so you traverse the nested association on a single source. The
field collector requests the right `fields=` expansion automatically.

**A group with its member elements** (`metadata-group-members.d2ql`):

```
dataElementGroups | transform { id: id, name: name, items: dataElements.select({ id: id, name: name }) }
```

**A data set with its elements** — through the `dataSetElements.dataElement` join entity
(`metadata-dataset-elements.d2ql`):

```
dataSets | transform { id: id, name: name, elements: dataSetElements.dataElement.select({ id: id, name: name }) }
```

**An org unit with its parent and children** — the self-referential hierarchy
(`orgunits-with-children.d2ql`):

```
organisationUnits | where level = 2 | transform { id: id, name: name, parent: parent.name, children: children.name }
```

The same pattern covers dataSet→elements, optionSet→options, indicator→indicatorType, category→options,
etc. A *true* cross-source join (correlating unrelated sources) isn't supported.

## Organisation units & GeoJSON

**Facilities per level** (`orgunits-per-level.d2ql`):

```
organisationUnits | group by level { facilities: count() } | order level asc
```

**Districts with their parent** (`orgunits-with-parent.d2ql`):

```
organisationUnits | where level = 2 | select id, name, parent.name as parent | order name asc
```

**Export districts as a GeoJSON FeatureCollection** — `transform` each row to a Feature, `fold` them
into one object, write the file (`geojson-featurecollection.d2ql`):

```
define function feature(ou): {
  type: "Feature",
  properties: { id: $ou.id, name: $ou.name, level: $ou.level },
  geometry: $ou.geometry
}

organisationUnits
  | where level = 2 and geometry.type = "Polygon"
  | transform feature($this)
  | fold { type: "FeatureCollection", features: $rows }
  >> "/tmp/districts.geojson"
```

## Aggregate data

**Indicator time series** — reshape analytics to one row per month (`analytics-time-series.d2ql`):

```
analytics(dx: "fbfJHSPpUQD", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd")
  | transform { month: pe, anc1: value }
  | order month asc
```

**Roll analytics up per data element** (`analytics-rollup.d2ql`):

```
analytics(dx: "fbfJHSPpUQD;cYeuwXTCPkU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd")
  | where value > 1000
  | group by dx { total: sum(value), periods: count() }
  | order total desc
```

**Readable output + indicator numerator/denominator** — `analytics(...)` takes analytics options
(not just dimensions): `outputIdScheme: "NAME"` returns names instead of UIDs, and `includeNumDen:
true` exposes an indicator's `numerator`/`denominator`/`factor` (`analytics-named-output.d2ql`,
`analytics-indicator-numden.d2ql`):

```
analytics(dx: "Uvn6LCg7dVU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd", includeNumDen: true, outputIdScheme: "NAME")
  | transform { month: pe, coverage: value, numerator: numerator, denominator: denominator }
  | order month asc
```

Other options route the same way: `aggregationType`, `measureCriteria`, `displayProperty`,
`startDate`/`endDate`, `relativePeriodDate`, `skipMeta`, `skipData`. Any other arg (e.g. `co`) is a
dimension. The `analytics-*` examples cover COC breakdowns, org-unit-level rollups, and multi-period
and multi-org-unit comparisons; the `export-*` examples show writing results to CSV/JSON/ndjson files.

**Raw data values** from a dataset/period/org unit (`datavalues-by-dataset.d2ql`):

```
dataValues(dataSet: "BfMAe6Itzgt", period: "202401", orgUnit: "ImspTQPwCqd")
  | transform { de: dataElement, ou: orgUnit, value: value }
```

`dataValues(...)` accepts the full `/api/dataValueSets` selection: `dataSet` **or**
`dataElementGroup`, a single `period` **or** a `startDate`/`endDate` window, `orgUnit` **or**
`orgUnitGroup` with optional `children: true` to include its subtree, `includeDeleted: true`,
`lastUpdated` (modified-since date/duration), and `limit`
(`datavalues-date-window.d2ql`, `datavalues-with-children.d2ql`, `datavalues-by-group.d2ql`,
`datavalues-recently-updated.d2ql`):

```
dataValues(dataSet: "BfMAe6Itzgt", startDate: "2024-01-01", endDate: "2024-03-31", orgUnit: "ImspTQPwCqd", children: true)
  | transform { de: dataElement, pe: period, ou: orgUnit, value: value }
```

## Reshape with `transform`

`transform { … }` builds one object per row from d2path expressions — flat renames, computed fields,
nested objects, arrays. These are the building blocks the FHIR/GeoJSON recipes below are made of.

**Rename and compute** — a flat row with a derived initial and a boolean:

```
dataElements | transform { name: name, initial: name.substring(0, 1), aggregate: domainType = "AGGREGATE" }
```
```json
[
  { "name": "Accute Flaccid Paralysis (Deaths < 5 yrs)", "initial": "A", "aggregate": true },
  { "name": "Acute Flaccid Paralysis (AFP) follow-up", "initial": "A", "aggregate": true }
]
```

**Nested object** — group fields under a sub-object:

```
dataElements | transform { id: id, meta: { type: valueType, combo: categoryCombo.name } }
```
```json
[
  { "id": "FTRrcoaog83", "meta": { "type": "NUMBER", "combo": "default" } },
  { "id": "P3jJH5Tu5VC", "meta": { "type": "NUMBER", "combo": "Morbidity Cases" } }
]
```

**Build an array** — e.g. a FHIR-style `coding` list:

```
dataElements | transform { display: name, coding: [ { system: "dhis2", code: id } ] }
```
```json
[
  { "display": "Accute Flaccid Paralysis (Deaths < 5 yrs)",
    "coding": [ { "system": "dhis2", "code": "FTRrcoaog83" } ] }
]
```

**Factor the shape into a function** — `transform fn($this)` keeps the pipeline readable when the
per-row object grows (this is how the FHIR recipes are written):

```
define function summary(de): { code: $de.id, label: $de.name, type: $de.valueType }
dataElements | transform summary($this)
```

## Read from local files (`read(...)`)

A pipeline's source is usually a DHIS2 resource, but `read("path")` reads rows from a local file
instead — a JSON array (or single object), or a `.ndjson` file (one object per line). Everything runs
locally, so these need **no profile or server**. Use it to shape exported data, join a d2ql pipeline
onto a previous run's output, or develop a transform offline against a fixture.

**Read a JSON array** — the top-level array becomes the rows (`read-json-array.d2ql`):

```d2ql
read("examples/d2ql/data/orgunits.json")
  | where level = 2
  | select id, name, parent.name as parent
  | order name asc
```
```json
[
  { "id": "OU_BO", "name": "Bo", "parent": "Sierra Leone" },
  { "id": "OU_BOMBALI", "name": "Bombali", "parent": "Sierra Leone" }
]
```

**Read NDJSON** — one JSON object per line, ideal for streamed exports (`read-ndjson.d2ql`):

```d2ql
read("examples/d2ql/data/facilities.ndjson")
  | select id, name, lastUpdated
  | order lastUpdated desc
```

**Group a local file** — `group by` + `count` work over any source (`read-group-by.d2ql`):

```d2ql
read("examples/d2ql/data/orgunits.json")
  | group by level { n: count() }
  | order level asc
```
```json
[ { "level": 2, "n": 2 }, { "level": 3, "n": 2 } ]
```

**Two-step chain: export, then read back** — run one program that writes a file, then a second that
reads it for further shaping without re-fetching. Step 1 (`read-chain-1-export.d2ql`) writes NDJSON:

```d2ql
read("examples/d2ql/data/orgunits.json")
  | where level = 2
  | transform { id: id, name: name, districts: children.count() }
  | order name asc
  >> "/tmp/d2ql-districts.ndjson"
```

Step 2 (`read-chain-2-reshape.d2ql`) reads that file back:

```d2ql
read("/tmp/d2ql-districts.ndjson")
  | where districts >= 2
  | select name, districts
  | order districts desc
```

> **Contract — d2ql file I/O is trusted-code-equivalent.** `read("path")` sources and `>> "path"`
> file sinks read and write arbitrary host paths with the running process's permissions. Running a
> d2ql program that uses them is equivalent to running local code: a query text is not a safe
> sandbox boundary on its own. The `d2w` CLI enables file I/O because the local operator already has
> shell access. An application that executes **untrusted** d2ql must disable it — construct the
> engine with `QueryEngine(library, binder, allow_file_io=False)`, which makes `read(...)` and file
> sinks raise a `SemanticError` instead of touching the filesystem. The DHIS2 MCP query surface sets
> this off, so a model-authored query can never read or write host files.

## Filter by date

A `@`-prefixed literal is a date (`@2024-01-01`) or datetime (`@2024-01-01T00:00:00`). Dates compare
as ISO strings, so `>=`/`<=` order correctly. Use it against audit fields like `lastUpdated` /
`created`. A plain `@date` pushes down into a native `lastUpdated:ge:2024-01-01` filter; a datetime
literal (it contains `:`) stays local instead.

**Modified since a date** (`date-modified-since.d2ql`):

```d2ql
dataElements
  | where lastUpdated >= @2024-01-01
  | select id, name, lastUpdated
  | order lastUpdated desc
  | limit 25
```

**A created-date window** — two literals AND'd, both pushed down (`date-created-window.d2ql`):

```d2ql
dataElements
  | where created >= @2020-01-01 and created <= @2024-12-31
  | select id, name, created
  | order created asc
  | limit 25
```

**A datetime literal over a local file** — the time part keeps the compare local
(`date-datetime-literal.d2ql`):

```d2ql
read("examples/d2ql/data/facilities.ndjson")
  | where lastUpdated >= @2024-01-01T00:00:00
  | select name, lastUpdated
  | order lastUpdated asc
```

## Build strings and keys

String `+` is concatenation when both sides are strings, so you can compose labels and keys in a
`transform`. `toString()` casts a number first; `join(sep)` collapses a collection into one string.

**Compose a display label** (`string-label.d2ql`):

```d2ql
dataElements
  | transform { id: id, label: "[" + valueType + "] " + name }
  | order name asc
  | limit 25
```
```json
[ { "id": "FTRrcoaog83", "label": "[NUMBER] Accute Flaccid Paralysis (Deaths < 5 yrs)" } ]
```

**Cast a number so `+` can concatenate it** (`string-tostring-cast.d2ql`):

```d2ql
organisationUnits
  | where level = 2
  | transform { label: name + " (level " + level.toString() + ")" }
  | order name asc
  | limit 25
```
```json
[ { "label": "Bo (level 2)" }, { "label": "Bombali (level 2)" } ]
```

**Join a collection into one delimited string** — the inverse of `split` (`string-join-codes.d2ql`):

```d2ql
optionSets
  | transform { name: name, codes: options.code.join(", ") }
  | order name asc
  | limit 25
```

## Take subsets of a collection

Inside a `transform`, d2path collection functions pick parts of a nested list. `first()`/`last()` take
the ends, `tail()` takes everything after the first, and `distinct()`/`isDistinct()` dedupe or test
for duplicates. A single-element collection collapses to a scalar.

**First and last child of each district** (`subset-first-last.d2ql`):

```d2ql
organisationUnits
  | where level = 2
  | transform { name: name, firstChild: children.name.first(), lastChild: children.name.last() }
  | order name asc
  | limit 25
```
```json
[ { "name": "Bombali", "firstChild": "Gbanti Kamaranka", "lastChild": "Safroko Limba" } ]
```

**Everything after the first** (`subset-tail.d2ql`):

```d2ql
organisationUnits
  | where level = 2
  | transform { name: name, otherChildren: children.name.tail() }
  | order name asc
  | limit 25
```

**Distinct values and a distinctness test** (`subset-distinct.d2ql`):

```d2ql
dataElementGroups
  | transform {
      name: name,
      valueTypes: dataElements.valueType.distinct(),
      allTypesDistinct: dataElements.valueType.isDistinct()
    }
  | order name asc
  | limit 25
```

## Convert string columns to numbers

Files carry everything as text. `toInteger()` / `toDecimal()` cast text columns so later stages can
compare and aggregate them numerically; `round(n)` trims a computed value.

**A per-1000 rate from raw string inputs** (`convert-rate.d2ql`, `convert-numeric.d2ql`):

```d2ql
read("examples/d2ql/data/readings.ndjson")
  | transform { facility: facility, per1000: ((cases.toDecimal() / population.toDecimal()) * 1000).round(1) }
  | order per1000 desc
```
```json
[
  { "facility": "Kamaranka CHP", "per1000": 4.1 },
  { "facility": "Njandama MCHP", "per1000": 3.9 }
]
```

## Regex filters

`matches(pattern)` is a regex predicate (Python `re.search`). Because it is a function call it always
runs locally over fetched rows (never pushed down), and a row whose field is missing simply fails the
match. Use it when a `like`/`~` substring test isn't precise enough (`filter-matches-regex.d2ql`):

```d2ql
dataElements
  | where code.matches("^[A-Z]{2}")
  | select id, name, code
  | order name asc
  | limit 25
```

## DHIS2 → FHIR

The recipe is always the same: a `define function` builds the resource, `transform` wraps each row,
`fold` builds the Bundle envelope.

**Data elements → a Bundle of Observations** (`fhir-bundle-de.d2ql`):

```
define function observation(de): {
  resourceType: "Observation", status: "final",
  code: { coding: [ { system: "dhis2", code: $de.id, display: $de.name } ] }
}

dataElements | where domainType = "AGGREGATE"
  | transform { resource: observation($this) }
  | fold { resourceType: "Bundle", type: "collection", entry: $rows }
```

**Option set → a CodeSystem** (`fhir-optionset-codesystem.d2ql`):

```
optionSets | where name like "Age" | limit 1
  | fold {
      resourceType: "CodeSystem", status: "active", content: "complete",
      concept: options.select({ code: code, display: name })
    }
```

**Option set → a ValueSet** (`fhir-optionset-valueset.d2ql`); **option sets → a Bundle of
CodeSystems** (`fhir-bundle-optionset.d2ql`); **data set → a Questionnaire** and **data sets → a
Bundle of Questionnaires** (`fhir-dataset-questionnaire.d2ql`, `fhir-bundle-dataset.d2ql`) all follow
the same `transform` + `fold` shape.

## Reusable libraries

A `.d2ql` file with `define`s is a library you keep under version control
(`library-immunisation.d2ql`):

```
define MinLevel: 2
define function isImmunisation(de): $de.name like "BCG" or $de.name like "measles" or $de.name like "Penta"
define Aggregates: dataElements | where domainType = "AGGREGATE"

Aggregates | where isImmunisation($this) | select id, name, valueType | order name asc | limit 25
```

Run it with `d2w query run examples/d2ql/library-immunisation.d2ql`, or run a specific definition with
`--define <name>`.

**A library of several named queries** — pick one at run time with `--define` (`library-run.d2ql`):

```d2ql
define MinLevel: 2
define function isImmunisation(de): $de.name like "BCG" or $de.name like "measles" or $de.name like "Penta"

define AggregateElements: dataElements | where domainType = "AGGREGATE" | select id, name, valueType | order name asc | limit 25
define ImmunisationElements: dataElements | where isImmunisation($this) | select id, name | order name asc | limit 25
define Districts: organisationUnits | where level = $MinLevel | select id, name | order name asc | limit 25
define TrackerPrograms: programs | where programType = "WITH_REGISTRATION" | select id, name | order name asc | limit 25

Districts
```

```bash
d2w query run examples/d2ql/library-run.d2ql --define AggregateElements   # run one named query
d2w query run examples/d2ql/library-run.d2ql --define TrackerPrograms
d2w query run examples/d2ql/library-run.d2ql                              # no --define runs the terminal (Districts)
```

## Output formats & sinks

A `>>` sink picks **destination** (stdout or a file) and **format** (json/ndjson/csv) independently.
Format comes from `as <format>`, a bare format keyword (stdout), or a file's extension.

```
dataElements | select id, name >> ndjson                 # ndjson to stdout (sink-stdout-ndjson.d2ql)
dataElements | select id, name >> csv                    # csv to stdout — escapes wide tables (sink-stdout-csv.d2ql)
dataElements | select id, name >> json                   # JSON array to stdout (sink-stdout-json.d2ql)
dataElements | select id, name >> stdout as ndjson       # explicit long form of `>> ndjson` (sink-stdout-as.d2ql)
dataElements | select id, name >> "elements.csv"         # csv file from the extension (export-csv.d2ql)
dataElements | select id, name >> "elements.txt" as csv  # `as` overrides the extension (sink-file-as-override.d2ql)
```

In the [REPL](d2ql.md#interactive-repl) the same formats apply, **Ctrl+F** cycles the
default render (table -> json -> ndjson -> csv) when a result is too wide for a table, and **Ctrl+T**
toggles a collapsible **JSON tree** that each query repopulates and focuses (arrows to navigate, Enter
to expand/collapse) — ideal for deeply nested rows.

## See also

- [d2ql tutorial](d2ql-tutorial.md) — build these up step by step.
- [d2ql reference](d2ql.md) and [d2path](d2path.md).
