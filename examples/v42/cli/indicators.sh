#!/usr/bin/env bash
# Indicator authoring surface under `dhis2 metadata`:
#
#   dhis2 metadata indicators            /api/indicators
#   dhis2 metadata indicator-groups      /api/indicatorGroups
#   dhis2 metadata indicator-group-sets  /api/indicatorGroupSets
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

dhis2 metadata list indicators --page-size 3 | head -10 || true
dhis2 metadata list indicatorGroups | head -10 || true
dhis2 metadata list indicatorGroupSets | head -10 || true

# ---------------------------------------------------------------------------
# Validate an expression before creating (typos catch early instead of
# surfacing as a 409 on the create path).
# ---------------------------------------------------------------------------

dhis2 metadata indicators validate-expression "#{$BCG_DE}"

# ---------------------------------------------------------------------------
# Create indicator + group + group-set round-trip. Clean up at end.
# ---------------------------------------------------------------------------

IND_OUT=$(dhis2 --json metadata indicators create \
    --name "Example demo indicator" \
    --short-name "ExDemoInd" \
    --indicator-type "$INDICATOR_TYPE" \
    --numerator "#{$BCG_DE}" \
    --denominator "1")
IND_UID=$(printf '%s' "$IND_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

GROUP_OUT=$(dhis2 --json metadata indicator-groups create \
    --name "Example demo indicator group" \
    --short-name "ExDemoIndGrp")
GROUP_UID=$(printf '%s' "$GROUP_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

dhis2 metadata indicator-groups add-members "$GROUP_UID" --indicator "$IND_UID"
dhis2 metadata indicator-groups get "$GROUP_UID"

GROUP_SET_OUT=$(dhis2 --json metadata indicator-group-sets create \
    --name "Example demo indicator dimension" \
    --short-name "ExDemoIndDim")
GROUP_SET_UID=$(printf '%s' "$GROUP_SET_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

dhis2 metadata indicator-group-sets add-groups "$GROUP_SET_UID" --group "$GROUP_UID"
dhis2 metadata indicator-group-sets get "$GROUP_SET_UID"

dhis2 metadata indicators rename "$IND_UID" --short-name "ExIndv2"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

dhis2 metadata indicator-group-sets remove-groups "$GROUP_SET_UID" --group "$GROUP_UID"
dhis2 metadata indicator-group-sets delete "$GROUP_SET_UID" --yes
dhis2 metadata indicator-groups remove-members "$GROUP_UID" --indicator "$IND_UID"
dhis2 metadata indicator-groups delete "$GROUP_UID" --yes
dhis2 metadata indicators delete "$IND_UID" --yes
