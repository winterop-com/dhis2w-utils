#!/usr/bin/env bash
# CategoryOption authoring surface — the last analytics triple:
#
#   d2w metadata category-options            /api/categoryOptions
#   d2w metadata category-option-groups      /api/categoryOptionGroups
#   d2w metadata category-option-group-sets  /api/categoryOptionGroupSets
#
# Same canonical-naming template as data-elements / indicators.
# Does NOT cover the Category → CategoryCombo → CategoryOptionCombo
# plumbing around these triples — that stays a strategic option on
# the roadmap.
set -euo pipefail

# ---------------------------------------------------------------------------
# List + show
# ---------------------------------------------------------------------------

d2w metadata list categoryOptions --page-size 3 | head -10 || true
d2w metadata list categoryOptionGroups | head -10 || true
d2w metadata list categoryOptionGroupSets | head -10 || true

# ---------------------------------------------------------------------------
# Create a throw-away CO with a 2024 validity window, attach to a
# group, roll through group-set membership, tear everything down.
# ---------------------------------------------------------------------------

CO_OUT=$(d2w --json metadata category-options create \
    --name "Example demo CO" \
    --short-name "ExDemoCO" \
    --code "EX_DEMO_CO" \
    --start-date 2024-01-01 \
    --end-date 2024-12-31)
CO_UID=$(printf '%s' "$CO_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

GROUP_OUT=$(d2w --json metadata category-option-groups create \
    --name "Example demo CO group" \
    --short-name "ExDemoCOGrp")
GROUP_UID=$(printf '%s' "$GROUP_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

d2w metadata category-option-groups add-members "$GROUP_UID" --category-option "$CO_UID"
d2w metadata category-option-groups get "$GROUP_UID"

GROUP_SET_OUT=$(d2w --json metadata category-option-group-sets create \
    --name "Example demo CO dimension" \
    --short-name "ExDemoCODim")
GROUP_SET_UID=$(printf '%s' "$GROUP_SET_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

d2w metadata category-option-group-sets add-groups "$GROUP_SET_UID" --group "$GROUP_UID"
d2w metadata category-option-group-sets get "$GROUP_SET_UID"

# Rename + validity-window update.
d2w metadata category-options rename "$CO_UID" --short-name "ExCOv2"
d2w metadata category-options set-validity "$CO_UID" --start-date 2025-01-01 --end-date 2025-12-31

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

d2w metadata category-option-group-sets remove-groups "$GROUP_SET_UID" --group "$GROUP_UID"
d2w metadata category-option-group-sets delete "$GROUP_SET_UID" --yes
d2w metadata category-option-groups remove-members "$GROUP_UID" --category-option "$CO_UID"
d2w metadata category-option-groups delete "$GROUP_UID" --yes
d2w metadata category-options delete "$CO_UID" --yes
