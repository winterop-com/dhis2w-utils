# FHIR plugin

`d2w fhir` turns DHIS2 metadata into a FHIR Implementation Guide source tree: a
SUSHI project whose FSH (FHIR Shorthand) definitions and pre-built FHIR JSON
resources are generated from `/api/optionSets`, `/api/categories`,
`/api/organisationUnits`, `/api/dataSets`, `/api/programs`, and
`/api/attributes`.

```
d2w fhir init [DIRECTORY]           Scaffold a dockerized SUSHI IG project (--profile seeds fhir.toml)
d2w fhir init --refresh             Bring an existing project's scaffold-managed files up to date
d2w fhir generate                   All seven targets in one run, off a single pass over the instance
d2w fhir generate foundation        Identifier aliases + the D2Period / D2FormType / D2AttributeValue extensions
d2w fhir generate option-sets       Option sets -> CodeSystem/ValueSet pairs
d2w fhir generate categories        Categories -> CodeSystem/ValueSet pairs
d2w fhir generate questionnaires    Data sets + event programs + tracker programs -> Questionnaire instances
d2w fhir generate examples          Example QuestionnaireResponses against those Questionnaires
d2w fhir generate org-units         Org units -> Organization/Location instances
d2w fhir generate pages             Narrative site pages + per-artifact intros
d2w fhir generate load-set          Synthetic QuestionnaireResponse corpus into load/ (not IG source)
d2w fhir validate                   FHIR-safety of the instance's codes (exit 1 on errors; --no-fail)
d2w fhir serve                      Serve the IG as a FHIR read + capture facade (package dhis2w-fhir-serve)
d2w fhir serve --ui                 ...plus the capture UI at / (built from dhis2w-fhir-serve/frontend)
```

The plugin ships as its own workspace member, `dhis2w-fhir`, and mounts
through the `dhis2.plugins` entry point - the same mechanism third-party
plugins use. It is version-neutral: the wire client auto-detects the DHIS2
major on connect, so one package serves v41/v42/v43 with no per-tree copies.

The [FHIR IG guide](../guides/fhir-ig.md) is the task-oriented companion to this
page: quickstart, the complete `fhir.toml` reference, and the regeneration
contract.

MCP exposes only the read surface: `fhir_validate` (`readOnlyHint`).
Scaffolding and generation - the page generation included - are CLI-only by design - they write a file tree
onto whatever machine the MCP server runs on, the wrong shape for an agent
protocol (the same judgment as the browser plugin and the security audit
runner). `serve` is CLI-only for the same reason and one more: it binds a port
and stays up, which is a process an operator starts, not a tool call.

## Project layout and fhir.toml

`d2w fhir init` scaffolds a complete project:

```
fhir.toml                   Minimal generation config (committed; no secrets)
fhir.toml.example           Every available option with its default, documented
pyproject.toml              The project's own uv project: dhis2w-cli + dhis2w-fhir,
                            pinned by a committed uv.lock and run through `uv run d2w`
.python-version             3.13, matching pyproject's requires-python - the
                            interpreter uv resolves the project with
Makefile                    setup / upgrade / generate / validate / cache-init /
                            sushi / build / refresh / clean / clean-all / help via
                            docker. cache-init makes the shared package-cache volume
                            writable by the publisher user; sushi and build depend on it
Dockerfile                  ghcr.io/fhir/ig-publisher-localdev + fsh-sushi
.gitignore                  The build output, caches, publisher side products,
                            ig/input/resources/, reports/, .serve/ (the serve
                            spool), load/ (the generated load set), and .venv -
                            never uv.lock, the pinned toolchain
ig/sushi-config.yaml        SUSHI IG identity (id, canonical, publisher)
ig/ig.ini                   IG publisher entry point (fhir2.base.template)
ig/fsh.ini                  Raises the publisher's internal SUSHI timeout to 1800s
ig/input/fsh/aliases.fsh    Hand-authored alias stub (never regenerated)
ig/input/pagecontent/index.md   Hand-authored home page; includes the four
                            publisher fragments (cross-version-analysis,
                            dependency-table, globals-table, ip-statements).
                            `generate pages` writes its siblings and never
                            touches this file.
ig/input/ignoreWarnings.txt
```

`sushi-config.yaml` carries `publisher.name` and, only when `d2w fhir init
--publisher-url` supplies a real home page, `publisher.url`. The IG publisher
links that URL from every generated page, so pointing it at the canonical of an
IG that is not yet published produces one broken link per page - 15,425 of them
on the Sierra Leone demo. Omitting it is the default.

Its `menu:` names the six generated site pages between `Home` and `Artifacts`, and
it carries no `pages:` section: SUSHI publishes every markdown file under
`ig/input/pagecontent/` on its own, so a page added by `generate pages` needs no
configuration to appear.

Its `parameters:` block carries `excludexml` / `excludettl` (JSON is the only
wire format worth a file and a rendered page per resource) plus one
`path-resource` glob per predefined-resource sub-folder - `registry/` for the
org-unit instances, `terminology/` for the option-set pairs, `concept-maps/` for
the ConceptMap beside each pair, `categories/` for the category pairs,
`attribute-option-combos/` for the attribute-option-combo pairs, `assignments/`
for the organisation-unit assignment Lists:

```yaml
  path-resource:
    - input/resources/registry/*
    - input/resources/terminology/*
    - input/resources/concept-maps/*
    - input/resources/categories/*
    - input/resources/attribute-option-combos/*
    - input/resources/assignments/*
```

SUSHI recurses into sub-folders of `input/resources` and loads what it finds into
the virtual `sushi-local#LOCAL` package; the IG Publisher does not recurse. The
globs are what carry those resources into the published ImplementationGuide. A
missing glob is therefore silent at compile time and lossy at publish time, which
is what `d2w fhir init --refresh` exists to repair - see
[Scaffold refresh](#scaffold-refresh).

It carries no `groups:` section. SUSHI's grouping matches by exact resource
reference, with no wildcard and no FSH-side `groupingId`, so grouping a real
instance's artifacts would mean enumerating every one of its thousands of
instances in `sushi-config.yaml`. The Artifacts page falls back to the template's
own categorisation by resource type, which is the same shape those groups would
have had.

`d2w fhir generate` discovers the nearest `fhir.toml` by walking up from the
working directory, the same idiom as `.dhis2/profiles.toml`. The file is
committed project config: it may pin a d2w `profile` by name, but explicit
`-p` / `DHIS2_PROFILE` always wins, and credentials never live in it.

```toml
# fhir.toml stays minimal - the profile pointer and the [ig] identity.
# Every other option lives in fhir.toml.example with its default.
profile = "myserver"                # optional

[ig]
id = "dhis2.fhir.example"
canonical = "http://example.org/fhir"
name = "Dhis2FhirExample"
title = "DHIS2 FHIR Example IG"
publisher = "Example Organisation"
```

Options worth calling out from `fhir.toml.example`:

```toml
[generate]
identifier_system_base = "http://dhis2.org/fhir"
concept_code_source = "id"          # "id" or "code"
locales = []                        # BCP-47 or DHIS2 tags; empty = every locale found

[generate.naming]
source = "id"                       # "id", "code-or-id", or "code"
prefix = "D2"                       # "" drops it; profiles keep a D2 token
option_set = "OS"                   # e.g. "OptionSet"; "" drops the token
category = "CAT"                    # category CodeSystem/ValueSet names
organisation_unit = "OU"            # e.g. "OrgUnit" -> D2OrgUnit_Level_CS
data_set = "DS"                     # data set Questionnaire names
program = "PR"                      # event program Questionnaire names
program_stage = "PS"                # tracker program stage Questionnaire names

[generate.option_sets]
# include_ids = ["Qdm5fPK5Ra9"]     # UIDs; absent = all

[generate.categories]
# include_ids = ["O5P6e8yu1T6"]     # UIDs; absent = all

[generate.data_sets]
# include_ids = ["BfMAe6Itzgt"]     # UIDs; absent or empty = all

[generate.event_programs]
# include_ids = ["VBqh0ynB2wv"]     # WITHOUT_REGISTRATION UIDs; absent or empty = all

[generate.tracker_programs]
# include_ids = ["IpHINAT79UW"]     # WITH_REGISTRATION UIDs; absent or empty = all

[generate.examples]
per_target = 1                      # example responses per questionnaire target; 0 disables
source = "synthetic"                # "synthetic" (generated) or "instance" (real values)

[generate.organisation_units]
# root = "ImspTQPwCqd"
# max_level = 4
terminology = false
```

Every selection reads the same way: absent or empty means *all*, a non-empty list
filters. `fhir.toml.example` shows every unset-by-default key as a commented,
real-shaped example rather than a magic placeholder, so the file parses to exactly
the defaults.

`identifier_system_base` is live: `generate foundation` writes it into
`foundation/d2-aliases.fsh` as the `$DHIS2-*` aliases, declares each of those
URLs as a NamingSystem in `foundation/d2-naming-systems.fsh`, and derives the
`^property` URIs the terminology concepts carry.

The full configuration reference, with the id-first-then-code workflow and the
canonical naming-token registry, is in the
[FHIR IG guide](../guides/fhir-ig.md).

Artifact names merge the prefix and kind tokens and underscore the segments
after them (`D2` + `OS` + `_Qdm5fPK5Ra9` + `_CS` - short tokens read by context);
ids join the kebab of each non-empty token, with the identity stem kept verbatim
(`d2-os-Qdm5fPK5Ra9-cs`), so renaming or dropping a token reshapes the whole IG
consistently. `[generate.naming] source` picks the stem: the DHIS2 id under the
default `"id"`, the object's code under `"code-or-id"` (falling back to the id
with a note) and `"code"` (refusing the run on a missing, unusable, or colliding
code). The two profile names always carry a token (default
`D2`) because FSH cannot name a profile identically to its parent core resource.

## Scaffold refresh

`d2w fhir init --refresh` re-renders the scaffold for an existing project and
writes only where nothing on disk is lost. `read_project_scaffold_state` recovers
the inputs from the project itself - `[ig]` and the selection tables from
`fhir.toml`, `[FSH] timeout` from `ig/fsh.ini`, and the publisher URL plus the
copyright year from `ig/sushi-config.yaml`, the two values no other file records -
so `build_scaffold_files` renders what *this* project's scaffold would be today
rather than a default one.

`preserves_every_line` is the whole decision: it walks the render as a single
forward iterator and asks whether every line currently on disk appears in it, in
order. When it does, the file is a strict subsequence of the render, so rewriting
adds and never removes, and the file is `refreshed`. When it does not, the file
holds something the scaffold would not produce and it is left byte-identical and
reported as `edited` - rendered by the CLI as `skipped (you edited it; your
version stays)`. A file the project lacks is `created`; one that already matches
is `unchanged`. `fhir.toml` is skipped by relative path before any comparison: it
is the user's configuration, not a scaffold-managed file.

Two consequences the design accepts. A scaffold line the user deliberately
**deleted** is restored, because a deletion leaves the file a subsequence of the
render - the same shape as a project that predates a scaffold addition, and the
rule cannot tell them apart. And a file that cannot be read as UTF-8 is reported
as edited rather than replaced, so unreadable content is never overwritten on a
guess. `--force`, which rewrites everything, is rejected alongside `--refresh` at
the CLI: they are opposite answers to the same question.

## Foundation -> identifier systems, D2Period, and the capture contract

`generate foundation` writes `ig/input/fsh/foundation/`, the part of the IG that
depends on `fhir.toml` alone and never opens a client:

- `d2-aliases.fsh` - `$DHIS2-OU` / `$DHIS2-OU-CODE` / `$DHIS2-OS` /
  `$DHIS2-OS-CODE` / `$DHIS2-DS` / `$DHIS2-DS-CODE` / `$DHIS2-PROGRAM` /
  `$DHIS2-PROGRAM-CODE` / `$DHIS2-DE` / `$DHIS2-COC` / `$DHIS2-PS` /
  `$DHIS2-PS-CODE` / `$DHIS2-TE` / `$DHIS2-TRACKER-ENROLLMENT`, built from
  `identifier_system_base`. Generating these rather
  than scaffolding them is what frees `ig/input/fsh/aliases.fsh` to be a pure
  hand-authored stub.
- `d2-naming-systems.fsh` - one `NamingSystem` per identifier system: a UID and a
  code declaration for each of the organisation unit, option set, category, data set,
  program, data element, category option combo, program stage, and tracked entity type
  (`D2OrgUnitIdentifierSystem`, `D2OptionSetCodeIdentifierSystem`,
  `D2DataSetIdentifierSystem`, ...), plus a UID declaration alone for the tracked
  entity and the tracker enrollment. The split is a property of the DHIS2 object, not
  a gap: `IdentifierSystemSubject.has_code` is false for a data object, because DHIS2
  gives a tracked entity and an enrollment no `code` attribute, so declaring a code
  system for them would declare a system nothing can ever populate. Each declaration is
  `kind = #identifier` with a single preferred `uri` uniqueId and a description
  stating the convention, including the code slot's UID fall-back. Without them
  the validator has no definition behind a DHIS2 `identifier.system` and warns on
  every artifact that carries one. R4 makes `NamingSystem.date` mandatory, so the
  declarations carry a pinned date rather than a run timestamp - a generated one
  would rewrite the file on every run.
- `d2-period.fsh` - the `D2Period` extension plus `D2PeriodType_CS`/`_VS`.
- `d2-form-type.fsh` - the `D2FormType` extension plus `D2FormType_CS`/`_VS`
  (`aggregate`, `event`, `tracker`, `tracker-event`). Its context covers
  `Questionnaire` *and* `QuestionnaireResponse`: the form states what kind of DHIS2
  form it is, and so does every response captured against it, which is what lets a
  consumer branch without re-reading the questionnaire. All four have a generator;
  `tracker` is the registration form a tracker program enrols a person through, whose
  questions are the program's tracked entity attributes rather than a stage's data
  elements. `CAPTURED_FORM_KINDS` is the tuple beside `FORM_KIND_PROFILES` naming the
  kinds a capture server accepts a response for and the translator converts, and it now
  holds all four - it is the one switch serve's index, the conversion gate, the
  `supportedProfile` declarations, `/metadata`, and the load set all read.
- `d2-attribute-value.fsh` - the `D2AttributeValue` extension, a complex extension of
  `attributeId` (string, 1..1), `attributeCode` (string, 0..1) and `value` (string,
  1..1), contexted on the five resource types that carry one: `Organization`,
  `Location`, `CodeSystem`, `ValueSet`, `Questionnaire`. A DHIS2 attribute value is
  an arbitrary key-value pair any metadata object may hold - a national registry id
  on a facility, an external warehouse key - so it maps onto an extension rather than
  onto any one FHIR element. `attributeCode` is optional because DHIS2 leaves most
  attributes uncoded (eleven of twelve on the Lao instance), and an uncoded attribute
  gets no sub-extension at all rather than an empty one. `value` is a string whatever
  the attribute's declared `valueType`, because that is the only shape DHIS2 sends -
  one real attribute carries a whole GeoJSON document that way.
- `d2-organisation-unit.fsh` - the `D2OrganisationUnit` extension, `value[x] only
  Reference(<location profile>)` with `valueReference` 1..1, contexted on
  `QuestionnaireResponse`. It exists because a tracker-event response spends its
  `subject` on the patient, so the unit the event was captured at needs a slot of its
  own.
- `d2-organisation-unit-assignment.fsh` - the `D2OrganisationUnitAssignment` extension,
  `value[x] only Reference(List)` with `valueReference` 1..1, contexted on
  `Questionnaire`. It names the `List` of Locations a form may be captured against.
  `List` rather than `Group` because R4 binds `Group.member.entity` to
  `Patient | Practitioner | PractitionerRole | Device | Medication | Substance | Group`
  and `Group.type` to `person | animal | practitioner | device | medication | substance`:
  a Location is neither a legal member nor a legal type, while `List.entry.item` is
  `Reference(Resource)` and `List.mode` says `snapshot`.
- `d2-attribute-option-combos.fsh` - the `D2AttributeOptionCombos` extension, `value[x]
  only canonical(ValueSet)` with `valueCanonical` 1..1, contexted on `Questionnaire`. It
  names the ValueSet of attribute option combos a form's responses may be keyed under.
  `canonical` rather than `Reference` because a ValueSet is a definitional resource the
  guide binds by URL everywhere else too (`Questionnaire.item.answerValueSet` is the
  nearest neighbour), where the assignment extension points at a `List` instance and is
  therefore a literal reference.
- `d2-attribute-option-combo.fsh` - the `D2AttributeOptionCombo` extension, `value[x] only
  Coding` with `valueCoding` 1..1 and both `system` and `code` required, contexted on
  `QuestionnaireResponse`. It carries the one attribute option combo an aggregate
  response's values are keyed under. Singular against its plural sibling on purpose: the
  form declares the set, the response names one member, the way `D2OrganisationUnit` and
  `D2OrganisationUnitAssignment` already split.
- `d2-organisation-unit-level.fsh` - the `D2OrganisationUnitLevel` extension, `value[x]
  only Coding` with `valueCoding` 1..1 bound extensibly to the org-unit level ValueSet,
  contexted on `Location`. Every registry Location carries one - the `D2Location` profile
  slices it `named level 1..1` - so the DHIS2 hierarchy level is stated on the resource
  rather than recovered by counting `partOf` hops. The Organization half gets none: it
  already states the same coding as `Organization.type`, and a level is a property of the
  place in the hierarchy, which is the Location.
- `d2-tracker-enrollment.fsh` - the `D2TrackerEnrollment` extension, `value[x] only
  Identifier` with `valueIdentifier.system` fixed to `{base}/id/tracker-enrollment`
  and `valueIdentifier.value` 1..1, contexted on `QuestionnaireResponse`. It is named
  for the tracker enrollment specifically rather than for enrollment in general, so a
  future enrollment kind gets its own namespace instead of overloading this one. Both
  tracker kinds carry it: a registration response mints the UID of the enrollment it
  creates, an event response names the enrollment it was captured under.
- `d2-enrollment-dates.fsh` - the `D2EnrolledAt` and `D2IncidentAt` extensions, each
  `value[x] only dateTime` with `valueDateTime` 1..1, contexted on
  `QuestionnaireResponse`. They carry the two dates a DHIS2 enrollment holds -
  `enrolledAt`, which every enrollment has, and `occurredAt`, the incident date a
  program states through `displayIncidentDate` whether it collects at all. That split is
  why the registration profile slices the first 1..1 and the second 0..1, and why the
  source projection carries `displays_incident_date`: the synthetic examples of a
  program that collects no incident date emit no `D2IncidentAt`. `dateTime` rather than
  `date` because DHIS2 writes both as timestamps, and both go through the same
  zone normalisation `authored` goes through (BUGS.md #62).
- `d2-responses.fsh` - the `D2AggregateResponse`, `D2EventResponse`,
  `D2TrackerRegistrationResponse`, and `D2TrackerEventResponse` profiles on
  `QuestionnaireResponse`, one per form kind. Each slices the extensions its kind has
  to carry (`D2Period` 1..1 on the aggregate one, `D2TrackerEnrollment` and
  `D2OrganisationUnit` 1..1 on both tracker ones plus `D2EnrolledAt` 1..1 /
  `D2IncidentAt` 0..1 on the registration one, `D2FormType` 1..1 on all four, fixed
  to the kind's own code), requires `questionnaire`, requires `subject`, and requires
  `authored` on all but the aggregate one. The aggregate and event profiles restrict
  `subject` to `Reference(D2Location)`; both tracker ones restrict it to
  `Reference(Patient)` - plus every other resource type the project's tracked entity
  types resolve to, since one profile is published for the whole IG - and make it a
  *logical* reference - `subject.identifier` 1..1 with `system` fixed to
  `{base}/id/tracked-entity` - because the IG publishes no subject instances at all and
  the tracked entity resolves against DHIS2 instead. What
  separates the two tracker contracts is who authored those identifiers: a stage
  response names a tracked entity and an enrollment that already exist, a registration
  response mints both, which is stated on the profile's `^short` rather than left to
  the reader. The four flags on `ResponseProfileDeclaration` (`period_required`,
  `authored_required`, `tracker_context_required`, `registration_context_required`) are
  what the one shared template branches on, so a fifth form kind is a declaration rather
  than a template. The slice names are the extension names, which is what lets an
  instance address them as `extension[D2Period]` the way the examples already did
  against the bare resource. `build_captured_response_profile_declarations` is the
  narrower list `d2-capture-server.fsh` and the served `/metadata` declare as
  `supportedProfile`: publishing a contract a client can build against is not the same
  as claiming an interaction the facade performs.
- `d2-generate-operation.fsh` - the `D2GenerateOperation` OperationDefinition behind
  `$generate`: `kind = #operation`, `code = #generate`, `resource = #Questionnaire`,
  `instance = true` with `system` and `type` false, `affectsState = false` so a GET is
  legal, one optional `seed` input of type `integer`, and a `return` output of type
  `QuestionnaireResponse` - a custom operation returning its resource directly rather
  than wrapped in `Parameters`. It carries a pinned `date` for the same byte-stability
  reason the NamingSystem declarations do. It is deliberately not SDC's `$populate`,
  and the `comment` on the definition says so, because `$populate` means
  fill-from-real-context and this invents its data.
- `d2-capture-server.fsh` - the `D2CaptureServer` CapabilityStatement,
  `kind = #requirements` so R4 forbids `software` and `implementation`. It declares
  `create` on `QuestionnaireResponse` with every response profile as
  `supportedProfile` - the template loops over the same declarations
  `d2-responses.fsh` renders, so the two cannot disagree about how many there are -
  and `read` + `search-type` on `Questionnaire`, `CodeSystem`,
  `ValueSet`, `Location`, and `Organization`. R4 makes `CapabilityStatement.date`
  mandatory, so it takes a pinned literal for the same byte-stability reason the
  NamingSystem declarations do.

The response profiles are the reason `foundation` reads
`OrganisationUnitNaming`: `subject only Reference(<location profile>)` and the
`D2OrganisationUnit` extension's `valueReference` both have to name
the very profile the org-unit target emits, under whatever `[generate.naming]` prefix
is configured. `naming.py` is a leaf module, so the dependency adds no cycle. The
profiles are only half the contract - the other half is that every complete generated
example declares `InstanceOf: D2AggregateResponse` / `D2EventResponse` /
`D2TrackerEventResponse` instead of
the bare resource, so SUSHI and the publisher validate the examples against the
profiles on every run and a profile that drifts from what generation produces fails
the build.

`D2Period` exists because a FHIR `Period` is a pair of instants while a DHIS2
period is a *typed* interval: `202401` is the January instance of the `Monthly`
type, and the type is what makes it comparable and round-trippable. The extension
carries `iso` (string, 1..1), `type` (code, 1..1, required-bound to the period
type ValueSet) and `period` (Period, 0..1). Its context names the two resources
that actually carry it - `QuestionnaireResponse` and `MeasureReport` - rather than
a bare `Element`, which the publisher's QA reads as an unbounded extension.
`dhis2w_fhir.period` holds the matching parser: `parse_period("2024BiW2")` returns
the type and the resolved dates for all twenty-three period types DHIS2 registers,
transcribed from `Period.Input.of` and `DateUnitPeriodTypeParser` in dhis2-core.
`recent_periods` is its inverse, built *on* the parser rather than beside it: each
type declares only how its ISO strings are spelled for a year, the parser decides
which of those exist and when they end, and the enumerator keeps the ones already
past. That is what keeps the two from drifting apart. Both are part of the
package's importable surface - see the
[`dhis2w_fhir` API reference](../api/fhir.md).

`D2AttributeValue` is defined in `foundation/` and *emitted* everywhere else, so
the shared halves live in two leaf modules. `attributes.py` holds the projection
`AttributeValueIn` (the attribute UID and the value, which is all DHIS2 sends:
the wire shape is `{"attribute": {"id": "..."}, "value": "..."}`) and
`AttributeCodeIndex`, the `uid -> code` mapping whose `code_for` returns `None`
for an attribute the instance left uncoded. `foundation/attribute_values.py`
holds the context list, the three sub-extension names, the canonical-URL helper,
and `attribute_value_extensions`, the one builder every emitter calls - so the
extension's structure is decided in one place and the Organization, Location,
CodeSystem, ValueSet, and Questionnaire emitters only decide *where* the result
hangs. The service resolves the index once per generate run through
`resolve_attribute_code_index`, unpaged: DHIS2 pages `/api/attributes` 50 at a
time by default, and an instance defining more than a page of them would
otherwise lose the tail of the join with no error. Every target of one run
therefore joins against the identical mapping, the same guarantee the option-set
identity plan gives names. The Questionnaire emitter is the one that does not
build R4 models - it renders FSH, so it projects each value onto a
`_AttributeValueView` of quoted literals and the template writes the
`extension[D2AttributeValue][+]` soft-index block, skipping the `attributeCode`
line entirely when the code is `None`.

## Option sets -> terminology

Two pre-built FHIR JSON documents per option set under
`ig/input/resources/terminology/` - `CodeSystem-d2-os-<stem>-cs.json` and
`ValueSet-d2-os-<stem>-vs.json` - carrying a `D2OS_<stem>_CS` CodeSystem plus a
matching ValueSet (naming tokens configurable). The stem is the set's identity
stem under `[generate.naming] source`: the UID under the default `"id"`, the
set's DHIS2 code under the code sources, and the CS/VS/ConceptMap triple of one
set shares it. The file name and the id keep the stem's own case - FHIR ids
permit mixed case, so an id-sourced id reads straight back to the DHIS2 object.
There is no truncation: a code longer than the surface's stem budget falls back
to the UID (or refuses the run under `source = "code"`). Every concept
carries **both** DHIS2 identifiers: with the default
`concept_code_source = "id"` the option UID is the concept code and the
DHIS2 option code rides along as a `dhis2-code` concept property; with
`"code"` they swap (the UID becomes a `dhis2-id` property). The code path is
gated by a FHIR `code`-datatype validity check; an option whose code is
missing or invalid falls back to the UID with a note in the report, so
generation is total. Concept codes are unique within a set by construction: the
codes are assigned in DHIS2 sort order by `concept_assignments` and a taken code
falls back to the option's UID; where that UID is taken too - a peer carries it as
its own DHIS2 code - the option is skipped with its own aggregate note rather than
emitted as a duplicate concept the publisher would reject. Every target that names
a concept reads that one assignment, so the examples cannot code an answer the
CodeSystem has no concept for. The set's own DHIS2 attribute values ride onto
both halves of the pair as `D2AttributeValue` extensions; the values on the
individual options do not, because a `CodeSystem.concept` has no carrier chosen
for them yet.

Names are decided once, for the whole selection, by `option_set_identities`,
through `resolve_identity_stems`: whether a code can serve as a stem depends on
the peers a set is resolved against, so a per-set name cannot be reconstructed
from one object alone. The resulting
`OptionSetIdentityPlan` is the boundary object every other target reads option-set
names from - the terminology emitter for its files, a question's `answerValueSet`,
an example's answer coding, and the narrative pages' `CodeSystem-<id>` links. The
service builds the plan from the identical selection in each generate path, so a
code-sourced run's `Canonical(D2OS_SEX_VS)` names the ValueSet that
same run writes. A bound set the plan somehow omits still emits a UID-derived name
and is reported by an aggregate note, never left dangling.

The pair ships as predefined resources: `sync_json_artifacts` writes them into
`ig/input/resources/terminology/`, `sushi-config.yaml` declares
`path-resource: input/resources/terminology/*`, and the publisher loads them
verbatim into `sushi-local#LOCAL` with no FSH parse. That is what keeps hundreds
of option sets out of the compile - see
[Toolchain performance](#toolchain-performance).

Writing JSON makes the target owner of three directories rather than one. A
definition SUSHI compiles from FSH and a predefined resource of the same identity
are a duplicate, and SUSHI rejects the pair, so the target follows
`sync_json_artifacts` with `clean_generated_files` over
`ig/input/fsh/terminology/`. Only a file carrying the generated header is removed,
which leaves anything hand-authored in that directory alone. Every page-facing
`title` and `description` it writes goes through `page_string`, the JSON
counterpart of the `page_text` the FSH emitters use: a predefined resource reaches
the same breadcrumb template an FSH-authored one does, so it takes the same
HTML-escaping.

**The FSH name is what carries across the FSH/JSON boundary.** A Questionnaire is
FSH and binds its question with `answerValueSet = Canonical(D2OS_<stem>_VS)`, an
FSH name rather than a URL, and it resolves against a JSON document because SUSHI
fishes predefined resources by their `name` element. Every emitted CodeSystem and
ValueSet carries exactly the FSH name `option_set_identities` handed the
questionnaire target, which is why one plan serving both emitters is load-bearing
rather than tidy.

### The ConceptMap back to DHIS2

Beside each pair the target writes one `ConceptMap-<id-stem><slug>-cm.json` into
`ig/input/resources/concept-maps/`, its own owned directory for the same reason
`categories/` is one: `sync_json_artifacts` deletes every unproduced `*.json` in
its target, so two JSON syncs sharing a directory would delete each other's
documents. `CONCEPT_MAP_DIRECTORY` names it, and the scaffolded
`sushi-config.yaml` declares the matching `path-resource` glob - SUSHI recurses on
its own, the publisher does not.

The map answers the question a consumer holding a generated coding has: *which
DHIS2 option is this?* Two groups, both with `group.source` set to the set's own
CodeSystem canonical, carry the answer for both DHIS2 identifiers - `group.target`
`<base>/id/option` for the option UID and `<base>/id/option-code` for the DHIS2
code - with `equivalence = #equal` on every row, because the concept and the
target identifier name the same DHIS2 option under two conventions rather than
two vocabularies. `sourceCanonical` is the pair's ValueSet; there is no
`target[x]`, because R4 types it as a value set and an identifier namespace is not
one. `identifier` is a single element rather than a list, which is R4's
cardinality for ConceptMap alone.

`OptionSetIdentity` carries `concept_map_id` and `concept_map_name` beside the
pair's, so all three artifacts of one set take one slug and the map cannot drift
from the pair it belongs to. The rows come from `concept_assignments`, the same
plan `build_concepts` reads, so a mapping can only ever name a concept the
CodeSystem really holds - the discipline the example answers already follow. The
code group is emitted only where an option carries a DHIS2 code that is a valid
FHIR `code` (an R4 `group` with no `element` is invalid), and a set with no
concepts at all emits no map.

Two things this leaves for later: `<base>/id/option` and `<base>/id/option-code`
are new DHIS2 identifier namespaces that `IDENTIFIER_SYSTEM_SUBJECTS` does not yet
declare as NamingSystems, and categories emit no map yet - their concepts come
from the same `build_concepts`, so the emitter carries over as it stands.

## Categories -> terminology

A DHIS2 category is one axis of a disaggregation and its category options are the
values along that axis, which is structurally an option set and its options. So
`generate categories` emits the same pair through the same machinery: two
pre-built R4 JSON documents per category under `ig/input/resources/categories/` -
`CodeSystem-d2-cat-<stem>-cs.json` and `ValueSet-d2-cat-<stem>-vs.json` - with the
concepts built by `build_concepts`, the option-set component's own concept-code
assignment, so the code fall-backs and the duplicate-skip rule are decided in one
place for both sources. `category_identities` mirrors `option_set_identities`:
slugs, FSH names, and artifact ids assigned once over the whole selection
through `resolve_identity_stems`, whose collision grading depends on the peers
a category is resolved against.

The pair carries the `CAT` naming token (`D2CAT_Sex_CS` / `_VS`), the category's
own UID and code as `identifier` business identifiers under
`<base>/id/category` and `<base>/id/category-code`, and the category's DHIS2
attribute values as `D2AttributeValue` extensions on both halves. Under
`naming.source = "id"` the slug is the category UID verbatim, mixed case
included; under the code sources it is the category's DHIS2 code, falling back
to the UID or refusing the run as the source dictates.

**Its own sync directory is structural, not cosmetic.** `sync_json_artifacts`
owns its target outright - it deletes every `*.json` the run did not produce,
because JSON carries no header to mark - so two JSON targets sharing a directory
would delete each other's documents on every run. `CATEGORY_DIRECTORY` is
therefore `categories`, beside `TERMINOLOGY_DIRECTORY` and `REGISTRY_DIRECTORY`,
and the scaffolded `sushi-config.yaml` declares a third `path-resource` glob for
it.

**There is no `category_option` naming token, deliberately.** A category option is
a concept inside its category's CodeSystem, exactly as an option is a concept
inside its option set's, and neither has a token: a concept is not an artifact, so
nothing names it. The `CO` token stays reserved in the
[canonical token registry](../guides/fhir-ig.md#the-canonical-token-registry) for
a future artifact that publishes category options in their own right.

`[generate.categories] include_ids` selects, absent or empty = all, unmatched UIDs
noted - identical to `[generate.option_sets]`. There is no closure: nothing
generated today binds a category, so the list stands alone rather than being
unioned with what the forms reference. DHIS2's own `default` category is emitted
like any other and is filterable like any other.

## Data sets, event programs, and tracker programs -> Questionnaires

`generate questionnaires` owns four sync directories under `ig/input/fsh/`, split
by what the files describe rather than by which command wrote them:

```
data-sets/<stem>.fsh                     One Questionnaire per DHIS2 data set
event-programs/<stem>.fsh                One Questionnaire per DHIS2 event program
tracker-programs/<program stem>/<stage stem>.fsh
                                         One Questionnaire per tracker program stage
tracker-programs/<program stem>/registration.fsh
                                         The program's own registration form
data-dictionary/data-elements.fsh        D2DE_CS / _VS over every referenced element
data-dictionary/tracked-entity-attributes.fsh
                                         D2TEA_CS / _VS over every referenced attribute
data-dictionary/category-option-combos.fsh   D2COC_CS / _VS over every option combo
```

It also writes three JSON targets under `ig/input/resources/`, because a form's context
is published beside the form rather than by a command of its own:

```
assignments/List-<id>.json                One List of Locations per form whose
                                          assignment narrows the registry
attribute-option-combos/                  D2AOC_<stem>_CS / _VS per distinct
  {CodeSystem,ValueSet}-<id>.json         non-default attribute category combo
concept-maps/ConceptMap-d2-aoc-<stem>-cm.json   Each pair's route back to DHIS2
```

`<stem>` is each target's identity stem - the DHIS2 id under the default
`[generate.naming] source`, the object's code under the code sources.

The attribute-option-combo pair is what makes a data set on a non-default category
combo capturable at all: a data value set is keyed by
`(orgUnit, period, attributeOptionCombo)`, and a response naming no combo is refused
with `E8023`. The pair belongs to the combo rather than the form, so two data sets on
one combo share one pair, and a default-combo data set publishes nothing - absence is
the default combo, the same economy the assignment List keeps. `concept-maps/` now holds
three families behind one publisher glob, each sweeping its own id-stem prefix
(`ConceptMap-d2-os-`, `ConceptMap-d2-cat-`, `ConceptMap-d2-aoc-`).

`tracker-programs/` is the only nested layout, and it is nested because a national
instance's stage count is what makes a flat directory unreadable: grouping by program
UID means a program's forms are one folder. The FSH sweep serves it by tracking
produced files by path *relative to the sync root* and walking subdirectories, so a
deletion is still scoped to header-bearing generated files, and a subdirectory the
sweep emptied is removed with them. The JSON sweep keeps its flat
whole-directory-ownership semantics - it has no nested target.

`D2DE_CS` carries three concept properties: `dhis2-code` (the DHIS2 code, falling back to the
UID), `domain` - a `code` valued `#aggregate` or `#tracker` from the data element's DHIS2
`domainType`, omitted along with its declaration when the instance answers none - and
`value-type`. All take a `<identifier_system_base>/property/<code>` URI, the same scheme the
option-set terminology uses.

`D2TEA_CS` is its twin over the objects a registration form asks its questions from. It
declares `dhis2-code` and `value-type` the same way, and one property the data-element pair
has no use for: `unique`, a `boolean` from the attribute's DHIS2 `unique` flag, which is what
tells a consumer that a question identifies the person - a national id, a case number - rather
than describing them. Which pair a form's questions land in is a property of the form *kind*,
carried on `FormKindProfile.question_subject`, so `collect_referenced_objects` routes them and
`question_code_system` names the CodeSystem an item's `code` points into. A run whose forms ask
no attributes writes no such file, the same way a run that disaggregates nothing writes no
`D2COC_CS`. The property prose lives on `SupportTerminologyProfile` rather than in the shared
template, because the two pairs describe different DHIS2 objects and would otherwise share
wording that is true of only one.

The targets are `[generate.data_sets]` / `[generate.event_programs]` /
`[generate.tracker_programs]` `include_ids`,
absent or empty = all, exactly like the terminology and registry selections. The
service makes one `sync_artifacts` call per directory, each swept against its own
files alone, and merges the four reports into the single `GenerateReport` whose
`target_directory` reads `data-sets, event-programs, tracker-programs,
data-dictionary`. The two
support pairs are FSH under `ig/input/fsh/data-dictionary/`, a different tree
from the option-set target's `ig/input/resources/terminology/`, so its cleanup
can never reach them. The command is still
`d2w fhir generate questionnaires` - it names the action, not a folder.

One Questionnaire is `Usage: #definition`, `id` the target's identity stem (the
bare DHIS2 id under the default source), `url` the IG canonical
plus `/Questionnaire/<stem>`, `status` and `experimental`, both DHIS2 identifiers
(`$DHIS2-DS` / `$DHIS2-PROGRAM` / `$DHIS2-PS` and their code slots), and `name`
composed from the naming tokens (`D2DS_BfMAe6Itzgt`, `D2PS_A03MvHHogjR`).
`subjectType` states who the form is answered for: `#Location` for a data set and an
event program (a DHIS2 form is answered for an organisation unit), and the program's
own tracked entity type for both tracker forms (a registration is answered about the
entity being enrolled and a stage about the entity already enrolled, and the
organisation unit moves onto the response's `D2OrganisationUnit` extension).
`form_subject_type` resolves that one type for every consumer: `[generate.tracked_entity_types]`
maps a tracked entity type UID onto the FHIR resource type it is, keyed by type rather
than by program so two programs tracking one type cannot disagree, and an unmapped type
is the form kind's own default - a `Patient`.

A tracker stage's identity is the *stage's* - its UID, its code, its description, its
attribute values - and the program travels beside it as `ProgramContextIn`, which
shapes three things: the `title` reads `<program> - <stage>`, the file path nests
under the program UID, and a third identifier slice carries the program UID under
`$DHIS2-PROGRAM`. That slice is the grouping handle a plain FHIR server can search on
(`Questionnaire?identifier={base}/id/program|<programUid>` returns a program's
stages), which is why the program is an identifier rather than only a title.
`_tracker_program_sources` emits the stages in DHIS2's own order - `sortOrder`, then
name, then UID - because `programStages` is a Java `Set` on the wire and its order is
neither the form's nor stable across requests.

**A tracker program publishes one more form: its registration.** `_registration_source`
maps the program itself onto a `tracker`-kind source, so the form's UID, code, name,
description, and attribute values are the *program's*, and its questions are the
program's `programTrackedEntityAttributes` - the join table carrying `mandatory` and
`sortOrder` exactly as `programStageDataElements` carries `compulsory` and `sortOrder`,
which is why the two read the same way and an attribute projects onto the very
`QuestionnaireItemIn` a data element does. The file is `registration.fsh` rather than a
stem: it already sits in the program's own directory. Because the form *is* the program,
it needs no `ProgramContextIn` - `source_program` answers with the source's own identity
for a `tracker` kind, which is what lets the stem plan register a program that has no
stage at all, and what makes `assignment_container` resolve both tracker kinds through
the program surface so one program never names two assignment Lists. Its identifiers are
the program's `$DHIS2-PROGRAM` / `$DHIS2-PROGRAM-CODE` pair - the very pair a stage
carries as its grouping identifier, so one identifier search selects a program's whole
capture surface - plus `$DHIS2-TET` naming the tracked entity type it enrols a person as.
`grouping_identifiers` is the one function both emitters read that list from, spelled
alias-and-segment for the same reason `FormKindProfile` spells its systems twice. Two
more facts ride the source for the response side alone: `tracked_entity_type_uid` and
`displays_incident_date`.

Sections become `#group` items; data elements become questions
whose type comes from the DHIS2 `valueType` table, or `#choice` plus an
`answerValueSet` when the element is option-set bound; a `MULTI_TEXT` question is that
`#choice` plus `repeats = true`, which is the whole of what MULTI_TEXT means; a compulsory
program-stage element is `required`; on an *aggregate* source a non-default category combo turns
the question into a group
with one child per option combo, `linkId` `<deUid>.<cocUid>` - the same key a DHIS2
data value carries. Disaggregation is aggregate-only by construction: a data set's values land
on `/api/dataValueSets`, where every value carries a category option combo, while an event data
value has no `categoryOptionCombo` slot on the wire - so an event or tracker-stage question
stays flat whatever combo its data element declares, because a form must not ask a question the
capture endpoint cannot accept an answer to. A cell asks the element's own question one option combo at a time, so
each child takes the element's effective item type, its `answerValueSet`, its `repeats`, and
its bounds; only the `linkId`, the text, and the code differ. A section holding such a group
also carries the standard
`questionnaire-itemControl` extension coded `#gtable`, which is the DHIS2 data-entry
grid stated in FHIR terms. The source's own DHIS2 attribute values follow the
`D2FormType` extension as `D2AttributeValue` extensions, in DHIS2's order; the
data elements' attribute values do not travel, because they would land on
`D2DE_CS` concepts.

**Three tables, routed by `programType`.** `[generate.data_sets]` picks aggregate
data sets, `[generate.event_programs]` picks `WITHOUT_REGISTRATION` programs, and
`[generate.tracker_programs]` picks `WITH_REGISTRATION` programs. The two program
tables are read independently in `_fetch_program_sources`, each on its own terms, and
the two selection modes handle a mismatched shape differently - the split is
deliberate. When a table's `include_ids` is **explicit**, its UIDs are fetched by name
and every one is routed to that table's type; a program of the other type raises by
name, and the message points at the table the program does belong under - the operator
named that UID, so silence would be a lie. When
`include_ids` is **absent or empty** the whole instance is that table's target, so
refusing would make the mode unusable on any real database: the sweep routes each
program by its live `programType` and collects the types neither table maps into a
single aggregate note. With *both* tables empty one unfiltered fetch serves both,
because the split is a property of the response, not of the request. Listed UIDs that
resolve to nothing, and data elements no section references, are aggregate notes in
both modes.

The option-set closure keeps the IG internally consistent: when
`[generate.option_sets] include_ids` narrows the terminology, the option sets the
selected targets bind to are unioned in and listed in a note - including in target
all-mode, where the closure covers every form on the instance. An empty option-set
include list already means every option set, so the closure short-circuits there and
the targets are not fetched twice.

## Example responses -> QuestionnaireResponse instances

`generate examples` owns one sync directory, `ig/input/fsh/examples/`, holding one
`Usage: #example` QuestionnaireResponse per example, named `<targetUID>-<n>.fsh`.
The targets are the questionnaire targets - the same `_fetch_questionnaire_sources`
call, so all-mode and the routing rules behave identically, a tracker program
contributes one target per stage, and no example can point at
a Questionnaire the IG lacks.

`[generate.examples]` carries `per_target` (0 disables the target, which still
sweeps the directory clean; the ceiling is `MAXIMUM_EXAMPLES_PER_TARGET` = 10, so
the field validates in 0..10 and a larger value is a config error rather than a
thousand-file run) and `source`. The two sources meet at one emitter:
each produces a list of `ExampleResponseIn` - identity, organisation unit, status,
optional period, optional `authored`, and a flat list of
`(dataElement, categoryOptionCombo, value)` answers holding DHIS2 wire strings -
and `build_example_artifacts` does the typing, the structure mirroring, and the
rendering once.

- **`synthetic`** is the default, and deliberately so: an example is published,
  and real values off a production instance would travel with it. No data endpoint
  is called. `build_synthetic_responses` seeds a `random.Random` with the leading
  64 bits of `sha256("<targetUID>:<n>")` - never `hash()`, which is salted per
  process - so a regenerate is byte-identical across machines and restarts. Every
  question is answered and every option combo of a disaggregated element filled;
  `TRUE_ONLY` is always `true`; an option-set-bound question draws a real concept
  from the set the IG publishes. The only value that moves with the calendar is the
  anchor: a data-set example takes the newest completed period of its period type,
  and its temporal values are drawn from that window. A tracker-event example draws
  its tracked entity and enrollment UIDs off the same seeded generator, so the
  contract's two required UIDs are deterministic placeholders rather than identifiers
  borrowed from a live database.
- **`instance`** reads the server. Data sets walk `recent_periods(periodType, 6,
  today)` newest-first against `GET /api/dataValueSets` (root org unit,
  `children=true`) and stop at the first period holding values, which are then
  grouped by the DHIS2 reporting key `(orgUnit, period, attributeOptionCombo)`,
  richest group first. Both program kinds read `GET /api/tracker/events` ordered
  `occurredAt:desc`, tolerating both the `instances` and `events` envelope keys at
  the boundary: an event program selects by `program`, a tracker stage by
  `programStage` *plus* its `program`, which DHIS2 demands even though the stage pins
  it ([BUGS.md #67](../project/upstream-quirks.md#67-get-apitrackereventsprogramstageuid-demands-program-even-though-the-stage-pins-it)).
  A stage read also asks for `enrollment` and `trackedEntity`, the two UIDs the
  tracker-event contract requires. A target the instance answers nothing for is one
  aggregate note, never a failure.

An example that reaches the emitter without both tracker UIDs declares
`InstanceOf: QuestionnaireResponse` rather than the tracker profile and is tallied in
one aggregate note. Degrading rather than dropping is the same choice the answer
casting makes: a real captured form is worth publishing, and a document that cannot
meet a contract must not claim it.

The emitted items mirror the questionnaire exactly - section groups nest their
questions, a disaggregated element nests one child per option combo under
`<deUid>.<cocUid>` - but only the branches an answer reaches are emitted, so a
partial data value set produces a partial, still-valid response. Answers are cast
from the data element's `valueType`; an option code resolves to a `valueCoding`
into that set's CodeSystem, carrying the very concept code `concept_assignments`
handed the terminology target - fall-backs, collisions, and all - so an answer can
only ever name a concept the run really wrote. An answer selecting an option that
received no concept code is left unanswered and counted. Anything that will not
cast falls back to `valueString` and is counted, as is a captured value for a data
element the form does not ask for.

Two normalisations happen at the FHIR edge rather than being left to fail in
SUSHI: a zone-less DHIS2 timestamp gains `Z`
([BUGS.md #62](../project/upstream-quirks.md#62-tracker-occurredat-and-datetime-data-values-are-zone-less-local-timestamps-under-fields-typed-instant) -
R4 requires an offset on a `dateTime` that carries a time, and DHIS2 serves local
timestamps under fields its OpenAPI types as `Instant`), and a bare `HH:MM` gains
its seconds. A temporal value that still does not match the R4 primitive is answered as a string,
and an unusable `occurredAt` drops `authored` entirely - with a note either way. A
third upstream quirk is handled a layer earlier, at the wire-parse boundary:
`categoryOptionCombos` comes back in a different order on every request
([BUGS.md #64](../project/upstream-quirks.md#64-categorycombocategoryoptioncombos-is-serialised-in-a-different-order-on-every-request),
the same Java `Set` shape as `dataSetElements` in
[#63](../project/upstream-quirks.md#63-datasetdatasetelements-is-serialised-in-a-different-order-on-every-request)),
so the option combos are sorted by name and UID once at parse time, giving the questionnaire's child
items, the answers here, and the `D2COC_CS` concepts one shared order - which is
what keeps a disaggregated example past the validator's
`QuestionnaireResponse: Structural Error: items are out of order`.

An answer to an `ORGANISATION_UNIT` question is a `valueReference` at
`Location/<stem>` - the unit's identity stem, the DHIS2 id under the default
source - matching the `#reference` item type the questionnaire declares
and the `Location` instances the registry target publishes. `REFERENCE` and
`TRACKER_ASSOCIATE` point at DHIS2 objects the IG publishes nothing for yet, so a
synthetic example leaves them unanswered alongside the attachment and geometry
types, in one aggregate note.

## Organisation units -> instances

The definitional half is FSH, under `ig/input/fsh/organization/`:

- `profiles.fsh` - `D2Organization` and `D2Location`. Both take their `^status`
  from `[ig] status` and both slice `identifier` on `system` into `dhis2id 1..1`
  and `dhis2code 1..1`. `Organization.type` binds to the level ValueSet
  **extensible**, not required: an IG that adds group-set codings later must not
  be made non-conformant by the binding. `D2Location` also declares the
  `location-boundary-geojson` extension as a named `boundary 0..1` slice, so the
  profile states the geometry contract its instances carry instead of leaving the
  extension loose.
- `org-unit-levels.fsh` - `D2OU_Level_CS`/`_VS` covering the levels observed in the
  selection.
- `org-units-terminology.fsh` (only with `terminology = true`) - the whole
  selection as one `D2OU_CS` with `level` / `parent` / `dhis2-code` concept
  properties, for flows that want the hierarchy as codes instead of resources.

The registry itself is pre-built R4 JSON, under `ig/input/resources/registry/` -
`Organization-<stem>.json` and `Location-<stem>.json`, two files per unit, `id`
the unit's identity stem (the bare UID under the default source, the unit's code
under the code sources). Each carries both identifier slices and its profile in
`meta`, with `partOf` and `managingOrganization` following the same stems as
relative references
(`Organization/<stem>`, `Location/<stem>`), `partOf` omitted for the root or when the parent
falls outside the selection - noted, never silent. A unit whose `closedDate` has
passed carries `active: false` / `status: "inactive"`. Both halves also carry the
unit's DHIS2 attribute values as `D2AttributeValue` extensions - 244 of the Lao
instance's 300 organisation units have at least one, which makes the registry the
densest carrier of them. On the Location the emission order is part of the
byte-stability contract rather than incidental: `_extensions` puts the GeoJSON
boundary first and the attribute values after it in DHIS2's own order, so a
regenerate of an unchanged unit produces the identical file and
`sync_json_artifacts` reports it unchanged.

**Why JSON.** SUSHI loads `input/resources` and the sub-folders `path-resource`
declares as *predefined resources*: they land in the virtual `sushi-local#LOCAL`
package exactly as written, with no FSH parse and no conversion pass. The
registry is the largest thing in the IG and it is pure data - no profiling, no
invariants, nothing FSH's authoring conveniences buy - so the compile has nothing
to do with it. The measured cost of the alternative is in the guide under
[Registry scale](../guides/fhir-ig.md#registry-scale).

The documents are serialised from the pydantic models in `dhis2w_fhir/r4/` -
`Organization`, `Location`, and the element types they compose - rather than
rendered from a template, because JSON is a data structure and jinja would be
building one out of text. Every model is `frozen`, alias-aware, and
`extra="forbid"`, so a round trip through
`model_validate` / `model_dump_json(exclude_none=True, by_alias=True)` reproduces
the document key for key.

`ig/input/resources/` is gitignored by the scaffold. It is generated output that
`make generate` rebuilds from the instance in a few minutes, and a national
hierarchy plus its option-set terminology puts tens of thousands of files there;
`ig/input/fsh/` stays committed, so the reviewable diff is the definitional one.

Every artifact representing a DHIS2 object exposes both DHIS2 identifiers
wherever FHIR has a slot, and the code slot repeats the UID when the DHIS2 code is
missing or not FHIR-valid - so `dhis2code` can be `1..1` and consumers never
special-case absence. `d2w fhir validate` warns on every organisation unit
without a code, which is what drives those fall-backs out over time. Every
identifier system those slots name is declared by a foundation NamingSystem.
Every generated CodeSystem also points back at its ValueSet through `valueSet`
(spelled `^valueSet` in the FSH ones) and gives each concept property a
`<base>/property/<code>` URI so the property has a defined meaning outside this
IG. Every generated definitional resource - every response
profile, every extension, every CodeSystem/ValueSet pair, every Questionnaire -
states its publication `status` and its `experimental` flag from `[ig] status`:
`#draft` and `true` while the IG is `draft`, `#active` and `false` once it is
`active`. The flag is always populated, because ShareableCodeSystem /
ShareableValueSet make it mandatory. NamingSystem instances take the `status` -
R4 gives them the same publication-status codes - but no `experimental` element,
which R4 NamingSystem does not have. The Organization and Location instances are
outside this: their `active` / `status` carries the organisation unit's
closedDate, a different question with the same element names.

The tree is fetched with a 500-per-page loop ordered by `path:asc` (stable
output), filtered by `[generate.organisation_units]` `root` (DHIS2 `path:like`) and
`max_level`.

## Narrative pages -> pagecontent

`generate pages` owns one sync directory outside the FSH tree,
`ig/input/pagecontent/`, and writes markdown rather than FSH. SUSHI publishes
everything it finds there without a `pages:` block, and the IG publisher injects a
`<Type>-<id>-intro.md` into the top of the matching artifact page - so the same
directory carries both halves of the narrative layer:

```
pagecontent/forms.md                     Data set + event program + tracker stage catalog
pagecontent/registry.md                  Organisation unit registry summary
pagecontent/terminology.md               Option sets + the support CodeSystems
pagecontent/identifiers.md               The two identifier slices + NamingSystems
pagecontent/periods.md                   D2Period + every DHIS2 period type
pagecontent/capture.md                   The capture contract, worked per form kind
pagecontent/Questionnaire-<stem>-intro.md One per generated Questionnaire
pagecontent/CodeSystem-<id>-intro.md     Option sets carrying a DHIS2 description
pagecontent/Organization-<stem>-intro.md Org units carrying a DHIS2 description
```

The six site pages are the scaffolded menu: `Home`, `Forms`, `Registry`,
`Terminology`, `Identifiers`, `Periods`, `Capture`, `Artifacts`. The two intro kinds
that are gated on a DHIS2 description emit nothing when there is none - most
organisation units have no description, and an intro page repeating the title would
be noise.

`capture.md` is the narrative half of the capture contract. It works an aggregate
response, an event response, and a tracker event response step by step against forms
this project actually selected, with a
real ISO period resolved through `parse_period` from the pinned reference date and a
real organisation unit off the registry. The tracker walkthrough is the one that needs
prose most, because its shape is the least guessable: the logical `Patient` subject
carrying no `reference`, the `D2TrackerEnrollment` identifier, the
`D2OrganisationUnit` reference standing in for the `subject` an aggregate response
spends on the unit, and a pointer at `d2w data tracker enrollment list` for where the
two UIDs come from - DHIS2, not this guide. A project with no tracker stage selected
gets the rules without the worked example rather than a missing section. The page then
tabulates the answer typing for every
DHIS2 value type. That table is not written twice: the value type to answer element
mapping is `answer_element` in `resources/examples`, which `_typed_answer` dispatches
on and the page reads directly, and the event status table is the examples component's
own `STATUS_BY_EVENT_STATUS`. Only the prose spelling rule per value type is the
page's own. `forms.md` groups the same way the FSH tree does: a "Tracker programs"
section with one heading per program and that program's stages catalogued beneath it,
and each stage's `Questionnaire-<stem>-intro.md` names the program it belongs to, so a
form found on its own says what it is part of. `build_page_artifacts` takes the IG
canonical for this page alone - the
capture contract has to state the canonical URL rule a client resolves a Questionnaire
by, and that lives in `[ig]` rather than `[generate]`.

The target adds no endpoint. `PagesIn` is the three projections the other targets
already fetch - `QuestionnaireSourceIn`, `OptionSetIn`, `OrganisationUnitIn` - so a
page can never disagree with the FSH about what was generated. Link targets are
derived rather than reconstructed: `option_set_identities` is the one place an option
set's slug and `CodeSystem-<id>` are decided, read by the emitter for its file names,
by the questionnaire and example targets for their option-set names, and by the
terminology page for its links, and `periods.md` tabulates
`PERIOD_TYPE_DEFINITIONS` with examples resolved through `recent_periods` +
`parse_period` from a pinned reference date, so a regenerate never moves with the
calendar.

Markdown is the reason `names.markdown_text` exists. The same publisher quirk that
forced `page_text` onto the FSH page furniture applies to page bodies, and a markdown
table adds a second escape: `&`, then `<` and `>`, then `|` as `\|` with whitespace
flattened in table-cell context. Every DHIS2-derived string on a page goes through it;
the FSH layer is untouched by it.

## Translations

DHIS2 holds a translation as a `{locale, property, value}` triple with a
Java-style locale tag. `i18n.py` is the shared leaf over them: `TranslationIn`
is the projection the service wraps the raw dicts into at the fetch boundary,
`normalize_locale` renders the tag as BCP-47 (`pt_BR` -> `pt-BR`), and
`name_translations` selects the `NAME` entries, filters them to
`[generate] locales` (empty = all), deduplicates by locale, and sorts - so an
unchanged instance regenerates an unchanged file. Emission splits by what FHIR
offers on the target: CodeSystem concepts (options and, with
`terminology = true`, organisation units) take designations, while the
option-set CS/VS titles and the `Organization.name` / `Location.name` of every
instance take the standard
`http://hl7.org/fhir/StructureDefinition/translation` extension with its `lang`
and `content` sub-extensions. In the pre-built JSON that extension hangs off the
`_x` sibling of the primitive - `_title` on a CodeSystem or ValueSet, `_name` on
an Organization or Location - carried by `r4.Element`, the R4 root a primitive's
extensions hang from, and built by `i18n.translated_element`. Only `NAME` is
emitted. The deep option-set validation pass suffixes a finding's name with the subject's first matching
translation; the instance-wide sweep does not fetch translations at all.

## The full pipeline: one fetch, seven emitters

Bare `d2w fhir generate` calls `service.generate_full`, which is the whole IG on one
client. Each target is split in two: an `_emit_*` function that takes already-fetched
inputs and owns the build plus the sync, and a `generate_*` coroutine that fetches for
itself and calls it. The solo commands keep their own fetches verbatim, so
`d2w fhir generate option-sets` behaves exactly as it always did; `generate_full` opens
one client, runs `fetch_live_ig_inputs` once, and hands the result to all seven emitters.

That collapses the duplicated reads the seven solo commands perform between them: the
option sets are read once instead of five times, `/api/attributes` once instead of four,
the organisation-unit pagination once instead of twice. **Eight requests where the solo
targets total twenty-five.** Each emitter still keeps the notes it alone owns, so a
target's report reads exactly as the solo command's does, and a test asserts
`generate_full` writes a byte-identical tree to running all seven targets separately.

The foundation runs first because it reads nothing at all, and the pages run last
because they narrate what the other targets wrote.

### Progress

Every service function with an instance behind it takes `reporter: ProgressReporter | None`
from `dhis2w_core.progress` and announces its phases through a `_StepAnnouncer`: a step
opens with a label, re-captions itself with as many `tick` captions as the work warrants,
and closes with exactly one completion line. A tick is a caption an animated display
overwrites in place, so a fifty-page organisation-unit walk costs no more output than a
one-page one; a completion is the durable `[k/N] label: summary` line.

The service never calls `start`, `finish`, or `stop` - those bound the whole run and
belong to the caller. `cli.py` builds the reporter (`make_reporter(STDERR_CONSOLE,
animated=animated_progress(...))`), starts it with the run's exported step total
(`GENERATE_FULL_STEPS`, `GENERATE_TARGET_STEPS`, `GENERATE_FOUNDATION_STEPS`,
`VALIDATE_CODES_STEPS`), and stops it in a `finally`, so a writer error cannot leave a
Live display's refresh thread running and the terminal corrupted. `--no-progress` and
`--json` build no reporter at all, and the service treats a missing one as "announce to
nothing".

### Output channels

Tables, notes, hints, and progress are narration and go to stderr through
`STDERR_CONSOLE`; stdout carries the `--json` payload and nothing else. A full run
renders one summary row per target rather than seven detail tables, with each note
labelled by the target that raised it, because seven tables scrolled the thing worth
reading off the screen.

## Regeneration contract

Every generated file starts with a header line chosen by extension:
`// Generated by d2w fhir generate - do not edit` for FSH, and the HTML comment
`<!-- Generated by d2w fhir generate - do not edit -->` for the markdown pages,
which renders invisibly. A generate run first writes its target subdirectory, then
deletes the header-bearing `.fsh` / `.md` files in that subdirectory it did not just
produce - hand-authored FSH and the hand-authored `pagecontent/index.md` in the same
trees are never touched, and re-running converges instead of stacking files. Files whose
content already matches are not rewritten, so a no-op regenerate leaves both the
timestamps and `git status` untouched.

JSON has no comment syntax, so a header cannot mark the pre-built files.
`sync_json_artifacts` owns its directory outright instead - `registry/` for the
org-unit target, `terminology/` for the option-set target, `categories/` for the
category target: it deletes every `*.json` in that directory the run did not
produce, without an `is_generated_file` check, and leaves files of other
extensions and nested sub-directories alone. That is exactly why the three have a
directory each rather than sharing one. All three are gitignored, so nothing
hand-authored belongs there.

## Toolchain performance

Generation is the cheap half and the toolchain is where the minutes go; the
measured numbers live in the guide under
[Build time and the two caches](../guides/fhir-ig.md#build-time-and-the-two-caches).
Four structural facts explain the shape of it. The registry and the option-set
terminology are both predefined JSON, so the compile scales with the forms and
the five CodeSystems that are FSH rather than with the hierarchy or the
option-set count - and the publisher's rendering pass, which writes a page per
resource, is where that volume lands instead. The publisher runs **its own**
SUSHI over the same FSH, so a chain that compiles first and then publishes pays
for the compile twice - which is why `make refresh` goes straight from
`validate` to `build`. The phases are serial, SUSHI then the validator then
Jekyll, so nothing overlaps. And on a cold machine the package cache dominates
the front of the run, because the publisher fetches the core packages,
`hl7.terminology.r4`, and `hl7.fhir.uv.extensions.r4` before doing any work,
while a container started with `docker run --rm` throws them away again.

Two mitigations ship in the scaffold:

- **Package cache volume.** `make sushi` and `make build` mount the named volume
  `fhir-ig-cache` at `/home/publisher/.fhir`, so the package downloads survive
  the container. `make clean-all` removes the volume when you want the cold path
  back.
- **Terminology cache.** The publisher writes its tx cache into
  `ig/input-cache/`. `make clean` deliberately leaves it alone (only
  `clean-all` removes it), and `.gitignore` keeps it out of git. A warm tx cache
  is what takes the validation phase from minutes to seconds on a re-run.

**Iterate without the publisher.** `d2w fhir generate` plus `make sushi` is the
edit loop - SUSHI alone compiles the FSH and tells you whether it is valid
without rendering a site. `d2w fhir serve` (roadmap) is the rest of that loop.
`make build` is a release step, not an inner-loop step.

The upstream DHIS2 and tooling quirks that shape this code - including the two
that surface while reading a publisher run - are catalogued in
[fhir roadmap and review guide, section 4](../project/fhir-roadmap.md#4-upstream-dhis2-and-tooling-quirks-that-shape-the-code).
Two publisher behaviours worth knowing at the point you read its output:

- **The QA summary contradicts its own link checker.** The same run prints
  `... 1099935 links, 0 broken links (0%)` from the HTML checker and
  `Errors: 0, Warnings: 6710, Info: 177, Broken Links: 15425` in the QA summary.
  The 15,425 are not broken links at all: they are the
  "canonical link and is therefore unsafe with regard to versions" warning, one
  per page carrying the `publisher.url`. Dropping `publisher.url` removes the
  whole class.
- **`Error generating combined package: .../output/package.tgz (No such file or
  directory)`, exit 0.** An upstream call-ordering defect, not a project
  problem: `PublisherGenerator.genCombinedPackage()` opens `output/package.tgz`,
  but since publisher 2.2.9 it runs *before* `npm.finish()` writes that file
  (commit `f868684`, "generate combined package before shutting down the
  terminology system", moved the call). The exception is swallowed and logged.
  There is nothing an IG author can add to fix it - the publisher clears
  `output/` at startup, so a stale file cannot satisfy it either, and it
  reproduces on single-language IGs unrelated to this project. Only
  `output/package-combined.tgz` is lost; `output/package.tgz` itself is written
  correctly a moment later. Unreported upstream as of publisher 2.3.0.

## Validation

`d2w fhir validate` (MCP: `fhir_validate`) checks the whole instance against
the R4 primitives (https://hl7.org/fhir/R4/datatypes.html#primitive) in three
passes.

The **instance-wide sweep** over `GET /api/metadata?fields=id,name,code` is the
broad one: every metadata object's code, in every collection the endpoint returns,
with invalid codes as errors and per-type duplicates as warnings. It passes
`defaults=EXCLUDE`, so DHIS2's auto-generated default objects stay out of the
counts.

The **deep option-set pass** previews `concept_code_source = "code"` generation
(invalid/duplicate option codes are errors, missing codes warn,
spaced-but-valid codes are infos).

The **code-stem pass** previews what a code-sourced `[generate.naming] source`
does with each in-scope object of the six naming surfaces - `optionSets`,
`categories`, `organisationUnits`, `dataSets`, `programs`, `programStages`.
`_stem_findings` grades each object with `describe_stem_defect`, the same
predicate `resolve_identity_stems` decides fall-backs and refusals with, against
the very stem budgets the emitters bound their surfaces to - so validate and
generate can never disagree about which code serves. Under `"code-or-id"`
semantics a defective code is a `code-stem-fallback` warning (the artifact ids
silently fall back to the id); under `source = "code"` it is a
`code-stem-refusal` error, the run `d2w fhir generate` refuses through
`CodeStemError` before writing a file. A per-object check structurally cannot
see collisions - a stem is graded against its selected peers, a code equal to a
peer's id included - so `_stem_namespaces` groups the surfaces into the id
namespaces generate resolves stems over: option sets, categories, and
organisation units each on their own, data sets, event programs, and tracker
stages pooled into the `Questionnaire-<stem>` namespace exactly as
`plan_questionnaire_stems` scans them, and tracker programs (whose stem only
names the stage directory) on their own. Under the default `source = "id"` the
pass finds nothing. Over-long slugs are excluded from the collision report because
`long-name` already accounts for their suffix.

The **deep attribute pass** reads the sweep's own `attributes` collection - no
request of its own - and reports every attribute the instance left uncoded. The
emitter writes the `attributeCode` sub-extension only for a coded attribute, so an
uncoded one leaves every value it carries resolvable by DHIS2 UID alone across all
five contexted resource types. It is `info`: that is the emitted IG working as
designed, and a coverage signal rather than a defect. `FhirValidationReport`
carries `attribute_count` beside the option-set, option, resource-type, and object
counts, rendered in the Markdown report, the PDF, and the CLI table.

Every pass additionally raises `template-hostile-name` (warning, in either code
source) on any object whose **name** holds `<`, `>`, or `&` - the characters the
publisher's template injects into HTML unescaped. That one is about the published
pages rather than about codes, which is why it does not move with `--code-source`;
the sweep covers every metadata object and the deep option-set pass covers option
names, which the sweep excludes.

Its sibling `template-hostile-code` reads the object's **code** for the same three
characters, because the two failures are not the same size. A name deforms the page
it appears on; a code rides an identifier value, and the publisher writes identifier
values into a table cell unescaped and then strict-parses the page it just produced,
so the build aborts with `Unable to Parse HTML - node 'td' has unexpected content`.
It aborts in the publisher's final pass, after every resource has been rendered,
which is what makes catching it in a seconds-long `validate` worth an error rather
than a warning. The publisher escapes the other DHIS2 text that reaches a page -
concept displays, designations, `dhis2-code` property values, translation extensions
all survive a raw `<` - so the identifier table is the single carrier, and the code
is the single field that reaches it.

**The check is doubly restricted, and both restrictions are load-bearing**, because
an error here asserts that a build will fail. It fires only on
`_CODE_IDENTIFIER_COLLECTIONS` - `optionSets`, `categories`, `organisationUnits`,
`dataSets`, `programs` - the five whose objects emit a resource carrying the code as
an identifier value; every other collection either emits nothing or carries its code
through an escaped surface. And only `<` is an error: it opens a tag, which is the
failure that was observed, while `>` is text to an HTML parser and a bare `&` is
widely tolerated, so both are warnings rather than claims. Unrestricted, the check
raised 23 errors on the national instance it was written against - dashboards, data
elements, program indicators - of which one was the object that failed the build.

**What the deep passes do not repeat, and why** is stated in
`validation/__init__.py`'s own module docstring, and it is the reason the deep
layer is thin rather than a mirror of every emitter. The sweep already applies
both checks instance-wide to every collection the emitters read - `dataElements`,
`categoryOptionCombos`, `dataSets`, `programs`, `sections`,
`programStageSections`, `organisationUnits`, `attributes` - and under
`source = "id"` every emitted resource id is a DHIS2 UID (or `level-<n>`), valid
and unique by construction; under the code sources the code-stem pass checks the
codes the ids would derive from.
Two passes are deliberately absent. An organisation-unit deep pass would need
`_fetch_organisation_units`, the single unbounded read in the plugin, and would
find nothing the sweep does not already report: the registry's ids and concept
codes are UIDs, its names and codes are swept, and `organisationUnits` is the one
collection where the sweep already treats a missing code as a finding. A
questionnaire-target deep pass would repeat the sweep for the same reason - its
sources are all top-level `/api/metadata` collections.

The option-pass severities are gated on the effective code source - the
`--code-source` flag, else `concept_code_source`. In id mode `invalid-code`,
`missing-code`, and `duplicate-code` downgrade to `info` with the reason in the
message: generation is not reading those codes yet, so they are a readiness
signal for switching to code mode rather than a defect. The instance-wide sweep
keeps its severities either way. `d2w fhir validate --code-source code` is the
readiness probe for that switch.

The terminal shows errors and warnings; infos roll up per category (`--details`
lists them). Reports are written in three formats into the `--output-dir`
*directory* (default `reports/` under the project root, gitignored by the scaffold),
each named `fhir-validate-report`, with `--format` a comma list of `md`, `csv`, `pdf`:

- Markdown, grouped by resource type;
- CSV (`severity,category,resource_type,uid,name,code,message`), for
  spreadsheets and for diffing two runs;
- PDF, with a summary cover page, a clickable table of contents carrying
  per-type severity breakdowns, and one bookmarked section per resource type
  with severity-tinted rows. It is typeset in Noto Sans with a Noto Sans Lao
  fallback (both vendored under `validation/fonts/` with their OFL licence), so
  Lao-script DHIS2 names render instead of dropping to boxes.

Exit 1 on errors makes it a CI gate; `--fail` is the default and `--no-fail` drops
both the exit code and the red count line with it. A `fhir.toml`
is not required - validation targets the instance. MCP's `fhir_validate` takes
the same `code_source` and returns the report; writing files stays CLI-only.

## Code layout

Everything lives in the `dhis2w-fhir` workspace member, split into
components that each own their code, their schemas, and their templates.
There is no central models module: a component's pydantic models sit in its
own `schemas.py`.

Flat modules carry what every component shares: `names.py` (slug, FSH
literal, and URI helpers), `i18n.py` (the `TranslationIn` projection, locale
normalisation, and NAME selection), `attributes.py` (the `AttributeValueIn`
projection and the `AttributeCodeIndex` join every emitter reads an attribute's
code from), `notes.py` (the one aggregate-note
formatter),
`writer.py` (the `FshArtifact` / `FshBuild` and `JsonArtifact` / `JsonBuild`
contracts every emitter returns, plus the header-aware sync behind the first and
the directory-owning sync behind the second), `r4/schemas.py` (the FHIR R4
resource and element models the pre-built JSON is serialised from, and the ones a
received document is read back as - `Questionnaire`, `QuestionnaireResponse`, `Bundle`,
`OperationOutcome`, `CapabilityStatement`, `ConceptMap`, plus `JsonResource` for a
resource carried verbatim), `r4/primitives.py` (the lexical and semantic checks for R4's primitive types,
shared by the emitters that write a value and the capture path that reads one), and
`config.py` (the `fhir.toml`
document - `IgConfig`, `NamingConfig`, `GenerateConfig`, `FhirProjectConfig`,
`FhirProject` - with discovery, load, and save). `service.py` holds the
shared orchestration and its own `GenerateReport` / `GenerateFullReport`;
`cli.py` / `mcp.py` stay thin over it. `plugin.py` exports the descriptor
referenced by the `dhis2.plugins` entry point; `dhis2w-cli` and `dhis2w-mcp`
depend on the package so `d2w fhir` is present by default.

The components:

- `scaffold/` - the twelve files `d2w fhir init` writes (`InitOptions`,
  `ScaffoldFile`, `ScaffoldReport`, and `normalize_project_name`, which turns the
  IG id into the PEP 508 name of the scaffolded `pyproject.toml`), plus
  `refresh.py`: `read_project_scaffold_state` recovering the scaffold inputs off
  disk into a `ProjectScaffoldState`, `preserves_every_line` deciding whether a
  rewrite loses anything, and `refresh_project` behind `d2w fhir init --refresh`.
  Refresh is a CLI path rather than package API, so it stays out of the top-level
  re-exports.
- `resources/option_sets/` - the pre-built CodeSystem/ValueSet pair per option
  set, its `TERMINOLOGY_DIRECTORY` sync directory, the ConceptMap taking that
  pair's concept codes back to the DHIS2 option UID and code
  (`build_option_set_concept_maps` and its `CONCEPT_MAP_DIRECTORY`),
  `option_set_identities` and the
  `OptionSetIdentityPlan` / `OptionSetIdentityIndex` every other target reads
  option-set names from, `build_concepts` (the concept-code assignment the
  category component shares), plus `max_slug_length` (validation previews the same
  id bound) and the `OptionSetIn` / `OptionIn` / `ConceptSourceIn` /
  `OptionSetSelection` schemas. It builds `r4.schemas` models and ships no
  templates - JSON is a data structure, not a text layout.
- `resources/categories/` - the pre-built CodeSystem/ValueSet pair per DHIS2
  category, its own `CATEGORY_DIRECTORY` sync directory, `category_identities` and
  the `CategoryIdentity` / `CategoryIdentityPlan` it assigns over the whole
  selection, `category_fsh_name`, `max_category_slug_length`, and the `CategoryIn`
  / `CategorySelection` schemas. It reads `resources/option_sets/` for the shared
  concept assignment and is read by none of them.
- `resources/attribute_combos/` - the pre-built CodeSystem/ValueSet pair per distinct
  non-default attribute category combo a selected data set rides, its own
  `ATTRIBUTE_COMBO_DIRECTORY` sync directory, `attribute_combo_sources` reducing the run's
  forms to the combos they share, `attribute_combo_identities` and the
  `AttributeComboIdentity` / `AttributeComboIdentityPlan` it assigns over that selection,
  the `AttributeComboPlan` both Questionnaire emitters stamp their
  `D2AttributeOptionCombos` extension from and both example emitters code their
  `D2AttributeOptionCombo` from, and `build_attribute_combo_concept_map_artifacts` taking
  every concept back to `<base>/id/category-option-combo` and its `-code` sibling. It
  reads `resources/option_sets/` for the shared concept assignment and
  `resources/questionnaires/schemas` for the form projection; the questionnaire emitters
  read only its `schemas`, so nothing cycles.
- `resources/questionnaires/` - the Questionnaire instance per data set / event
  program / tracker program stage plus the two support terminology pairs, the exported
  `ITEM_TYPES_BY_VALUE_TYPE` table mapping every DHIS2 `valueType` on v41/v42/v43 to its
  FHIR item type (guarded by a test that reads the three generated `ValueType` enums, so a
  codegen refresh cannot introduce a silent `string`), the four sync directory names
  (`DATA_SET_DIRECTORY` / `EVENT_PROGRAM_DIRECTORY` / `TRACKER_PROGRAM_DIRECTORY` /
  `DATA_DICTIONARY_DIRECTORY`,
  collected as `QUESTIONNAIRE_DIRECTORIES`), `assignments.py` emitting the
  organisation-unit assignment `List` of every form whose assignment is a proper subset
  of the published registry into `ASSIGNMENT_DIRECTORY` and answering with the
  `AssignmentPlan` both Questionnaire emitters stamp their `D2OrganisationUnitAssignment`
  extension from, with `TargetSelection`, the
  `QuestionnaireSourceIn` / `QuestionnaireSectionIn` / `QuestionnaireItemIn` /
  `ProgramContextIn` / `CategoryComboIn` / `CategoryOptionComboIn` projections, and
  `QuestionnaireNaming`
  deriving every name from the `DS` / `PR` / `PS` / `DE` / `COC` tokens - option-set names
  are not among them, they come in on the `OptionSetIdentityPlan`. Item nesting is
  resolved in Python into a flat list of view-models carrying their FSH soft-index
  paths (`item[=].item[+]`), so the template stays a layout, not a recursion. `documents.py`
  is the JSON twin of that emitter - `build_questionnaire_documents` and
  `build_data_dictionary_documents` return the finished R4 documents with every name
  already absolute, exactly as SUSHI would have resolved it, through the same exported
  decisions (`item_type`, `is_disaggregated`, `source_description`, `source_program`,
  the `FormKindProfile` / `FORM_KIND_PROFILES` identifier segments) the FSH path calls,
  so the two cannot drift; `test_fhir_questionnaire_parity.py` is the gate, asserting
  each built document equals the SUSHI output key for key. `d2w fhir serve --live` is
  what consumes it.
- `resources/examples/` - the `Usage: #example` QuestionnaireResponse per example,
  its `EXAMPLES_DIRECTORY` sync directory, the `ExampleSelection` /
  `ExampleResponseIn` / `ExampleAnswerIn` projections (the option sets come in on
  the option-set component's own `OptionSetIn`), the seeded
  `build_synthetic_responses`, and the answer typing (including the R4 temporal
  normalisations and their calendar, clock, and offset checks, which live in
  `r4/primitives.py`). `documents.py` is its JSON twin: `build_example_documents` returns
  the same responses as finished `QuestionnaireResponse` documents, which is what
  `d2w fhir generate load-set` writes into `load/`. It depends on `resources/questionnaires/`
  for the source projection and naming, never the other way round.
- `resources/pages/` - the narrative markdown layer: the six site pages, the
  per-artifact intros, `PagesIn` (the fetched-input view the pages render from),
  and the per-page view-models. It reads the other components' naming helpers and
  projections - including the examples component's answer typing, which
  `capture.md` tabulates rather than restates - and is read by none of them.
- `resources/organisation_units/` - split by FHIR resource: `naming.py`
  derives every artifact name and id from the `[generate.naming]` tokens,
  `organization.py` builds the profiles artifact, the `REGISTRY_DIRECTORY`
  constant, and the Organization instances, `location.py` the Location instances
  (position, boundary extension, level extension, `partOf`), `terminology.py` the level pair and
  the optional whole-selection pair. The two instance builders return
  `r4.schemas` models that `organization.py` serialises into `JsonArtifact`s;
  only the profiles and the terminology go through jinja. Group / group-set
  emission lands here next.
- `foundation/` - the instance-independent artifacts: the DHIS2 identifier
  aliases, the NamingSystem declarations, the `D2Period` / `D2FormType` /
  `D2AttributeValue` / `D2OrganisationUnit` / `D2OrganisationUnitAssignment` /
  `D2OrganisationUnitLevel` / `D2TrackerEnrollment` extensions, the
  three response profiles, and the CapabilityStatement, with `FoundationNaming` deriving
  their names from the prefix token. `attribute_values.py` additionally holds the
  `D2AttributeValue` builder the resource emitters call, which is why the only
  definitional component is also imported at emit time.
- `period/` - the DHIS2 ISO period grammar: `PeriodValue`, the period-type
  catalogue the CodeSystem is generated from, `parse_period`, and the
  `recent_periods` inverse the example target discovers data with.
- `validation/` - the two check passes, `report.py` rendering the Markdown and
  CSV, `pdf.py` the PDF, and the finding/report schemas.

`resources/` is reserved for DHIS2 resource domains, which is why `scaffold/`,
`validation/`, and `r4/` stay top level - the last of those is FHIR's own R4
vocabulary, shared by whichever resource domain emits JSON.

Dependencies point one way: `config.py` composes the per-component selection
tables (`OptionSetSelection`, `OrganisationUnitSelection`, and the shared
`TargetSelection` behind both data-definition tables), and no component
imports `config.py` at runtime - an emitter receives its `GenerateConfig` as
a parameter and annotates it under `TYPE_CHECKING`. `dhis2w_fhir/__init__.py`
re-exports the whole public surface, so `from dhis2w_fhir import
GenerateConfig` keeps working however the components are arranged.

No FSH, TOML, YAML, or Markdown body - the narrative pages and their intros
included - is assembled by string concatenation in Python. Every component that emits one ships a `templates/` directory of jinja2 templates
loaded through a `PackageLoader` scoped to that subpackage
(`StrictUndefined`, `trim_blocks`, `lstrip_blocks`, `keep_trailing_newline`
- the same settings `dhis2w-codegen` uses, so control tags never leak blank
lines and rebuilds stay byte-stable). The Python side resolves every
conditional into a pydantic view-model and renders; the templates hold the
layout.

JSON is the exception, and for the same reason: it is a data structure, not a
text layout. The registry and terminology documents are built as `r4.schemas`
models and serialised with
`model_dump_json(exclude_none=True, by_alias=True, indent=2)`, which is
byte-stable for the same input and cannot emit a malformed document the way a
template can. `resources/option_sets/` therefore has no `templates/` directory at
all.

The service opens the version-neutral
`dhis2w_core.client_context.open_client` and maps generated `OptionSet` /
`OrganisationUnit` / `DataSet` / `Program` / `Attribute` schemas into the `*In`
projections at the boundary, `attributeValues[attribute[id],value]` among the
fields each of the first four asks for.
Geometry becomes a frozen `GeoPoint`: Point coordinates directly, and for
Polygon/MultiPolygon the area-weighted (shoelace) centroid of the outer ring
with the largest absolute area - not a bounding-box midpoint, which lands
outside concave boundaries. Both are nominal paths that raise no note; the
report's position and boundary counters carry the numbers.

Every unit whose geometry parses carries the full GeoJSON into `Location`
through the standard `location-boundary-geojson` extension, wrapped in a
`Feature` whose properties hold the UID, name, and level, with the attachment's
`title` and `size` set. That includes geometry types no position can be derived
from - LineString, MultiPoint, GeometryCollection - which are embedded without a
position and rolled into one note naming the types. Only geometry with unusable
or empty coordinates is malformed, and that alone yields neither position nor
boundary.

## Serving the IG -> the `dhis2w-fhir-serve` member

`d2w fhir serve` is a second verb over a generated project: a FastAPI application that
serves the resources the IG publishes and receives `QuestionnaireResponse` captures
against them. The command lives in this package's `cli.py`; everything it runs lives in
`dhis2w-fhir-serve`, a workspace member of its own.

**Why a member and not a subpackage.** `dhis2w-fhir` generates a file tree - it needs
httpx, pydantic, and jinja2, and nothing that listens on a socket. The facade needs
FastAPI and uvicorn. Folding the server into the generator would put both into every
install that only ever writes FSH, including a CI job and an MCP server. So the server
is its own member, `dhis2w-cli` declares it as the optional `serve` extra
(`pip install 'dhis2w-cli[serve]'`), and the command's body guards the import: without
the package it raises a `LookupError` naming both install routes, which the CLI error
funnel renders as a one-line message. The dependency arrow points one way -
`dhis2w-fhir-serve` -> `dhis2w-fhir` - so the generator never learns the server exists.

**The store is two trees merged.** `ig/fsh-generated/resources` is what SUSHI compiled
from the emitted FSH. `ig/input/resources/{registry,terminology,concept-maps,categories}` is the
pre-built JSON the generate targets wrote, which SUSHI loads as predefined resources and
**never re-emits** - so a store built from the compiled tree alone would serve an IG
missing its whole registry and terminology. `load_compiled_store` reads both, compiled
first, and indexes each entry by `(resourceType, id)`, by canonical url, and by every
`system|value` identifier token it carries. The resource body itself is passed through
untouched: the facade's contract is byte-faithful passthrough, so what a client reads is
what the project published, down to key order.

**Live mode runs the JSON builders instead.** `live.py` resolves the generation profile,
opens **one** client, fetches through `fetch_live_ig_inputs`, closes it, and builds the
same read set from `build_questionnaire_documents`, `build_data_dictionary_documents`,
`build_option_set_artifacts`, `build_category_artifacts`, and
`build_organisation_unit_instances`. The first two are the JSON twins of the FSH
questionnaire emitter - the same projection, the same item typing, the same ValueSet
binding decisions, through the very functions the FSH path calls - and the equality is a
gate rather than an aspiration: `test_fhir_questionnaire_parity.py` rebuilds the
compiled questionnaires from the committed source fixtures and asserts each equals the
SUSHI output key for key. The last three already return serialised JSON artifacts, so
`live.py` reads their documents back out of that exact text rather than serialising a
second time. What live mode does not hold is the foundation artifacts: StructureDefinitions
and the IG's `kind #requirements` CapabilityStatement exist only once SUSHI has compiled
the FSH, and no FSH compiler runs in this process. That costs nothing - the served read
set is `CAPTURE_SERVER_READ_RESOURCE_TYPES`, every one of which a JSON builder produces,
and `/metadata` names the IG's statement by canonical, which needs no artifact to state.

**Capture is a phase machine.** `capture/` has four modules in the order a request
passes through them: `naming` derives the extension urls and identifier systems this
project's contract is written in from `fhir.toml` alone, `index` reads one served
Questionnaire into the lookups an answer is checked against, `resolve` maps a received
code back to the DHIS2 option it names against the served terminology, and `validate`
runs the phases - body and R4 shape (400), the `D2FormType` kind and its profile
invariants, the questionnaire and its index, the organisation-unit assignment, the
attribute option combo, the period, then every answer (422). A
phase that finds an error is the last one to run, so a rejection is readable; inside a
phase every issue is collected, so one round trip reports every problem at that level.
`outcome` is the OperationOutcome vocabulary every answer is spoken in, accepted or
refused. Nothing in `capture/` talks to DHIS2.

**Coded answers have one flip point.** `DEFAULT_STRICT_CODES` in `capture/validate.py`
is the single constant behind roadmap decision 5.1, and `ServeSettings.strict_codes` is
the runtime value a request is validated against; `--strict-codes` is the flag that sets
it. Lenient resolution walks three tiers - concept code, option UID, DHIS2 code - and
warns on anything below the first, because the generated CodeSystem publishes both DHIS2
spellings and a client that sent the other one still named exactly one option. Two
options matching one code is an ambiguity refused under either setting.

**Three things grade on that one dial.** A drifted code, an organisation unit outside the
form's published assignment, and the attribute option combo a form declares its responses
carry - all of them describe drift between a client and the instance rather than a
malformed document, so all of them warn by default and refuse under `--strict-codes`.
`CaptureIndex.attribute_option_combos` is where the form's `D2AttributeOptionCombos`
declaration is read into the phase, resolved through the served ValueSet to the CodeSystem
a coding into it names; absence means the data set rides the default category combo, and a
response naming a combo against such a form grades too, because it would be stored and
then silently not written. What is refused whatever the dial is what the coded-answer path
refuses whatever the dial: a coding from another system, a coding with no code, and an
ambiguity.

**`$generate` reads the capture index backwards.** `GET|POST
/Questionnaire/{id}/$generate` answers a served form with a synthetic
`QuestionnaireResponse`, and `synthesize.py` builds it from the very `CaptureIndex` the
validator checks a submission against: the same `value[x]` element per question, the same
`minValue` / `maxValue` bounds, the same `repeats`, the same `answerValueSet` binding
resolved through the same `CodingResolverSet`. That is what holds the invariant the
operation exists for - **generated output posted back at the same server answers 201** -
because a rule cannot be enforced on receipt without being honoured on generation. One
route serves both modes: a live store holds the same compiled-shape Questionnaires and
CodeSystems, so nothing about generation branches on `--live`. The `seed` input makes a
call reproducible and rides back on `QuestionnaireResponse.identifier`, so a seedless call
is reproducible too. Two facts a compiled Questionnaire does not carry get documented
rules rather than guesses: the data set's period type is read off a served example
response answering the same form and falls back to `Monthly`, and `TRUE_ONLY` is
indistinguishable from `BOOLEAN` so both generate either value. A form declaring an
attribute-option-combo vocabulary gets one drawn out of the served CodeSystem, in the
concept-code spelling, which is what keeps the 201 invariant holding for a non-default
data set under `--strict-codes`; a form declaring one this project never published gets
the extension left off, exactly as an unpublished `answerValueSet` leaves a question
unanswered. The operation is custom -
not SDC's `$populate`, which means fill-from-real-context - so the IG publishes its own
`OperationDefinition` and `/metadata` declares it on the `Questionnaire` resource entry,
where R4 puts an instance-level operation.

**The spool is a directory, not an index.** `ResponseSpool` is a path plus the rules for
reading it: `.serve/responses/{received,forwarded,rejected}/<id>.json`, one directory per
lifecycle state, re-read on every call. That is deliberate, and it is the one place the
facade pays for a read. `d2w fhir forward` is a separate process that renames files
between those directories while the server is up, so an index built at startup would keep
calling forwarded receipts `received` and a UI reading it would show a queue that never
empties. Writes are atomic (`mkstemp` in the same directory, then `os.replace`), so a
reader never sees a half-written file and a crash leaves the directory consistent, and
`ls received/` is the pending count with no extra bookkeeping. The receipt id is a uuid4
hex rather than a DHIS2 UID - a receipt is a resource the facade owns, and an
11-character DHIS2-shaped id would read as one.

**`GET /spool` is the one endpoint that is deliberately not FHIR.** The receipts
themselves are `GET /QuestionnaireResponse`, and that search answers whatever state a
receipt is in - draining a receipt must not expire the id its sender was handed. What the
search cannot carry is the receipt *envelope*: when the facade accepted the submission,
which DHIS2 form kind it was validated as, what it had to warn about, which directory the
file now sits in, and the DHIS2 import report `d2w fhir forward` left beside a rejection.
None of those are QuestionnaireResponse elements. Two could be forced into `meta`, and an
`ImportSummary` could be bent into an `OperationOutcome`, but that spreads one record
across a resource, a tag system this IG does not publish, and a second operation - and
the import counts still have nowhere honest to go. So the envelope is served as what it
is: typed JSON at a fixed one-segment lowercase path, which no PascalCase FHIR resource
type can ever collide with.

**What the store is not.** It is loaded once in the lifespan and held frozen on
`app.state.context` for the life of the process. Nothing invalidates it, because nothing
can: a compiled IG changes when someone runs a build, and a live store is a snapshot of
the instance the server started against. Restart to serve new state.

### The capture UI -> `frontend/`, built into the package

`d2w fhir serve --ui` serves a browser UI off the same process and the same port as the
FHIR routes. Its source is a React + TypeScript app at
`packages/dhis2w-fhir-serve/frontend/`; its build output is
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/static/`, which ships inside the wheel
and is what `ui.py` mounts.

**Why inside the Python package.** The alternative - a separately hosted UI pointed at
the endpoint by configuration - buys nothing here and costs a CORS story, a URL to
mis-type, and a version skew between a UI and a facade that are otherwise released
together. Same-origin means the UI reads relative paths, `apiFetch` needs no base URL,
and a `pip install` is the whole deployment. The trade is that the wheel carries a
frontend build, which is why `make build-frontend` runs before `make build`.

**The bundle is gitignored, not committed.** This workspace publishes wheels from CI, and
CI runs the build; a committed bundle would only be a second copy of the same bytes going
stale between rebuilds. The directory is kept by a `.gitkeep` that the vite build rewrites
after `emptyOutDir` wipes it.

**Mount order is the whole of `ui.py`, and it cuts both ways.** Starlette matches routes in
registration order, and the read routes are catch-alls: `/{resource_type}` claims every
one-segment path, `/{resource_type}/{resource_id}` every two-segment one. A single mount
at `/` placed last therefore serves the shell and nothing else, because
`/assets/index-<hash>.js` is two segments and the read route answers it with an
OperationOutcome saying `assets` is not a served type - a white page whose cause is in the
router table. A mount placed first swallows `/metadata` and every Bundle. So the bundle
mounts in two pieces: `mount_ui_assets` registers `/assets` **with the fixed-path routers**,
ahead of the catch-alls, and `mount_ui_shell` registers `/` **after everything**.
`register_routes(app, serve_ui=...)` owns both calls, and `tests/test_ui.py` holds both
halves - every FHIR path still answers FHIR with the UI mounted, and every asset the real
built shell names still loads.

**A missing bundle is a refusal, never a blank page.** `create_app` builds the mount, so
`--ui` on a checkout that has never run `make build-frontend` raises `UiBundleMissingError`
(a `LookupError`, which the CLI error funnel renders as one line) before the banner - the
same shape as the taken-port refusal.

**Nothing about the frontend leaks into the Python.** `ui.py` knows a directory and a mount
order; it does not know React, or which pages exist. Symmetrically the UI knows the wire
contract and nothing else: `lib/api.ts` is the single credentialed exit and guards every
path against the served set (`/metadata` plus `read.SERVED_RESOURCE_TYPES` plus
`ConceptMap`), and `lib/fhir.ts` hand-types the narrow R4 shapes the UI reads. Its tests
run against fixtures harvested from a real facade over the committed goldens, so a change
to the emitter that breaks the UI's reading of the wire breaks a test.

**The form renderer takes its submission context from `$generate`, not from arithmetic.** A
capture-valid QuestionnaireResponse is not only its answers: `capture/validate.py` checks a
`meta.profile` naming the form kind's response profile, a D2Period on an aggregate submission,
a Location subject, an `authored` instant on an event, a tracked entity identifier and an
enrollment extension on a tracker event - all before it looks at a single answer. A browser
deriving that would be a second implementation of DHIS2 period arithmetic and the organisation
unit hierarchy, in a language with none of the tests. So `pages/FormFill.tsx` reads one
`GET /Questionnaire/{id}/$generate` when the page opens, keeps the skeleton's envelope, throws
away its answers, and puts the user's in their place. That call is pinned postable to this same
server by `test_generate_endpoint.py`, so the context leaving the page is valid by construction
and the operation earns a second consumer beyond its fill-with-test-data button. The seed
identifier is dropped on the way out, because it names a draw the answers may no longer be. The
one exception is the attribute option combo: a form declaring `D2AttributeOptionCombos` gets a
reporting-context picker above its items - expanded from that ValueSet, pre-selected from whatever
`$generate` drew, and required, because which combo a submission is filed under is the third key of
every value it carries and the one piece of context nothing can derive.

`lib/questionnaire.ts` is where that lives, and it is deliberately the only interesting file in
the UI without a DOM in it: the item tree flattened into an ordered spec, one reducer keyed by
`linkId` (which R4 makes unique per questionnaire and `conversion/context.py` already keys its
own question index by), `enableWhen` as a derived predicate, and the assembly of the response.
`ANSWER_ELEMENTS_BY_ITEM_TYPE` there is a transcription of the table of the same name in
`dhis2w_fhir.conversion.context` - the UI must write the exact `value[x]` the validator demands,
and the two tables drifting apart is what its tests over `$generate` goldens catch.

The frontend has its own toolchain and its own make targets - `make frontend-dev`,
`build-frontend`, `lint-frontend`, `test-frontend`, `e2e-frontend` - kept out of `make lint`
and `make test` so those stay a pure-Python run on a machine with no node installed.

`make e2e-frontend` is the browser suite: Playwright over chromium against a **real**
`d2w fhir serve --ui` on its own port (8377, not 8080, where a local DHIS2 stack lives),
booted by the config's `webServer` over a fixture IG project written from
`packages/dhis2w-fhir-serve/tests/fixture_project.py` - the same builder the pytest suite
uses, so there is one copy of the goldens in the workspace and the browser sees the IG the
Python tests prove the capture path against. A mocked API would be the wrong thing to test:
the failures worth catching here are of the router table - an asset arriving as an
OperationOutcome, a path typo landing on the SPA shell with a 200 - and only the actual
server serving the actual bundle can produce them. The suite covers the shell and the nav
rail, the Forms listing, the operations the CapabilityStatement declares, and the capture
loop twice over: once at the API level (`$generate`, POST, the receipt on the Responses
page) and once through the renderer, as a person performs it. `make build-frontend` and
`pnpm exec playwright install chromium` are documented prerequisites rather than things the
target runs behind you: one writes into the Python package, and the other downloads a
browser.

### What Dimension A concluded

The [review dimension](../project/fhir-roadmap.md#dimension-a-the-seams-serve-will-consume)
asked what breaks when a long-running server calls the generator's seams instead of a
one-shot CLI process. The facade answers it by construction rather than by hardening:

- **The profile is resolved once.** `resolve_generation_profile` reads `os.environ` at
  call time, which is a different thing in a process that lives for hours. Live mode
  calls it exactly once, in the lifespan, before any request exists.
- **One client, startup only.** A named generate target opens and closes a client of its own;
  `build_live_store` opens one, fetches everything through `fetch_live_ig_inputs`, and
  closes it before the first request. No request path holds a DHIS2 connection.
- **The store is immutable and shared.** Frozen models, indexes built once in
  `model_post_init`, and reads that are dict lookups - so concurrency needs no locking on
  the read side.
- **The one writer needs no lock either.** `sync_artifacts` has no locking and two
  concurrent generate calls would interleave, but the facade never generates: its only
  write is the spool, whose single-writer assumption is exactly what one server process
  is, and whose writes are atomic renames.
- **Partial failure is a refusal to start.** A missing compiled IG or an unreachable
  instance propagates out of the lifespan and the server does not come up, rather than
  serving an empty IG that reads to a client as a project that published nothing.

## Roadmap and review material

Everything roadmap-shaped about this plugin - the near-term, mid-term, and
long-term items, the terminology source candidates, the settled decisions behind
the current design, the open decisions still needing an owner call, the four
review dimensions, and the measured build numbers - lives in the
[FHIR roadmap and review guide](../project/fhir-roadmap.md). This page describes
what the package is; that page describes where it is going and what to look at.
