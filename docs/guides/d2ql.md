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

This page is the reference. New to d2ql? Start with the **[tutorial](d2ql-tutorial.md)**, then come
back here to look things up; the **[cookbook](../query/cookbook.md)** has ready-to-run recipes.

## Running a program

```bash
d2w query eval 'dataElements | where domainType = "AGGREGATE" | select id, name | limit 20'
d2w query run report.d2ql                 # run a program from a file (or `eval --file`)
d2w query explain 'dataElements | ...'    # show what is pushed to DHIS2 vs. run locally
d2w query ast 'dataElements | ...'        # print the parsed AST (offline)
d2w query repl                            # interactive REPL
```

`eval`, `explain`, and `ast` also accept `--file/-f <path>` to read a program from a file.

The same engine is available as MCP tools (`query_eval`, `query_explain`, `query_d2path`).

### Interactive REPL

`d2w query repl` opens an interactive prompt. With the **`tui` extra** installed
(`uv add 'dhis2w-cli[tui]'`) it's a full-screen [Textual](https://textual.textualize.io/) editor:
**Enter runs** the program, **Shift+Enter** / **Ctrl+J** insert a newline, and pasting a multi-line
pipeline drops it in cleanly. **Up/Down** recall history at the buffer edges (or Ctrl+P/Ctrl+N), and
move the cursor within a multi-line program otherwise; **Ctrl+L** clears, **Ctrl+Q** quits. The editor
has full readline-style keys (Ctrl+A/E/W/K/U, word nav, undo/redo). **Ctrl+F** cycles the output
format (table / json / ndjson / csv) for wide results, and **Ctrl+T** toggles **tree mode** — the
result pane becomes a collapsible **JSON tree** that each new query repopulates (so you see the tree,
not JSON, first). It takes focus on toggle so you can navigate immediately (arrows move, Enter
expands/collapses); Tab back to the editor to run another query; **Escape** or **Ctrl+T** returns to
the log. The tree is structural, so it renders json and ndjson results alike.
Without the extra, `repl` falls back to a line-mode prompt that runs on a blank line or a trailing `;`.

A library of runnable, commented programs lives in
[`examples/d2ql/`](https://github.com/winterop-com/dhis2w-utils/tree/main/examples/d2ql) — run any
with `d2w query run examples/d2ql/<name>.d2ql`, inspect with `d2w query ast "$(cat <file>)"`, or load
from Python via `parse(open(<file>).read())`.

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
      maps to an analytics filter. Beyond dimensions, `analytics(...)` also takes analytics **option**
      args, routed to the matching query params: `aggregationType`, `measureCriteria`,
      `outputIdScheme`, `displayProperty`, `startDate`, `endDate`, `relativePeriodDate`, `skipMeta`,
      `skipData`, and `includeNumDen` (adds `numerator`/`denominator`/`factor`). Any arg that isn't a
      known option or `filter` is treated as a dimension.
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
| `group by <expr> { name: agg, … }` | Group rows by a key and reduce each group. |
| `fold { … }` | Collapse the whole stream into one object (FHIR Bundle, GeoJSON FeatureCollection). |

### group by

`group by <group> { total: sum(value), n: count() }` groups rows by the group expression and
emits one object per group: the group key (named like a `select` column) plus each aggregation.
Aggregation expressions are evaluated against the group's rows, so `sum(value)` gathers `value`
across the group. Works over any source — metadata, analytics, or data values:

```
analytics(dx: "fbfJHSPpUQD;cYeuwXTCPkU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd")
  | where value > 1000
  | group by dx { total: sum(value), periods: count() }
  | order total desc
```

### fold

`group by`/`count` reduce per group; `fold { … }` reduces the **whole stream into one object** —
an envelope like a FHIR `Bundle` or a GeoJSON `FeatureCollection`. The template is built once with
the entire stream in focus: `$rows` is the rows as a list, and `select(...)` / aggregate functions
see all rows. Pair it with `define function`s to keep the per-item shape readable:

```
define function observation(de): { resourceType: "Observation", status: "final",
                                    code: { coding: [ { system: "dhis2", code: $de.id, display: $de.name } ] } }

dataElements | where domainType = "AGGREGATE"
  | transform { resource: observation($this) }
  | fold { resourceType: "Bundle", type: "collection", entry: $rows }
```

`fold` (like `count`) yields a single value, so `--json` / a `.json` sink emit the object itself,
not a one-element array.

### transform

`transform` builds a new value per row — an object literal `{ … }` **or** any expression that
evaluates to one, e.g. a `define function` call `transform feature($this)`. Nested objects, arrays,
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

End a pipeline with `>>` to choose where the result goes and in which format. **Destination** is
`stdout` or a quoted file path; **format** is `json` / `ndjson` / `csv`, set explicitly with
`as <format>` or, for files, inferred from the extension. Format and destination are independent:

| Sink | Destination | Format |
|------|-------------|--------|
| *(no sink)* / `>> stdout` | stdout | table (or JSON under `--json`) — the default renderer |
| `>> json` / `>> ndjson` / `>> csv` | stdout | that format (bare-keyword shorthand) |
| `>> stdout as ndjson` | stdout | ndjson (explicit; identical to `>> ndjson`) |
| `>> "out.csv"` / `>> "out.json"` / `>> "out.ndjson"` | file | from the extension |
| `>> "out.txt" as csv` | file | csv (`as` overrides the extension) |

```
dataElements | select id, name >> ndjson                # ndjson to stdout (pipe to jq; escapes wide tables)
dataElements | select id, name >> csv                   # csv to stdout
dataElements | select id, name >> "elements.csv"        # csv file (extension)
dataElements | select id, name >> "elements.txt" as csv # csv file, extension overridden
```

A `json`/`ndjson`/`csv` format applies in the **REPL** too; or cycle the REPL's default render with
**Ctrl+F** (or open a tree with **Ctrl+T**) when tables are too wide. On the CLI, `--out FILE` is the equivalent of an in-program file
sink.

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

One predicate is not just local but meaningless: `where field = null`. A missing or null field is the
empty collection, so `= null` matches nothing and is never pushed. Use `where field.exists()` /
`where field.empty()` to test presence and absence — see [d2path](d2path.md#presence-and-absence-there-is-no--null).

## See also

- [d2ql tutorial](d2ql-tutorial.md) — learn the language step by step.
- [d2path](d2path.md) — the expression language used inside every stage.
- [Cookbook](../query/cookbook.md) — ready-to-run recipes (FHIR, GeoJSON, reports).
- API reference: [`dhis2w_ql`](../api/query.md).
