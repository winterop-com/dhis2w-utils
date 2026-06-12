# Analytics plugin

`dhis2w-core/v42/plugins/analytics/` wraps DHIS2's analytics API at `/api/analytics` and the analytics-table management endpoint at `/api/resourceTables/analytics`. The analytics engine is DHIS2's aggregation pipeline — pre-computed tables behind every dashboard, pivot table, and data query.

## What it exposes

| Operation | CLI | MCP tool |
| --- | --- | --- |
| Aggregated query | `d2w analytics query` | `analytics_query` |
| Raw (pre-aggregation) query | `d2w analytics query --shape raw` | `analytics_query (shape=raw)` |
| DataValueSet-shaped output | `d2w analytics query --shape dvs` | `analytics_query (shape=dvs)` |
| Trigger analytics rebuild | `d2w maintenance refresh analytics` | `maintenance_refresh_analytics` |

Refresh commands live under `d2w maintenance refresh ...` — see the [maintenance plugin](maintenance-plugin.md) for the full surface. This page focuses on the query side.

## Dimensions and filters

Every analytics query is built from **dimensions** (rows/columns you want to see) and **filters** (rows/columns you want to constrain but not display).

Each dimension is a string `<type>:<UID[;UID...]>` or `<type>:<keyword>`:

| Type prefix | What it is | Example |
| --- | --- | --- |
| `dx` | Data — data elements, indicators, data sets, event data | `dx:fbfJHSPpUQD;cYeuwXTCPkU` |
| `pe` | Periods | `pe:LAST_12_MONTHS` or `pe:202401;202402` |
| `ou` | Organisation units | `ou:ImspTQPwCqd` or `ou:LEVEL-2;OU_GROUP-ABC` |
| `co` | Category option combos | `co:KsP9obVY8jF` |
| `ao` | Attribute option combos | `ao:...` |

Period keywords DHIS2 understands include `LAST_12_MONTHS`, `LAST_6_MONTHS`, `THIS_MONTH`, `LAST_YEAR`, `THIS_QUARTER`, `LAST_4_QUARTERS`, `LAST_5_YEARS`, etc.

## CLI examples

```bash
# Simple aggregated query: one data element over the last 12 months at a specific org unit
d2w analytics query \
  --dim dx:fbfJHSPpUQD \
  --dim pe:LAST_12_MONTHS \
  --dim ou:ImspTQPwCqd \
  --skip-meta

# Multiple data elements + a filter
d2w analytics query \
  --dim 'dx:fbfJHSPpUQD;cYeuwXTCPkU' \
  --dim pe:LAST_12_MONTHS \
  --dim ou:ImspTQPwCqd \
  --filter co:KsP9obVY8jF \
  --agg SUM \
  --output-id-scheme NAME

# Raw data variant (no server-side aggregation)
d2w analytics query --shape raw \
  --dim dx:fbfJHSPpUQD \
  --dim pe:LAST_3_MONTHS \
  --dim ou:ImspTQPwCqd

# DataValueSet shape (for pipelines that want dataValues[] output)
d2w analytics query --shape dvs \
  --dim dx:fbfJHSPpUQD \
  --dim pe:LAST_12_MONTHS \
  --dim ou:ImspTQPwCqd

# Trigger a rebuild of the analytics tables (async; returns a task reference).
d2w maintenance refresh analytics --last-years 2

# Same, but stream notifications until the table rebuild reports completed=true.
d2w maintenance refresh analytics --last-years 2 --watch --interval 1 --timeout 300

# Event analytics — line-listed events in a program.
d2w analytics events query <PROG_UID> \
  --dim pe:LAST_12_MONTHS \
  --dim ou:<OU_UID> \
  --stage <STAGE_UID>

# Event analytics — aggregated counts grouped by the supplied dimensions.
d2w analytics events query <PROG_UID> --mode aggregate \
  --dim dx:<DATA_ELEMENT_UID> --dim pe:LAST_12_MONTHS --dim ou:<OU_UID>

# Enrollment analytics — line-listed enrollments.
d2w analytics enrollments query <PROG_UID> \
  --dim pe:LAST_12_MONTHS --start-date 2026-01-01 --end-date 2026-06-30
```

## MCP examples

```python
# Aggregated query
await mcp.call_tool("analytics_query", {
    "dimensions": [
        "dx:fbfJHSPpUQD;cYeuwXTCPkU",
        "pe:LAST_12_MONTHS",
        "ou:ImspTQPwCqd",
    ],
    "aggregation_type": "SUM",
    "output_id_scheme": "NAME",
    "include_num_den": True,
})

# Raw
await mcp.call_tool("analytics_query (shape=raw)", {
    "dimensions": ["dx:fbfJHSPpUQD", "pe:LAST_3_MONTHS", "ou:ImspTQPwCqd"],
})

# Trigger rebuild
await mcp.call_tool("maintenance_refresh_analytics", {"last_years": 2})
```

## Response shape

```json
{
  "headers": [
    {"name": "dx", "column": "Data", "valueType": "TEXT", ...},
    {"name": "pe", "column": "Period", "valueType": "TEXT", ...},
    {"name": "ou", "column": "Organisation unit", "valueType": "TEXT", ...},
    {"name": "value", "column": "Value", "valueType": "NUMBER", ...}
  ],
  "rows": [
    ["fbfJHSPpUQD", "202401", "ImspTQPwCqd", "4852"],
    ["fbfJHSPpUQD", "202402", "ImspTQPwCqd", "4911"],
    ...
  ],
  "metaData": {
    "dimensions": { "dx": [...], "pe": [...], "ou": [...] },
    "items": { "fbfJHSPpUQD": {"name": "Penta1 doses given"}, ... }
  },
  "width": 4,
  "height": N
}
```

`metaData` is the item-name dictionary — use it to translate UIDs to human-readable labels. `skip_meta=True` strips this section for lighter payloads when the caller already knows the UIDs.

## Refresh is asynchronous

`maintenance_refresh_analytics` returns a DHIS2 task reference:

```json
{"response": {"id": "KjN4PQxQDkO", "jobType": "ANALYTICS_TABLE"}}
```

Poll `/api/system/tasks/ANALYTICS_TABLE/{taskId}` to watch progress. A typical refresh on a small instance takes 1–5 minutes; production instances can be 30+ minutes. The analytics tables need regeneration whenever data values change beyond the last-refresh window.

## Output ID schemes

By default, UIDs stay as UIDs in responses. Set `output_id_scheme` to:

- `UID` — default
- `NAME` — replace UIDs with display names (human-readable)
- `CODE` — use the object's code field if set
- `ID` — numeric database ID (not recommended; changes across instances)

## Outlier detection

`/api/analytics/outlierDetection` flags anomalous data values against the
standard-deviation profile of their series. Three algorithms supported
upstream: `Z_SCORE` (default), `MODIFIED_Z_SCORE` (median-based, robust to
existing outliers), and `MIN_MAX` (hard-bound cutoffs).

```bash
# Outliers across one data set + the Kambia org unit for the last 12 months:
d2w analytics outlier-detection \
    --data-set BfMAe6Itzgt \
    --org-unit PMa2VCrupOd \
    --period LAST_12_MONTHS \
    --algorithm Z_SCORE --threshold 2.0 --max-results 10

# Or a narrow set of data elements over an explicit date range:
d2w analytics outlier-detection \
    --data-element fClA2Erf6IO --data-element I78gJm4KBo7 \
    --org-unit jUb8gELQApl \
    --start-date 2025-01-01 --end-date 2025-12-31 \
    --algorithm MODIFIED_Z_SCORE
```

Returns a typed `OutlierDetectionResponse` (OAS-generated):
`.metadata` has the effective algorithm + threshold + count; `.outlierValues`
is a list of `OutlierValue` entries with `de`, `deName`, `pe`, `ou`, `ouName`,
`value`, `mean`, `stdDev`, `absDev`, and `zScore`.

## Tracked entity analytics

`/api/analytics/trackedEntities/query/{TET_UID}` line-lists tracked entities
of a given type, with the same dimension/filter grammar as event/enrollment
analytics.

```bash
d2w analytics tracked-entities query FsgEX4d3Fc5 \
    --dimension ou:ImspTQPwCqd --ou-mode DESCENDANTS \
    --program IpHINAT79UW \
    --page-size 50 --asc created
```

Returns the `Grid` envelope with the familiar headers/rows/metaData shape.
Useful for exporting a TET slice to external BI or building a registry view;
the `--asc` / `--desc` flags sort on any response column.

## Resource-table regeneration

Three endpoints rebuild different layers of DHIS2's analytics backing store:

| Command | Endpoint | Job type | Rebuilds |
|---|---|---|---|
| `d2w maintenance refresh analytics` | `/api/resourceTables/analytics` | `ANALYTICS_TABLE` | Full star schema (fact + dim tables). Also refreshes resource tables unless `--skip-resource-tables`. |
| `d2w maintenance refresh resource-tables` | `/api/resourceTables` | `RESOURCE_TABLE` | Supporting OU / category hierarchy tables only — skip the analytics star schema. |
| `d2w maintenance refresh monitoring` | `/api/resourceTables/monitoring` | `MONITORING` | Tables backing DHIS2's data-quality / validation-rule monitoring (validation-rule evaluation reads from these). Bundled into `refresh analytics` unless skipped; standalone rebuild is rarely needed. |

All three accept `--watch` / `-w` to stream the job to completion via
`/api/system/tasks/{jobType}/{taskUid}`. Library callers use
`service.refresh_analytics` / `refresh_resource_tables` / `refresh_monitoring`
— each returns a `WebMessageResponse` whose `.task_ref()` pairs with
`client.tasks.await_completion` for typed async waits.

## Not yet exposed

- **Measure criteria with multiple operators** — `--measure-criteria EQ:42:GT:100` etc.
- **Response format overrides** — `.csv`, `.xml`, `.xlsx` variants available via `client.analytics.stream_to` in the library; not yet on the CLI.

The plugin's `service.py` is small; extensions land as new service functions + one CLI command + one MCP tool per.
