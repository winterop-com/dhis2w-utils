#!/usr/bin/env bash
# GET /facade/data-sets/{uid}/responses — what DHIS2 holds for one form, read from the instance.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# The facade runs `--live`, so there is no SUSHI compile and no docker; nothing here writes to DHIS2.
set -euo pipefail

# The record answers "what has happened to this person". This answers "what does DHIS2 hold for
# this form, this period, this organisation unit" — one QuestionnaireResponse per reporting key,
# each in the shape the data set's own published form describes.
#
# The shape is the capture contract's, read backwards: the same document a client posts to capture
# an aggregate form is the document it reads back, so an aggregate client round-trips a form
# through the guide without ever speaking the DHIS2 API.

DATA_SET="BfMAe6Itzgt"
ROOT_ORG_UNIT="ImspTQPwCqd"

pick_port() {
    local candidate
    for candidate in $(seq 8230 8299); do
        if ! (exec 3<>"/dev/tcp/127.0.0.1/${candidate}") 2>/dev/null; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    echo "no free port between 8230 and 8299" >&2
    return 1
}
PORT="${FHIR_DATA_SET_PORT:-$(pick_port)}"
BASE="http://127.0.0.1:${PORT}"

# One data set, and the organisation units deep enough that the facility a value was reported at is
# published as a Location the served document's subject can point at.
d2w fhir init demo-data-set --id dhis2.fhir.datasetdemo \
    --canonical http://example.org/fhir/data-set-demo \
    --publisher "Demo Org" --data-set "$DATA_SET" --max-level 4
cd demo-data-set

start_facade() {
    d2w fhir serve --live --no-ui --port "$PORT" >facade.log 2>&1 &
    SERVER_PID=$!
    trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
    for _ in $(seq 1 120); do
        if [ "$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/metadata")" = "200" ]; then
            return 0
        fi
        sleep 1
    done
    echo "the facade did not answer ${BASE}/metadata within 120s:" >&2
    tail -20 facade.log >&2
    return 1
}

stop_facade() {
    kill "$SERVER_PID" 2>/dev/null || true
    trap - EXIT
    wait "$SERVER_PID" 2>/dev/null || true
}

# Which organisation unit reported this data set, and for which period. The read below is bounded by
# exactly those two, so they are what has to be found first — and the DHIS2 side of `d2w` is what
# finds them, since the facade deliberately answers no "everywhere, ever" question.
d2w --json data aggregate get --ds "$DATA_SET" --ou "$ROOT_ORG_UNIT" --children \
    --start-date 2020-01-01 --end-date 2030-12-31 --limit 500 >discovered.json
ORG_UNIT="$(jq -r '.dataValues[0].orgUnit' discovered.json)"
PERIODS="$(jq -r '[.dataValues[].period] | unique | .[0:2] | .[]' discovered.json)"
[ "$ORG_UNIT" != "null" ] || { echo "this instance holds no values for ${DATA_SET}" >&2; exit 1; }
QUERY="orgUnit=${ORG_UNIT}"
for period in $PERIODS; do QUERY="${QUERY}&period=${period}"; done
echo "reporting:     ${ORG_UNIT}, periods $(printf '%s ' $PERIODS)"

start_facade

# How many forms the selection holds, without building a page of them. R4's own `_count=0`.
echo "forms:         $(curl -s "${BASE}/facade/data-sets/${DATA_SET}/responses?${QUERY}&_count=0" | jq -r '.total')"

# The forms themselves, ordered by the reporting key — organisation unit, then period, then
# attribute option combo — so two reads of an unchanged period answer the same bytes.
curl -s "${BASE}/facade/data-sets/${DATA_SET}/responses?${QUERY}" >responses.json
jq -r '.entry[]? | select(.search.mode == "match") | .resource
       | "form   " + .id
         + "  questionnaire " + (.questionnaire | split("/") | last)
         + "  status " + .status' responses.json

# Every reported cell, typed by the very form a submission is checked against: the item type decides
# which `value[x]` element carries it, and the DHIS2 value type decides what that element carries. A
# disaggregated cell's link id is `<dataElement>.<categoryOptionCombo>`, which is the one place the
# pair travels on the wire.
jq -r '[.entry[]? | select(.search.mode == "match") | .resource | .. | objects
        | select(has("linkId") and has("answer"))] | .[0:6][]
       | .linkId as $cell | (.answer[0] | to_entries[0])
       | "cell   " + $cell + " = " + (.value | tostring) + "  [" + .key + "]"' responses.json

# The period each form reports for, as the D2Period extension carries it — the DHIS2 ISO identifier,
# its period type, and the calendar range it resolves to. It is the same spelling `$generate` writes
# onto a draft, so a draft and a served document date themselves identically.
jq -r 'first(.entry[]? | select(.search.mode == "match") | .resource.extension[]
       | select(.url | endswith("d2-period")) | .extension)
       | "period " + (map(select(.url == "iso")) | .[0].valueString)
         + "  type " + (map(select(.url == "type")) | .[0].valueCode)
         + "  " + (map(select(.url == "period")) | .[0].valuePeriod.start)
         + " to " + (map(select(.url == "period")) | .[0].valuePeriod.end)' responses.json

# One reported form on its own, at the URL its entry named. The id is the three reporting keys —
# `{orgUnit}-{period}-{attributeOptionCombo}`, with `default` for a data set on the default category
# combination — so this read needs no parameters at all: the id names the read.
FORM_URL="$(jq -r 'first(.entry[]? | select(.search.mode == "match") | .fullUrl)' responses.json)"
echo "one form:      $(curl -s -o form.json -w '%{http_code}' "$FORM_URL")"
jq -r '"subject  " + .subject.reference' form.json

# The organisation unit and at least one period are required. A read missing either is every
# organisation unit that reports this data set, for every period it collects, in one answer.
echo "no period:     $(curl -s -o refusal.json -w '%{http_code}' "${BASE}/facade/data-sets/${DATA_SET}/responses?orgUnit=${ORG_UNIT}")"
jq -r '.issue[].diagnostics' refusal.json

# `period` repeats, and every value named is read whole — so the count is what bounds what one
# request costs, and `[serve.data_sets] period_limit` is where a project writes down how much it
# will answer at once. A request above it names both numbers, so the client knows how to split it.
MANY="orgUnit=${ORG_UNIT}"
for year in 2014 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025 2026; do
    MANY="${MANY}&period=${year}"
done
echo "13 periods:    $(curl -s -o toomany.json -w '%{http_code}' "${BASE}/facade/data-sets/${DATA_SET}/responses?${MANY}")"
jq -r '.issue[].diagnostics' toomany.json

# Anything this surface cannot apply is refused rather than ignored, because a parameter that was
# quietly dropped would answer a narrower question with the whole selection.
echo "children=true: $(curl -s -o unknown.json -w '%{http_code}' "${BASE}/facade/data-sets/${DATA_SET}/responses?${QUERY}&children=true")"
jq -r '.issue[].diagnostics' unknown.json

stop_facade

# The values are a dial of their own. A project that publishes its data set forms and not the numbers
# reported against them keeps the forms and drops this surface, and the refusal names the line.
cat >>fhir.toml <<'TOML'

[serve.data_sets]
responses = false
TOML
start_facade
echo "responses off: $(curl -s -o disabled.json -w '%{http_code}' "${BASE}/facade/data-sets/${DATA_SET}/responses?${QUERY}")"
jq -r '.issue[].diagnostics' disabled.json
echo "the form:      $(curl -s -o /dev/null -w '%{http_code}' "${BASE}/Questionnaire?identifier=http://dhis2.org/fhir/id/data-set|${DATA_SET}")"
stop_facade

cd .. && rm -rf demo-data-set
