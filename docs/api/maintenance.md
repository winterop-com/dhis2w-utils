# Maintenance

`MaintenanceAccessor` on `Dhis2Client.maintenance` — the data-integrity reader (`get_integrity_report`, `iter_integrity_issues`), the on-demand CategoryOptionCombo matrix regeneration (`update_category_option_combos`), and the analytics-table build trigger (`run_analytics_tables`). Predictor and validation runs live on their own accessors; see [Validation + predictors](validation.md).

## When to reach for it

- Run DHIS2's built-in data-integrity scan (81 checks) and pull the typed report.
- Stream tagged integrity issues as they're emitted (large instances can have thousands; `iter_integrity_issues` is the streaming consumer).
- Trigger COC matrix regeneration after a `CategoryCombo` save on v43 (`update_category_option_combos`) — see also [`category_combos.wait_for_coc_generation`](category-combos.md) for the polling helper that pairs with it.
- Build the analytics tables after a data push (`run_analytics_tables`) and follow the job through `client.tasks`.

## Worked example — stream integrity issues

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    # `iter_integrity_issues` is an async iterator — one `IntegrityIssueRow`
    # per row as DHIS2 emits it; safe for instances with thousands of issues.
    # Each row carries the owning check's metadata (`check_name`,
    # `check_display_name`, `severity`) plus the typed issue itself
    # (`row.issue.name`, `row.issue.id`, `row.issue.comment`).
    severity_counts: dict[str, int] = {}
    async for row in client.maintenance.iter_integrity_issues():
        sev = row.severity or "UNKNOWN"
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if severity_counts[sev] <= 3:
            print(f"  [{sev}] {row.check_display_name or row.check_name}: {row.issue.name} ({row.issue.id})")
    print(f"total by severity: {severity_counts}")
```

## Worked example — full integrity report (snapshot, not stream)

```python
async with open_client(profile_from_env()) as client:
    # Returns a typed `DataIntegrityReport` carrying `.results`, a
    # `dict[str, DataIntegrityResult]` keyed by check name. Each result
    # has `.name`, `.severity`, `.count`, and `.issues` (list of
    # DataIntegrityIssue with `.name`, `.id`, `.comment`).
    report = await client.maintenance.get_integrity_report()
    print(f"{len(report.results)} checks ran")
    for check_key, result in list(report.results.items())[:5]:
        print(f"  {check_key}  severity={result.severity}  issues={len(result.issues)}")
```

## Worked example — build the analytics tables

`run_analytics_tables` POSTs `/api/resourceTables/analytics` and returns the job-kickoff `WebMessageResponse`. `last_years` caps how many years the tables cover; each `skip_*` flag drops one build phase and is only sent when set. The envelope's `task_ref()` is what `client.tasks` takes, and `notifier_endpoint()` is the `/api/system/tasks/{jobType}/{uid}` path verbatim.

```python
async with open_client(profile_from_env()) as client:
    envelope = await client.maintenance.run_analytics_tables(last_years=1, skip_outliers=True)
    ref = envelope.task_ref()
    if ref is None:
        raise RuntimeError(f"no job scheduled: {envelope.message}")
    print(f"feed at {envelope.notifier_endpoint()}")

    # Block until DHIS2 posts the terminal notification ...
    completion = await client.tasks.await_completion(ref, timeout=None)
    print(f"{completion.level}  {completion.message}")
```

... or read the feed one poll at a time with `client.tasks.poll_once` when the caller has its own clock; see [Tasks module](tasks.md). The CLI equivalent is `d2w maintenance refresh analytics --watch`, and the MCP tool is `maintenance_refresh_analytics`; both call the plugin service, which wraps this accessor.

## Related examples

- [`examples/client/analytics_tables_poll_once.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/analytics_tables_poll_once.py) — `run_analytics_tables` followed with `client.tasks.poll_once`, one poll per tick.
- [`examples/client/task_await.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/task_await.py) — `run_analytics_tables` blocked on with `client.tasks.await_completion`.
- [`examples/client/integrity_issues_stream.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/integrity_issues_stream.py) — `iter_integrity_issues` + severity histogram + early-break scan.

::: dhis2w_client.v42.maintenance
