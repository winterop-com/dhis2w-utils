#!/usr/bin/env bash
# FHIR facade — generate an IG, compile it, serve it, post a load set, read the receipts back.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# Needs docker for the SUSHI compile, so this one is slow: it is in the verify_examples
# skip-by-default set under "slow server-side jobs".
set -euo pipefail

PORT="${FHIR_SERVE_PORT:-8123}"
BASE="http://127.0.0.1:${PORT}"
CANONICAL="http://example.org/fhir/serve-demo"

# Scaffold a small project. --data-set and --event-program keep the IG to two forms, which
# is what makes the compile short enough to sit inside an example script.
d2w fhir init serve-demo --id dhis2.fhir.servedemo --canonical "$CANONICAL" \
    --publisher "Demo Org" --data-set BfMAe6Itzgt --event-program VBqh0ynB2wv --max-level 2

cd serve-demo

# Generate the IG source, then compile it. The facade serves what SUSHI wrote merged with
# the pre-built JSON the generate targets left in ig/input/resources/ - SUSHI never
# re-emits those, so both trees are loaded.
d2w fhir generate
make setup
make sushi

# Serve it. The default binds loopback (the facade has no authentication) on port 8080;
# --port moves it. Startup loads the project, the store, and the response spool once.
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
curl -sf "${BASE}/Questionnaire/BfMAe6Itzgt" | head -c 200
echo

# Search. Within a parameter, comma-separated values are alternatives; across parameters
# they combine. An unrecognised parameter is ignored, and the Bundle's self link echoes
# back only what was applied.
curl -sf "${BASE}/Questionnaire?_id=BfMAe6Itzgt" | head -c 200
echo

# The identifier search is how a tracker program's stages are selected - the same query
# the published guide documents, answered by a running server. (Scaffold this project
# with --tracker-program IpHINAT79UW to see it return stages.)
curl -sf "${BASE}/Questionnaire?identifier=${CANONICAL}/id/program%7CIpHINAT79UW" | head -c 200
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

# Stop the server and clean up.
kill "$SERVER_PID"
trap - EXIT
wait "$SERVER_PID" 2>/dev/null || true
cd .. && rm -rf serve-demo
