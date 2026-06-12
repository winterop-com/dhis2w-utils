#!/usr/bin/env bash
# ValidationRule + Predictor authoring surface — the CRUD flip side of
# `d2w maintenance validation run` + `d2w maintenance predictors run`.
#
#   d2w metadata validation-rules         /api/validationRules
#   d2w metadata validation-rule-groups   /api/validationRuleGroups
#   d2w metadata predictors               /api/predictors (CRUD; run lives on maintenance)
#   d2w metadata predictor-groups         /api/predictorGroups
#
# This example creates a throw-away rule + predictor over the seeded
# BCG DataElement, groups each with its domain group, then tears
# everything down.
set -euo pipefail

# ---------------------------------------------------------------------------
# Look up an aggregate DE + a facility-level OrganisationUnitLevel UID to
# target with the throw-away objects.
# ---------------------------------------------------------------------------

DE_UID=$(d2w --json metadata list dataElements --page-size 1 --fields "id,name" \
    | python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
OU_LEVEL_UID=$(d2w --json metadata list organisationUnitLevels \
    | python -c 'import json,sys; rows=json.load(sys.stdin); print(rows[-1]["id"] if rows else "")')
echo "using DE $DE_UID  facility-level $OU_LEVEL_UID"

# ---------------------------------------------------------------------------
# ValidationRule + group
# ---------------------------------------------------------------------------

VR_OUT=$(d2w --json metadata validation-rules create \
    --name "Example demo rule" \
    --short-name "ExDemoVR" \
    --left "#{${DE_UID}}" \
    --operator "greater_than_or_equal_to" \
    --right "0" \
    --importance MEDIUM \
    --ou-level 4)
VR_UID=$(printf '%s' "$VR_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created validationRule $VR_UID"

VRG_OUT=$(d2w --json metadata validation-rule-groups create \
    --name "Example demo rule group" \
    --short-name "ExDemoVRG")
VRG_UID=$(printf '%s' "$VRG_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

d2w metadata validation-rule-groups add-members "$VRG_UID" --rule "$VR_UID"
d2w metadata validation-rule-groups get "$VRG_UID"

# ---------------------------------------------------------------------------
# Predictor + group — predictor writes into the same DE for demo purposes.
# (Real-world predictors write into a dedicated output DE.)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Rename + cleanup
# ---------------------------------------------------------------------------

d2w metadata validation-rules rename "$VR_UID" --short-name "ExVRv2"
d2w metadata predictors rename "$PRD_UID" --short-name "ExPrdv2"

d2w metadata predictor-groups remove-members "$PDG_UID" --predictor "$PRD_UID"
d2w metadata predictor-groups delete "$PDG_UID" --yes
d2w metadata predictors delete "$PRD_UID" --yes

d2w metadata validation-rule-groups remove-members "$VRG_UID" --rule "$VR_UID"
d2w metadata validation-rule-groups delete "$VRG_UID" --yes
d2w metadata validation-rules delete "$VR_UID" --yes
