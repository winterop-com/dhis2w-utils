#!/usr/bin/env bash
# d2w fhir check-artifacts — the build refusal, read off the artifacts already on disk.
set -euo pipefail

# `d2w fhir generate` refuses a selection whose DHIS2 names or codes carry a raw '<', because the
# IG publisher writes both into pages it strict-parses after writing and dies on the malformed page
# in its final pass - after every resource has already been rendered. A build reads no such gate: it
# publishes whatever ig/fsh-generated/ and ig/input/ hold. Output written before the gate existed,
# output from an older toolchain pin, and hand-authored FSH all reach the publisher without passing
# it. This command applies the same refusal, through the same predicates, to the files themselves.
#
# It opens no connection and reads no profile, so this whole example runs offline.
d2w fhir init demo-check-artifacts --id dhis2.fhir.checkdemo \
    --canonical http://example.org/fhir/check-demo --publisher "Demo Org"
cd demo-check-artifacts

# The foundation target is the one that reads fhir.toml alone, so the project has real artifacts
# without an instance behind it.
d2w fhir generate foundation

# A clean tree is a build that may start: every publishable file read, nothing found, exit 0.
d2w fhir check-artifacts

# Now the thing the command exists for - a compiled resource on disk that no generate run would have
# written. A stale artifact, an old lock's output, and a hand-authored file all look exactly like this.
mkdir -p ig/fsh-generated/resources
cat > ig/fsh-generated/resources/CodeSystem-d2-os-Age.json <<'JSON'
{
  "resourceType": "CodeSystem",
  "id": "d2-os-Age",
  "title": "Age (<5 - 49) & over",
  "identifier": [{"system": "http://example.org/fhir/check-demo/os", "value": "AGE<5"}],
  "concept": [{"code": "u5", "display": "<5 y"}]
}
JSON

# Three findings, in seconds, each naming the file, the resource, the element, and the value. The
# exit code is the whole point: it is what `make build` runs this for, so read it rather than let
# `set -e` take the script down.
d2w fhir check-artifacts || echo "check-artifacts refused the build - the gate did its job"

cd .. && rm -rf demo-check-artifacts
