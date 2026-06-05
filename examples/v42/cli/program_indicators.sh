#!/usr/bin/env bash
# ProgramIndicator authoring surface under `dhis2 metadata`:
#
#   dhis2 metadata program-indicators         /api/programIndicators
#   dhis2 metadata program-indicator-groups   /api/programIndicatorGroups
#
# Note: DHIS2 does NOT expose a ProgramIndicatorGroupSet resource, so
# the program-indicator surface is a *pair* rather than the `X / XGroup
# / XGroupSet` triple the other analytics resources use.
set -euo pipefail

CHILD_PROGRAM=IpHINAT79UW   # "Child Programme" — seeded Sierra Leone tracker program
BCG_DE=s46m5MS0hxu          # BCG doses given — seeded DE referenced by program events

# ---------------------------------------------------------------------------
# List + show
# ---------------------------------------------------------------------------

dhis2 metadata list programIndicators --filter program.id:eq:"$CHILD_PROGRAM" --page-size 3 | head -10 || true
dhis2 metadata list programIndicatorGroups | head -10 || true

# ---------------------------------------------------------------------------
# Pre-flight expression validation — catches DE-reference typos before
# create returns a 409.
# ---------------------------------------------------------------------------

dhis2 metadata program-indicators validate-expression "#{$CHILD_PROGRAM.$BCG_DE}"

# ---------------------------------------------------------------------------
# Create PI + group, link, clean up.
# ---------------------------------------------------------------------------

PI_OUT=$(dhis2 --json metadata program-indicators create \
    --name "Example demo PI" \
    --short-name "ExDemoPI" \
    --program "$CHILD_PROGRAM" \
    --expression "#{$CHILD_PROGRAM.$BCG_DE}" \
    --analytics-type EVENT)
PI_UID=$(printf '%s' "$PI_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

GROUP_OUT=$(dhis2 --json metadata program-indicator-groups create \
    --name "Example demo PI group" \
    --short-name "ExDemoPIGrp")
GROUP_UID=$(printf '%s' "$GROUP_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

dhis2 metadata program-indicator-groups add-members "$GROUP_UID" --program-indicator "$PI_UID"
dhis2 metadata program-indicator-groups get "$GROUP_UID"

# Rename the PI (partial update).
dhis2 metadata program-indicators rename "$PI_UID" --short-name "ExPIv2"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

dhis2 metadata program-indicator-groups remove-members "$GROUP_UID" --program-indicator "$PI_UID"
dhis2 metadata program-indicator-groups delete "$GROUP_UID" --yes
dhis2 metadata program-indicators delete "$PI_UID" --yes
