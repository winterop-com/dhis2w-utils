# Visualizations + dashboards — step-by-step guide

DHIS2 visualizations are saved analytics queries with a chart type and axis placement attached. Every chart you see in the DHIS2 UI is a persisted `/api/analytics` query rendered by the chart plugin — which means two things:

1. **Writing a visualization is writing an analytics query, plus rendering hints.** If `client.analytics.aggregate(...)` produces the right numbers, the same `dx` / `pe` / `ou` selection turned into a `VisualizationSpec` will produce the right chart.
2. **Debugging a broken chart starts with the analytics query.** Before blaming the viz config, run the equivalent analytics query and confirm the values are non-zero.

This guide walks through the authoring + dashboard-composition loop end-to-end. The worked examples target the seeded v42 stack (see `infra/scripts/build_e2e_dump.py` for UIDs).

## Prerequisites

- A profile pointing at your instance (`dhis2 profile list`).
- Analytics tables populated — `dhis2 maintenance refresh analytics` if it's been a while.
- Seeded demo data (`make dhis2-seed`).

## 1. Start from the analytics query

The seeded stack has four districts (`jUb8gELQApl`, `PMa2VCrupOd`, `qhqAxPSTUXp`, `kJq2mPyFEHo`) and data elements including `fClA2Erf6IO` (Penta1 doses given). To chart Penta1 doses per district for 2024, first confirm the data is actually there:

```bash
dhis2 analytics query \
  --dim dx:fClA2Erf6IO \
  --dim 'pe:202401;202402;202403;202412' \
  --dim 'ou:jUb8gELQApl;PMa2VCrupOd;qhqAxPSTUXp;kJq2mPyFEHo'
```

You should see rows per district × period with non-zero values. If not, the visualization can't render either — fix the data first.

## 2. Author with `VisualizationSpec`

`VisualizationSpec` captures the dimensional query plus a chart type and lets the accessor handle the full round-trip:

```python
from dhis2w_client import VisualizationSpec
from dhis2w_client.generated.v42.enums import VisualizationType
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async def main():
    async with open_client(profile_from_env()) as client:
        spec = VisualizationSpec(
            name="Penta1 doses — monthly by district (2024)",
            viz_type=VisualizationType.LINE,
            data_elements=["fClA2Erf6IO"],
            periods=[f"2024{m:02d}" for m in range(1, 13)],
            organisation_units=["jUb8gELQApl", "PMa2VCrupOd", "qhqAxPSTUXp", "kJq2mPyFEHo"],
        )
        viz = await client.visualizations.create_from_spec(spec)
        print(f"created {viz.id}: {viz.name}")
```

The spec's default placement for `LINE` is `rows=[pe]` / `columns=[ou]` / `filters=[dx]`, so time runs along the x-axis with one line per district. That's what the dashboard app expects for a time-series chart. If you want one line per data element instead (say comparing Penta1 vs Fully Immunized over time), pass two DEs and override the placement:

```python
spec = VisualizationSpec(
    name="Penta1 vs Fully Immunized — Sierra Leone monthly",
    viz_type=VisualizationType.LINE,
    data_elements=["fClA2Erf6IO", "UOlfIjgN8X6"],
    periods=[f"2024{m:02d}" for m in range(1, 13)],
    organisation_units=["ImspTQPwCqd"],
    category_dimension="pe",   # x-axis stays as time
    series_dimension="dx",     # one line per data element
    filter_dimension="ou",     # single root org unit
)
```

### Rolling windows via `RelativePeriod`

Explicit period IDs like `"202401"` freeze to a calendar month. For charts that should "follow the data" — always show the last 12 months, the last 5 years, this quarter, yesterday — pass a `relative_periods` set instead. The spec emits DHIS2's `relativePeriods` block on the wire, matching what the UI authoring screen produces:

```python
from dhis2w_client import RelativePeriod, VisualizationSpec
from dhis2w_client.generated.v42.enums import VisualizationType

spec = VisualizationSpec(
    name="Penta1 doses — rolling last 5 years",
    viz_type=VisualizationType.COLUMN,
    data_elements=["fClA2Erf6IO"],
    relative_periods=frozenset({RelativePeriod.LAST_5_YEARS}),
    organisation_units=["ImspTQPwCqd"],
)
```

`RelativePeriod` covers every window DHIS2 supports (45 total) — daily (`THIS_DAY`, `YESTERDAY`, `LAST_7_DAYS`, …), weekly, monthly (`LAST_12_MONTHS`, `THIS_MONTH`, …), quarterly, and yearly (`LAST_5_YEARS`, `LAST_10_YEARS`, …). `periods` and `relative_periods` can be combined — DHIS2 unions them at query time. At least one has to be set, or the spec rejects the build.

### Indicators + mixed data dimensions

Chart data items aren't limited to data elements. `indicators` takes a list of Indicator UIDs and emits `dataDimensionItems` of type `INDICATOR` alongside any `DATA_ELEMENT` entries:

```python
spec = VisualizationSpec(
    name="Stock coverage indicators — rolling window",
    viz_type=VisualizationType.PIVOT_TABLE,
    indicators=["OEWO2PpiUKx", "bASXd9ukRGD", "loEBZlcsTlx"],
    relative_periods=frozenset({RelativePeriod.LAST_12_MONTHS}),
    organisation_units=["ImspTQPwCqd"],
    category_dimension="dx",   # indicators on rows, not filter
)
```

DHIS2 rejects viz where multiple indicators (or calculations) land on the filter dimension — override `category_dimension="dx"` so they render as row/column categories instead. One of `data_elements` / `indicators` has to be set.

## 3. Pivot tables are just a different default

For tabular breakdowns, flip to `PIVOT_TABLE`:

```python
spec = VisualizationSpec(
    name="Measles doses by district — 2024",
    viz_type=VisualizationType.PIVOT_TABLE,
    data_elements=["YtbsuPPo010"],
    periods=[f"2024{m:02d}" for m in range(1, 13)],
    organisation_units=["jUb8gELQApl", "PMa2VCrupOd", "qhqAxPSTUXp", "kJq2mPyFEHo"],
)
```

The default `PIVOT_TABLE` placement is `rows=[ou]` / `columns=[pe]` / `filters=[dx]`, which renders as districts down the side, months across the top, one data element filter.

## 4. KPI tiles use `SINGLE_VALUE`

Big-number tiles need the grid to collapse to exactly one cell. `SINGLE_VALUE` takes care of that:

```python
spec = VisualizationSpec(
    name="Fully Immunized — 2024 total",
    viz_type=VisualizationType.SINGLE_VALUE,
    data_elements=["UOlfIjgN8X6"],
    periods=["2024"],
    organisation_units=["ImspTQPwCqd"],
)
```

Placement: `rows=[]` / `columns=[dx]` / `filters=[pe, ou]`. DHIS2 resolves to one data element × one period × one org unit = one number.

## 5. Clone an existing chart

Cloning is how most admin workflows iterate — find a chart that's 90% right, clone it, tweak the name / description, and the clone gets a fresh UID but keeps every axis + data selection:

```python
clone = await client.visualizations.clone(
    "Qyuliufvfjl",               # source UID
    new_name="Penta1 doses — 2025 preview",
    new_description="Clone of the 2024 chart with the period bump",
)
# Then swap the periods via a second metadata post if needed:
#   clone.periods = [{"id": pe} for pe in 2025_monthly_periods]
#   await client.visualizations.create_from_spec(...)   # or raw POST
```

`clone()` strips `created` / `lastUpdated` / `createdBy` / `lastUpdatedBy` / `user` / `access` / `favorites` / display-computed fields off the payload so DHIS2 treats the clone as a fresh create. The data dimensions + period selection + organisation units all survive.

## 6. Compose a dashboard

Dashboards are lists of `DashboardItem`s placed on a 60-unit-wide grid. `DashboardsAccessor.add_item` handles read-modify-write against `/api/metadata`:

```python
from dhis2w_client import DashboardSlot

# Auto-stack below existing items — good for append-only builds.
await client.dashboards.add_item("TAMlzYkstb7", "Qyuliufvfjl")

# Or explicit placement — ship two tiles side-by-side in the same row.
await client.dashboards.add_item(
    "TAMlzYkstb7",
    "DNRhUsVbTgT",
    slot=DashboardSlot(x=0, y=0, width=20, height=15),
)
await client.dashboards.add_item(
    "TAMlzYkstb7",
    "pRBQ77mhEJ8",
    slot=DashboardSlot(x=20, y=0, width=20, height=15),
)
```

When `slot` is omitted, the new item's `y` becomes `max(existing_y + existing_height)` — the item appends below every existing item, full width, at default height 20.

To assemble a dashboard from scratch programmatically (e.g. a "monthly PDF" automation):

1. Build every visualization you need via `create_from_spec` — they each return a typed model carrying the server-assigned UID.
2. POST a new Dashboard with an empty `dashboardItems` list via `client.resources.dashboards.create(...)`.
3. Loop through the visualizations, calling `client.dashboards.add_item(dashboard_uid, viz.id, slot=...)` for each.

That pattern powers the seeded Overview dashboard in `infra/scripts/build_e2e_dump.py` — worth reading as a template.

## 7. Render a PNG (screenshot path)

DHIS2 has no native `/api/visualizations/{uid}.png` endpoint. Two paths to a PNG:

- **`dhis2 browser viz screenshot <uid>`** — captures one or more saved Visualizations through the DHIS2 Data Visualizer app. Navigates to `/dhis-web-data-visualizer/#/<uid>` in an authenticated Playwright context, waits for the chart (SVG / canvas / table) to render, hides the outer DHIS2 header, and writes a PNG with an info banner (name / type / instance / user / timestamp). Works across LINE / COLUMN / STACKED / PIVOT_TABLE / SINGLE_VALUE — same session drives every capture so you pay the login cost once.
- **`dhis2 browser dashboard screenshot`** — captures a whole dashboard in the same way. Use this when the composition of several vizes on one dashboard is what you want to see.

Both require the `[browser]` extra (Chromium via Playwright). Install via `uv add 'dhis2w-cli[browser]'` + `playwright install chromium`.

```bash
# One viz.
dhis2 browser viz screenshot --only Qyuliufvfjl

# Every viz on the instance.
dhis2 browser viz screenshot --output-dir ./screenshots

# Whole dashboard (all its items in one PNG).
dhis2 browser dashboard screenshot --only TAMlzYkstb7
```

A lightweight analytics-plus-matplotlib path is also possible (`client.analytics.aggregate(...)` returns the data), but it re-implements DHIS2's chart styling. The browser path is the canonical one — every screenshot test in the e2e suite goes through it.

## 8. Debugging a chart that renders but looks wrong

If the chart renders but the values look off:

1. **Run the equivalent analytics query** (`dhis2 analytics query --dim dx:... --dim pe:... --dim ou:...`) with exactly the UIDs listed in the viz's `dataDimensionItems` / `periods` / `organisationUnits`. If the query returns zeros, analytics tables probably haven't refreshed — `dhis2 maintenance refresh analytics` and retry.
2. **Inspect the stored axes** via `dhis2 --json metadata get visualizations <uid> --fields 'columns[id,items[id]],rows[id,items[id]],filters[id,items[id]]'`. DHIS2 populates these from `rowDimensions` / `columnDimensions` / `filterDimensions` at import time; if they're empty the viz won't render (the importer may have silently dropped them on a hand-rolled PUT — that's why `create_from_spec` routes through `/api/metadata`).
3. **Check chart-type assumptions**. `LINE` with `rows=[dx]` (a single DE) and `columns=[pe]` (12 months) produces one x-axis category with 12 single-point series — a flat line at zero. `LINE` wants time on rows (`pe`) and OU or DE on columns as the series dimension.

The dimensional-placement cheat sheet in the [API reference](../api/visualizations.md#dimensional-placement) covers every viz type. Most "chart looks weird" bugs reduce to a mismatched default.

## From the CLI

Everything above is reachable through `dhis2 metadata visualizations` and `dhis2 metadata dashboards`. The CLI forwards the same flags `VisualizationSpec` consumes; defaults match the library builder.

```bash
# Multi-line Penta1 by district, one command, no hand-rolled JSON.
dhis2 metadata visualizations create \
    --name "Penta1 monthly by district" \
    --type LINE \
    --de fClA2Erf6IO \
    --pe 202401 --pe 202402 --pe 202403 --pe 202404 \
    --pe 202405 --pe 202406 --pe 202407 --pe 202408 \
    --pe 202409 --pe 202410 --pe 202411 --pe 202412 \
    --ou jUb8gELQApl --ou PMa2VCrupOd --ou qhqAxPSTUXp --ou kJq2mPyFEHo

# Override dimensional placement — one line per DE instead of per OU.
dhis2 metadata visualizations create \
    --name "Penta1 vs Measles — Sierra Leone monthly" \
    --type LINE \
    --de fClA2Erf6IO --de YtbsuPPo010 \
    --pe 202401 --pe 202406 --pe 202412 \
    --ou ImspTQPwCqd \
    --category-dim pe --series-dim dx --filter-dim ou

# Clone + compose into a dashboard.
dhis2 metadata visualizations clone VizSourceUid --new-name "2025 preview" --new-uid VizNewClone1
dhis2 metadata dashboards add-item TAMlzYkstb7 --viz VizNewClone1 --x 0 --y 95 --width 60 --height 20
```

Listing goes through the generic metadata surface — `dhis2 metadata list visualizations` (CLI) / `metadata_list(resource="visualizations")` (MCP). The typed authoring verbs each have a CLI command and a matching MCP tool: `get / create / clone / delete` on `metadata visualizations` (`metadata_visualization_*`), and `get / add-item / remove-item` on `metadata dashboards` (`metadata_dashboard_*`).

## Worked examples in `examples/v42/client/`

- `examples/v42/client/viz_create_basic.py` — simplest spec → create → show.
- `examples/v42/client/viz_multiline_by_province.py` — multi-line time-series with one line per district, with an analytics-probe sanity check up front.
- `examples/v42/client/viz_pivot_and_kpi.py` — pivot table + SINGLE_VALUE tile on the same data set, showing the two default placements side-by-side.
- `examples/v42/client/viz_clone_and_modify.py` — clone an existing chart, rename, verify the clone survives deletion of the source.
- `examples/v42/client/dashboard_compose.py` — build a dashboard from scratch with typed `DashboardSlot`s for side-by-side KPI tiles above a full-width line chart.

Each example cleans up after itself so reruns stay idempotent.
