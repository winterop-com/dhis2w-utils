#!/usr/bin/env bash
# `dhis2 metadata category-combos` — disaggregation grids (ordered Categories).
# DHIS2 materialises the cross-product as CategoryOptionCombos on save.
# Run via `uv run bash examples/v41/cli/category_combos.sh` so `dhis2` resolves.
set -euo pipefail

# Read paths.
dhis2 metadata list categoryCombos --page-size 5
CC_UID=$(dhis2 --json metadata list categoryCombos --page-size 1 | jq -r '.[0].id')
[ -n "$CC_UID" ] && dhis2 metadata category-combos get "$CC_UID"

# Read the materialised matrix for one combo.
dhis2 metadata list categoryOptionCombos-for-combo "$CC_UID"

# Authoring (commented — running creates real metadata).
# Pick two categories with N and M options. Their cross-product is N*M
# CategoryOptionCombos; we wait for the matrix to land before doing
# anything that depends on it (data-element creation, viz pivot, ...).
#
# CAT_UIDS=$(dhis2 --json metadata list categories --page-size 2 | jq -r '.[].id' | xargs)
# read -ra CAT_ARR <<<"$CAT_UIDS"
# CC_NEW=$(dhis2 metadata category-combos create \
#     --name "DemoCombo" \
#     --category "${CAT_ARR[0]}" --category "${CAT_ARR[1]}" \
#     --json | jq -r '.id')
# # Compute the expected COC count from the option counts on each category:
# CAT_A_COUNT=$(dhis2 --json metadata categories get "${CAT_ARR[0]}" | jq '.categoryOptions | length')
# CAT_B_COUNT=$(dhis2 --json metadata categories get "${CAT_ARR[1]}" | jq '.categoryOptions | length')
# EXPECTED=$((CAT_A_COUNT * CAT_B_COUNT))
# dhis2 metadata category-combos wait-for-cocs "$CC_NEW" --expected "$EXPECTED"

# Per-item membership edits.
# dhis2 metadata category-combos add-category "$CC_UID" "$CAT_UID"
# dhis2 metadata category-combos remove-category "$CC_UID" "$CAT_UID"

# Partial label rename.
# dhis2 metadata category-combos rename "$CC_UID" --name "Renamed"

# Delete (DHIS2 rejects the default combo + combos in use).
# dhis2 metadata category-combos delete "$CC_UID" --yes
