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

In the [REPL](../guides/d2ql.md#interactive-repl) the same formats apply, **Ctrl+F** cycles the
default render (table -> json -> ndjson -> csv) when a result is too wide for a table, and **Ctrl+T**
toggles a collapsible **JSON tree** that each query repopulates (Tab to navigate, Enter to
expand/collapse) — ideal for deeply nested rows.

## See also

- [d2ql tutorial](../guides/d2ql-tutorial.md) — build these up step by step.
- [d2ql reference](../guides/d2ql.md) and [d2path](../guides/d2path.md).
