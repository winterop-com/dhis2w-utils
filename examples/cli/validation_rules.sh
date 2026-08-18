#!/usr/bin/env bash
# ValidationRule authoring — the CRUD flip side of `d2w maintenance validation run`.
#
#   d2w metadata validation-rules         /api/validationRules
#   d2w metadata validation-rule-groups   /api/validationRuleGroups
#
# Creates a throw-away rule over a seeded DataElement, groups it, renames it,
# then tears everything down.
set -euo pipefail

DE_UID=$(d2w --json metadata list dataElements --page-size 1 --fields "id,name" \
    | python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
echo "using DE $DE_UID"

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

d2w metadata validation-rules rename "$VR_UID" --short-name "ExVRv2"

d2w metadata validation-rule-groups remove-members "$VRG_UID" --rule "$VR_UID"
d2w metadata validation-rule-groups delete "$VRG_UID" --yes
d2w metadata validation-rules delete "$VR_UID" --yes
