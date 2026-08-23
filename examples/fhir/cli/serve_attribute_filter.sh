#!/usr/bin/env bash
# `d2-attribute` — asking the register which of its records hold a value.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# The facade runs `--live`, so there is no SUSHI compile and no docker; nothing here writes to
# DHIS2, and only `d2w fhir sync` writes to the projection.
set -euo pipefail

# `identifier` answers the attributes DHIS2 declares unique - it names ONE record. This is the
# other question: the attributes DHIS2 declares nothing about describe a lot of records at once,
# and `d2-attribute={trackedEntityAttributeUid}|{value}` is how a caller asks for the ones holding
# a value.
#
# IT MATCHES THE WHOLE VALUE. Equality, case-insensitively, and nothing else - no prefix, no
# substring, no range. `_content` is the search that matches part of a value, and it needs the
# synced backend; this one is answered by both.

pick_port() {
    local candidate
    for candidate in $(seq 8152 8199); do
        if ! (exec 3<>"/dev/tcp/127.0.0.1/${candidate}") 2>/dev/null; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    echo "no free port between 8152 and 8199" >&2
    return 1
}
PORT="${FHIR_ATTRIBUTE_FILTER_PORT:-$(pick_port)}"
BASE="http://127.0.0.1:${PORT}"

# The Child Programme's tracked entity type on the seeded demo database, and two of the attributes
# its registration form asks: the sex, which DHIS2 binds to an option set, and the given name,
# which is free text.
PERSON_TYPE="nEenWmSyUEp"
GENDER="cejWyOfXge6"
FIRST_NAME="w75KJ2mc4zz"

d2w fhir init demo-attribute-filter --id dhis2.fhir.attributefilterdemo \
    --canonical http://example.org/fhir/attribute-filter-demo \
    --publisher "Demo Org" --tracker-program IpHINAT79UW --max-level 2
cd demo-attribute-filter

cat >>fhir.toml <<TOML

[serve.tracked_entities]
tracked_entity_types = ["${PERSON_TYPE}"]

[serve.projection]
store = "sqlite"
TOML

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

# WHICH ATTRIBUTES A REGISTER FILTERS ON IS DECLARED BEFORE ANY REQUEST, because the filter names
# an attribute by an eleven-character DHIS2 id nobody guesses. `/metadata` states it as prose on
# the search parameter, which is where a FHIR client reads what a parameter means.
curl -s "${BASE}/metadata" \
    | jq -r '.rest[].resource[] | select(.type == "Patient") | .searchParam[]
             | select(.name == "d2-attribute") | .documentation'

# `/uiconfig` states the same set as values, which is what a screen needs to draw the control: the
# id to filter by, the name to label it, the DHIS2 value type, and - where DHIS2 binds an option
# set - the canonical of the published ValueSet whose concepts are the choices.
curl -s "${BASE}/uiconfig" \
    | jq -r '.tracked_entities.registers[] | select(.resource == "Patient") | .filter_attributes[]
             | "\(.uid)  \(.name)  \(.value_type)  \(.value_set // "no option set - free text")"'

# `_count=0` asks how large a register is without carrying anybody back, so the whole register and
# the filtered register are two numbers read the same way. They differ, which is the whole point.
echo "everybody:            $(curl -s "${BASE}/Patient?_count=0" | jq -r '.total')"
echo "sex = Female:         $(curl -s "${BASE}/Patient?_count=0&d2-attribute=${GENDER}%7CFemale" | jq -r '.total')"

# Case is the one thing equality forgives here, because DHIS2's own `eq` forgives it (BUGS.md 109).
echo "sex = female:         $(curl -s "${BASE}/Patient?_count=0&d2-attribute=${GENDER}%7Cfemale" | jq -r '.total')"

# A PREFIX FINDS NOBODY. This is equality; a filter that quietly answered a prefix would be a
# search wearing equality's name.
echo "sex = Fem:            $(curl -s "${BASE}/Patient?_count=0&d2-attribute=${GENDER}%7CFem" | jq -r '.total')"

# The parameter repeated narrows: whoever holds both values. Two filters, one tracker query, ANDed
# by the endpoint. Every Jennifer here is a woman, so the second number is the first and the third
# is nobody - which is the difference between narrowing and widening, in three lines.
echo "given name Jennifer:  $(curl -s "${BASE}/Patient?_count=0&d2-attribute=${FIRST_NAME}%7CJennifer" | jq -r '.total')"
echo "  and sex = Female:   $(curl -s "${BASE}/Patient?_count=0&d2-attribute=${FIRST_NAME}%7CJennifer&d2-attribute=${GENDER}%7CFemale" | jq -r '.total')"
echo "  and sex = Male:     $(curl -s "${BASE}/Patient?_count=0&d2-attribute=${FIRST_NAME}%7CJennifer&d2-attribute=${GENDER}%7CMale" | jq -r '.total')"

# And it composes with everything else the register answers - here `_count`, which sizes the page
# the matches come back on. Each entry is read from the instance under the credentials this request
# runs as, exactly as an unfiltered page is.
curl -s "${BASE}/Patient?d2-attribute=${FIRST_NAME}%7CJennifer&d2-attribute=${GENDER}%7CFemale&_count=5" >filtered.json
jq -r '.entry[]? | select(.search.mode == "match") | "live       " + .resource.id' filtered.json

# An attribute this register does not filter on is a refusal naming the ones it does. Answering it
# with an empty searchset would tell a client that nobody holds the value, which is a different and
# false statement.
echo "an undeclared attribute: $(curl -s -o refusal.json -w '%{http_code}' "${BASE}/Patient?d2-attribute=aaaaaaaaaaa%7CFemale")"
jq -r '.issue[].diagnostics' refusal.json

stop_facade

# THE SAME QUESTION OF THE SYNCED COPY. `d2w fhir sync` indexes every attribute value every record
# holds - it is the index `_content` reads - so the filter is one indexed query over a local file
# rather than a tracker query, and the answer is the same records.
sed -i.bak 's/^store = "sqlite"$/store = "sqlite"\n\n[serve.search]\nbackend = "projection"/' fhir.toml && rm fhir.toml.bak
d2w fhir sync
start_facade

curl -s "${BASE}/Patient?d2-attribute=${FIRST_NAME}%7CJennifer&d2-attribute=${GENDER}%7CFemale&_count=5" >synced.json
jq -r '.entry[]? | select(.search.mode == "match") | "projection " + .resource.id' synced.json

# The same records, whichever backend was asked - sorted here, because the two orders are the two
# backends' own: DHIS2 answers in its order and the projection walks its rows by id.
diff <(jq -r '.entry[]? | select(.search.mode == "match") | .resource.id' filtered.json | sort) \
     <(jq -r '.entry[]? | select(.search.mode == "match") | .resource.id' synced.json | sort) \
    && echo "both backends named the same records"

# A synced answer states the instant it is as of, which a live one does not - the membership came
# from the projection, and every record on the page was still read from the instance.
jq -r '.entry[]? | select(.search.mode == "outcome") | .resource.issue[].diagnostics' synced.json

stop_facade

cd .. && rm -rf demo-attribute-filter
