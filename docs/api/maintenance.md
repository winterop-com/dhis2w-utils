# Maintenance

`MaintenanceAccessor` on `Dhis2Client.maintenance` — the data-integrity reader (`get_integrity_report`, `iter_integrity_issues`) plus the on-demand CategoryOptionCombo matrix regeneration (`update_category_option_combos`). DHIS2's other background-job triggers (analytics refresh, predictor runs, validation runs, cache clears) live in the matching plugin services and on the CLI / MCP — see [Triggering analytics / monitoring refresh](#triggering-analytics-monitoring-refresh) below for the right entry point.

## When to reach for it

- Run DHIS2's built-in data-integrity scan (81 checks) and pull the typed report.
- Stream tagged integrity issues as they're emitted (large instances can have thousands; `iter_integrity_issues` is the streaming consumer).
- Trigger COC matrix regeneration after a `CategoryCombo` save on v43 (`update_category_option_combos`) — see also [`category_combos.wait_for_coc_generation`](category-combos.md) for the polling helper that pairs with it.

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

## Triggering analytics / monitoring refresh

The accessor doesn't expose a refresh trigger directly — refresh is a plugin-service surface, not a raw-client one. Three real paths:

1. **CLI**: `d2w maintenance refresh analytics --watch`.
2. **MCP**: `maintenance_refresh_analytics` tool with `watch=true`.
3. **Python via plugin service**: import `dhis2w_core.v42.plugins.maintenance.service.refresh_analytics(profile, ...)` directly — see [`examples/client/task_polling.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/task_polling.py) for the full kick-off + poll-with-`client.tasks.await_completion` pattern.

## Related examples

- [`examples/client/task_polling.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/task_polling.py) — kick off an analytics refresh via raw `client.post_raw("/api/resourceTables/analytics", ...)` + block on it with `client.tasks.await_completion`.
- [`examples/client/integrity_issues_stream.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/integrity_issues_stream.py) — `iter_integrity_issues` + severity histogram + early-break scan.

::: dhis2w_client.v42.maintenance
