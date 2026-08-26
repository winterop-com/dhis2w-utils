#!/usr/bin/env bash
# POST /evaluate and POST /$evaluate — the evaluation engine answering over a served guide, from curl.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# The facade runs `--live`, so there is no SUSHI compile and no docker; nothing here writes to DHIS2.
set -euo pipefail

# `d2w fhir` has no evaluate command, and that is the point of this file: evaluation is a property of
# the served guide rather than of the toolchain, so what drives it is an HTTP client. Anything that
# speaks HTTP is a caller - curl here, a notebook, a rules engine, an agent.
#
# Two addresses answer the same evaluation over the same three contexts:
#
#   POST /evaluate    this project's own JSON - typed results, and a parse failure's line and column
#   POST /$evaluate   the FHIR operation - one Parameters resource, one parameter per define
#
# The second is declared in the conformance document and defined by an OperationDefinition the
# server hands out, which is where the contract lives.

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
PORT="${FHIR_EVALUATE_PORT:-$(pick_port)}"
BASE="http://127.0.0.1:${PORT}"

# One data set and two organisation-unit levels: the smallest selection that still publishes a
# Questionnaire worth asking questions about.
d2w fhir init demo-evaluate --id dhis2.fhir.evaluatedemo \
    --canonical http://example.org/fhir/evaluate-demo \
    --publisher "Demo Org" --data-set BfMAe6Itzgt --max-level 2
cd demo-evaluate

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

# The operation is declared at the service base, because what it runs over is whatever the request
# names as its context - so no resource type owns it.
curl -s "${BASE}/metadata" >metadata.json
jq -r '.rest[0].operation[]? | "operation  $" + .name + "  " + .definition' metadata.json

# And the definition itself is served like any other resource. This is the contract: which parameters
# are required, which are optional, and what the parts of a context are.
curl -s "${BASE}/OperationDefinition/serve-evaluate" >operation.json
jq -r '.parameter[] | ("  " + .use + "  " + .name + "  "
         + (.min | tostring) + ".." + .max + "  " + (.type // "(parts)")),
       (.part[]? | "      part  " + .name + "  "
         + (.min | tostring) + ".." + .max + "  " + .type)' operation.json

# The form this guide publishes for the selected data set. Under the default naming a form id is
# the DHIS2 UID, so the data set this project was scaffolded around is the form to ask about.
FORM=BfMAe6Itzgt
echo "stored form: Questionnaire/${FORM} - $(curl -s "${BASE}/Questionnaire/${FORM}" | jq -r '.title')"

# 1. One FHIRPath expression over a resource the server already holds. Nothing is posted but the
#    question: `stored` names the document by type and id, the way a read names one.
evaluate_fhirpath() {
    curl -s -X POST "${BASE}/evaluate" -H 'Content-Type: application/json' -d @- <<JSON
{"language": "fhirpath", "source": "$1",
 "context": {"kind": "stored", "resource_type": "Questionnaire", "resource_id": "${FORM}"}}
JSON
}
for expression in 'Questionnaire.title' 'Questionnaire.item.text' 'Questionnaire.item.item.count()'; do
    echo "  ${expression}  ->  $(evaluate_fhirpath "$expression" | jq -c '.results[0].values')"
done

# 2. An expression that will not parse. It answers 200 with the position the parser stopped on -
#    which is what a caller acts on, and what a 500 would have thrown away.
echo "a bad expression: HTTP $(curl -s -o parse.json -w '%{http_code}' \
      -X POST "${BASE}/evaluate" -H 'Content-Type: application/json' \
      -d '{"language": "fhirpath", "source": "Questionnaire..title"}')"
jq -r '.diagnostics[] | "  " + .kind + " error at line " + (.line | tostring)
       + ", column " + (.column | tostring) + ": " + (.message | split("\n")[0])' parse.json

# 3. The same evaluation as a FHIR operation. A CQL library this time, so the answer has several
#    parameters to show: a string rides value[x], and a collection rides one `part` per value.
curl -s -X POST "${BASE}/\$evaluate" -H 'Content-Type: application/fhir+json' -d @- >parameters.json <<JSON
{"resourceType": "Parameters", "parameter": [
  {"name": "language", "valueCode": "cql"},
  {"name": "source", "valueString": "library FormReview version '1.0'\nusing FHIR version '4.0.1'\n\ndefine \"Form Title\": [Questionnaire] Q return Q.title\ndefine \"Section Count\": [Questionnaire] Q return Count(Q.item)\ndefine \"Section Names\": flatten ([Questionnaire] Q return (Q.item) I return I.text)"},
  {"name": "context", "part": [
    {"name": "kind", "valueCode": "stored"},
    {"name": "resourceType", "valueCode": "Questionnaire"},
    {"name": "resourceId", "valueString": "${FORM}"}]}]}
JSON
echo "the answer is a $(jq -r '.resourceType' parameters.json) of $(jq '.parameter | length' parameters.json) parameter(s)"
jq -r '.parameter[] | "  " + .name + ": "
       + (if .part then ([.part[] | .valueString // .valueInteger | tostring] | join(", "))
          else (.valueString // .valueInteger // .valueBoolean | tostring) end)' parameters.json

# 4. A define that matched nothing carries no parameter at all - FHIR has no empty collection. The
#    same question asked at /evaluate keeps "matched nothing" as a stated row with an empty value.
curl -s -X POST "${BASE}/\$evaluate" -H 'Content-Type: application/fhir+json' -d @- >empty.json <<JSON
{"resourceType": "Parameters", "parameter": [
  {"name": "language", "valueCode": "fhirpath"},
  {"name": "source", "valueString": "Questionnaire.publisher"},
  {"name": "context", "part": [
    {"name": "kind", "valueCode": "stored"},
    {"name": "resourceType", "valueCode": "Questionnaire"},
    {"name": "resourceId", "valueString": "${FORM}"}]}]}
JSON
echo "an expression matching nothing: \$evaluate answered $(jq '.parameter | length' empty.json) parameter(s)"
echo "  the same at /evaluate: $(evaluate_fhirpath 'Questionnaire.publisher' | jq -c '.results[0]')"

# 5. A stored context the guide cannot resolve. Not an empty answer - the question was never asked,
#    and the refusal is an OperationOutcome under a 4xx.
echo "naming a form nobody holds: HTTP $(curl -s -o refusal.json -w '%{http_code}' \
      -X POST "${BASE}/evaluate" -H 'Content-Type: application/json' \
      -d '{"language": "fhirpath", "source": "Questionnaire.title",
           "context": {"kind": "stored", "resource_type": "Questionnaire", "resource_id": "no-such-form"}}')"
jq -r '.issue[] | "  " + .code + ": " + .diagnostics' refusal.json

stop_facade
cd .. && rm -rf demo-evaluate
