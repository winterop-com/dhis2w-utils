#!/usr/bin/env bash
# Tracker delete — remove events / enrollments / tracked entities by UID.
# Each builds the minimal {<kind>: [{<idField>: uid}]} bundle and pushes it
# with importStrategy=DELETE. Deleting a tracked entity cascades to its
# enrollments and events.
set -euo pipefail

# Delete one event by UID.
dhis2 data tracker event delete evt01234567

# Delete an enrollment by UID.
dhis2 data tracker enrollment delete enr01234567

# Delete a tracked entity (cascades to its enrollments + events).
dhis2 data tracker delete teI01234567

# Delete several at once; --async returns a job reference instead of waiting.
dhis2 data tracker event delete evt01234567 evt7654321X --async
