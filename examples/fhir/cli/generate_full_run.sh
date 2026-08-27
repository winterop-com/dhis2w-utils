#!/usr/bin/env bash
# d2w fhir generate — every target of the IG source off one pass over the instance.
set -euo pipefail

# A small project: one data set, one event program, one tracker program, the registry capped
# at level 2 so the run stays quick. Generation reads its config from the nearest fhir.toml
# (walking up from $PWD), so run from inside the project; the DHIS2 profile comes from
# -p/DHIS2_PROFILE, falling back to the optional `profile` key in fhir.toml.
d2w fhir init demo-generate --id dhis2.fhir.generatedemo \
    --canonical http://example.org/fhir/generate-demo --publisher "Demo Org" \
    --data-set TuL8IOPzpHh --event-program EVTsupVis01 --tracker-program PrAncCare01 \
    --max-level 2
cd demo-generate

# `init` has a flag per data-definition table and none for the terminology, so the option sets
# and the categories are written straight into fhir.toml — which is what every guide in
# examples/fhir/igs/ does too. Naming them is not an optimisation: a table left absent selects
# everything of its kind, and one DHIS2 name carrying a raw '<' anywhere in that everything
# refuses the whole run. On the seeded instance that is option set "Age (<5 - 49) & over".
# `d2w fhir validate` is the command that lists the offenders before you spend a run on them.
cat >>fhir.toml <<'TOML'

[generate.option_sets]
include_ids = ["OsVaccType1"]

[generate.categories]
include_ids = ["yY2bQYqNt0o", "Qzh0MSUx4RM"]
TOML

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

# The scaffolded project compiles this source with `make setup && make sushi`, and
# examples/fhir/cli/serve.sh is the compile and the facade in one script.

cd .. && rm -rf demo-generate
