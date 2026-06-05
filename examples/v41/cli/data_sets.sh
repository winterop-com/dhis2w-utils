#!/usr/bin/env bash
# DataSet + Section authoring surface:
#
#   dhis2 metadata data-sets   /api/dataSets
#   dhis2 metadata sections    /api/sections
#
# DataSets are the aggregate-capture parent — a collection of
# DataElements rendered together for one period. Sections optionally
# group + order the DEs inside a DataSet for the data-entry app.
#
# This example creates a throw-away DataSet, attaches two DEs, groups
# them inside a Section, reorders, then tears everything down.
set -euo pipefail

# ---------------------------------------------------------------------------
# List what's already on the instance
# ---------------------------------------------------------------------------

dhis2 metadata list dataSets --page-size 3 | head -10 || true
dhis2 metadata list sections --page-size 3 | head -10 || true

# ---------------------------------------------------------------------------
# Round up two existing DEs to use as section members.
# ---------------------------------------------------------------------------

DES_JSON=$(dhis2 --json metadata list dataElements --page-size 2 --fields "id,name")
DE_A=$(printf '%s' "$DES_JSON" | python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
DE_B=$(printf '%s' "$DES_JSON" | python -c 'import json,sys; print(json.load(sys.stdin)[1]["id"])')
echo "using data elements $DE_A + $DE_B"

# ---------------------------------------------------------------------------
# Create the DataSet + attach both DEs.
# ---------------------------------------------------------------------------

DS_OUT=$(dhis2 --json metadata data-sets create \
    --name "Example demo DataSet" \
    --short-name "ExDemoDS" \
    --period-type Monthly \
    --code "EX_DEMO_DS" \
    --open-future-periods 2 \
    --expiry-days 10 \
    --timely-days 3)
DS_UID=$(printf '%s' "$DS_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created dataSet $DS_UID"

dhis2 metadata data-sets add-element "$DS_UID" "$DE_A"
dhis2 metadata data-sets add-element "$DS_UID" "$DE_B"
dhis2 metadata data-sets get "$DS_UID"

# ---------------------------------------------------------------------------
# Create a Section on the DataSet, seed it with the two DEs, reorder.
# ---------------------------------------------------------------------------

SECTION_OUT=$(dhis2 --json metadata sections create \
    --name "Example demo Section" \
    --data-set "$DS_UID" \
    --sort-order 1 \
    --data-element "$DE_A" \
    -de "$DE_B")
SECTION_UID=$(printf '%s' "$SECTION_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created section $SECTION_UID"

dhis2 metadata sections get "$SECTION_UID"
dhis2 metadata sections reorder "$SECTION_UID" "$DE_B" "$DE_A"
dhis2 metadata sections get "$SECTION_UID"

# Rename the section + DataSet labels.
dhis2 metadata sections rename "$SECTION_UID" --name "Example demo Section (renamed)"
dhis2 metadata data-sets rename "$DS_UID" --short-name "ExDS2"

# ---------------------------------------------------------------------------
# Cleanup — section first, then DEs off the DataSet, then DataSet.
# ---------------------------------------------------------------------------

dhis2 metadata sections delete "$SECTION_UID" --yes
dhis2 metadata data-sets remove-element "$DS_UID" "$DE_A"
dhis2 metadata data-sets remove-element "$DS_UID" "$DE_B"
dhis2 metadata data-sets delete "$DS_UID" --yes
