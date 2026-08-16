# Maintenance plugin

`d2w maintenance` wraps the DHIS2 server's maintenance surface: background-task polling, cache reset, soft-delete cleanup, and data-integrity checks. Every long-running DHIS2 operation returns a task UID — the `task` sub-tree is the shared polling surface those UIDs feed into.

- CLI: `d2w maintenance {task,cache,cleanup,dataintegrity}`
- MCP: `maintenance_{task_types,task_list,task_status,cache_clear,cleanup_soft_deleted,dataintegrity_checks,dataintegrity_run,dataintegrity_result}`
- Models: `Notification`, `DataIntegrityCheck`, `DataIntegrityResult`, `DataIntegrityReport` — all exported from `dhis2w_client`.

## Tasks

DHIS2 records every background job under `/api/system/tasks`. Three levels:

| Endpoint | Shape | Surfaces as |
|---|---|---|
| `GET /api/system/tasks` | `{TaskType: {uid: [notifications]}}` | `task types` |
| `GET /api/system/tasks/{type}` | `{uid: [notifications]}` | `task list <type>` |
| `GET /api/system/tasks/{type}/{uid}` | `[Notification]` | `task status <type> <uid>` |

```bash
# Which job types does this instance track?
d2w maintenance task types

# Which task UIDs exist for ANALYTICS_TABLE?
d2w maintenance task list ANALYTICS_TABLE

# Every notification emitted by one task, oldest first.
d2w maintenance task status ANALYTICS_TABLE e1xqWiuxDce

# Stream notifications as they arrive; exits on the first completed=true row.
d2w maintenance task watch DATA_INTEGRITY <uid> --interval 1 --timeout 120
```

`Notification` fields: `level` (`INFO`/`WARN`/`ERROR`), `category` (the task type), `message`, `completed`, `time`, `uid`, `id`. DHIS2 returns newest-first; the service reverses to chronological so `task status` reads top-to-bottom with the job.

`task watch` de-duplicates rows by `uid`/`id`/`time` so a long poll doesn't print the same notification twice when DHIS2 returns them repeatedly. Pass `--timeout none` (or `None` via the service API) to wait forever — useful for multi-minute analytics rebuilds.

## Cache

```bash
d2w maintenance cache
```

POSTs `/api/maintenance/cache` (204 No Content). Drops every server-side cache — Hibernate session cache, Ehcache, the DHIS2 app-settings cache. Useful after a SQL-level config change so the server re-reads from disk.

## Soft-delete cleanup

`d2w data aggregate delete` and `d2w data tracker push` with `importStrategy=DELETE` don't actually remove rows — they mark them `deleted=true` so DHIS2 can preserve audit trails. Soft-deleted children block parent-metadata removal (see BUGS.md #2). The cleanup sub-commands hit the dedicated maintenance endpoints to purge each kind:

```bash
d2w maintenance cleanup data-values         # POST /api/maintenance/softDeletedDataValueRemoval
d2w maintenance cleanup events              # POST /api/maintenance/softDeletedEventRemoval
d2w maintenance cleanup enrollments         # POST /api/maintenance/softDeletedEnrollmentRemoval
d2w maintenance cleanup tracked-entities    # POST /api/maintenance/softDeletedTrackedEntityRemoval
```

Each POST returns 204 No Content when successful; run in order (entities → enrollments → events → data values) when dismantling a full tracker program.

## Data integrity

DHIS2 ships ~108 data-integrity checks (v42). Each has a stable `name` (query-param value when running it), a `displayName`, `section`, `severity` (`INFO`/`WARNING`/`SEVERE`/`CRITICAL`), `description`, and `recommendation`.

```bash
# Catalog — every built-in check.
d2w maintenance dataintegrity list

# Kick off a summary run on one check (or omit for all). Async — returns
# a JobConfigurationWebMessageResponse whose response.id is the task UID.
d2w maintenance dataintegrity run orgunits_invalid_geometry

# Same, but populates issues[] per check (heavier; use on specific checks).
d2w maintenance dataintegrity run orgunits_invalid_geometry --details

# Read stored results. Summary mode gives per-check `count`; details gives issues[].
d2w maintenance dataintegrity result orgunits_invalid_geometry
d2w maintenance dataintegrity result orgunits_invalid_geometry --details
```

`run` kicks off the job; `result` reads what the job stored. Pass `--watch/-w` to have `run` poll to completion itself — it extracts `jobType` + `id` from the response envelope and streams notifications:

```bash
d2w maintenance dataintegrity run orgunits_invalid_geometry -w --interval 1 --timeout 60
d2w maintenance dataintegrity result orgunits_invalid_geometry
```

The same `--watch/-w` flag is on every command that returns a JobConfigurationWebMessageResponse (today: `d2w maintenance refresh analytics`, `d2w maintenance dataintegrity run`). For cases where you only have a task UID — not the response envelope — use the lower-level `d2w maintenance task watch <type> <uid>` directly.

DHIS2 uses separate job types for the two data-integrity modes: `DATA_INTEGRITY` for summary, `DATA_INTEGRITY_DETAILS` for details — `--watch` picks the right one from the response, but pass the matching type explicitly if you're calling `task watch` yourself.

## Library API

Every operation is a plain async function in `dhis2w_core.v42.plugins.maintenance.service`:

```python
from dhis2w_core.v42.plugins.maintenance import service
from dhis2w_core.v42.plugins.maintenance.service import SoftDeleteTarget

await service.list_task_types(profile)
await service.watch_task(profile, "DATA_INTEGRITY", task_uid, interval=1.0)
await service.clear_cache(profile)
await service.remove_soft_deleted(profile, SoftDeleteTarget.DATA_VALUES)
await service.run_dataintegrity(profile, checks=["check_a"], details=False)
report = await service.get_dataintegrity_summary(profile)
```

The `DataIntegrityReport.results: dict[check_name, DataIntegrityResult]` shape mirrors DHIS2's response shape directly — iterate `.results.items()` to render tables or filter by severity.

### `client.maintenance` — streaming accessor on the client

The client exposes the read side directly so callers can avoid the `service` + `profile` round-trip when they already have an open `Dhis2Client`:

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    # Full typed report — same shape as service.get_dataintegrity_summary / _details.
    report = await client.maintenance.get_integrity_report(details=True)

    # Flat stream — one IntegrityIssueRow at a time, each tagged with the
    # owning check's name / displayName / severity. Break mid-stream at will.
    async for row in client.maintenance.iter_integrity_issues():
        if (row.severity or "").upper() == "WARNING":
            print(f"{row.check_name}: {row.issue.id}  {row.issue.name}")
```

`iter_integrity_issues(checks=[...])` narrows to specific checks. DHIS2's `/api/dataIntegrity/details` returns the full `{check_name: {issues: [...]}}` map in one response; the iterator flattens + tags it so you don't have to walk the two-level shape manually. See `examples/client/integrity_issues_stream.py` for a worked example (severity histogram + noisiest-checks table + early-break scan).

Writes — kicking off a run, clearing cache — stay on `service.*` because they need the `Profile` for OAuth2 token-store keying.

## Validation rules + predictors

Two sibling workflows live under `d2w maintenance`:

```
d2w maintenance validation run <ou> --start-date ... --end-date ...
d2w maintenance validation result {list,get,delete}
d2w maintenance validation validate-expression "<expr>" [--context ...]
d2w maintenance validation send-notifications
d2w maintenance predictors run --start-date ... --end-date ... [--predictor|--group]
```

CRUD on the rules / predictors themselves stays on the generic metadata
surface (`d2w metadata list validationRules` / `get` / `patch` +
`d2w metadata list predictors`). What's plugin-scoped here is the
*workflow* side — running the rules against live data, polling
violations, firing notifications, running predictor expressions to emit
synthetic data values.

### `client.validation` — run + results + expression checks

```python
async with open_client(profile_from_env()) as client:
    # Parse-check an expression against the validation-rule parser.
    description = await client.validation.describe_expression(
        "#{fClA2Erf6IO} > 0",
        context="validation-rule",
    )
    assert description.valid, description.message

    # Run every rule on the Sierra Leone sub-tree for 2025.
    violations = await client.validation.run_analysis(
        org_unit="ImspTQPwCqd",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    # List persisted results (populated by earlier runs with `persist=True`).
    results = await client.validation.list_results(org_unit="ImspTQPwCqd")

    # Bulk-delete (at least one filter required — can't wipe the whole table).
    await client.validation.delete_results(periods=["202412"])
```

`describe_expression` accepts the full context set: `generic` /
`validation-rule` / `indicator` / `predictor` / `program-indicator`.
Each hits a different DHIS2 parser; `validation-rule` and friends POST
the expression as `text/plain`, `generic` GETs it as a query parameter.

### `client.predictors` — run only, no result endpoint

Predictors produce data values directly (written to `/api/dataValues`);
there's no separate result table. The three run shapes DHIS2 exposes all
return the standard `WebMessageResponse` envelope with an
`ImportCount`:

```python
envelope = await client.predictors.run_all(start_date="2025-01-01", end_date="2025-12-31")
count = envelope.import_count()
# count.imported / .updated / .ignored — predictions emitted.

# Or scoped:
await client.predictors.run_one(uid, start_date=..., end_date=...)
await client.predictors.run_group(group_uid, start_date=..., end_date=...)
```

All three are synchronous — DHIS2 doesn't expose a job variant for
predictors, so `--watch` isn't wired. For a large sweep, split by
`PredictorGroup` and run concurrently from Python via `asyncio.gather`.

### MCP tools

`maintenance_validation_run`, `maintenance_validation_result_list`,
`maintenance_validation_validate_expression`, `maintenance_predictors_run`.
Same service layer as the CLI.
