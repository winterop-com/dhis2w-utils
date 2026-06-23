# d2ql tutorial

This is a hands-on walkthrough of **d2ql**, the DHIS2 query + transform language. Work through it
top to bottom — each step is a query you can run, the output you should see, and one new idea. By the
end you'll filter, reshape, aggregate, build reusable libraries, and emit FHIR/GeoJSON.

Everything here runs read-only against the DHIS2 demo (`play`). Set a profile once and follow along:

```bash
DHIS2_PASSWORD=district d2w profile add play \
  --url https://play.im.dhis2.org/dev --auth basic --username admin
# or use an existing profile and pass --profile <name> on each command
```

Run a query with `d2w query eval '<program>'`. Add `--json` for machine output (this tutorial shows
JSON); without it you get a table. Global flags go **before** the command:
`d2w --profile play --json query eval '…'`.

---

## 1. Your first query

A d2ql program is a **source** followed by a chain of **stages** separated by `|`. The simplest
program is just a resource name; cap it with `limit`:

```
dataElements | select id, name | limit 3
```
```json
[
  { "id": "FTRrcoaog83", "name": "Accute Flaccid Paralysis (Deaths < 5 yrs)" },
  { "id": "P3jJH5Tu5VC", "name": "Acute Flaccid Paralysis (AFP) follow-up" },
  { "id": "FQ2o8UBlcrS", "name": "Acute Flaccid Paralysis (AFP) new" }
]
```

`select` picks the columns. Drop it (`dataElements | limit 3`) and you get the whole objects.

> **Tip:** `d2w query ast '<program>'` prints the parsed program without contacting DHIS2 — handy
> when you're learning the syntax.

## 2. Filter with `where`

`where` keeps rows matching a predicate. `like` is case-insensitive matching; combine clauses with
`and` / `or`:

```
dataElements | where domainType = "AGGREGATE" and name like "ANC" | select id, name | limit 3
```
```json
[
  { "id": "hCVSHjcml9g", "name": "Albendazole given at ANC (2nd trimester)" },
  { "id": "fbfJHSPpUQD", "name": "ANC 1st visit" },
  { "id": "cYeuwXTCPkU", "name": "ANC 2nd visit" }
]
```

Other operators: `!=`, `<` `<=` `>` `>=`, and membership `in ["A", "B"]`. Strings are
double-quoted.

**Where does the work happen?** d2ql pushes simple filters down to DHIS2 so the server does them, and
runs the rest locally. See exactly what gets pushed with `explain`:

```
$ d2w --profile play query explain 'dataElements | where domainType = "AGGREGATE" | transform { code: id }'
source: dataElements (resource)
pushed down: filter[AND] domainType:eq:AGGREGATE
local stages: transform
```

## 3. Pick and rename columns

`select` takes expressions, each optionally renamed with `as`. Navigate into nested objects with `.`:

```
dataElements | select name, categoryCombo.name as combo, valueType | limit 3
```
```json
[
  { "name": "Accute Flaccid Paralysis (Deaths < 5 yrs)", "combo": "default", "valueType": "NUMBER" },
  { "name": "Acute Flaccid Paralysis (AFP) follow-up", "combo": "Morbidity Cases", "valueType": "NUMBER" }
]
```

The expressions inside `select`/`where` are written in **[d2path](d2path.md)** — dotted path
navigation plus operators and functions, e.g. `categoryCombo.name`, `name.upper()`, `code.coding.first()`.

## 4. Reshape with `transform`

`select` makes a flat row; `transform` builds an arbitrary object per row — nested objects, arrays,
computed values:

```
dataElements | transform { code: id, label: name, aggregate: domainType = "AGGREGATE" } | limit 2
```
```json
[
  { "code": "FTRrcoaog83", "label": "Accute Flaccid Paralysis (Deaths < 5 yrs)", "aggregate": true },
  { "code": "P3jJH5Tu5VC", "label": "Acute Flaccid Paralysis (AFP) follow-up", "aggregate": true }
]
```

This is the tool you reach for to emit foreign shapes (FHIR, GeoJSON) — more in step 9.

## 5. Order, count, page

```
dataElements | select id, name | order name asc | limit 5     # sort; add desc to reverse
dataElements | where domainType = "AGGREGATE" | count          # a single number
dataElements | select id, name | skip 50 | limit 25            # page: offset then take
```

`count` returns a scalar (e.g. `621`), not a list.

## 6. Group and aggregate

`group by <key> { name: agg, … }` groups rows and reduces each group with `sum`/`avg`/`min`/`max`/
`count`. Profile the data dictionary by value type:

```
dataElements | group by valueType { n: count() } | order n desc
```
```json
[
  { "valueType": "NUMBER", "n": 506 },
  { "valueType": "TEXT", "n": 160 },
  { "valueType": "TRUE_ONLY", "n": 135 },
  { "valueType": "BOOLEAN", "n": 91 }
]
```

Or count facilities per org-unit level: `organisationUnits | group by level { n: count() } | order level asc`.

## 7. Reuse with definitions

A program can begin with `define`s, turning a `.d2ql` file into a reusable library. Reference a
scalar value or a function parameter with `$`; reference a named query as a source:

```
define MinLevel: 3
define function isImmunisation(de): $de.name like "BCG" or $de.name like "measles" or $de.name like "Penta"
define Aggregates: dataElements | where domainType = "AGGREGATE"

Aggregates
  | where isImmunisation($this)
  | select id, name
  | limit 5
```

- `define NAME: <pipeline>` — a named query; use it as a source.
- `define NAME: <expression>` — a scalar; reference it as `$NAME`.
- `define function NAME(p): <expr>` — a function; its parameter is `$p`, and `$this` is the current row.

Save a program to a `.d2ql` file and run it with `d2w query run report.d2ql`.

## 8. Aggregate data, not just metadata

Two call sources read aggregate data. `analytics(...)` hits the analytics tables; rows are keyed by
dimension (`dx`/`pe`/`ou`/`value`):

```
analytics(dx: "fbfJHSPpUQD;cYeuwXTCPkU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd")
  | where value > 1000
  | group by dx { total: sum(value), periods: count() }
  | order total desc
```
```json
[
  { "dx": "fbfJHSPpUQD", "total": 143714.0, "periods": 7 },
  { "dx": "cYeuwXTCPkU", "total": 135717.0, "periods": 7 }
]
```

`dataValues(dataSet: "…", period: "…", orgUnit: "…")` reads raw aggregate values from
`/api/dataValueSets`.

## 9. Emit FHIR and GeoJSON with `fold`

`transform` reshapes per row; `fold { … }` collapses the **whole stream** into one envelope object —
a FHIR `Bundle`, a GeoJSON `FeatureCollection`. Inside `fold`, `$rows` is the stream. Combine it with
a `define function` for the per-item shape:

```
define function observation(de): {
  resourceType: "Observation", status: "final",
  code: { coding: [ { system: "dhis2", code: $de.id, display: $de.name } ] }
}

dataElements | where domainType = "AGGREGATE"
  | transform { resource: observation($this) }
  | fold { resourceType: "Bundle", type: "collection", entry: $rows }
```
```json
{
  "resourceType": "Bundle",
  "type": "collection",
  "entry": [
    { "resource": { "resourceType": "Observation", "status": "final",
                    "code": { "coding": [ { "system": "dhis2", "code": "s46m5MS0hxu", "display": "BCG doses given" } ] } } }
  ]
}
```

The same pattern emits a GeoJSON FeatureCollection from org units (geometry passes through whole) —
see `fhir-bundle-de.d2ql` and `geojson-featurecollection.d2ql` in the example library.

## 10. Write the result to a file

End a pipeline with `>>` to write instead of return; the format follows the extension:

```
dataElements | select id, name >> "elements.csv"
dataElements | transform { code: id, label: name } >> "out.json"
```

On the CLI, `--out elements.csv` does the same.

---

## Where to next

- The full list of stages, sources, sinks, and pushdown rules: [d2ql reference](d2ql.md).
- The expression language inside every stage: [d2path](d2path.md).
- Ready-to-run programs for every pattern above: the
  [`examples/d2ql/`](https://github.com/winterop-com/dhis2w-utils/tree/main/examples/d2ql) library —
  `d2w query run examples/d2ql/<name>.d2ql`.
- More recipes (FHIR Bundle/CodeSystem/ValueSet/Questionnaire, GeoJSON): [Cookbook](../query/cookbook.md).
- Programmatic use: [`dhis2w_ql` API](../api/query.md).
