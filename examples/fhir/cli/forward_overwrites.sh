#!/usr/bin/env bash
# d2w fhir forward — the two postures a drain takes towards a value already sent.
# Needs the serve extra, docker for the SUSHI compile, a bound port, and its `--import` runs
# write data values to the instance. `make verify-examples` skips it for the same reasons it
# skips forward_import.sh. Run it by hand, against an instance you are willing to write to.
set -euo pipefail

PORT="${FHIR_FORWARD_PORT:-8124}"
BASE="http://127.0.0.1:${PORT}"

d2w fhir init overwrite-demo --id dhis2.fhir.overwritedemo \
    --canonical http://example.org/fhir/overwrite-demo \
    --publisher "Demo Org" --data-set TuL8IOPzpHh --max-level 2
cd overwrite-demo
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

# Capture one aggregate load set and land it.
post_load_set() {
    d2w fhir serve --port "$PORT" &
    SERVER_PID=$!
    trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
    sleep 5
    for response in load/*.json; do
        curl -s -o /dev/null -X POST "${BASE}/QuestionnaireResponse" \
            -H 'Content-Type: application/fhir+json' \
            --data-binary "@${response}"
    done
    kill "$SERVER_PID"
    trap - EXIT
    wait "$SERVER_PID" 2>/dev/null || true
}
d2w fhir generate load-set --per-target 3
post_load_set
d2w fhir forward --import

# Post the same load set again. Every cell it names is one the run above already landed -
# DHIS2 replaces those values in place and counts the write exactly as it counts a first
# entry, so no import summary can say it happened. The run says it instead, naming each
# value, the receipt that sent it before, and when that receipt arrived. The dry run states
# it as a prediction, which is the moment there is still something to be done about it.
post_load_set
d2w fhir forward --details

# `refuse` is the posture for a deployment where forwarded data changes only through a
# declared correction. Nothing is posted: a response carrying any already-sent value is
# refused whole - posting part of it would land a report nobody filled in - and stays in the
# queue with `<id>.refusal.json` beside it naming every covered value and the receipt that
# sent it. The spool listing reads that record back.
d2w fhir forward --import --overwrites refuse --details
d2w fhir spool --details

# `allow` is the default, and it is the way forward from a refusal: the same receipts, now
# posted, with every value they replaced named. The move that drains a receipt deletes the
# refusal record - the import report is the answer about it from then on.
d2w fhir forward --import --overwrites allow --details

cd .. && rm -rf overwrite-demo
