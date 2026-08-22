#!/usr/bin/env bash
# [serve.search] backend = "projection" — a register search answered from the synced copy.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# The facade runs `--live`, so there is no SUSHI compile and no docker; nothing here writes to
# DHIS2, and only `d2w fhir sync` writes to the projection.
set -euo pipefail

# `d2w fhir sync` fills the projection - examples/fhir/cli/sync.sh is that command's own story.
# This one is the half that reads it: `[serve.search] backend` says where a register search is
# answered from, and it is the only thing that changes between the two facades below.
#
#   backend = "dhis2"       every search is a tracker query on the instance, per key, per type.
#   backend = "projection"  the finding half is one indexed query over what the sync wrote.
#
# What does NOT move is who may see whom. A match found in the projection is read back from the
# instance before it is served, so DHIS2's sharing, organisation unit scopes, and access levels
# answer per caller exactly as they do under the live backend.

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
PORT="${FHIR_PROJECTION_PORT:-$(pick_port)}"
BASE="http://127.0.0.1:${PORT}"

# The Child Programme's tracked entity type on the seeded demo database.
PERSON_TYPE="nEenWmSyUEp"

d2w fhir init demo-projection-search --id dhis2.fhir.projectionsearchdemo \
    --canonical http://example.org/fhir/projection-search-demo \
    --publisher "Demo Org" --tracker-program IpHINAT79UW --max-level 2
cd demo-projection-search

cat >>fhir.toml <<TOML

[serve.tracked_entities]
tracked_entity_types = ["${PERSON_TYPE}"]

[serve.projection]
store = "sqlite"

[serve.search]
backend = "projection"
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

# Fill the copy. The two keys have to agree before the socket opens - `[serve.search] backend =
# "projection"` with no `[serve.projection] store` is refused when fhir.toml is read, naming both -
# and a store nobody has ever synced into answers a 404 saying so, rather than an empty page that
# would tell a client the instance holds nobody.
d2w fhir sync

start_facade

# Every answer says what it is as of. The instant is the sync's own watermark, not the moment of
# the read - so a client can tell how fresh the answer it is holding is.
curl -s -D- -o /dev/null "${BASE}/Patient?_count=1" | grep -i '^x-dhis2w-projection-as-of'

# `_content` searches across every value a person holds, which is the parameter the projection
# exists for: one indexed query instead of one tracker query per attribute per type.
echo "_content, projection backend: $(curl -s -o bundle.json -w '%{http_code}' "${BASE}/Patient?_content=Sarah&_count=3")"
jq -r '.entry[]? | select(.search.mode == "match") | "match  " + .resource.id' bundle.json

# The bundle says the same thing about itself, in the entry FHIR reserves for saying it.
jq -r '.entry[]? | select(.search.mode == "outcome") | .resource.issue[].diagnostics' bundle.json

stop_facade

# The same project with the one key changed back. `_content` is refused exactly as every other
# parameter this server cannot answer is refused - it names what it does support rather than
# quietly answering something narrower - and no answer carries the as-of header, because there is
# no projection behind it to be as of anything.
sed -i.bak 's/backend = "projection"/backend = "dhis2"/' fhir.toml && rm fhir.toml.bak
start_facade

echo "_content, dhis2 backend:      $(curl -s -o outcome.json -w '%{http_code}' "${BASE}/Patient?_content=Sarah")"
jq -r '.issue[] | .diagnostics' outcome.json
curl -s -D- -o /dev/null "${BASE}/Patient?_count=1" | grep -i '^x-dhis2w-projection-as-of' \
    || echo "no as-of header - this answer came from the instance, as of the moment it was read"
stop_facade

cd .. && rm -rf demo-projection-search
