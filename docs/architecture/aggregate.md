# Aggregate plugin

`dhis2w-core/v42/plugins/aggregate/` wraps DHIS2's aggregate data-values endpoints: `/api/dataValueSets` (bulk) and `/api/dataValues` (single). It's the workhorse for reading and writing aggregated data — monthly counts, weekly indicators, period snapshots, etc.

## What it exposes

| Operation | CLI | MCP tool |
| --- | --- | --- |
| Fetch a data value set | `d2w data aggregate get` | `data_aggregate_get` |
| Bulk push values | `d2w data aggregate push <file>` | `data_aggregate_push` |
| Set a single value | `d2w data aggregate set` | `data_aggregate_set` |
| Delete a single value | `d2w data aggregate delete` | `data_aggregate_delete` |

## CLI examples

```bash
# Fetch values for a dataset over a date range, limited to 50 rows
d2w data aggregate get \
  --data-set eigJ6l6i7u9 \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --org-unit IWp9dQGM0bS \
  --children \
  --limit 50

# Bulk push from a JSON file (accepts either a dataValues array or an envelope)
echo '{"dataValues": [{"dataElement": "X", "orgUnit": "Y", "period": "202401", "value": "42"}]}' > values.json
d2w data aggregate push values.json --dry-run

# Set a single value
d2w data aggregate set --de X --pe 202401 --ou Y --value 42 --comment "corrected"

# Delete it
d2w data aggregate delete --de X --pe 202401 --ou Y
```

## MCP examples

```python
# Get
await mcp.call_tool("data_aggregate_get", {
    "data_set": "eigJ6l6i7u9",
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "org_unit": "IWp9dQGM0bS",
    "children": True,
    "limit": 50,
})

# Bulk push with dry-run
await mcp.call_tool("data_aggregate_push", {
    "data_values": [
        {"dataElement": "X", "orgUnit": "Y", "period": "202401", "value": "42"},
    ],
    "dry_run": True,
})

# Single set
await mcp.call_tool("data_aggregate_set", {
    "data_element": "X", "period": "202401", "org_unit": "Y", "value": "42",
})
```

## Important parameters

- **`period`** vs **`start_date`+`end_date`** — DHIS2 accepts either. `period` is a single DHIS2 period (`202401`, `2024W12`, `2024`). Date range gives more flexibility across period types.
- **`org_unit`** + **`children=True`** — `children` includes the unit's descendants. Without it you get only that specific unit.
- **`import_strategy`** — DHIS2 defaults to `CREATE_AND_UPDATE`. Override with `CREATE`, `UPDATE`, or `DELETE` for bulk removal.
- **`dry_run`** — always validates; server returns an import-summary without writing. Use this to check a payload before a real push.

## File shape for `push`

The CLI `push` command accepts either:

```json
[{"dataElement": "X", "orgUnit": "Y", "period": "202401", "value": "42"}]
```

or an envelope:

```json
{
  "dataSet": "Z",
  "dataValues": [
    {"dataElement": "X", "orgUnit": "Y", "period": "202401", "value": "42"}
  ]
}
```

Envelope-level `dataSet`, `period`, `orgUnit` fields become POST-body fields and can be overridden by CLI flags if the caller prefers.

## Errors and quirks

- **409 from `/api/dataValueSets`** on queries without `org_unit` — DHIS2 requires at least one of `orgUnit`, `orgUnitGroup`, or a similar scope. The plugin doesn't enforce this — it's the caller's job to supply something scoped.
- **Single-value POST uses query params, not a JSON body** — DHIS2's `/api/dataValues` accepts `de`, `pe`, `ou`, `value` as query params. The `data_aggregate_set` service handles this transparently via `client.post_raw(..., params=...)`.
- **`value` is always a string** — even for numeric values. DHIS2 coerces server-side based on the data element's `valueType`.

## Not yet exposed

- **Attribute option combos** via UIDs (params are threaded but not exposed in CLI for every command).
- **Audit trail endpoints** (`/api/audits/dataValue`).

Add any of these to the plugin's `service.py` when the need arises; the CLI and MCP surfaces pick up new service functions by adding one decorator each.
