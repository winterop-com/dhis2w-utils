#!/usr/bin/env bash
# GET /Patient/{uid}/$summary — one person's International Patient Summary, assembled from the record.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# The facade runs `--live`, so there is no SUSHI compile and no docker; nothing here writes to DHIS2.
set -euo pipefail

# The register answers who somebody is, the record answers what has happened to them, and this
# answers the one document a clinician asks for: a FHIR document Bundle whose Composition indexes
# the sections of an International Patient Summary.
#
# Two things make that document honest. Which attribute is a person's name and sex is stated in
# [ips.identity], and which recorded values are doses is stated in [ips.sections.immunizations] -
# DHIS2 states neither itself. Everything nobody stated is absent and says so.

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
PORT="${FHIR_SUMMARY_PORT:-$(pick_port)}"
BASE="http://127.0.0.1:${PORT}"

d2w fhir init demo-summary --id dhis2.fhir.summarydemo \
    --canonical http://example.org/fhir/summary-demo \
    --publisher "Demo Org" --tracker-program IpHINAT79UW --max-level 2
cd demo-summary

# The two nominations, and the dial that publishes the document at all. `[ips] enabled` is false by
# default: a clinical document about a person is a posture a deployment states rather than one it
# inherits, and a project that states nothing is refused by the key's own name.
cat >>fhir.toml <<'TOML'

[ips]
enabled = true

[ips.identity]
name = "w75KJ2mc4zz"
sex = "cejWyOfXge6"

[ips.identity.administrative_gender]
Female = "female"
Male = "male"

# Child Programme records one data element per vaccine and the value says which dose - so the data
# element is the vaccine and the value is the dose.
[ips.sections.immunizations]
program_stages = ["A03MvHHogjR", "ZzYYXq4fJie"]
dose_data_elements = ["bx6fsa0t90x", "ebaJjqltK5N", "FqlgKAG8HOu", "vTUhAUZFoys", "rxBfISxXS2U", "pOe0ogW4OWd"]
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

# A client that speaks IPS finds the operation where the IPS defines it: `summary` on Patient,
# under HL7's own OperationDefinition rather than one this project invented.
curl -s "${BASE}/metadata" >metadata.json
jq -r '.rest[0].resource[] | select(.operation) | .type as $t | .operation[]
       | "operation  " + $t + "/$" + .name + "  " + .definition' metadata.json

# Find somebody with a dose recorded. A child the demo database enrolled but never followed up has
# a summary with an empty Immunizations section, which is a true answer and a dull example.
curl -s "${BASE}/Patient?_count=30" >register.json
PERSON=""
for candidate in $(jq -r '.entry[]?.resource.id' register.json); do
    curl -s "${BASE}/Patient/${candidate}/\$summary" >candidate.json
    [ "$(jq -r '[.entry[]?.resource | select(.resourceType == "Immunization")] | length' candidate.json)" != "0" ] || continue
    PERSON="$candidate"
    break
done
[ -n "$PERSON" ] || { echo "no person on this page of the register has a dose recorded yet" >&2; exit 1; }

# The instance form. The caveat rides twice: in the document's own `Composition.text`, which is what
# a reader of the saved file meets, and in a header, which is what a proxy log or a `curl -I` meets.
curl -s -D headers.txt "${BASE}/Patient/${PERSON}/\$summary" >summary.json
echo "bundle type:   $(jq -r '.type' summary.json), $(jq -r '.entry | length' summary.json) entries"
grep -i '^x-dhis2w-summary-caveat:' headers.txt | cut -c1-160

# Section by section. The three the IPS requires carry an empty reason - DHIS2 marks no data element
# as a problem, an allergy, or a medication, and nothing is invented to fill them. The one this
# project mapped carries real entries.
jq -r '.entry[0].resource.section[]
       | "section  " + (.title | .[0:28])
         + "  entries " + ((.entry // []) | length | tostring)
         + "  " + (.emptyReason.coding[0].code // "populated")' summary.json

# Every dose, read off this person's own events. `vaccineCode` carries the DHIS2 data element the
# dose was recorded against: the IPS binds that element preferably rather than requiredly, so a
# DHIS2 coding is publishable there while an international vaccine vocabulary is still missing.
jq -r '.entry[].resource | select(.resourceType == "Immunization")
       | "dose     " + (.vaccineCode.coding[0].display // .vaccineCode.coding[0].code)
         + "  " + (.occurrenceDateTime // "not dated by the instance")
         + "  " + ((.protocolApplied[0].doseNumberString // "no dose number stated"))' summary.json

# The subject is the very resource the register serves, with the nominated name and sex read off it.
jq -r '.entry[].resource | select(.resourceType == "Patient")
       | "subject  " + (.id) + "  " + ((.name[0].text) // "no name nominated")
         + "  " + (.gender // "no gender mapped")' summary.json

# The type-level form: the IPS says a requestor SHALL provide an identifier, and it is the same
# token grammar `GET /Patient?identifier=` answers. It resolves to the same person and therefore
# the same document.
IDENTIFIER="$(jq -r '.entry[].resource | select(.resourceType == "Patient")
                     | .identifier[0].system + "|" + .identifier[0].value' summary.json)"
curl -s -G "${BASE}/Patient/\$summary" --data-urlencode "identifier=${IDENTIFIER}" >by_identifier.json
echo "same document: $(jq -S 'del(.timestamp) | .entry[0].resource |= del(.date)' summary.json \
                       | diff -q - <(jq -S 'del(.timestamp) | .entry[0].resource |= del(.date)' by_identifier.json) \
                       >/dev/null && echo yes || echo no)"

# A summary is about one person, so a type-level call naming nobody is refused rather than answered
# with a page of them.
echo "no identifier: $(curl -s -o refusal.json -w '%{http_code}' "${BASE}/Patient/\$summary")"
jq -r '.issue[].diagnostics' refusal.json

stop_facade

# The dial is the whole surface. A project that publishes no summary is refused by the key's name,
# and its register and record answer exactly as they always did.
sed -i.bak 's/^enabled = true$/enabled = false/' fhir.toml && rm -f fhir.toml.bak
start_facade
echo "enabled=false: $(curl -s -o disabled.json -w '%{http_code}' "${BASE}/Patient/${PERSON}/\$summary")"
jq -r '.issue[].diagnostics' disabled.json
echo "the register:  $(curl -s -o /dev/null -w '%{http_code}' "${BASE}/Patient/${PERSON}")"
stop_facade

cd .. && rm -rf demo-summary
