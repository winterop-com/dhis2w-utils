#!/usr/bin/env bash
# DataElement authoring surface under `d2w metadata`:
#
#   d2w metadata data-elements             /api/dataElements
#   d2w metadata data-element-groups       /api/dataElementGroups
#   d2w metadata data-element-group-sets   /api/dataElementGroupSets
#
# Canonical DHIS2 resource names (same rule as the organisation-unit
# sub-apps). Runs against the seeded Sierra Leone stack.
set -euo pipefail

# ---------------------------------------------------------------------------
# List + show
# ---------------------------------------------------------------------------

d2w metadata list dataElements --filter domainType:eq:AGGREGATE --page-size 5 | head -14 || true
d2w metadata list dataElementGroups | head -10 || true
d2w metadata list dataElementGroupSets | head -10 || true

# ---------------------------------------------------------------------------
# Create a throwaway aggregate DE, attach to a group, roll through the
# group-set membership dance, then clean up.
# ---------------------------------------------------------------------------

DE_OUT=$(d2w --json metadata data-elements create \
    --name "Example demo DE" \
    --short-name "ExDemoDE" \
    --value-type NUMBER)
DE_UID=$(printf '%s' "$DE_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

GROUP_OUT=$(d2w --json metadata data-element-groups create \
    --name "Example demo DE group" \
    --short-name "ExDemoDEGrp")
GROUP_UID=$(printf '%s' "$GROUP_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

d2w metadata data-element-groups add-members "$GROUP_UID" --data-element "$DE_UID"
d2w metadata data-element-groups get "$GROUP_UID"

# Wire the group into a fresh DataElementGroupSet (analytics dimension).
GROUP_SET_OUT=$(d2w --json metadata data-element-group-sets create \
    --name "Example demo DE dimension" \
    --short-name "ExDemoDEDim")
GROUP_SET_UID=$(printf '%s' "$GROUP_SET_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

d2w metadata data-element-group-sets add-groups "$GROUP_SET_UID" --group "$GROUP_UID"
d2w metadata data-element-group-sets get "$GROUP_SET_UID"

# Rename the DE (partial update).
d2w metadata data-elements rename "$DE_UID" --short-name "ExDEv2"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

d2w metadata data-element-group-sets remove-groups "$GROUP_SET_UID" --group "$GROUP_UID"
d2w metadata data-element-group-sets delete "$GROUP_SET_UID" --yes
d2w metadata data-element-groups remove-members "$GROUP_UID" --data-element "$DE_UID"
d2w metadata data-element-groups delete "$GROUP_UID" --yes
d2w metadata data-elements delete "$DE_UID" --yes
