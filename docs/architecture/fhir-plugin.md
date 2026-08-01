# FHIR plugin

`d2w fhir` turns DHIS2 metadata into a FHIR Implementation Guide source tree:
a SUSHI project whose FSH (FHIR Shorthand) files are generated from
`/api/optionSets` and `/api/organisationUnits`.

```
d2w fhir init [DIRECTORY]           Scaffold a dockerized SUSHI IG project
d2w fhir generate foundation        Identifier aliases + the D2Period extension
d2w fhir generate option-sets       Option sets -> CodeSystem/ValueSet pairs
d2w fhir generate org-units         Org units -> Organization/Location instances
d2w fhir generate all               All three targets in one run
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
Makefile                    setup / upgrade / generate / sushi / build via docker
Dockerfile                  ghcr.io/fhir/ig-publisher-localdev + fsh-sushi
ig/sushi-config.yaml        SUSHI IG identity (id, canonical, publisher)
ig/ig.ini                   IG publisher entry point (fhir2.base.template)
ig/fsh.ini                  Raises the publisher's internal SUSHI timeout to 900s
ig/input/fsh/aliases.fsh    Hand-authored alias stub (never regenerated)
ig/input/pagecontent/index.md
ig/input/ignoreWarnings.txt
```

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
concept_code_source = "uid"         # "uid" or "code"

[generate.naming]
prefix = "D2"                       # "" drops it; profiles keep a D2 token
option_set = "OS"                   # e.g. "OptionSet"; "" drops the token
organisation_unit = "OU"            # e.g. "OrgUnit" -> D2OrgUnitLevelCS

[generate.option_sets]
include_ids = []                    # UIDs; absent or empty = all

[generate.organisation_units]
root = ""
max_level = 0
terminology = false
```

`identifier_system_base` is live: `generate foundation` writes it into
`foundation/d2-aliases.fsh` as the `$DHIS2-*` aliases, and the option-set
terminology uses it for its `^identifier` business identifiers.

The full configuration reference, with the uid-first-then-code workflow and the
canonical naming-token registry, is in the
[FHIR IG guide](../guides/fhir-ig.md).

Artifact names concatenate the pascal naming tokens
(`D2` + `OS` + `BirthType` + `CS` - short tokens read by context); ids join
the kebab of each non-empty token (`d2-os-birth-type-cs`), so renaming or
dropping a token reshapes the whole IG consistently. The two profile names always carry
a token (default `D2`) because FSH cannot name a profile identically to its
parent core resource.

## Foundation -> aliases and D2Period

`generate foundation` writes `ig/input/fsh/foundation/`, the part of the IG that
depends on `fhir.toml` alone and never opens a client:

- `d2-aliases.fsh` - `$DHIS2-OU` / `$DHIS2-OU-CODE`, built from
  `identifier_system_base`. Generating these rather than scaffolding them is what
  frees `ig/input/fsh/aliases.fsh` to be a pure hand-authored stub.
- `d2-period.fsh` - the `D2Period` extension plus `D2PeriodTypeCS`/`VS`.

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
`D2OS<Name>CS` CodeSystem plus a matching ValueSet (naming tokens
configurable). Artifact ids
stay within FHIR's 64-character id limit: an over-long option-set name is
truncated and suffixed with the set's UID (noted in the report), which also
keeps bounded ids unique. Every concept
carries **both** DHIS2 identifiers: with the default
`concept_code_source = "uid"` the option UID is the concept code and the
DHIS2 option code rides along as a `dhis2-code` concept property; with
`"code"` they swap (the UID becomes a `dhis2-uid` property). The code path is
gated by a FHIR `code`-datatype validity check; an option whose code is
missing or invalid falls back to the UID with a note in the report, so
generation is total and never silently drops a concept.

## Organisation units -> instances

Under `ig/input/fsh/organization/`:

- `profiles.fsh` - `D2Organization` and `D2Location`. Both are `^status = #active`
  and both slice `identifier` on `system` into `dhis2uid 1..1` and
  `dhis2code 1..1`. `Organization.type` binds to the level ValueSet
  **extensible**, not required: an IG that adds group-set codings later must not
  be made non-conformant by the binding.
- `org-unit-levels.fsh` - `D2OULevelCS`/`VS` covering the levels observed in the
  selection.
- `org-units-level-<n>.fsh` - one file per hierarchy level. Every unit becomes an
  `Organization<UID>` *and* a `Location<UID>` - the FHIR pair of legal entity and
  physical place - each carrying both identifier slices, with `partOf` mirroring
  the hierarchy on both sides (omitted for the root or when the parent falls
  outside the selection - noted, never silent). A unit whose `closedDate` has
  passed emits `active = false` / `status = #inactive`. Instances are
  `Usage: #definition`: they are the IG's normative content, not illustrative
  examples.
- `org-units-terminology.fsh` (only with `terminology = true`) - the whole
  selection as one `D2OUCS` with `level` / `parent` / `dhis2-code` concept
  properties, for flows that want the hierarchy as codes instead of resources.

Every artifact representing a DHIS2 object exposes both DHIS2 identifiers
wherever FHIR has a slot, and the code slot repeats the UID when the DHIS2 code is
missing or not FHIR-valid - so `dhis2code` can be `1..1` and consumers never
special-case absence. `d2w fhir validate` warns on every organisation unit
without a code, which is what drives those fall-backs out over time. Every
generated CodeSystem also points back at its ValueSet through `^valueSet`.

The tree is fetched with a 500-per-page loop ordered by `path:asc` (stable
output), filtered by `[generate.organisation_units]` `root` (DHIS2 `path:like`) and
`max_level`.

## Regeneration contract

Every generated file starts with the header line
`// Generated by d2w fhir generate - do not edit`. A generate run first
deletes only header-bearing `.fsh` files in its target subdirectory, then
writes the new set - hand-authored FSH in the same tree is never touched, and
re-running converges instead of stacking files.

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
`--code-source` flag, else `concept_code_source`. In uid mode `invalid-code`,
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
literal, and URI helpers), `notes.py` (the one aggregate-note formatter),
`writer.py` (the `FshArtifact` / `FshBuild` contract every emitter returns,
plus the header-aware sync that writes it), and `config.py` (the `fhir.toml`
document - `IgConfig`, `NamingConfig`, `GenerateConfig`, `FhirProjectConfig`,
`FhirProject` - with discovery, load, and save). `service.py` holds the
shared orchestration and its own `GenerateReport` / `GenerateAllReport`;
`cli.py` / `mcp.py` stay thin over it. `plugin.py` exports the descriptor
referenced by the `dhis2.plugins` entry point; `dhis2w-cli` and `dhis2w-mcp`
depend on the package so `d2w fhir` is present by default.

The components:

- `scaffold/` - the ten files `d2w fhir init` writes (`InitOptions`,
  `ScaffoldFile`, `ScaffoldReport`).
- `resources/option_sets/` - the CodeSystem/ValueSet pair per option set,
  plus `max_slug_length` (validation previews the same id bound) and the
  `OptionSetIn` / `OptionIn` / `OptionSetSelection` schemas.
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
tables (`OptionSetSelection`, `OrganisationUnitSelection`), and no component
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
`OrganisationUnit` schemas into the `*In` projections at the boundary.
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
- Questionnaire generation from programs / program stages (valueType mapping
  tables exist in the lao-v1 generator).
- Translations as FHIR designations / translation extensions.
- Data layer: dataset -> `Questionnaire` + `MeasureReport` (summary), events ->
  `QuestionnaireResponse`, tracker -> `Patient` + `EpisodeOfCare` (see
  `docs/project/fhir-data-mapping.md` when committed).
- Curated real-world `Usage: #example` instances per profile - especially once
  the data layer lands, where a worked `QuestionnaireResponse` says more than a
  profile ever does.
- `d2w fhir ui` / `browser`: a tree-widget explorer over the generated IG and
  hierarchy, modelled on the security plugin's offline d3 sharing explorer.
- `d2w fhir serve`: serve the generated IG as a FHIR service (FastAPI per repo
  convention) - read-only endpoints over the generated resources with a
  generated `CapabilityStatement`.
- `d2w fhir proxy`: a live translation service in front of a DHIS2 instance -
  option sets and other supported resources answered as FHIR on the fly from the
  live instance instead of from pre-generated files.
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
