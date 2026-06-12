#!/usr/bin/env bash
# Indicator authoring surface under `d2w metadata`:
#
#   d2w metadata indicators            /api/indicators
#   d2w metadata indicator-groups      /api/indicatorGroups
#   d2w metadata indicator-group-sets  /api/indicatorGroupSets
#
# Canonical DHIS2 resource names (same rule as the data-element and
# organisation-unit sub-apps). Runs against the seeded Sierra Leone
# stack.
set -euo pipefail

INDICATOR_TYPE=JkWynlWMjJR   # "Number (Factor 1)" — seeded
BCG_DE=s46m5MS0hxu           # BCG doses given — seeded DE

# ---------------------------------------------------------------------------
# List + show
# ---------------------------------------------------------------------------

d2w metadata list indicators --page-size 3 | head -10 || true
d2w metadata list indicatorGroups | head -10 || true
d2w metadata list indicatorGroupSets | head -10 || true

# ---------------------------------------------------------------------------
# Validate an expression before creating (typos catch early instead of
# surfacing as a 409 on the create path).
# ---------------------------------------------------------------------------

d2w metadata indicators validate-expression "#{$BCG_DE}"

# ---------------------------------------------------------------------------
# Create indicator + group + group-set round-trip. Clean up at end.
# ---------------------------------------------------------------------------

IND_OUT=$(d2w --json metadata indicators create \
    --name "Example demo indicator" \
    --short-name "ExDemoInd" \
    --indicator-type "$INDICATOR_TYPE" \
    --numerator "#{$BCG_DE}" \
    --denominator "1")
IND_UID=$(printf '%s' "$IND_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

GROUP_OUT=$(d2w --json metadata indicator-groups create \
    --name "Example demo indicator group" \
    --short-name "ExDemoIndGrp")
GROUP_UID=$(printf '%s' "$GROUP_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

d2w metadata indicator-groups add-members "$GROUP_UID" --indicator "$IND_UID"
d2w metadata indicator-groups get "$GROUP_UID"

GROUP_SET_OUT=$(d2w --json metadata indicator-group-sets create \
    --name "Example demo indicator dimension" \
    --short-name "ExDemoIndDim")
GROUP_SET_UID=$(printf '%s' "$GROUP_SET_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

d2w metadata indicator-group-sets add-groups "$GROUP_SET_UID" --group "$GROUP_UID"
d2w metadata indicator-group-sets get "$GROUP_SET_UID"

d2w metadata indicators rename "$IND_UID" --short-name "ExIndv2"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

d2w metadata indicator-group-sets remove-groups "$GROUP_SET_UID" --group "$GROUP_UID"
d2w metadata indicator-group-sets delete "$GROUP_SET_UID" --yes
d2w metadata indicator-groups remove-members "$GROUP_UID" --indicator "$IND_UID"
d2w metadata indicator-groups delete "$GROUP_UID" --yes
d2w metadata indicators delete "$IND_UID" --yes
