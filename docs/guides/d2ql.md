# d2ql — the query + transform language

d2ql is a pipeline language for querying and reshaping DHIS2 data. A program reads as a source
feeding a chain of stages, optionally ending in a sink:

```
dataElements
  | where domainType = "AGGREGATE" and name ~ "ANC"
  | select id, name, categoryCombo.name as combo
  | transform { code: id, label: name }
  | order name asc
  | limit 20
  >> "elements.csv"
```

Expressions inside `where`, `select`, `order`, and `transform` are written in
[d2path](d2path.md), the embedded path/expression language.

## Running a program

```bash
d2w query eval 'dataElements | where domainType = "AGGREGATE" | select id, name | limit 20'
d2w query run report.d2ql                 # run a program from a file
d2w query explain 'dataElements | ...'    # show what is pushed to DHIS2 vs. run locally
d2w query ast 'dataElements | ...'        # print the parsed AST (offline)
```

The same engine is available as MCP tools (`query_eval`, `query_explain`, `query_d2path`).

## Sources

- A **resource** name — any DHIS2 metadata resource: `dataElements`, `indicators`,
  `organisationUnits`, … An inline filter is shorthand for a leading `where`:
  `dataElements[domainType = "AGGREGATE"]`.
- **`read("path.json")`** — read rows from a local JSON or NDJSON file (FHIR bundles, fixtures, the
  output of an earlier query).
- A **definition** — reference a named query as a source (see [Definitions](#definitions)).
- A scalar **expression** — `define Total: 1 + 2` (used by definitions, not usually run directly).
- A **call source** for aggregate data:
    - `analytics(dx: "...", pe: "LAST_12_MONTHS", ou: "...")` — rows from `/api/analytics`, one dict
      per row keyed by dimension (`dx`, `pe`, `ou`, `value`, ...). An optional `filter: "..."` arg
      maps to an analytics filter.
    - `dataValues(dataSet: "...", period: "...", orgUnit: "...")` — raw aggregate values from
      `/api/dataValueSets` (navigate `dataElement`, `period`, `orgUnit`, `value`).

## Stages

| Stage | Purpose |
|-------|---------|
| `where <predicate>` | Keep rows where the d2path predicate is true. |
| `select <expr> [as name], …` | Project columns; name with `as` or let the path name it. |
| `transform { key: <expr>, … }` | Build a new object per row (native reshaping — see below). |
| `order <expr> [asc\|desc], …` | Sort by one or more keys. |
| `limit <n>` / `skip <n>` | Take / drop rows. |
| `count` | Replace the stream with its length (a scalar result). |
| `aggregate by <expr> { name: agg, … }` | Group rows by a key and reduce each group. |

### aggregate

`aggregate by <group> { total: sum(value), n: count() }` groups rows by the group expression and
emits one object per group: the group key (named like a `select` column) plus each aggregation.
Aggregation expressions are evaluated against the group's rows, so `sum(value)` gathers `value`
across the group. Works over any source — metadata, analytics, or data values:

```
analytics(dx: "fbfJHSPpUQD;cYeuwXTCPkU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd")
  | where value > 1000
  | aggregate by dx { total: sum(value), periods: count() }
  | order total desc
```

### transform

`transform` builds an arbitrary object per row from d2path expressions — nested objects, arrays,
and computed values are all allowed. It depends on nothing FHIR-specific, but it is exactly what you
use to emit FHIR-shaped output:

```
dataElements
  | where domainType = "AGGREGATE"
  | transform {
      resourceType: "Observation",
      status: "final",
      code: { coding: [ { system: "dhis2", code: id, display: name } ] }
    }
```

## Sinks

End a pipeline with `>>` to write the result instead of returning it. The format is inferred from
the file extension:

```
dataElements | select id, name >> "elements.csv"      # csv
dataElements | transform { … }   >> "out.json"        # json
dataElements | select id, name >> "elements.ndjson"   # ndjson
```

On the CLI, `--out FILE` is the equivalent of an in-program sink.

## Definitions

A program may begin with `define`s, making a `.d2ql` file a reusable library. Reference a scalar
definition or a function parameter with the `$` sigil.

```
define MinLevel: 3
define function isAnc(de): $de.name ~ "ANC"
define Aggregates: dataElements | where domainType = "AGGREGATE"

Aggregates
  | where isAnc($this) and level >= $MinLevel
  | select id, name
```

- `define NAME: <pipeline>` — a named query; reference it as a source.
- `define NAME: <expression>` — a scalar value; reference it as `$NAME`.
- `define function NAME(params): <expression>` — a reusable function; parameters are read as
  `$param` inside the body. `$this` is the current row inside `where`/`select`/`transform`.

## Pushdown — what runs where

d2ql does not fetch everything and filter in memory when it does not have to. The planner pushes a
leading run of `where` filters, then `order`, then paging, down to DHIS2's list endpoint (compiled
to `filter=`, `order=`, `pageSize`), and runs everything it cannot express — transforms, function
predicates, cross-field expressions — locally over the rows DHIS2 returns. `d2w query explain`
shows the split:

```
$ d2w query explain 'dataElements | where domainType = "AGGREGATE" | transform { code: id }'
source: dataElements (resource)
pushed down: filter[AND] domainType:eq:AGGREGATE
             order (none); skip None; limit None
local stages: transform
```

A predicate the server cannot express (for example `where name.substring(0, 3) = "ANC"`) simply
stays local — the result is identical, only the work moves.

## See also

- [d2path](d2path.md) — the expression language used inside every stage.
- API reference: [`dhis2w_ql`](../api/query.md).
