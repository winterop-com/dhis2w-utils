#!/usr/bin/env bash
# `d2w metadata visualizations ...` and `d2w metadata dashboards ...` —
# visualization authoring + dashboard composition from the terminal.
#
# A DHIS2 Visualization is a saved analytics query with a chart type +
# axis placement attached. Chart rendering depends on dimensional
# placement (see `d2w --json metadata visualizations get | jq '.rowDimensions,
# .columnDimensions, .filterDimensions'`). When in doubt, prove the
# data path first: run an analytics query with the same dx/pe/ou
# selection before saving the viz.
set -euo pipefail

# Seeded DEs + OUs — swap for your own to run against a real instance.
DE_PENTA1=fClA2Erf6IO
DE_MEASLES=YtbsuPPo010
OU_ROOT=ImspTQPwCqd
PROVINCES=(jUb8gELQApl PMa2VCrupOd qhqAxPSTUXp kJq2mPyFEHo)
DASHBOARD=TAMlzYkstb7

# ---------------------------------------------------------------------------
# List + inspect
# ---------------------------------------------------------------------------

# Every visualization, sorted by name. Filter by type to scope.
d2w metadata list visualizations
d2w metadata list visualizations --filter type:eq:LINE

# Show one viz with its axes, data elements, periods, and org units.
d2w metadata visualizations get Qyuliufvfjl

# Same as show but emits the full JSON payload — pipe into jq.
d2w --json metadata visualizations get Qyuliufvfjl | jq '.type, .rowDimensions, .columnDimensions, .filterDimensions'

# ---------------------------------------------------------------------------
# Create from flags — no hand-rolled JSON required
# ---------------------------------------------------------------------------

# Simplest case: LINE default placement (rows=[pe], columns=[ou], filters=[dx]).
# Multi-line chart with one line per district, 2024 monthly.
d2w metadata visualizations create \
    --name "Penta1 monthly by district (demo)" \
    --type LINE \
    --de "$DE_PENTA1" \
    --pe 202401 --pe 202402 --pe 202403 --pe 202404 \
    --pe 202405 --pe 202406 --pe 202407 --pe 202408 \
    --pe 202409 --pe 202410 --pe 202411 --pe 202412 \
    --ou "${PROVINCES[0]}" --ou "${PROVINCES[1]}" \
    --ou "${PROVINCES[2]}" --ou "${PROVINCES[3]}" \
    --uid VizCliDem01

# Explicit dimensional placement — one line per data element instead of per district.
d2w metadata visualizations create \
    --name "Penta1 vs Measles — Sierra Leone monthly" \
    --type LINE \
    --de "$DE_PENTA1" --de "$DE_MEASLES" \
    --pe 202401 --pe 202406 --pe 202412 \
    --ou "$OU_ROOT" \
    --category-dim pe \
    --series-dim dx \
    --filter-dim ou \
    --uid VizCliDem02

# PIVOT_TABLE with default placement (rows=[ou], columns=[pe], filters=[dx]).
d2w metadata visualizations create \
    --name "Measles doses by district x month (demo)" \
    --type PIVOT_TABLE \
    --de "$DE_MEASLES" \
    --pe 202401 --pe 202406 --pe 202412 \
    --ou "${PROVINCES[@]/#/--ou }" \
    --uid VizCliDem03 2>/dev/null || true  # bash array expansion above is shell-specific; simpler form below

d2w metadata visualizations create \
    --name "Measles doses by district x month (demo)" \
    --type PIVOT_TABLE \
    --de "$DE_MEASLES" \
    --pe 202401 --pe 202406 --pe 202412 \
    --ou "${PROVINCES[0]}" --ou "${PROVINCES[1]}" \
    --ou "${PROVINCES[2]}" --ou "${PROVINCES[3]}" \
    --uid VizCliDem04

# SINGLE_VALUE tile — big number for a KPI dashboard.
d2w metadata visualizations create \
    --name "Measles doses — 2024 Sierra Leone total" \
    --type SINGLE_VALUE \
    --de "$DE_MEASLES" \
    --pe 2024 \
    --ou "$OU_ROOT" \
    --uid VizCliDem05

# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------

# Clone the multi-line chart with a renamed display title.
d2w metadata visualizations clone VizCliDem01 \
    --new-name "Penta1 monthly by district (2025 preview)" \
    --new-uid VizCliCln01 \
    --new-description "Clone of the 2024 demo chart — period set matches source"

# ---------------------------------------------------------------------------
# Compose a dashboard
# ---------------------------------------------------------------------------

# Auto-stack a new item below everything already on the dashboard.
d2w metadata list dashboards
d2w metadata dashboards get "$DASHBOARD"

# Add the demo line chart to the overview dashboard (auto-stack, full width).
d2w metadata dashboards add-item "$DASHBOARD" --viz VizCliDem01

# Add two KPI tiles side-by-side above the auto-stack line. Pass explicit
# slot so the tiles share a row.
d2w metadata dashboards add-item "$DASHBOARD" --viz VizCliDem05 \
    --x 0 --y 95 --width 20 --height 15
d2w metadata dashboards add-item "$DASHBOARD" --viz VizCliCln01 \
    --x 20 --y 95 --width 40 --height 15

# Show the dashboard again to confirm placement.
d2w metadata dashboards get "$DASHBOARD"

# ---------------------------------------------------------------------------
# Clean up — keep reruns idempotent
# ---------------------------------------------------------------------------

# Remove items we added (item UID comes from `d2w metadata dashboards get`).
# Adjust the UIDs below if you run this against a fresh instance.

# d2w metadata dashboards remove-item "$DASHBOARD" <item-uid>

# Delete the demo vizes.
d2w metadata visualizations delete VizCliDem01 -y
d2w metadata visualizations delete VizCliDem02 -y
d2w metadata visualizations delete VizCliDem04 -y
d2w metadata visualizations delete VizCliDem05 -y
d2w metadata visualizations delete VizCliCln01 -y

# ---------------------------------------------------------------------------
# Generic CRUD still works for the raw surface
# ---------------------------------------------------------------------------

d2w metadata list visualizations --fields 'id,name,type' --order 'lastUpdated:desc' --page-size 5
d2w metadata list dashboards --fields 'id,name'
