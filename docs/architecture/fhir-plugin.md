# FHIR plugin

`d2w fhir` turns DHIS2 metadata into a FHIR Implementation Guide source tree:
a SUSHI project whose FSH (FHIR Shorthand) files are generated from
`/api/optionSets` and `/api/organisationUnits`.

```
d2w fhir init [DIRECTORY]           Scaffold a dockerized SUSHI IG project
d2w fhir generate option-sets       Option sets -> CodeSystem/ValueSet pairs
d2w fhir generate org-units         Org units -> Organization/Location instances
d2w fhir generate all               Both targets in one run
d2w fhir validate                   FHIR-safety of the instance's codes (exit 1 on errors; --no-fail)
```

The plugin ships as its own workspace member, `dhis2w-fhir`, and mounts
through the `dhis2.plugins` entry point - the same mechanism third-party
plugins use. It is version-neutral: the wire client auto-detects the DHIS2
major on connect, so one package serves v41/v42/v43 with no per-tree copies.

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
ig/input/fsh/aliases.fsh    $DHIS2-OU / $DHIS2-OU-CODE / $V2-0203 aliases
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
org_unit = "OU"                     # e.g. "OrgUnit" -> D2OrgUnitLevelCS

[generate.option_sets]
include_ids = []                    # UIDs; absent or empty = all

[generate.org_units]
root = ""
max_level = 0
terminology = false
```

Artifact names concatenate the pascal naming tokens
(`D2` + `OS` + `BirthType` + `CS` - short tokens read by context); ids join
the kebab of each non-empty token (`d2-os-birth-type-cs`), so renaming or
dropping a token reshapes the whole IG consistently. The two profile names always carry
a token (default `D2`) because FSH cannot name a profile identically to its
parent core resource.

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

- `profiles.fsh` - `DHIS2Organization` (identifier slices `dhis2uid` /
  `dhis2code` discriminated on `system`, `partOf only
  Reference(DHIS2Organization)`) and `DHIS2Location`.
- `org-unit-levels.fsh` - `DHIS2OrgUnitLevelCS`/`VS` covering the levels
  observed in the selection.
- `org-units-level-<n>.fsh` - one file per hierarchy level. Each unit is an
  `Organization<UID>` instance carrying the UID/code identifier slices, its
  level as `type`, telecom/contact when present, and `partOf` referencing the
  parent instance (omitted for the root or when the parent falls outside the
  selection - noted, never silent). Units whose geometry is a GeoJSON Point
  also get a `Location<UID>` instance; GeoJSON stores `[longitude, latitude]`,
  so the mapper swaps into `position.latitude` / `position.longitude`.
- `org-units-terminology.fsh` (only with `terminology = true`) - the whole
  selection as one `DHIS2OrgUnitCS` with `level` / `parent` / `dhis2-code`
  concept properties, for flows that want the hierarchy as codes instead of
  resources.

The tree is fetched with a 500-per-page loop ordered by `path:asc` (stable
output), filtered by `[generate.org_units]` `root` (DHIS2 `path:like`) and
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
warn, spaced-but-valid codes are infos). The terminal shows errors and
warnings; infos roll up per category (`--all` lists them). A Markdown report
grouped by resource type is always written (default
`fhir-validate-report.md` beside `fhir.toml`, `--report` to move it). Exit 1
on errors makes it a CI gate; `--no-fail` suppresses that. A `fhir.toml` is
not required - validation targets the instance.

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
- `validation/` - the two check passes, `report.py` rendering the Markdown,
  and the finding/report schemas.

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
outside concave boundaries. Every unit whose geometry parses also carries
the compact GeoJSON into `Location` through the standard
`location-boundary-geojson` extension.

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
