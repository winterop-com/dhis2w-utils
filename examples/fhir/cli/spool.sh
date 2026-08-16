#!/usr/bin/env bash
# FHIR spool operators — read the capture queue, and put a receipt DHIS2 refused back in it.
# Both commands are directory work: no DHIS2 connection, no profile, no network. That is the
# point of them — an operator asks what is queued exactly when the instance is down.
set -euo pipefail

CANONICAL="http://example.org/fhir/spool-demo"

# A scaffolded project is enough. Nothing here generates, serves, or forwards: the spool is a
# directory under the project root, and these two verbs read and rename inside it.
d2w fhir init spool-demo --id dhis2.fhir.spooldemo --canonical "$CANONICAL" \
    --publisher "Demo Org" --data-set BfMAe6Itzgt --max-level 2

cd spool-demo

# Stand in for `d2w fhir serve`: a receipt is the submission as it arrived plus the envelope
# the facade records around it. One waiting in the queue, one DHIS2 refused with its import
# report beside it, and one file that is not a receipt at all.
mkdir -p .serve/responses/received .serve/responses/rejected

cat > .serve/responses/received/queued-1.json <<'JSON'
{
  "response_id": "queued-1",
  "received_at": "2026-08-15T09:00:00Z",
  "form_kind": "aggregate",
  "questionnaire": "http://example.org/fhir/spool-demo/Questionnaire/d2-ds-child-health",
  "warnings": [],
  "response": {"resourceType": "QuestionnaireResponse", "id": "queued-1", "status": "completed"}
}
JSON

cat > .serve/responses/rejected/refused-1.json <<'JSON'
{
  "response_id": "refused-1",
  "received_at": "2026-08-15T09:05:00Z",
  "form_kind": "aggregate",
  "questionnaire": "http://example.org/fhir/spool-demo/Questionnaire/d2-ds-child-health",
  "warnings": [],
  "response": {"resourceType": "QuestionnaireResponse", "id": "refused-1", "status": "completed"}
}
JSON

cat > .serve/responses/rejected/refused-1.report.json <<'JSON'
{
  "status": "ERROR",
  "message": "Import failed",
  "issues": [
    {"error_code": "E1029", "subject": "ImspTQPwCqd", "message": "Organisation unit is not assigned to the data set"}
  ]
}
JSON

printf '{ not json' > .serve/responses/received/half-written.json

# How many receipts wait in each state. The directory a receipt's file is in IS its state, so
# there is no index to be stale: this reads the tree every time. `unreadable files` counts the
# holding pen, which holds no receipts at all - only bytes that would not parse as one.
d2w fhir spool

# --details is the row-per-receipt view: the id, its state, the form it answered, when it
# arrived, and - for a receipt DHIS2 refused - the short reason read off the report beside it.
d2w fhir spool --details

# The read is what finds a file that is no longer a receipt, so the read is what files it: the
# file moves to .serve/responses/malformed/ with a <file>.reason.json naming what stopped it,
# and the listing carries on. One unreadable byte costs one row rather than the whole answer.
ls .serve/responses/malformed
cat .serve/responses/malformed/half-written.json.reason.json

# --json puts the whole SpoolStateReport on stdout and nothing else, so the tables on stderr
# never have to be filtered out.
d2w --json fhir spool | head -c 300
echo

# A rejection is DHIS2 stating that this payload is wrong, so nothing moves it back on its own.
# `requeue` is the operator saying otherwise, once the instance, the guide, or their mind has
# changed. The import report STAYS in rejected/ - it is what DHIS2 answered about that post,
# which is still true of that post - and the next drain writes a fresh one wherever the receipt
# lands.
d2w fhir requeue refused-1

ls .serve/responses/received
ls .serve/responses/rejected

# --all-rejected moves everything DHIS2 refused, which is the usual case after a fix on the
# instance. An id that is not in rejected/ is refused by name, and refused before anything
# moves, so a run of five never leaves you working out which three it got to.
d2w fhir requeue --all-rejected || true
d2w fhir requeue queued-1 || true

# From here, `d2w fhir forward --import` posts the requeued receipts again - see
# examples/fhir/cli/forward.sh for the drain itself.

cd .. && rm -rf spool-demo
