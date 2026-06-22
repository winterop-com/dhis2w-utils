# d2ql roadmap

Phase 1 (metadata) is in place: the d2ql pipeline language, the d2path expression language, the
engine (planner + executor + sinks + definitions), and a `query` plugin across v41/v42/v43 with
CLI and MCP surfaces. This roadmap covers the next phases. The engine seam stays fixed: each phase
adds **new source kinds** and, where needed, **new stages** — the parser AST, evaluator, planner,
and sinks are reused, not rewritten.

## Phase 2 — aggregate data

Goal: query aggregate data values and analytics through the same pipeline language.

New source kinds (parser + AST):

- `CallSource` — a source written as a function call with named arguments, e.g.
  `analytics(dx: "fbfJHSPpUQD", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd")` and
  `dataValues(dataSet: "BfMAe6Itzgt", period: "202401", orgUnit: "ImspTQPwCqd")`.
  Add a `CallSource(name, args: list[ObjectField])` node and a parser branch (an identifier
  followed by `(` in source position). This is the only grammar addition Phase 2 needs.

New stage:

- `aggregate by <expr> { total: sum(value), n: count() }` — group rows by a key expression and
  reduce each group with d2path aggregate functions (`sum`/`avg`/`min`/`max`/`count`). Add an
  `AggregateStage` node, parser rule, and an executor branch that groups then builds one object per
  group. (The existing `count` stage is its degenerate case.)

DHIS2 binding (in the `query` plugin, three trees):

- `AnalyticsDataSource` — resolves `analytics(...)` by calling the existing
  `analytics/service.query_analytics`; converts the columnar `Grid` (headers + rows) into row
  dicts keyed by header name (`dx`, `pe`, `ou`, `value`, ...) so d2path navigates them naturally.
  Capabilities: dimensions/filters are the natural pushdown (the planner maps `where dx = ...`
  and friends to analytics dimensions).
- `AggregateDataSource` — resolves `dataValues(...)` by calling `aggregate/service.get_data_values`;
  rows are `DataValue` models (navigable as `dataElement`, `period`, `orgUnit`, `value`).
- `Dhis2Binder` gains a registry of these virtual sources alongside the metadata resource catalog.

Result: `analytics(dx: "...", pe: "LAST_12_MONTHS", ou: "...") | where value > 100 | transform { de: dx, period: pe, v: value } | order v desc`.

## Phase 3 — event and tracker data

Goal: query tracker events, enrollments, and tracked entities, including their nested data values
and attributes.

New source kinds (CallSource reused):

- `events(program: "...", orgUnit: "...", status: "COMPLETED")`
- `enrollments(program: "...", orgUnit: "...")`
- `trackedEntities(trackedEntityType: "...", program: "...", orgUnit: "...")`

DHIS2 binding (three trees): `TrackerDataSource` backed by `tracker/service.list_events` /
`list_enrollments` / `list_tracked_entities`. Rows are `TrackerEvent` / `TrackerEnrollment` /
`TrackerTrackedEntity` models. d2path already navigates these — e.g.
`events(program: "...") | where dataValues.where(dataElement = "abc").value > 10 | select event, occurredAt`
and `trackedEntities(...) | transform { id: trackedEntity, name: attributes.where(attribute = "w75KJ2mc4zz").value }`.

Pushdown: program/orgUnit/status/date filters map to the tracker query params; per-event d2path
predicates over `dataValues` stay local.

## Cross-cutting workstreams

- **Thousands of examples from live instances.** Extend `generate.py` to build a `SchemaSpec` from a
  live instance's resource catalog and a sampling of real field names / option values (scraped via
  the metadata service against the public dev instances at `im.dhis2.org`, v41/v42/v43). The full
  catalog (~150 resources) yields several thousand parse-valid programs per version, each guaranteed
  valid against that instance. A harness runs the corpus through `explain` (offline) and a sampled
  subset through `eval` (read-only, against the dev instances) to catch regressions.
- **Web playground (shadcn).** A `dhis2w-web` FastAPI member exposes the engine
  (`POST /parse|/explain|/eval|/d2path`, `GET /samples|/resources`) and serves a Vite + React +
  Tailwind + shadcn/ui SPA: a sample gallery (curated `SAMPLES` + generated corpus), an editor, a
  results table / JSON / explain view, and a d2path tester. The samples catalog is the single
  source the gallery reads.
- **Tests, docs, examples.** Per-version example files (`examples/v{41,42,43}/cli|mcp|client`), the
  `docs/guides/d2ql.md` and `docs/guides/d2path.md` guides, `docs/api/query.md`, and the pytest
  suites (engine unit tests, a parse-conformance test over `SAMPLES` + `generate()`, and
  respx-mocked plugin integration tests).
