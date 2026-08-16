# d2ql roadmap

Phase 1 (metadata) is in place: the d2ql pipeline language, the d2path expression language, the
engine (planner + executor + sinks + definitions), and a `query` plugin across v41/v42/v43 with
CLI and MCP surfaces. This roadmap covers the next phases. The engine seam stays fixed: each phase
adds **new source kinds** and, where needed, **new stages** — the parser AST, evaluator, planner,
and sinks are reused, not rewritten.

## Phase 2 — aggregate data (DONE)

Shipped: a `CallSource` node (`analytics(...)`, `dataValues(...)`) and an `AggregateStage`
(`group by <expr> { total: sum(value), n: count() }`) in the parser/AST/executor; aggregate
d2path functions (`sum`/`avg`/`min`/`max`/`count`) take an optional field argument. The `query`
plugin binds `analytics(...)` to `analytics/service.query_analytics` (columnar `Grid` → row dicts
keyed by dimension) and `dataValues(...)` to `aggregate/service.get_data_values` (typed `DataValue`
rows) via `Dhis2Binder.bind_call`, across all three version trees. Verified live against play42, e.g.
`analytics(dx: "...", pe: "LAST_12_MONTHS", ou: "...") | where value > 1000 | group by dx { total: sum(value), periods: count() } | order total desc`.

Follow-ups: push analytics dimensions/filters down (currently fetched whole, reduced locally), and a
fast-path that maps a metadata `... | count` to `count_metadata` instead of fetching all rows.

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

- **Streaming execution for large result sets.** Today the engine is fully materialized: a
  `DataSource.fetch` returns `list[Any]`, the metadata source uses `list_metadata` (whole response;
  `limit` caps it via `pageSize`), and the analytics source returns the entire `Grid` in one
  response — so a huge analytics query is memory-bound. The seam to fix it is small: make
  `DataSource.fetch` return an async iterator (the metadata service already has the paginated
  `iter_metadata` generator), and have the executor stream rows through the non-blocking stages
  (`where`/`select`/`transform`/`skip`/`limit`) while only the blocking ones (`order`/`group by`/
  `fold`) materialize. Combined with the NDJSON sink, that gives constant-memory export. Until then,
  bound large queries with `limit` (metadata) and dimension narrowing (analytics). Analytics has no
  server-side paging for aggregate data; events/enrollments analytics do and can page when wired.
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
- **Tests, docs, examples.** The example files (`examples/{cli,mcp,client}/`), the
  `docs/guides/d2ql.md` and `docs/guides/d2path.md` guides, `docs/api/query.md`, and the pytest
  suites (engine unit tests, a parse-conformance test over `SAMPLES` + `generate()`, and
  respx-mocked plugin integration tests).
