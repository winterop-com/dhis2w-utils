#!/usr/bin/env bash
# FHIR IG generation — scaffold a SUSHI project, then generate FSH from DHIS2 metadata.
set -euo pipefail

# Scaffold a complete dockerized SUSHI IG project (fhir.toml, sushi-config.yaml,
# ig.ini, a hand-authored aliases.fsh stub, Makefile, Dockerfile) into ./demo-ig.
# --publisher-url is deliberately omitted: the IG publisher links it from every generated
# page, so aiming it at the canonical of an unpublished IG warns once per page.
d2w fhir init demo-ig --id dhis2.fhir.demo --canonical http://example.org/fhir/demo --publisher "Demo Org"

# Generation reads its config from the nearest fhir.toml (walking up from $PWD),
# so run from inside the project. The DHIS2 profile comes from -p/DHIS2_PROFILE,
# falling back to the optional `profile` key in fhir.toml.
cd demo-ig

# Foundation: the $DHIS2-OU aliases built from [generate] identifier_system_base,
# plus the D2Period extension and its period-type CodeSystem/ValueSet, under
# ig/input/fsh/foundation/. Reads fhir.toml only - it never opens a DHIS2 client.
d2w fhir generate foundation

# Option sets: one CodeSystem/ValueSet pair per set under ig/input/fsh/terminology/.
# Concept codes are DHIS2 option UIDs; the DHIS2 code rides along as a dhis2-code
# property (set concept_code_source = "code" in fhir.toml to swap them).
d2w fhir generate option-sets

# Organisation units: one file per level under ig/input/fsh/organization/. Every
# unit becomes an Organization AND a Location, both carrying the UID and code
# identifiers, with partOf mirroring the hierarchy. Geometry is embedded as a
# GeoJSON Feature; Point and Polygon geometry also yield Location.position.
# Narrow the tree with [generate.organisation_units] root / max_level.
d2w fhir generate org-units

# DHIS2 NAME translations ride along with both targets: as CodeSystem concept
# designations, and as HL7 translation extensions on titles and instance names.
# Narrow them with [generate] locales = ["lo", "km"] (empty = every locale found).

# Or all three in one run. Re-running replaces previously generated files
# (identified by their header line); hand-authored .fsh files are never touched.
d2w fhir generate all

# Preflight: check the instance's option-set codes and names for FHIR-safety
# (exit 1 on errors - CI-friendly; works without a fhir.toml too). Writes three
# report files next to fhir.toml: fhir-validate-report.md, .csv, and .pdf.
# --report takes a path stem, --format narrows the set (e.g. --format md,csv).
d2w fhir validate

# Readiness probe for switching concept_code_source from "id" to "code": reports
# what the switch would cost right now, at error severity instead of info.
d2w fhir validate --code-source code --no-fail

# Compile the IG with SUSHI via the scaffolded docker setup:
# make setup && make sushi

# Clean up the demo project.
cd .. && rm -rf demo-ig
