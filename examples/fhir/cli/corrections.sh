#!/usr/bin/env bash
# [forward] corrections / withdrawals — a marked submission is decided at the door.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# The facade runs `--live`, so there is no SUSHI compile and no docker; every capture stops in the
# spool, so nothing here is written to DHIS2.
set -euo pipefail

# A QuestionnaireResponse says what it is in its own `status`. `completed` is an ordinary
# submission. `amended` says it corrects one this project already forwarded, and `entered-in-error`
# says it retracts one. Both are valid R4 and the published form admits both - so whether this
# deployment receives them is a decision the project makes, not something the form settles:
#
#   [forward] corrections = "off" | "amend"      receive a submission that corrects a forwarded one
#   [forward] withdrawals = "off" | "retract"    receive one that retracts it
#
# Both default to off. A deployment that publishes forms and forwards them is not thereby a
# deployment that lets a submitter reach back into what DHIS2 already holds, so the capability is
# stated once rather than assumed. The door is where it is applied: a marked submission against an
# off dial never reaches the spool.

pick_port() {
    local candidate
    for candidate in $(seq 8130 8199); do
        if ! (exec 3<>"/dev/tcp/127.0.0.1/${candidate}") 2>/dev/null; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    echo "no free port between 8130 and 8199" >&2
    return 1
}
PORT="${FHIR_CORRECTIONS_PORT:-$(pick_port)}"
BASE="http://127.0.0.1:${PORT}"

d2w fhir init demo-corrections --id dhis2.fhir.correctionsdemo \
    --canonical http://example.org/fhir/corrections-demo \
    --publisher "Demo Org" --event-program EVTsupVis01 --max-level 2
cd demo-corrections

start_facade() {
    d2w fhir serve --live --no-ui --port "$PORT" >facade.log 2>&1 &
    SERVER_PID=$!
    trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
    for _ in $(seq 1 90); do
        if [ "$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/metadata")" = "200" ]; then
            return 0
        fi
        sleep 1
    done
    echo "the facade did not answer ${BASE}/metadata within 90s:" >&2
    tail -20 facade.log >&2
    return 1
}

stop_facade() {
    kill "$SERVER_PID" 2>/dev/null || true
    trap - EXIT
    wait "$SERVER_PID" 2>/dev/null || true
}

# The status is the whole difference between the three submissions, so each is the same response
# with one field rewritten.
post_as() {
    jq --arg status "$1" '.status = $status' load/EVTsupVis01-example-1.json >submission.json
    curl -s -o outcome.json -w '%{http_code}' -X POST "${BASE}/QuestionnaireResponse" \
        -H 'Content-Type: application/fhir+json' --data-binary @submission.json
}

start_facade
d2w fhir generate load-set --per-target 1

# An ordinary submission, under the defaults. Accepted, spooled, and served back at the Location
# the 201 names.
echo "completed, dials off:         $(post_as completed)"

# A correction, under the same defaults. Refused - and the refusal names the key that would receive
# it, because that is the one thing the client cannot work out from the response it got. `amended`
# is valid R4 and the form admits it, so a bare "not accepted" would read as a mistake in the
# submission rather than as a decision this project made.
echo "amended, corrections off:     $(post_as amended)"
jq -r '.issue[] | "\(.severity)\t\(.expression // [] | join(","))\t\(.diagnostics)"' outcome.json

# A withdrawal, same story, naming its own key.
echo "entered-in-error, off:        $(post_as entered-in-error)"
jq -r '.issue[] | .diagnostics' outcome.json

stop_facade

# Now state both. `amend` receives a submission that names the receipt it corrects; `retract` is
# what `d2w fhir withdraw` requires before it deletes anything. The keys live in fhir.toml because
# they are the deployment's posture rather than one run's - `d2w fhir forward --corrections` and
# `--withdrawals` override them for a single drain.
cat >>fhir.toml <<'TOML'

[forward]
corrections = "amend"
withdrawals = "retract"
TOML

start_facade

# The same two bodies, byte for byte. Stored like any other receipt, status and all: what the door
# decided was whether this project receives them, and nothing about their content changed.
echo "amended, corrections amend:   $(post_as amended)"
echo "entered-in-error, retract:    $(post_as entered-in-error)"
stop_facade

# Three receipts queued - the ordinary one and the two marked ones. Where they go next is the other
# half of each dial: `d2w fhir forward` lands a correction on the corrected receipt's own DHIS2
# identity rather than as a second record, and `d2w fhir withdraw` reads `withdrawals` and deletes
# what a receipt landed. See examples/fhir/cli/forward.sh and examples/fhir/cli/withdraw.sh.
d2w fhir spool --details

cd .. && rm -rf demo-corrections
