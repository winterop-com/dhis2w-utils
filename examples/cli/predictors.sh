#!/usr/bin/env bash
# Predictor authoring — the CRUD flip side of `d2w maintenance predictors run`.
#
#   d2w metadata predictors          /api/predictors (CRUD; run lives on maintenance)
#   d2w metadata predictor-groups    /api/predictorGroups
#
# Creates a throw-away predictor writing into a seeded DataElement (a real
# predictor writes into a dedicated output DE), groups it, renames it, then
# tears everything down.
set -euo pipefail

DE_UID=$(d2w --json metadata list dataElements --page-size 1 --fields "id,name" \
    | python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
OU_LEVEL_UID=$(d2w --json metadata list organisationUnitLevels \
    | python -c 'import json,sys; rows=json.load(sys.stdin); print(rows[-1]["id"] if rows else "")')
echo "using DE $DE_UID  facility-level $OU_LEVEL_UID"

PRD_OUT=$(d2w --json metadata predictors create \
    --name "Example demo predictor" \
    --short-name "ExDemoPrd" \
    --expression "#{${DE_UID}}" \
    --output "$DE_UID" \
    --sequential 3 \
    ${OU_LEVEL_UID:+--ou-level "$OU_LEVEL_UID"})
PRD_UID=$(printf '%s' "$PRD_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created predictor $PRD_UID"

PDG_OUT=$(d2w --json metadata predictor-groups create \
    --name "Example demo predictor group" \
    --short-name "ExDemoPDG")
PDG_UID=$(printf '%s' "$PDG_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

d2w metadata predictor-groups add-members "$PDG_UID" --predictor "$PRD_UID"
d2w metadata predictor-groups get "$PDG_UID"

d2w metadata predictors rename "$PRD_UID" --short-name "ExPrdv2"

d2w metadata predictor-groups remove-members "$PDG_UID" --predictor "$PRD_UID"
d2w metadata predictor-groups delete "$PDG_UID" --yes
d2w metadata predictors delete "$PRD_UID" --yes
