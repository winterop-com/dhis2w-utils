#!/usr/bin/env bash
# Tracker schema authoring — step 1: TrackedEntityType + TrackedEntityAttribute.
#
# DHIS2's tracker writes (`d2w tracker register / enroll / add-event`)
# need a schema on the instance first: a `TrackedEntityType` that defines
# the kind of subject being tracked plus `TrackedEntityAttribute`s that
# describe the fields captured per TEI.
#
#   d2w metadata tracked-entity-attributes  /api/trackedEntityAttributes
#   d2w metadata tracked-entity-types       /api/trackedEntityTypes
#
# This example creates a throw-away National-ID + Given-Name TEA, a
# throw-away Person TET, wires both TEAs onto the TET (mandatory vs
# searchable), flips a label, then tears everything down.
set -euo pipefail

# ---------------------------------------------------------------------------
# Two attributes — a unique + generated National-ID and a plain-text name.
# ---------------------------------------------------------------------------

NATID_OUT=$(d2w --json metadata tracked-entity-attributes create \
    --name "Example demo national id" \
    --short-name "ExDemoNID" \
    --value-type TEXT \
    --unique --generated \
    --pattern "RANDOM(#######)")
NATID_UID=$(printf '%s' "$NATID_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created TEA $NATID_UID (national id)"

NAME_OUT=$(d2w --json metadata tracked-entity-attributes create \
    --name "Example demo given name" \
    --short-name "ExDemoGivN" \
    --value-type TEXT)
NAME_UID=$(printf '%s' "$NAME_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created TEA $NAME_UID (given name)"

# ---------------------------------------------------------------------------
# A Person TET, then wire both TEAs in with different flags.
# ---------------------------------------------------------------------------

TET_OUT=$(d2w --json metadata tracked-entity-types create \
    --name "Example demo person" \
    --short-name "ExDemoPers" \
    --allow-audit-log \
    --feature-type NONE \
    --min-attrs 1)
TET_UID=$(printf '%s' "$TET_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "created TET $TET_UID"

# National ID: mandatory on enrollment + searchable.
d2w metadata tracked-entity-types add-attribute "$TET_UID" "$NATID_UID" \
    --mandatory --searchable
# Given name: display in list only.
d2w metadata tracked-entity-types add-attribute "$TET_UID" "$NAME_UID"

d2w metadata tracked-entity-types get "$TET_UID"

# ---------------------------------------------------------------------------
# Flip a label via rename, then tear down.
# ---------------------------------------------------------------------------

d2w metadata tracked-entity-attributes rename "$NAME_UID" --short-name "ExGivNv2"

d2w metadata tracked-entity-types remove-attribute "$TET_UID" "$NAME_UID"
d2w metadata tracked-entity-types remove-attribute "$TET_UID" "$NATID_UID"
d2w metadata tracked-entity-types delete "$TET_UID" --yes
d2w metadata tracked-entity-attributes delete "$NAME_UID" --yes
d2w metadata tracked-entity-attributes delete "$NATID_UID" --yes
