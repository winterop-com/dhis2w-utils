#!/usr/bin/env bash
# d2w fhir forward — drain the capture spool back into DHIS2: dry run, import, three states.
# Needs the serve extra to fill the spool: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# Needs docker for the SUSHI compile and binds a port to fill the spool, and its `--import` run
# writes data values to the instance. `make verify-examples` skips it for all three reasons:
# `infra/scripts/verify_examples.py` lists it under "slow server-side jobs". Run it by hand,
# against an instance you are willing to write to.
set -euo pipefail

PORT="${FHIR_FORWARD_PORT:-8124}"
BASE="http://127.0.0.1:${PORT}"

# Scaffold a small project and generate + compile its guide. The forwarder reads the very
# resources the facade serves, so a project that cannot be served cannot be forwarded either.
d2w fhir init forward-demo --id dhis2.fhir.forwarddemo \
    --canonical http://example.org/fhir/forward-demo \
    --publisher "Demo Org" --data-set TuL8IOPzpHh --event-program EVTsupVis01 --max-level 2
cd forward-demo

# `init` has no flag for the terminology tables, so they are written here. A table left
# absent selects everything of its kind, and one DHIS2 name carrying a raw '<' anywhere in
# that everything refuses the whole generate run.
cat >>fhir.toml <<'TOML'

[generate.option_sets]
include_ids = ["OsVaccType1"]

[generate.categories]
include_ids = ["yY2bQYqNt0o", "Qzh0MSUx4RM"]
TOML

d2w fhir generate
make setup
make sushi

# Fill the spool: serve the guide, POST a load set at it. Every accepted response is written
# to .serve/responses/received/<id>.json as a receipt - the queue the forwarder drains.
d2w fhir serve --port "$PORT" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 5
d2w fhir generate load-set --per-target 5
for response in load/*.json; do
    curl -s -o /dev/null -X POST "${BASE}/QuestionnaireResponse" \
        -H 'Content-Type: application/fhir+json' \
        --data-binary "@${response}"
done
kill "$SERVER_PID"
trap - EXIT
wait "$SERVER_PID" 2>/dev/null || true
ls .serve/responses/received | wc -l

# DRY RUN IS THE DEFAULT. Every payload still goes to the real endpoint on the real instance,
# under that endpoint's own validate-only mode - dryRun=true on /api/dataValueSets,
# importMode=VALIDATE on /api/tracker - so DHIS2's own rules decide each answer while nothing
# is written and no receipt moves. A stage event whose enrollment a registration of the same
# run creates is counted unverifiable rather than rejected: a dry run writes nothing, so
# there is no enrollment for DHIS2 to check the event against. A DHIS2 rejection exits 1; a
# dry run whose only failures are unverifiable exits 0.
d2w fhir forward

# Nothing moved: the queue is exactly as long as it was, so the same run can be repeated.
ls .serve/responses/received | wc -l

# Commit. --import posts for real and then files each receipt by what it became:
#   accepted -> .serve/responses/forwarded/<id>.json
#   rejected -> .serve/responses/rejected/<id>.json, beside <id>.report.json saying why
#   refused  -> stays in received/, and the next `d2w fhir forward` is the retry
d2w fhir forward --import

# The three states after an import run. received/ holds only what the translator refused.
ls .serve/responses/received 2>/dev/null | wc -l
ls .serve/responses/forwarded 2>/dev/null | wc -l
ls .serve/responses/rejected 2>/dev/null | wc -l

# The scaffolded project has both runs as make targets, reading the same [serve] and
# [generate] tables the rest of the project does:
#   make forward          # the dry run
#   make forward-import   # the committing run

cd .. && rm -rf forward-demo
