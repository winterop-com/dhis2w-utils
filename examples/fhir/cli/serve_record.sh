#!/usr/bin/env bash
# GET /tracked-entities/{uid}/events — one tracked entity's own record, read from the instance.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# The facade runs `--live`, so there is no SUSHI compile and no docker; nothing here writes to DHIS2.
set -euo pipefail

# The register answers who somebody is. This answers what has happened to them: every event of
# every enrollment one tracked entity holds, each served as the QuestionnaireResponse the guide
# already publishes for its program stage.
#
# The shape is the capture contract's, read backwards - the same document a client posts to capture
# an event is the document it reads back - so nothing new has to be learned to consume it, and no
# clinical resource is invented for data DHIS2 states no mapping for.

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
PORT="${FHIR_RECORD_PORT:-$(pick_port)}"
BASE="http://127.0.0.1:${PORT}"

d2w fhir init demo-record --id dhis2.fhir.recorddemo \
    --canonical http://example.org/fhir/record-demo \
    --publisher "Demo Org" --tracker-program IpHINAT79UW --max-level 2
cd demo-record

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

start_facade

# Find somebody the instance holds, the way a client with no identifier to type would: one page of
# the register. Then ask each of them for their record until one has a value recorded in it - a
# person the demo database enrolled but never followed up has a record with nothing in it, which is
# a true answer and a dull example.
curl -s "${BASE}/Patient?_count=30" >register.json
PERSON=""
for candidate in $(jq -r '.entry[]?.resource.id' register.json); do
    curl -s "${BASE}/tracked-entities/${candidate}/events" >candidate.json
    [ "$(jq -r '.total' candidate.json)" != "0" ] || continue
    [ -n "$PERSON" ] || PERSON="$candidate"
    if [ "$(jq -r '[.. | objects | select(has("linkId") and has("answer"))] | length' candidate.json)" != "0" ]; then
        PERSON="$candidate"
        break
    fi
done
[ -n "$PERSON" ] || { echo "no person on this page of the register has an event yet" >&2; exit 1; }

# How long the record is, without building a page of it. R4's own `_count=0`.
echo "events in the record: $(curl -s "${BASE}/tracked-entities/${PERSON}/events?_count=0" | jq -r '.total')"

# The record itself, newest first. Each entry is one event: which form it answers, when it happened,
# and the URL that one document is served at.
curl -s "${BASE}/tracked-entities/${PERSON}/events" >record.json
jq -r '.entry[]? | select(.search.mode == "match")
       | "event  " + .resource.id
         + "  form " + (.resource.questionnaire | split("/") | last)
         + "  occurred " + (.resource.authored // "not dated by the instance")' record.json

# Every recorded value, typed by the very form a submission is validated against: the item type
# decides which `value[x]` element carries it, and the DHIS2 value type decides what that element
# carries. An answer to an option-set question comes back as the concept this guide publishes -
# DHIS2 stores the option's own code, and the served CodeSystem publishes that code beside the
# concept code, so a consumer resolves the coding rather than guessing what the string meant.
jq -r '[.entry[]? | select(.search.mode == "match") | .resource | .. | objects
        | select(has("linkId") and has("answer"))] | .[0:6][]
       | .linkId as $question | (.answer[0] | to_entries[0])
       | "value  " + $question + " = "
         + (if (.value | type) == "object"
            then (.value.code // "") + " (" + (.value.display // "no display") + ")"
            else (.value | tostring) end)
         + "  [" + .key + "]"' record.json

# One event on its own, at the URL its entry named. `QuestionnaireResponse/{id}` is deliberately a
# different address: that one answers the spool, where a document is a receipt of what a client
# submitted rather than what DHIS2 holds now.
EVENT_URL="$(jq -r 'first(.entry[]? | select(.search.mode == "match") | .fullUrl)' record.json)"
echo "one event:     $(curl -s -o event.json -w '%{http_code}' "$EVENT_URL")"
jq -r '"subject  " + (.subject.type // "no type") + " " + (.subject.identifier.value // "")' event.json

# `_count` and `page` walk the record; anything else is refused rather than ignored, because a
# parameter this server cannot apply, ignored, answers a narrower question with the whole record.
echo "programStage:  $(curl -s -o refusal.json -w '%{http_code}' "${BASE}/tracked-entities/${PERSON}/events?programStage=A03MvHHogjR")"
jq -r '.issue[].diagnostics' refusal.json

stop_facade

# The record is a dial of its own. A project that publishes who its subjects are and not what was
# recorded about them keeps the register and drops this surface, and the refusal names the line.
cat >>fhir.toml <<'TOML'

[serve.tracked_entities]
events = false
TOML
start_facade
echo "events = false: $(curl -s -o disabled.json -w '%{http_code}' "${BASE}/tracked-entities/${PERSON}/events")"
jq -r '.issue[].diagnostics' disabled.json
echo "the register:   $(curl -s -o /dev/null -w '%{http_code}' "${BASE}/Patient/${PERSON}")"
stop_facade

cd .. && rm -rf demo-record
