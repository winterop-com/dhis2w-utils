#!/usr/bin/env bash
# d2w --json fhir generate — the typed GenerateFullReport on stdout, for jq and for CI.
set -euo pipefail

d2w fhir init demo-generate-json --id dhis2.fhir.generatejsondemo \
    --canonical http://example.org/fhir/generate-json-demo --publisher "Demo Org" \
    --data-set TuL8IOPzpHh --max-level 2
cd demo-generate-json

# A table left absent selects everything of its kind, and one DHIS2 name carrying a raw '<'
# anywhere in that everything refuses the whole run, so the terminology tables are named here.
cat >>fhir.toml <<'TOML'

[generate.option_sets]
include_ids = ["OsVaccType1"]

[generate.categories]
include_ids = ["yY2bQYqNt0o", "Qzh0MSUx4RM"]
TOML

# --json carries the typed GenerateFullReport on stdout while the narration stays on stderr, so
# a caller pipes it straight into jq; --no-progress silences that narration too, which is what a
# log wants from a run nobody is watching. One run, read twice below.
d2w --json fhir generate --no-progress > generate-report.json

# One field per target, in the order the run executes them, so a row per target is `to_entries`.
jq -r 'to_entries[] | "\(.key)\t\(.value.written_files | length) written\t\(.value.unchanged_count) unchanged\t\(.value.deleted_files | length) deleted"' generate-report.json

# Every target's notes are that target's own, exactly as a solo run of it would report them, so a
# full run repeats a note under each target that read the same input. The whole-run reading is the
# distinct set - what the terminal count and reports/fhir-generate-notes.md state - grouped here by
# the kind of decision each note records. `echoes_validate` marks the three kinds that only restate
# what `d2w fhir validate` says about the instance better, so a gate can leave those to it.
jq -r '[.[].notes[] | {category, message}] | unique | group_by(.category)[] | "\(.[0].category)\t\(length)"' generate-report.json

cd .. && rm -rf demo-generate-json
