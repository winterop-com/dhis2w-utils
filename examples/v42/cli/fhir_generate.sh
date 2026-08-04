#!/usr/bin/env bash
# FHIR IG generation — scaffold a SUSHI project, then generate FSH from DHIS2 metadata.
set -euo pipefail

# Scaffold a complete dockerized SUSHI IG project (fhir.toml, sushi-config.yaml,
# ig.ini, a hand-authored aliases.fsh stub, pyproject.toml, Makefile, Dockerfile)
# into ./demo-ig.
# --publisher-url is deliberately omitted: the IG publisher links it from every generated
# page, so aiming it at the canonical of an unpublished IG warns once per page.
d2w fhir init demo-ig --id dhis2.fhir.demo --canonical http://example.org/fhir/demo --publisher "Demo Org"

# The IG scaffolds as [ig] status = "draft", which is also the sushi-config status and
# the status and experimental flag on every generated definitional resource. Pass
# --status active for a production IG, or edit [ig] status in fhir.toml and regenerate.
# d2w fhir init demo-ig --id dhis2.fhir.demo --canonical http://example.org/fhir/demo \
#     --publisher "Demo Org" --status active

# --data-set / --event narrow the data-definition targets at scaffold time (repeatable,
# offline - the UIDs are written to fhir.toml, never checked against an instance). Leave
# them out and generation covers the whole instance. On the play 2.42 demo: two data sets
# and one event program.
# d2w fhir init demo-ig --id dhis2.fhir.demo --canonical http://example.org/fhir/demo \
#     --publisher "Demo Org" \
#     --data-set BfMAe6Itzgt --data-set Nyh6laLdBEJ --event VBqh0ynB2wv

# --profile seeds the `profile` key of the scaffolded fhir.toml, so the project points at
# an instance from the first run instead of needing -p on every later command. Offline too:
# the name is written as given, never resolved against profiles.toml.
# d2w fhir init demo-ig --id dhis2.fhir.demo --canonical http://example.org/fhir/demo \
#     --publisher "Demo Org" --profile demo

# Generation reads its config from the nearest fhir.toml (walking up from $PWD),
# so run from inside the project. The DHIS2 profile comes from -p/DHIS2_PROFILE,
# falling back to the optional `profile` key in fhir.toml.
cd demo-ig

# The project pins its own toolchain: pyproject.toml declares dhis2w-cli + dhis2w-fhir,
# uv sync writes .venv and the committed uv.lock, and the make targets run `uv run d2w`
# against that pin. The bare `d2w` calls below do the same work with whatever d2w is on
# PATH; inside a scaffolded project, prefer `uv run d2w` or the make targets.
# uv sync

# Foundation: the $DHIS2-* aliases built from [generate] identifier_system_base and
# the NamingSystem declaring each of those URLs, the D2Period extension with its
# period-type CodeSystem/ValueSet, the D2FormType extension with its own pair, and the
# capture contract a third party builds against - d2-responses.fsh carries the
# D2AggregateResponse and D2EventResponse QuestionnaireResponse profiles, one per form
# kind, and d2-capture-server.fsh the D2CaptureServer CapabilityStatement stating the
# interactions a server accepting them supports. All under ig/input/fsh/foundation/.
# Reads fhir.toml only - it never opens a DHIS2 client.
d2w fhir generate foundation

# Option sets: one CodeSystem/ValueSet pair per set under ig/input/fsh/terminology/.
# Concept codes are DHIS2 option UIDs; the DHIS2 code rides along as a dhis2-code
# property (set concept_code_source = "code" in fhir.toml to swap them).
d2w fhir generate option-sets

# Questionnaires: one Questionnaire per selected data set under ig/input/fsh/data-sets/
# and per event program under ig/input/fsh/event-programs/, plus the shared data-element
# and category-option-combo support terminology under ig/input/fsh/data-dictionary/.
# Sections become #group items, data elements become questions typed from their DHIS2
# valueType, option-set-bound elements answer from the option set's ValueSet, and a
# non-default category combo becomes a group with one child per option combo.
# Narrow the targets with [generate.data_sets] / [generate.event_programs] include_ids;
# with neither configured this target covers the whole instance (tracker and multi-stage
# programs are skipped with a note).
d2w fhir generate questionnaires

# Examples: one Usage: #example QuestionnaireResponse per configured example under
# ig/input/fsh/examples/<targetUID>-<n>.fsh, answering its Questionnaire on the same link
# ids (section groups nested, disaggregated elements one child per <deUid>.<cocUid>), with
# the D2FormType extension and - for data sets - the full D2Period extension.
# [generate.examples] per_target sets how many each target gets (0 disables) and source
# picks where the answers come from. The default "synthetic" generates them locally from a
# SHA-256 seed, so nothing off the instance is published and a regenerate is byte-stable.
# Set source = "instance" to read real data value sets and tracker events instead - demo
# servers only: those values land in the published IG, so review examples/ before shipping.
d2w fhir generate examples

# Organisation units: one file per level under ig/input/fsh/organization/. Every
# unit becomes an Organization AND a Location, both carrying the UID and code
# identifiers, with partOf mirroring the hierarchy. Geometry is embedded as a
# GeoJSON Feature; Point and Polygon geometry also yield Location.position.
# Narrow the tree with [generate.organisation_units] root / max_level.
d2w fhir generate org-units

# DHIS2 NAME translations ride along with the option-set and org-unit targets: as CodeSystem concept
# designations, and as HL7 translation extensions on titles and instance names.
# Narrow them with [generate] locales = ["lo", "km"] (empty = every locale found).

# Pages: the IG's narrative layer, written as markdown into ig/input/pagecontent/
# rather than as FSH. Six site pages - forms.md, registry.md, terminology.md,
# identifiers.md, periods.md, capture.md - which are the menu entries d2w fhir init
# scaffolds, plus the per-artifact intros the IG publisher injects into an artifact page:
# Questionnaire-<UID>-intro.md for every generated form, and CodeSystem-<id>-intro.md
# / Organization-<UID>-intro.md for the option sets and org units carrying a DHIS2
# description. Everything on these pages comes from the same metadata the FSH targets
# fetch, so a page can never disagree with the resources it links.
# The hand-authored ig/input/pagecontent/index.md is never touched: the sweep only
# deletes markdown carrying the generated header comment.
d2w fhir generate pages

# Or every target in one run (foundation, option-sets, questionnaires, examples,
# org-units, pages - pages last, so it sees everything the run generated).
# Re-running replaces previously generated files (identified by their header line);
# hand-authored .fsh and .md files are never touched.
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
