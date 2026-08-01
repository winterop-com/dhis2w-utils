#!/usr/bin/env bash
# FHIR IG generation — scaffold a SUSHI project, then generate FSH from DHIS2 metadata.
set -euo pipefail

# Scaffold a complete dockerized SUSHI IG project (fhir.toml, sushi-config.yaml,
# ig.ini, aliases.fsh, Makefile, Dockerfile) into ./demo-ig.
d2w fhir init demo-ig --id dhis2.fhir.demo --canonical http://example.org/fhir/demo --publisher "Demo Org"

# Generation reads its config from the nearest fhir.toml (walking up from $PWD),
# so run from inside the project. The DHIS2 profile comes from -p/DHIS2_PROFILE,
# falling back to the optional `profile` key in fhir.toml.
cd demo-ig

# Option sets: one CodeSystem/ValueSet pair per set under ig/input/fsh/terminology/.
# Concept codes are DHIS2 option UIDs; the DHIS2 code rides along as a dhis2-code
# property (set concept_code_source = "code" in fhir.toml to swap them).
d2w fhir generate option-sets

# Organisation units: DHIS2Organization instances with partOf hierarchy, one file
# per level under ig/input/fsh/organization/, plus Location instances for units
# with Point geometry. Narrow the tree with [generate.org_units] root / max_level.
d2w fhir generate org-units

# Or both in one run. Re-running replaces previously generated files (identified
# by their header line); hand-authored .fsh files are never touched.
d2w fhir generate all

# Preflight: check the instance's option-set codes and names for FHIR-safety
# (exit 1 on errors - CI-friendly; works without a fhir.toml too).
d2w fhir validate

# Compile the IG with SUSHI via the scaffolded docker setup:
# make setup && make sushi

# Clean up the demo project.
cd .. && rm -rf demo-ig
