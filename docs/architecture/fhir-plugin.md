# FHIR plugin

`d2w fhir` turns DHIS2 metadata into a FHIR Implementation Guide source tree:
a SUSHI project whose FSH (FHIR Shorthand) files are generated from
`/api/optionSets`, `/api/organisationUnits`, `/api/dataSets`, and `/api/programs`.

```
d2w fhir init [DIRECTORY]           Scaffold a dockerized SUSHI IG project
d2w fhir generate foundation        Identifier aliases + the D2Period / D2FormType extensions
d2w fhir generate option-sets       Option sets -> CodeSystem/ValueSet pairs
d2w fhir generate questionnaires    Data sets + event programs -> Questionnaire instances
d2w fhir generate org-units         Org units -> Organization/Location instances
d2w fhir generate all               All four targets in one run
d2w fhir validate                   FHIR-safety of the instance's codes (exit 1 on errors; --no-fail)
```

The plugin ships as its own workspace member, `dhis2w-fhir`, and mounts
through the `dhis2.plugins` entry point - the same mechanism third-party
plugins use. It is version-neutral: the wire client auto-detects the DHIS2
major on connect, so one package serves v41/v42/v43 with no per-tree copies.

The [FHIR IG guide](../guides/fhir-ig.md) is the task-oriented companion to this
page: quickstart, the complete `fhir.toml` reference, and the regeneration
contract.

MCP exposes only the read surface: `fhir_validate` (`readOnlyHint`).
Scaffolding and generation are CLI-only by design - they write a file tree
onto whatever machine the MCP server runs on, the wrong shape for an agent
protocol (the same judgment as the browser plugin and the security audit
runner).

## Project layout and fhir.toml

`d2w fhir init` scaffolds a complete project:

```
fhir.toml                   Minimal generation config (committed; no secrets)
fhir.toml.example           Every available option with its default, documented
Makefile                    setup / upgrade / generate / validate / sushi / build /
                            clean / clean-all / help via docker
Dockerfile                  ghcr.io/fhir/ig-publisher-localdev + fsh-sushi
.gitignore                  The build output, caches, and publisher side products
ig/sushi-config.yaml        SUSHI IG identity (id, canonical, publisher)
ig/ig.ini                   IG publisher entry point (fhir2.base.template)
ig/fsh.ini                  Raises the publisher's internal SUSHI timeout to 900s
ig/input/fsh/aliases.fsh    Hand-authored alias stub (never regenerated)
ig/input/pagecontent/index.md
ig/input/ignoreWarnings.txt
```

`sushi-config.yaml` carries `publisher.name` and, only when `d2w fhir init
--publisher-url` supplies a real home page, `publisher.url`. The IG publisher
links that URL from every generated page, so pointing it at the canonical of an
IG that is not yet published produces one broken link per page - 15,425 of them
on the Sierra Leone demo. Omitting it is the default.

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
source = "id"                       # "id" or "name"
prefix = "D2"                       # "" drops it; profiles keep a D2 token
option_set = "OS"                   # e.g. "OptionSet"; "" drops the token
organisation_unit = "OU"            # e.g. "OrgUnit" -> D2OrgUnit_Level_CS
data_set = "DS"                     # data set Questionnaire names
program = "PR"                      # event program Questionnaire names

[generate.option_sets]
# include_ids = ["Qdm5fPK5Ra9"]     # UIDs; absent = all

[generate.data_sets]
# include_ids = ["BfMAe6Itzgt"]     # UIDs; absent = none

[generate.event_programs]
# include_ids = ["VBqh0ynB2wv"]     # UIDs; absent = none

[generate.organisation_units]
# root = "ImspTQPwCqd"
# max_level = 4
terminology = false
```

The data-definition selections invert the default: absent means *none*, because a
form is added to a project one UID at a time. `fhir.toml.example` shows every
unset-by-default key as a commented, real-shaped example rather than a magic
placeholder, so the file parses to exactly the defaults.

`identifier_system_base` is live: `generate foundation` writes it into
`foundation/d2-aliases.fsh` as the `$DHIS2-*` aliases, declares each of those
URLs as a NamingSystem in `foundation/d2-naming-systems.fsh`, and derives the
`^property` URIs the terminology concepts carry.

The full configuration reference, with the id-first-then-code workflow and the
canonical naming-token registry, is in the
[FHIR IG guide](../guides/fhir-ig.md).

Artifact names merge the prefix and kind tokens and underscore the segments
after them (`D2` + `OS` + `_Qdm5fPK5Ra9` + `_CS` - short tokens read by context);
ids join the kebab of each non-empty token, with the UID kept verbatim
(`d2-os-Qdm5fPK5Ra9-cs`), so renaming or dropping a token reshapes the whole IG
consistently. With `naming.source = "name"` the same set reads `D2OS_BirthType_CS`
/ `d2-os-birth-type-cs`. The two profile names always carry a token (default
`D2`) because FSH cannot name a profile identically to its parent core resource.

## Foundation -> identifier systems, D2Period, and D2FormType

`generate foundation` writes `ig/input/fsh/foundation/`, the part of the IG that
depends on `fhir.toml` alone and never opens a client:

- `d2-aliases.fsh` - `$DHIS2-OU` / `$DHIS2-OU-CODE` / `$DHIS2-OS` /
  `$DHIS2-OS-CODE` / `$DHIS2-DS` / `$DHIS2-DS-CODE` / `$DHIS2-PROGRAM` /
  `$DHIS2-PROGRAM-CODE` / `$DHIS2-DE` / `$DHIS2-COC`, built from
  `identifier_system_base`. Generating these rather
  than scaffolding them is what frees `ig/input/fsh/aliases.fsh` to be a pure
  hand-authored stub.
- `d2-naming-systems.fsh` - one `NamingSystem` per identifier system: a UID and a
  code declaration for each of the organisation unit, option set, data set,
  program, data element, and category option combo
  (`D2OrgUnitIdentifierSystem`, `D2OptionSetCodeIdentifierSystem`,
  `D2DataSetIdentifierSystem`, ...), each
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
  consumer branch without re-reading the questionnaire. The two tracker codes are
  declared ahead of their generators so the terminology does not churn later.

`D2Period` exists because a FHIR `Period` is a pair of instants while a DHIS2
period is a *typed* interval: `202401` is the January instance of the `Monthly`
type, and the type is what makes it comparable and round-trippable. The extension
carries `iso` (string, 1..1), `type` (code, 1..1, required-bound to the period
type ValueSet) and `period` (Period, 0..1), on an `Element` context so the data
layer can hang it off anything. `dhis2w_fhir.period` holds the matching parser:
`parse_period("2024BiW2")` returns the type and the resolved dates for all
twenty-three period types DHIS2 registers, transcribed from `Period.Input.of`
and `DateUnitPeriodTypeParser` in dhis2-core.

## Option sets -> terminology

One file per option set under `ig/input/fsh/terminology/`: a
`D2OS_<UID>_CS` CodeSystem plus a matching ValueSet (naming tokens configurable).
The file name and the id keep the UID's own case (`terminology/Qdm5fPK5Ra9.fsh`,
`d2-os-Qdm5fPK5Ra9-cs`) - FHIR ids permit mixed case, so the id reads straight
back to the DHIS2 object. With `naming.source = "name"` the artifacts take
kebab-cased name slugs instead, and ids
stay within FHIR's 64-character id limit: an over-long option-set name is
truncated and suffixed with the set's UID (noted in the report), which also
keeps bounded ids unique. Every concept
carries **both** DHIS2 identifiers: with the default
`concept_code_source = "id"` the option UID is the concept code and the
DHIS2 option code rides along as a `dhis2-code` concept property; with
`"code"` they swap (the UID becomes a `dhis2-id` property). The code path is
gated by a FHIR `code`-datatype validity check; an option whose code is
missing or invalid falls back to the UID with a note in the report, so
generation is total and never silently drops a concept.

## Data sets and event programs -> Questionnaires

`generate questionnaires` writes `ig/input/fsh/questionnaires/`: one
`<UID>.fsh` per configured target (`[generate.data_sets]` /
`[generate.event_programs]` `include_ids`, absent = none - a data definition is
explicit opt-in, unlike the terminology and registry selections), plus
`data-elements.fsh` (`D2DE_CS`/`_VS`) and `category-option-combos.fsh`
(`D2COC_CS`/`_VS`) over everything those forms reference. The two support pairs live
in the questionnaire sync directory, not `terminology/`, so the option-set target's
cleanup can never delete them.

One Questionnaire is `Usage: #definition`, `id` the bare UID, `url` the IG canonical
plus `/Questionnaire/<uid>`, `subjectType = #Location` (a DHIS2 form is answered for
an organisation unit), `status` and `experimental`, both DHIS2 identifiers (`$DHIS2-DS` /
`$DHIS2-PROGRAM` and their code slots), and `name` composed from the naming tokens
(`D2DS_BfMAe6Itzgt`). Sections become `#group` items; data elements become questions
whose type comes from the DHIS2 `valueType` table, or `#choice` plus an
`answerValueSet` when the element is option-set bound; a compulsory program-stage
element is `required`; a non-default category combo turns the question into a group
with one child per option combo, `linkId` `<deUid>.<cocUid>` - the same key a DHIS2
data value carries. A section holding such a group also carries the standard
`questionnaire-itemControl` extension coded `#gtable`, which is the DHIS2 data-entry
grid stated in FHIR terms.

The service refuses what it cannot map rather than guessing: a configured program
whose live `programType` is not `WITHOUT_REGISTRATION` raises by name (tracker
programs need `Patient` / `EpisodeOfCare`, not a bare Questionnaire), and so does an
event program with more than one stage. Configured UIDs that resolve to nothing, and
data elements no section references, are aggregate notes.

The option-set closure keeps the IG internally consistent: when
`[generate.option_sets] include_ids` narrows the terminology, the option sets the
configured targets bind to are unioned in and listed in a note. An empty include
list already means every option set, so the closure short-circuits and the targets
are not fetched twice.

## Organisation units -> instances

Under `ig/input/fsh/organization/`:

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
- `org-units-level-<n>.fsh` - one file per hierarchy level. Every unit becomes an
  `Organization-<UID>` *and* a `Location-<UID>` - the FHIR pair of legal entity and
  physical place - each carrying both identifier slices, with `partOf` mirroring
  the hierarchy on both sides (omitted for the root or when the parent falls
  outside the selection - noted, never silent). A unit whose `closedDate` has
  passed emits `active = false` / `status = #inactive`. Instances are
  `Usage: #definition`: they are the IG's normative content, not illustrative
  examples. Each one pins `id` to the bare UID, so the compiled files and URLs
  read `Organization-<uid>.json` / `Location-<uid>.json`; the FSH instance names
  keep their `Organization` / `Location` prefixes, which is the namespace that
  keeps the two unique within one file.
- `org-units-terminology.fsh` (only with `terminology = true`) - the whole
  selection as one `D2OU_CS` with `level` / `parent` / `dhis2-code` concept
  properties, for flows that want the hierarchy as codes instead of resources.

Every artifact representing a DHIS2 object exposes both DHIS2 identifiers
wherever FHIR has a slot, and the code slot repeats the UID when the DHIS2 code is
missing or not FHIR-valid - so `dhis2code` can be `1..1` and consumers never
special-case absence. `d2w fhir validate` warns on every organisation unit
without a code, which is what drives those fall-backs out over time. Every
identifier system those slots name is declared by a foundation NamingSystem.
Every generated CodeSystem also points back at its ValueSet through `^valueSet`
and gives each concept property a `<base>/property/<code>` URI so the property has
a defined meaning outside this IG. Every generated definitional resource - the two
profiles, the two extensions, every CodeSystem/ValueSet pair, every Questionnaire -
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

## Translations

DHIS2 holds a translation as a `{locale, property, value}` triple with a
Java-style locale tag. `i18n.py` is the shared leaf over them: `TranslationIn`
is the projection the service wraps the raw dicts into at the fetch boundary,
`normalize_locale` renders the tag as BCP-47 (`pt_BR` -> `pt-BR`), and
`name_translations` selects the `NAME` entries, filters them to
`[generate] locales` (empty = all), deduplicates by locale, and sorts - so an
unchanged instance regenerates an unchanged file. Emission splits by what FHIR
offers on the target: CodeSystem concepts (options and, with
`terminology = true`, organisation units) take `^designation`, while the
option-set CS/VS titles and the `Organization.name` / `Location.name` of every
instance take the standard
`http://hl7.org/fhir/StructureDefinition/translation` extension with its `lang`
and `content` sub-extensions. Only `NAME` is emitted. The deep option-set
validation pass suffixes a finding's name with the subject's first matching
translation; the instance-wide sweep does not fetch translations at all.

## Regeneration contract

Every generated file starts with the header line
`// Generated by d2w fhir generate - do not edit`. A generate run first writes
its target subdirectory, then deletes the header-bearing `.fsh` files in that
subdirectory it did not just produce - hand-authored FSH in the same tree is
never touched, and re-running converges instead of stacking files. Files whose
content already matches are not rewritten, so a no-op regenerate leaves both the
timestamps and `git status` untouched.

## Toolchain performance

Generation is seconds; the IG publisher is twenty minutes. The Sierra Leone demo
(171 option sets, 1332 org units, 2664 instances) breaks down as: 15m27s
generate, of which the template phase alone is 6m36s and spreadsheet generation
1m41s; 1m44s validation over 3014 resources; 1m25s Jekyll; 25s for the final
zip. On a cold machine the package cache dominates the front of that - the
publisher fetches the core packages, `hl7.terminology.r4`, and
`hl7.fhir.uv.extensions.r4` before it does any work, and a container started
with `docker run --rm` throws them away again. Terminology round-trips to
`tx.fhir.org` are the other repeated cost: every code the validator has not seen
is a request. All three phases are serial - SUSHI, then the validator, then
Jekyll - so nothing overlaps.

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
edit loop - SUSHI alone compiles the FSH and tells you whether it is valid, in
seconds rather than in a coffee break. `d2w fhir serve` (roadmap) is the rest of
that loop. `make build` is a release step, not an inner-loop step.

Two upstream quirks worth knowing when reading a publisher run:

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
the R4 primitives (https://hl7.org/fhir/R4/datatypes.html#primitive) in two
passes: an instance-wide sweep over `GET /api/metadata?fields=id,name,code`
(every metadata object's code: invalid codes are errors, per-type duplicates
warn) plus the deep option-set pass previewing `concept_code_source =
"code"` generation (invalid/duplicate option codes are errors, missing codes
warn, spaced-but-valid codes are infos). The sweep passes `defaults=EXCLUDE`, so
DHIS2's auto-generated default category objects stay out of the counts.

The option-pass severities are gated on the effective code source - the
`--code-source` flag, else `concept_code_source`. In id mode `invalid-code`,
`missing-code`, and `duplicate-code` downgrade to `info` with the reason in the
message: generation is not reading those codes yet, so they are a readiness
signal for switching to code mode rather than a defect. The instance-wide sweep
keeps its severities either way. `d2w fhir validate --code-source code` is the
readiness probe for that switch.

The terminal shows errors and warnings; infos roll up per category (`--all` lists
them). Reports are written in three formats - `--report` takes a path *stem*
(default `fhir-validate-report` beside `fhir.toml`) and `--format` a comma list
of `md`, `csv`, `pdf`:

- Markdown, grouped by resource type;
- CSV (`severity,category,resource_type,uid,name,code,message`), for
  spreadsheets and for diffing two runs;
- PDF, with a summary cover page, a clickable table of contents carrying
  per-type severity breakdowns, and one bookmarked section per resource type
  with severity-tinted rows. It is typeset in Noto Sans with a Noto Sans Lao
  fallback (both vendored under `validation/fonts/` with their OFL licence), so
  Lao-script DHIS2 names render instead of dropping to boxes.

Exit 1 on errors makes it a CI gate; `--no-fail` suppresses that. A `fhir.toml`
is not required - validation targets the instance. MCP's `fhir_validate` takes
the same `code_source` and returns the report; writing files stays CLI-only.

## Code layout

Everything lives in the `dhis2w-fhir` workspace member, split into
components that each own their code, their schemas, and their templates.
There is no central models module: a component's pydantic models sit in its
own `schemas.py`.

Flat modules carry what every component shares: `names.py` (slug, FSH
literal, and URI helpers), `i18n.py` (the `TranslationIn` projection, locale
normalisation, and NAME selection), `notes.py` (the one aggregate-note
formatter),
`writer.py` (the `FshArtifact` / `FshBuild` contract every emitter returns,
plus the header-aware sync that writes it), and `config.py` (the `fhir.toml`
document - `IgConfig`, `NamingConfig`, `GenerateConfig`, `FhirProjectConfig`,
`FhirProject` - with discovery, load, and save). `service.py` holds the
shared orchestration and its own `GenerateReport` / `GenerateAllReport`;
`cli.py` / `mcp.py` stay thin over it. `plugin.py` exports the descriptor
referenced by the `dhis2.plugins` entry point; `dhis2w-cli` and `dhis2w-mcp`
depend on the package so `d2w fhir` is present by default.

The components:

- `scaffold/` - the eleven files `d2w fhir init` writes (`InitOptions`,
  `ScaffoldFile`, `ScaffoldReport`).
- `resources/option_sets/` - the CodeSystem/ValueSet pair per option set,
  plus `max_slug_length` (validation previews the same id bound) and the
  `OptionSetIn` / `OptionIn` / `OptionSetSelection` schemas.
- `resources/questionnaires/` - the Questionnaire instance per data set / event
  program plus the two support terminology pairs, with `TargetSelection`, the
  `QuestionnaireSourceIn` / `QuestionnaireSectionIn` / `QuestionnaireItemIn` /
  `CategoryComboIn` / `CategoryOptionComboIn` projections, and `QuestionnaireNaming`
  deriving every name from the `DS` / `PR` / `DE` / `COC` tokens. Item nesting is
  resolved in Python into a flat list of view-models carrying their FSH soft-index
  paths (`item[=].item[+]`), so the template stays a layout, not a recursion.
- `resources/organisation_units/` - split by FHIR resource: `naming.py`
  derives every artifact name and id from the `[generate.naming]` tokens,
  `organization.py` builds the profiles artifact and the Organization
  instances, `location.py` the Location instances (position, boundary
  extension, `partOf`), `terminology.py` the level pair and the optional
  whole-selection pair. Group / group-set emission lands here next.
- `foundation/` - the instance-independent artifacts: the DHIS2 identifier
  aliases and the `D2Period` extension, with `FoundationNaming` deriving their
  names from the prefix token.
- `period/` - the DHIS2 ISO period grammar: `PeriodValue`, the period-type
  catalogue the CodeSystem is generated from, and `parse_period`.
- `validation/` - the two check passes, `report.py` rendering the Markdown and
  CSV, `pdf.py` the PDF, and the finding/report schemas.

`resources/` is reserved for DHIS2 resource domains, which is why
`scaffold/` and `validation/` stay top level.

Dependencies point one way: `config.py` composes the per-component selection
tables (`OptionSetSelection`, `OrganisationUnitSelection`, and the shared
`TargetSelection` behind both data-definition tables), and no component
imports `config.py` at runtime - an emitter receives its `GenerateConfig` as
a parameter and annotates it under `TYPE_CHECKING`. `dhis2w_fhir/__init__.py`
re-exports the whole public surface, so `from dhis2w_fhir import
GenerateConfig` keeps working however the components are arranged.

No FSH, TOML, YAML, or Markdown body is assembled by string concatenation in
Python. Every component ships a `templates/` directory of jinja2 templates
loaded through a `PackageLoader` scoped to that subpackage
(`StrictUndefined`, `trim_blocks`, `lstrip_blocks`, `keep_trailing_newline`
- the same settings `dhis2w-codegen` uses, so control tags never leak blank
lines and rebuilds stay byte-stable). The Python side resolves every
conditional into a pydantic view-model and renders; the templates hold the
layout.

The service opens the version-neutral
`dhis2w_core.client_context.open_client` and maps generated `OptionSet` /
`OrganisationUnit` / `DataSet` / `Program` schemas into the `*In` projections at
the boundary.
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

## Roadmap

- Org unit groups / group sets: DHIS2 classifications beyond the level
  hierarchy (facility type, ownership, ...) mapped to additional
  `Organization.type` codings from group-set CodeSystems (tokens `OUG` /
  `OUGS`, same scheme) - the lao-v1
  inspiration IG already classifies provinces/districts/villages by group
  membership.
- Categories / category options: structurally close to option sets, mapped to
  CodeSystem/ValueSet pairs the same way.
- Tracker programs as Questionnaires: `WITH_REGISTRATION` programs need
  `Patient` + `EpisodeOfCare` alongside the per-stage forms, and the
  `tracker` / `tracker-event` codes are already in `D2FormType_CS` waiting for them.
  Multi-stage event programs land with them.
- `SHORT_NAME` and `DESCRIPTION` translations: `NAME` is emitted today, and the
  other two need a target apiece (`Organization.alias`, `^description`) before
  they can follow. Validation's instance-wide sweep stays translation-free until
  there is a cheaper way to ask `/api/metadata` for them than fetching every
  object's full translation list.
- Data layer: the captured values behind the generated forms - a data value set as
  a `QuestionnaireResponse` answering the data set's `Questionnaire` on the same
  `linkId`s (including the `<deUid>.<cocUid>` ones the disaggregated groups define),
  its period through `D2Period` and its org unit through `subject`, with
  `MeasureReport` as the later lossy summary projection over the same data; events
  -> `QuestionnaireResponse`, tracker -> `Patient` + `EpisodeOfCare` (see
  `docs/project/fhir-data-mapping.md` when committed).
- Curated real-world `Usage: #example` instances per profile - especially once
  the data layer lands, where a worked `QuestionnaireResponse` says more than a
  profile ever does.
- Instance-scoped project identity: `d2w fhir init --data-set <uid>` / `--event
  <uid>` seed the target lists offline today; deriving the IG identity (id,
  canonical, title) from the instance and its named targets on first init needs a
  live call, which `init` deliberately does not make yet. `fhir build` may still cut
  per-form deployables out of the instance project - a packaging choice, not a
  namespace choice, because the registry (org units), terminology (option sets), and
  foundation artifacts stay instance-level with instance-linked ids whichever form
  uses them.
- `d2w fhir ui` / `browser`: a tree-widget explorer over the generated IG and
  hierarchy, modelled on the security plugin's offline d3 sharing explorer.
- `d2w fhir serve`: one verb, two modes (FastAPI per repo convention, read-only
  endpoints with a generated `CapabilityStatement`). The default serves the
  compiled IG resources out of `fsh-generated`; `--live` translates on the fly
  from the instance the project points at, answering option sets and the other
  supported resources without a generate-and-compile round trip. Same routes,
  same shapes - the flag only decides where a resource comes from, which is also
  what makes it the fast half of the edit loop.
- `d2w fhir push`: outbound delivery of the generated resources into a real FHIR
  system - transaction bundles against a target server, with the identifier
  systems above as the reconciliation key.
- `d2w fhir build`: pack the IG into a real deployable package to build
  middleware on. Buildpack targets are python (pydantic + FastAPI) and rust
  (axum + utoipa), both codegenning their types from the IG's
  StructureDefinitions. Format conversion (DHIS2 wire <-> FHIR) is defined once
  at a higher level - StructureMap resources in the IG, or a language-neutral
  mapping manifest emitted by the generator - and each buildpack generates its
  conversion layer from that shared source, never hand-written per language.

### Terminology source candidates (DHIS2 group + item relationships)

What else in DHIS2 is shaped like terminology, and which naming token each
lands on. The full Group/GroupSet pattern repeats five times, and every GroupSet
is also an analytics dimension - which is why these are worth emitting as
terminology rather than as ad-hoc codings.

| Pattern | Chain | Tokens |
| --- | --- | --- |
| Group / GroupSet | `organisationUnitGroupSet` -> `organisationUnitGroups` -> org units | `OUG` / `OUGS` |
| Group / GroupSet | `dataElementGroupSet` -> `dataElementGroups` -> data elements | `DEG` / `DEGS` |
| Group / GroupSet | `indicatorGroupSet` -> `indicatorGroups` -> indicators | `INDG` / `INDGS` |
| Group / GroupSet | `categoryOptionGroupSet` -> `categoryOptionGroups` -> category options | `COG` / `COGS` |
| Group / GroupSet | `optionGroupSet` -> `optionGroups` -> options (classifies options across option sets) | `OG` / `OGS` |
| Group only | `programIndicatorGroup`, `validationRuleGroup`, `predictorGroup` | `PIG`, `VRG`, `PRED` |
| Category model | `category` -> `categoryOptions`; `categoryCombo` -> `categories`; `categoryOptionCombo` -> `categoryOptions` | `CAT`, `CO`, `CC`, `COC`, `AOC` |
| Adjacent | `legendSet` -> `legends` (threshold classifications; a CodeSystem with range properties) | `LS` |
| Adjacent | `organisationUnitLevel` - already emitted | `OU` |

`userGroup` is excluded: it is membership and ACL, not terminology.

The category model is first priority - the data layer's `$DHIS2-CAT` /
`$DHIS2-COC` stratifier codes depend on it. The full token registry these draw
from is in the [FHIR IG guide](../guides/fhir-ig.md).
