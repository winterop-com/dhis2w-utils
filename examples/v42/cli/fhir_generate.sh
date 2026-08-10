#!/usr/bin/env bash
# FHIR IG generation — scaffold a SUSHI project, then generate the IG source from DHIS2 metadata.
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

# --data-set / --event-program / --tracker-program narrow the three data-definition targets at
# scaffold time (repeatable, offline - the UIDs are written to fhir.toml, never checked
# against an instance). Leave them out and generation covers the whole instance. On the
# play 2.42 demo: two data sets, one event program, and one tracker program (which emits
# one Questionnaire per program stage).
# d2w fhir init demo-ig --id dhis2.fhir.demo --canonical http://example.org/fhir/demo \
#     --publisher "Demo Org" \
#     --data-set BfMAe6Itzgt --data-set Nyh6laLdBEJ --event-program VBqh0ynB2wv \
#     --tracker-program IpHINAT79UW

# --profile seeds the `profile` key of the scaffolded fhir.toml, so the project points at
# an instance from the first run instead of needing -p on every later command. Offline too:
# the name is written as given, never resolved against profiles.toml.
# d2w fhir init demo-ig --id dhis2.fhir.demo --canonical http://example.org/fhir/demo \
#     --publisher "Demo Org" --profile demo

# --max-level caps the organisation-unit registry at that depth, seeding
# [generate.organisation_units] max_level. Every unit emits two instances and a hierarchy fans
# out at the bottom, so the deepest level is usually most of the IG - and the IG publisher
# renders a page per resource, so that is what sets the wall clock of `make build`.
# d2w fhir init demo-ig --id dhis2.fhir.demo --canonical http://example.org/fhir/demo \
#     --publisher "Demo Org" --max-level 4

# --sushi-timeout sets [FSH] timeout in ig/fsh.ini, the ceiling the IG publisher gives its
# internal SUSHI run. That run compiles the FSH - the profiles, the extensions, the forms
# and the data-dictionary support terminology - and an IG whose FSH overruns the ceiling
# fails the build with exit 143. Neither the registry nor the option-set terminology is
# FSH, so neither is what the ceiling is guarding.
# d2w fhir init demo-ig --id dhis2.fhir.demo --canonical http://example.org/fhir/demo \
#     --publisher "Demo Org" --sushi-timeout 5400

# --refresh brings an existing project's scaffold-managed files up to date. The IG identity
# comes off the project itself - fhir.toml, ig/fsh.ini, ig/sushi-config.yaml - and a file is
# rewritten only when the current scaffold render reproduces every line already on disk, in
# order. So a refresh adds what the scaffold gained (a new path-resource glob, a new
# .gitignore entry, a new menu entry) and never drops a line you wrote; a file carrying
# anything the scaffold would not produce is left byte-identical and reported as skipped.
# fhir.toml is never written, and --force is rejected alongside it. The consequence to know:
# a scaffold line you deliberately deleted comes back, because a deletion leaves the file a
# subset of the render. Comment such a line out instead of removing it.
# The case it exists for: a project scaffolded before the categories path-resource glob
# landed compiles fine - SUSHI recurses into input/resources on its own - while the IG
# publisher, which does not recurse, drops those resources from the published guide.
# cd demo-ig && d2w fhir init . --refresh

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
# period-type CodeSystem/ValueSet, the D2FormType extension with its own pair, the
# D2AttributeValue extension that carries DHIS2 attributeValues onto the Organization,
# Location, CodeSystem, ValueSet and Questionnaire resources the other targets write,
# and the capture contract a third party builds against - d2-responses.fsh carries the
# D2AggregateResponse and D2EventResponse QuestionnaireResponse profiles, one per form
# kind, and d2-capture-server.fsh the D2CaptureServer CapabilityStatement stating the
# interactions a server accepting them supports. All under ig/input/fsh/foundation/.
# Reads fhir.toml only - it never opens a DHIS2 client.
d2w fhir generate foundation

# Option sets: one CodeSystem and one ValueSet per set as pre-built FHIR JSON under
# ig/input/resources/terminology/ - CodeSystem-d2-os-<uid>-cs.json and
# ValueSet-d2-os-<uid>-vs.json. SUSHI loads them as predefined resources, so hundreds of
# option sets never enter the FSH compile. Each document carries the FSH-style name
# (D2OS_<uid>_CS / _VS) that a Questionnaire's answerValueSet = Canonical(...) binding
# resolves against, because SUSHI fishes a predefined resource by its name element.
# Concept codes are DHIS2 option UIDs; the DHIS2 code rides along as a dhis2-code
# property (set concept_code_source = "code" in fhir.toml to swap them). Beside each
# pair the target writes ig/input/resources/concept-maps/ConceptMap-d2-os-<uid>-cm.json,
# whose two groups take every concept code back to the DHIS2 option UID (under
# {base}/id/option) and the DHIS2 option code (under {base}/id/option-code), so a
# consumer holding a generated coding resolves both DHIS2 identifiers from one document.
d2w fhir generate option-sets

# Categories: the same CodeSystem/ValueSet pair per DHIS2 category, its concepts being that
# category's category options, as pre-built FHIR JSON under ig/input/resources/categories/ -
# CodeSystem-d2-cat-<uid>-cs.json and ValueSet-d2-cat-<uid>-vs.json. A category is one axis
# of a disaggregation (Sex, EPI/nutrition age), so this is the terminology the disaggregated
# half of the data layer codes against. Concepts keep the category's own categoryOptions
# order, carry the complementary DHIS2 identifier as a dhis2-code / dhis2-id property, and
# the category's own attributeValues ride along as D2AttributeValue extensions on both halves.
# Narrow the set with [generate.categories] include_ids (absent or empty = every category).
d2w fhir generate categories

# Questionnaires: one Questionnaire per selected data set under ig/input/fsh/data-sets/,
# per event program under ig/input/fsh/event-programs/, and per tracker program stage
# under ig/input/fsh/tracker-programs/<programUid>/<stageUid>.fsh, plus the shared
# data-element and category-option-combo support terminology under
# ig/input/fsh/data-dictionary/.
# Sections become #group items, data elements become questions typed from their DHIS2
# valueType, option-set-bound elements answer from the option set's ValueSet, and a
# non-default category combo becomes a group with one child per option combo. A stage's
# Questionnaire is subjectType #Patient and carries a $DHIS2-PROGRAM identifier slice, so
# Questionnaire?identifier=<base>/id/program|<programUid> selects a program's stages.
# The target also writes the context a form is captured in, as pre-built FHIR JSON: the
# organisation-unit assignment List under ig/input/resources/assignments/, and - for a data
# set whose own category combo is not the default one - the attribute option combos its
# values are keyed by, as a CodeSystem/ValueSet pair under
# ig/input/resources/attribute-option-combos/ plus a ConceptMap back to the DHIS2
# identifiers. The Questionnaire names that pair through a D2AttributeOptionCombos
# extension, and a response answering it carries a D2AttributeOptionCombo coding out of it.
# A data set on the default combo publishes neither, because absence means the default.
# Narrow the targets with [generate.data_sets] / [generate.event_programs] /
# [generate.tracker_programs] include_ids; absent or empty means every object of that
# kind, and a program listed under the wrong table fails the run by name.
# A tracked entity is not always a person: [generate.tracked_entity_types] maps a tracked
# entity type UID onto the FHIR resource type its registrations are about (Patient, Person,
# Practitioner, RelatedPerson, Group, Device, Location, Organization, Specimen), which sets
# the subjectType of the program's registration form and of every stage form of that
# program. An unmapped type is a Patient, so a person-tracking project maps nothing.
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
# A tracker stage's examples read /api/tracker/events by programStage and carry the
# enrollment and tracked entity UIDs the D2TrackerEventResponse contract requires.
d2w fhir generate examples

# Organisation units: the D2Organization / D2Location profiles and the level CodeSystem
# under ig/input/fsh/organization/, and the registry itself as pre-built FHIR JSON under
# ig/input/resources/registry/ - one Organization-<uid>.json and one Location-<uid>.json
# per unit, both carrying the UID and code identifiers, with partOf mirroring the
# hierarchy as Organization/<uid> and Location/<uid> references. Geometry is embedded as
# a GeoJSON Feature; Point and Polygon geometry also yield Location.position.
# Both halves also carry the unit's DHIS2 attribute values as D2AttributeValue
# extensions - on the Location the boundary extension comes first and the attribute
# values follow it, so an unchanged unit regenerates byte-identically. Each generate
# target resolves the attribute uid -> code join once, unpaged, off /api/attributes;
# an attribute DHIS2 left uncoded emits no attributeCode sub-extension at all.
# SUSHI loads input/resources and the sub-folders sushi-config.yaml declares as
# predefined resources - no FSH conversion - which is why the registry and the
# option-set terminology are both JSON.
# ig/input/resources/ is gitignored by the scaffold: it is generated output, rebuilt from
# the instance in a few minutes, while ig/input/fsh/ is committed and is the diff worth
# reviewing.
# Narrow the tree with [generate.organisation_units] root / max_level.
d2w fhir generate org-units

# DHIS2 NAME translations ride along with the option-set and org-unit targets: as CodeSystem concept
# designations, and as HL7 translation extensions on titles and instance names.
# Narrow them with [generate] locales = ["lo", "km"] (empty = every locale found).

# DHIS2 attribute values ride along the same way, as D2AttributeValue extensions on the
# option-set CodeSystem/ValueSet pair, the Organization/Location pair, and the data set
# and event program Questionnaires. The values on individual data elements and options
# stay behind: a CodeSystem concept has no carrier chosen for them yet.

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

# Or every target in one run - and this is the one to reach for. Bare `generate` reads the
# instance once and builds all seven targets off that single result (8 requests where the
# solo commands above total 25), running foundation first because it reads nothing and
# pages last because they narrate the rest, and reports one summary row per target.
# Re-running replaces previously generated .fsh and .md files (identified by their header
# line); hand-authored ones are never touched. JSON carries no header, so each JSON target
# owns its directory outright and clears what it did not write - option-sets owns
# ig/input/resources/terminology/, categories owns ig/input/resources/categories/,
# questionnaires owns ig/input/resources/{assignments,attribute-option-combos}/, and
# org-units owns ig/input/resources/registry/. The three ConceptMap families share
# ig/input/resources/concept-maps/ and each sweeps only its own file-name prefix.
d2w fhir generate

# Every command with an instance behind it narrates its steps on stderr as they complete:
# a spinner on a terminal, one plain [k/N] line per step when stderr is redirected.
# --no-progress turns it off, and --json implies it (stderr stays quiet, stdout carries
# the report). Tables and notes are stderr too, so stdout is a clean document under --json.
# d2w fhir generate --no-progress
# d2w --json fhir generate > generate-report.json

# Preflight: check the instance's option-set codes and names for FHIR-safety
# (exit 1 on errors - CI-friendly; works without a fhir.toml too). Writes three
# report files into reports/ beside fhir.toml: fhir-validate-report.md, .csv, and .pdf.
# --output-dir names a different directory (the file names stay the same), --format
# narrows the set (e.g. --format md,csv), --details lists the info findings individually.
d2w fhir validate

# Readiness probe for switching concept_code_source from "id" to "code": reports
# what the switch would cost right now, at error severity instead of info.
# --no-fail exits 0 despite the errors, which is what a probe wants.
d2w fhir validate --code-source code --no-fail

# Compile the IG with SUSHI via the scaffolded docker setup:
# make setup && make sushi

# Clean up the demo project.
cd .. && rm -rf demo-ig
