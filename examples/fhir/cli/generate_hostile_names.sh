#!/usr/bin/env bash
# d2w fhir generate --substitute-hostile-names — publish a DHIS2 name the IG publisher cannot build.
set -euo pipefail

d2w fhir init demo-hostile-names --id dhis2.fhir.hostilenamesdemo \
    --canonical http://example.org/fhir/hostile-names-demo --publisher "Demo Org"
cd demo-hostile-names

# Child Health asks a data element DHIS2 calls "Vitamin A given to < 5y", and disaggregates
# over an age category whose options are named "<1y" and the like. Those names are the
# instance's own, and they are what a Questionnaire's question text, a data dictionary
# concept display, and a disaggregation cell label are built from.
cat >> fhir.toml <<'TOML'

[generate.data_sets]
include_ids = ["BfMAe6Itzgt"]

[generate.event_programs]
include_ids = []

[generate.tracker_programs]
include_ids = []
TOML

# The default answer: the run writes nothing and names the object. A '<' opens a tag in the
# pages the IG publisher writes and then strict-parses, so `make build` would die in its last
# pass, hours in, once every resource had already been rendered. Read the exit code rather
# than let `set -e` take the script down.
d2w fhir generate --refuse-hostile-names questionnaires \
    || echo "the run was refused - that is the gate, not a failure"

# The other answer. The guide publishes the wording the name stands for - "Vitamin A given to
# under 5y" - and every rewrite lands in the notes, one per distinct DHIS2 name. DHIS2 itself
# is never written to, and no code, UID, or identifier value is rewritten, so the ConceptMaps
# still take every published concept back to the DHIS2 object it came from. Without either
# flag the run shows the names with their rewrites and asks; with no terminal to ask on it
# names both flags and rewrites nothing, so a script is never left hanging on a question.
# `[generate] hostile_names = "substitute"` is the same answer, standing, for one project.
d2w fhir generate --substitute-hostile-names questionnaires

# What the guide now states, where DHIS2 states '<'.
grep -o "Vitamin A given to under 5y" ig/input/fsh/data-sets/*.fsh | head -1

# And the proof it was worth doing: the same predicates a build runs first, over every file
# this run wrote, find nothing.
d2w fhir check-artifacts

cd .. && rm -rf demo-hostile-names
