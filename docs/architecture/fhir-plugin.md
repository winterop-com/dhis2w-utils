# FHIR plugin

`d2w fhir` turns DHIS2 metadata into a FHIR Implementation Guide source tree:
a SUSHI project whose FSH (FHIR Shorthand) files are generated from
`/api/optionSets` and `/api/organisationUnits`.

```
d2w fhir init [DIRECTORY]           Scaffold a dockerized SUSHI IG project
d2w fhir generate option-sets       Option sets -> CodeSystem/ValueSet pairs
d2w fhir generate org-units         Org units -> Organization/Location instances
d2w fhir generate all               Both targets in one run
d2w fhir validate                   FHIR-safety of the instance's codes/names (exit 1 on errors)
```

The plugin ships as its own workspace member, `dhis2w-fhir`, and mounts
through the `dhis2.plugins` entry point - the same mechanism third-party
plugins use. It is version-neutral: the wire client auto-detects the DHIS2
major on connect, so one package serves v41/v42/v43 with no per-tree copies.

MCP mirrors the same surface: `fhir_init`, `fhir_generate_option_sets`,
`fhir_generate_org_units`, and the read-only `fhir_validate`
(`readOnlyHint`). Each generate tool takes a `project_directory`
argument because a long-lived MCP server's working directory is unrelated to
the IG project. The init/generate tools write local files, so they are classified as
write tools and refused under `DHIS2_MCP_READONLY=1`; `fhir_validate` stays
available there.

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

`d2w fhir validate` (MCP: `fhir_validate`) previews FHIR-safety without
writing anything, against the R4 primitives
(https://hl7.org/fhir/R4/datatypes.html#primitive): invalid codes (edge or
doubled whitespace - the R4 `code` prose constraint) and duplicate codes
within a set are errors; missing codes (UID fallback) and generated FSH names
past the 255-character `cnl-0` bound are warnings; spaced-but-valid codes,
id truncation, and slug collisions are infos. The CLI exits 1 when errors
exist, so it slots into CI as a preflight for `concept_code_source = "code"`.
A `fhir.toml` is not required - validation targets the instance.

## Code layout

Everything lives in the `dhis2w-fhir` workspace member: pure FSH emission
and config (`models`, `names`, `terminology`, `organization`, `scaffold`,
`writer`, `validation`, `config`), the shared `service.py`, and the thin
`cli.py` / `mcp.py` surfaces. `plugin.py` exports the descriptor referenced
by the `dhis2.plugins` entry point; `dhis2w-cli` and `dhis2w-mcp` depend on
the package so `d2w fhir` is present by default. The service opens the
version-neutral `dhis2w_core.client_context.open_client` and maps generated
`OptionSet` / `OrganisationUnit` schemas into the reduced input models at
the boundary.

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
