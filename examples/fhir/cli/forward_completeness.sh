#!/usr/bin/env bash
# d2w fhir forward — data set completeness: what a `completed` aggregate response registers.
# Needs the serve extra, docker for the SUSHI compile, a bound port, and its `--import` runs
# write data values to the instance. `make verify-examples` skips it for the same reasons it
# skips forward.sh. Run it by hand, against an instance you are willing to write to.
set -euo pipefail

PORT="${FHIR_FORWARD_PORT:-8124}"
BASE="http://127.0.0.1:${PORT}"

d2w fhir init completeness-demo --id dhis2.fhir.completenessdemo \
    --canonical http://example.org/fhir/completeness-demo \
    --publisher "Demo Org" --data-set BfMAe6Itzgt --max-level 2
cd completeness-demo
d2w fhir generate
make setup
make sushi

d2w fhir serve --port "$PORT" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 5
d2w fhir generate load-set --per-target 3
for response in load/*.json; do
    curl -s -o /dev/null -X POST "${BASE}/QuestionnaireResponse" \
        -H 'Content-Type: application/fhir+json' \
        --data-binary "@${response}"
done
kill "$SERVER_PID"
trap - EXIT
wait "$SERVER_PID" 2>/dev/null || true

# DHIS2 records whether a data set is *finished* for a period separately from the values,
# keyed by the same (data set, period, organisation unit, attribute option combo) tuple.
# QuestionnaireResponse.status states it: a `completed` response registers that tuple
# complete once DHIS2 has taken its values; an `in-progress` one imports its values and
# registers nothing. The claim is a second write, made only after the values landed - a
# completeness claim about data the instance refused would be a lie - and a refused
# registration does NOT un-import the values.
#
# The summary carries a `data set completeness` row, and --details prints the tuple each
# response claimed, because a registration has no UID to look it up by.
d2w fhir forward --import --details

# Off for a whole run: the values still import, and every `completed` response is reported
# `not-registered` rather than silently skipped.
d2w fhir forward --import --no-register-completeness

# A dry run posts nothing to the completeness endpoint - it wrote no values, so there is
# nothing for the claim to be about - and states the tuple it would register instead.
d2w fhir forward --details

cd .. && rm -rf completeness-demo
