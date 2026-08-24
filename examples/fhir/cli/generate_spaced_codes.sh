#!/usr/bin/env bash
# d2w fhir generate --substitute-hostile-names — publish a DHIS2 code carrying a space, hyphenated.
set -euo pipefail

d2w fhir init demo-spaced-codes --id dhis2.fhir.spacedcodesdemo \
    --canonical http://example.org/fhir/spaced-codes-demo --publisher "Demo Org"
cd demo-spaced-codes

# The "MNCH IPT" option set codes its options "IPT 1", "IPT 2", "IPT 3", "On CTX". A space is
# legal in an R4 code, so nothing refuses them - and the IG publisher's anchor slug strips
# whitespace, so two codes differing only in a space render one anchor id, and every URL and
# CQL reference below the guide escapes or quotes the space at its own discretion.
# `concept_code_source = "code"` publishes the DHIS2 code as the concept code, which is where
# the rewrite is easiest to see.
cat >> fhir.toml <<'TOML'
concept_code_source = "code"

[generate.option_sets]
include_ids = ["nH8Y04zS7UV"]
TOML

# The substitute posture hyphenates every space. DHIS2 is never written to and no UID moves:
# each rewritten concept states its DHIS2 code beside it as a `dhis2-code` property, and the
# ConceptMaps keep taking a published concept back to its DHIS2 UID. `--refuse-hostile-names`
# and an unanswered run publish every code byte-true instead.
d2w fhir generate --substitute-hostile-names option-sets

# What the guide publishes, and what it says DHIS2 holds.
grep -A 8 '"code": "IPT-1"' ig/input/resources/terminology/CodeSystem-d2-os-nH8Y04zS7UV-cs.json

# The identifier namespace the ConceptMaps target carries the same pair, which is the one
# BUGS.md 107's duplicate anchor ids collide in.
grep -B 1 -A 6 '"code": "On-CTX"' ig/input/resources/terminology/CodeSystem-d2-option-code-id-cs.json

cd .. && rm -rf demo-spaced-codes
