#!/usr/bin/env bash
# Tracker schema authoring — step 2: Program + PTEA + OU scope.
#
# A DHIS2 Program is the tracker container: it binds a
# TrackedEntityType (for WITH_REGISTRATION programs), a set of
# TEAs shown on the enrollment form, and the OUs that can capture
# enrollments.
#
#   dhis2 metadata programs   /api/programs
#
# This example creates a throw-away Person TET + one TEA,
# then a tracker Program that binds them together, wires the TEA
# into the enrollment form, scopes the program to the root OU,
# renames, then tears everything down.
set -euo pipefail

# ---------------------------------------------------------------------------
# Foundations: TET + TEA (leaf resources from tracker-schema step 1).
# ---------------------------------------------------------------------------

TEA_OUT=$(dhis2 --json metadata tracked-entity-attributes create \
    --name "Example program demo given name" \
    --short-name "ExPrgDGivN" \
    --value-type TEXT)
TEA_UID=$(printf '%s' "$TEA_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created TEA $TEA_UID (given name)"

TET_OUT=$(dhis2 --json metadata tracked-entity-types create \
    --name "Example program demo person" \
    --short-name "ExPrgDPers" \
    --allow-audit-log \
    --feature-type NONE \
    --min-attrs 1)
TET_UID=$(printf '%s' "$TET_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created TET $TET_UID"

# ---------------------------------------------------------------------------
# Pick the root org unit to scope the program to.
# ---------------------------------------------------------------------------

OU_UID=$(dhis2 --json metadata list organisationUnits --page-size 1 \
    | python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
echo "using root OU $OU_UID"

# ---------------------------------------------------------------------------
# A tracker program bound to the TET, with the TEA on its enrollment form.
# ---------------------------------------------------------------------------

PRG_OUT=$(dhis2 --json metadata programs create \
    --name "Example demo tracker program" \
    --short-name "ExDemoPrg" \
    --program-type WITH_REGISTRATION \
    --tracked-entity-type "$TET_UID" \
    --display-incident-date \
    --only-enroll-once \
    --min-attrs 1)
PRG_UID=$(printf '%s' "$PRG_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created tracker program $PRG_UID"

dhis2 metadata programs add-attribute "$PRG_UID" "$TEA_UID" --mandatory --searchable --sort-order 1
dhis2 metadata programs add-to-ou "$PRG_UID" "$OU_UID"
dhis2 metadata programs get "$PRG_UID"

# ---------------------------------------------------------------------------
# An event program too — quick WITHOUT_REGISTRATION variant.
# ---------------------------------------------------------------------------

EVT_OUT=$(dhis2 --json metadata programs create \
    --name "Example demo event program" \
    --short-name "ExDemoEvt" \
    --program-type WITHOUT_REGISTRATION)
EVT_UID=$(printf '%s' "$EVT_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created event program $EVT_UID"

# ---------------------------------------------------------------------------
# Rename + cleanup
# ---------------------------------------------------------------------------

dhis2 metadata programs rename "$PRG_UID" --short-name "ExPrgv2"

dhis2 metadata programs remove-from-ou "$PRG_UID" "$OU_UID"
dhis2 metadata programs remove-attribute "$PRG_UID" "$TEA_UID"
dhis2 metadata programs delete "$PRG_UID" --yes
dhis2 metadata programs delete "$EVT_UID" --yes
dhis2 metadata tracked-entity-types delete "$TET_UID" --yes
dhis2 metadata tracked-entity-attributes delete "$TEA_UID" --yes
