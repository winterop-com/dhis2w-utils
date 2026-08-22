#!/usr/bin/env bash
# FHIR facade — generate an IG, compile it, serve it, post a load set, read the receipts back.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# Needs docker for the SUSHI compile and binds a port for the facade, so `make verify-examples`
# skips it: `infra/scripts/verify_examples.py` lists it under "slow server-side jobs". Run it by
# hand.
set -euo pipefail

PORT="${FHIR_SERVE_PORT:-8123}"
BASE="http://127.0.0.1:${PORT}"
CANONICAL="http://example.org/fhir/serve-demo"

# Scaffold a small project. --data-set and --event-program keep the IG to two forms, which
# is what makes the compile short enough to sit inside an example script.
d2w fhir init serve-demo --id dhis2.fhir.servedemo --canonical "$CANONICAL" \
    --publisher "Demo Org" --data-set TuL8IOPzpHh --event-program EVTsupVis01 --max-level 2

cd serve-demo

# `init` has no flag for the terminology tables, so they are written here. A table left
# absent selects everything of its kind, and one DHIS2 name carrying a raw '<' anywhere in
# that everything refuses the whole generate run.
cat >>fhir.toml <<'TOML'

[generate.option_sets]
include_ids = ["OsVaccType1"]

[generate.categories]
include_ids = ["yY2bQYqNt0o", "Qzh0MSUx4RM"]
TOML

# Generate the IG source, then compile it. The facade serves what SUSHI wrote merged with
# the pre-built JSON the generate targets left in ig/input/resources/ - SUSHI never
# re-emits those, so both trees are loaded.
d2w fhir generate
make setup
make sushi

# Where this project is served from is project config, not an invocation detail: a [serve]
# table states it once and `make serve` reads it too. A flag still wins over the table.
cat >> fhir.toml <<'TOML'

[serve]
host = "127.0.0.1"
port = 8090
strict_codes = false
auth = "none"
TOML

# `auth` is who this facade serves: none, token, dhis2, or jwt. An absent key serves every
# caller on loopback and refuses any other interface at startup, naming the line to write -
# so a project that means to bind 0.0.0.0 states the posture rather than defaulting into it.
# `auth = "none"` written out is that statement. All four postures run in
# examples/fhir/cli/serve_auth_postures.sh; this script is about the routes.

# Serve it. The default binds loopback on port 8080, [serve] port overrides that, and
# --port overrides both. Startup loads the project, the store, and the response spool once.
d2w fhir serve --port "$PORT" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

# Give the store time to load. A large registry takes longer than a two-form IG.
sleep 5

# What this server is: a kind #instance CapabilityStatement instantiating the IG's own
# D2CaptureServer, narrowed to the resource types this store actually holds.
curl -sf "${BASE}/metadata" | head -c 400
echo

# Read one resource. The body is byte-faithful to what the project published.
curl -sf "${BASE}/Questionnaire/TuL8IOPzpHh" | head -c 200
echo

# Search. Within a parameter, comma-separated values are alternatives; across parameters
# they combine. An unrecognised parameter is ignored, and the Bundle's self link echoes
# back only what was applied.
curl -sf "${BASE}/Questionnaire?_id=TuL8IOPzpHh" | head -c 200
echo

# The identifier search is how a tracker program's stages are selected - the same query
# the published guide documents, answered by a running server. (Scaffold this project
# with --tracker-program IpHINAT79UW to see it return stages.)
curl -sf "${BASE}/Questionnaire?identifier=${CANONICAL}/id/program%7CIpHINAT79UW" | head -c 200
echo

# $translate takes a generated concept code back to both DHIS2 identifiers, over the
# ConceptMaps the option-set target publishes. system + code are required; targetsystem
# is optional and narrows the answer to one group. The reply is a Parameters resource.
curl -sf "${BASE}/ConceptMap/\$translate?system=${CANONICAL}/CodeSystem/d2-os-Qdm5fPK5Ra9-cs&code=Op1aaaaaaaa" \
    | head -c 300
echo

# The categories target publishes maps of its own, into the same directory, so the same
# call answers a disaggregation code: which DHIS2 category option is this? targetsystem
# narrows it to the DHIS2 code namespace instead of the UID one.
curl -sf "${BASE}/ConceptMap/\$translate?system=${CANONICAL}/CodeSystem/d2-cat-fMZEcRHuamy-cs&code=qkPbeWaFsnU&targetsystem=http://dhis2.org/fhir/id/category-option-code" \
    | head -c 300
echo

# $generate: hand it a served form and it answers with a synthetic QuestionnaireResponse
# filled in against that form's own rules - value types, bounds, repeats, and real
# concepts of the CodeSystems the questions bind. Instance-level, on the form's resource
# id. It is deliberately NOT SDC's $populate: $populate means fill-from-real-context.
curl -sf "${BASE}/Questionnaire/TuL8IOPzpHh/\$generate" | head -c 300
echo

# The invariant the operation exists for: generated output is immediately postable to the
# same server. 201 means the server accepts what it just produced.
curl -sf "${BASE}/Questionnaire/TuL8IOPzpHh/\$generate" \
    | curl -s -o /dev/null -w '%{http_code}\n' \
        -X POST "${BASE}/QuestionnaireResponse" \
        -H 'Content-Type: application/fhir+json' --data-binary @-

# seed makes it reproducible: same form, same seed, same bytes. Name it on the query, or
# in a Parameters body for the POST spelling. A call naming no seed is answered from one
# the server drew - and states it back on the response's identifier, so it replays too.
curl -sf "${BASE}/Questionnaire/TuL8IOPzpHh/\$generate?seed=4242" | head -c 200
echo
curl -sf -X POST "${BASE}/Questionnaire/TuL8IOPzpHh/\$generate" \
    -H 'Content-Type: application/fhir+json' \
    -d '{"resourceType":"Parameters","parameter":[{"name":"seed","valueInteger":4242}]}' \
    | head -c 200
echo

# A load set: synthetic QuestionnaireResponse JSON to POST at the facade. Seeded from the
# target UID and the ordinal, so a rerun over unchanged metadata writes identical files.
# It lands in load/ beside ig/ - a load set is not IG source, it is gitignored by the
# scaffold, and `d2w fhir generate` deliberately does not write it.
d2w fhir generate load-set --per-target 5

# Post the lot. An accepted capture answers 201 with a Location header naming where the
# receipt is served from; a refused one answers 400 or 422 with an OperationOutcome.
for response in load/*.json; do
    curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' \
        -X POST "${BASE}/QuestionnaireResponse" \
        -H 'Content-Type: application/fhir+json' \
        --data-binary "@${response}"
done

# Read the receipts back. A stored response is the submission as it arrived - what was
# submitted, never what DHIS2 currently holds. Nothing has been written to the instance.
curl -sf "${BASE}/QuestionnaireResponse" | head -c 200
echo

# The spool on disk is the same set, one file per receipt, so `ls` is the pending count.
ls .serve/responses/received | wc -l

# Coded answers are lenient by default: a code in the wrong DHIS2 spelling resolves and
# warns, and a code the served terminology does not hold is stored with a warning.
# --strict-codes refuses both instead. The published contract stays strict either way.
# d2w fhir serve --port "$PORT" --strict-codes

# --live skips the compile entirely and builds the served resources off the instance at
# startup, through one client closed before the first request. Same routes, same shapes.
# d2w fhir serve --port "$PORT" --live

# Who this facade answers is its own story, and it has its own script: static bearer tokens
# out of the environment, the caller's own DHIS2 credentials checked against the instance,
# and a token from an OpenID Connect issuer. See examples/fhir/cli/serve_auth_postures.sh.

# Stop the server and clean up.
kill "$SERVER_PID"
trap - EXIT
wait "$SERVER_PID" 2>/dev/null || true
cd .. && rm -rf serve-demo
