#!/usr/bin/env bash
# d2w fhir withdraw — take back from DHIS2 the event a forwarded receipt landed.
# Binds a port to fill the spool, and both its committing runs write to the instance: one
# creates an event, the other deletes it. `make verify-examples` skips it for the same reasons
# it skips forward.sh. Run it by hand, against an instance you are willing to write to.
set -euo pipefail

PORT="${FHIR_WITHDRAW_PORT:-8129}"
BASE="http://127.0.0.1:${PORT}"

# One event program, and no SUSHI compile at all: `--live` builds the guide off the instance,
# which is enough for a capture and for the drain that follows it.
d2w fhir init withdraw-demo --id dhis2.fhir.withdrawdemo \
    --canonical http://example.org/fhir/withdraw-demo \
    --publisher "Demo Org" --event-program EVTsupVis01 --max-level 2
cd withdraw-demo

# `[forward] withdrawals` is off unless a project says otherwise. A project that publishes
# forms and forwards them is not thereby a project that reaches back into what DHIS2 already
# holds, so the capability is stated once here rather than assumed.
cat >>fhir.toml <<'TOML'

[forward]
withdrawals = "retract"
TOML

# Fill the spool: serve the guide off the instance, POST one event response at it.
d2w fhir serve --live --port "$PORT" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 20
d2w fhir generate load-set --per-target 1
curl -s -o /dev/null -X POST "${BASE}/QuestionnaireResponse" \
    -H 'Content-Type: application/fhir+json' \
    --data-binary @load/EVTsupVis01-example-1.json
kill "$SERVER_PID"
trap - EXIT
wait "$SERVER_PID" 2>/dev/null || true

# Land it. The receipt moves to forwarded/ beside a report saying what DHIS2 took.
d2w fhir forward --import --details
RECEIPT="$(basename .serve/responses/forwarded/*[!t].json .json)"

# DRY RUN IS THE DEFAULT here too. The delete goes to the real tracker endpoint under
# importMode=VALIDATE, so DHIS2 answers whether it would take it while nothing is deleted and
# no receipt moves — which for a terminal act is the one rehearsal worth having. The event
# named is derived from the receipt's own id, so no guide and no metadata read are involved.
d2w fhir withdraw "$RECEIPT"

# Commit. The event is deleted, the receipt moves to withdrawn/ — the spool's fourth state —
# and a record of the delete lands beside it. The import report that said what the receipt
# landed stays in forwarded/, because that document is still true of that import.
d2w fhir withdraw --import "$RECEIPT"
d2w fhir spool --details

# WITHDRAWAL IS TERMINAL. DHIS2 burns the UID it deleted and refuses it under every import
# strategy afterwards, so the receipt can never be forwarded again — which is why a correction
# is never modelled as delete-then-recreate. What remains in the instance is a hidden copy of
# the event carrying its values, which no ordinary read returns.
ls .serve/responses/withdrawn
cat .serve/responses/withdrawn/"${RECEIPT}".report.json

cd .. && rm -rf withdraw-demo
