#!/usr/bin/env bash
# d2w fhir generate — the whole IG source from DHIS2 metadata, in one run.
set -euo pipefail

# A small project: two data sets, one event program, the registry capped at level 2 so the
# run stays quick. Generation reads its config from the nearest fhir.toml (walking up from
# $PWD), so run from inside the project; the DHIS2 profile comes from -p/DHIS2_PROFILE,
# falling back to the optional `profile` key in fhir.toml.
d2w fhir init demo-generate --id dhis2.fhir.generatedemo \
    --canonical http://example.org/fhir/generate-demo --publisher "Demo Org" \
    --data-set BfMAe6Itzgt --event-program VBqh0ynB2wv --max-level 2
cd demo-generate

# The bare run is the one to reach for: it reads the instance once and builds all seven
# targets off that single result (8 requests where the solo target commands total 25),
# running foundation first because it reads nothing and pages last because they narrate the
# rest. One summary row per target; the notes a run raises go to
# reports/fhir-generate-notes.md with one counted hint (--details prints them inline).
#
# Re-running replaces previously generated .fsh and .md files (identified by their header
# line); hand-authored ones are never touched. JSON carries no header, so each JSON target
# owns its directory outright and clears what it did not write.
d2w fhir generate

# What landed where: FSH under ig/input/fsh/, pre-built JSON under ig/input/resources/,
# markdown under ig/input/pagecontent/.
ls ig/input/fsh
ls ig/input/resources

# --no-progress silences the stderr narration; --json puts the whole report on stdout with
# stderr quiet, so a caller pipes it straight into jq.
# d2w fhir generate --no-progress
# d2w --json fhir generate > generate-report.json

# Compile the emitted source with the scaffolded docker setup when you are ready to build:
# make setup && make sushi

cd .. && rm -rf demo-generate
