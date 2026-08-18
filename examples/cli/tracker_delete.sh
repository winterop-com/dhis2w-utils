#!/usr/bin/env bash
# Tracker delete — remove events / enrollments / tracked entities by UID.
# Each delete builds the minimal {<kind>: [{<idField>: uid}]} bundle and pushes
# it with importStrategy=DELETE. Deleting a tracked entity cascades to its
# enrollments and events. DHIS2 refuses a delete of a UID it does not hold
# (E1032), so this script registers what it deletes.
set -euo pipefail

PROGRAM=IpHINAT79UW    # Child Programme (seeded)
STAGE=A03MvHHogjR      # Birth stage

# A level-4 facility to register against.
OU=$(d2w --json metadata list organisationUnits --filter level:eq:4 --page-size 1 --fields id | jq -r '.[0].id')

# Register a person with an enrollment, and log one event on it.
REGISTERED=$(d2w --json data tracker register "$PROGRAM" \
    --ou "$OU" \
    --attr w75KJ2mc4zz=Temporary \
    --attr zDhUuAYrxNC=Record \
    --enrolled-at 2025-06-01)
TRACKED_ENTITY=$(jq -r '.tracked_entity' <<< "$REGISTERED")
ENROLLMENT=$(jq -r '.enrollment' <<< "$REGISTERED")
EVENT=$(d2w --json data tracker event create \
    --enrollment "$ENROLLMENT" --program "$PROGRAM" --stage "$STAGE" \
    --at "$OU" --te "$TRACKED_ENTITY" --occurred-at 2025-06-02 | jq -r '.event')

# Delete the event by UID.
d2w data tracker event delete "$EVENT" --yes

# Delete the enrollment by UID.
d2w data tracker enrollment delete "$ENROLLMENT" --yes

# Delete the tracked entity. This one cascades: a second registration whose
# enrollment and event still exist goes down whole with it.
d2w data tracker delete "$TRACKED_ENTITY" --yes

CASCADE=$(d2w --json data tracker register "$PROGRAM" \
    --ou "$OU" \
    --attr w75KJ2mc4zz=Cascade \
    --attr zDhUuAYrxNC=Record \
    --enrolled-at 2025-06-01)
d2w data tracker delete "$(jq -r '.tracked_entity' <<< "$CASCADE")" --yes

# Several at once work too, and --async returns a job reference instead of
# waiting:
#   d2w data tracker event delete <uid> <uid> --async --yes
