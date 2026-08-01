# FHIR IG generation with `d2w fhir`

`d2w fhir` turns a DHIS2 instance's metadata into a FHIR Implementation Guide
source tree: a [SUSHI](https://fshschool.org/docs/sushi/) project whose FSH
(FHIR Shorthand) files are generated from the DHIS2 API and compiled to FHIR
resources by the IG publisher.

You get three things:

- **`d2w fhir init`** scaffolds a complete, dockerized SUSHI project - config,
  `sushi-config.yaml`, a Makefile, and a Dockerfile carrying SUSHI plus the IG
  publisher. Nothing else to install but Docker.
- **`d2w fhir generate`** reads DHIS2 metadata and writes FSH into the project.
  Re-running converges: generated files are replaced, hand-authored FSH beside
  them is never touched.
- **`d2w fhir validate`** checks the instance's codes for FHIR-safety before you
  generate anything, and writes a report in Markdown, CSV, and PDF.

The plugin is version-neutral - the wire client auto-detects the DHIS2 major on
connect, so one package serves v41, v42, and v43.

## Quickstart

```bash
# 1. Scaffold a project.
d2w fhir init my-ig --id org.example.dhis2 --canonical https://example.org/fhir --publisher "Example Org"
cd my-ig

# 2. Point it at a DHIS2 instance. Either set `profile` in fhir.toml, or use the
#    environment / flag - see "Which DHIS2 instance" below.
d2w profile add demo --url https://play.im.dhis2.org/stable-2-42-1 --username admin --password district

# 3. Check the instance's codes before generating anything.
d2w fhir validate

# 4. Generate the FSH.
d2w fhir generate all

# 5. Compile it. `make setup` builds the docker image once; `make sushi` runs SUSHI;
#    `make build` runs the full IG publisher.
make setup
make sushi
make build
```

The generated site lands in `ig/output/`. `make clean` removes build output;
`make clean-all` also drops the package cache.

## Which DHIS2 instance

Generation reads its config from the nearest `fhir.toml`, discovered by walking
up from the working directory - the same idiom as `.dhis2/profiles.toml`. The
profile it connects with is resolved in this order, first match wins:

1. the `DHIS2_PROFILE` environment variable,
2. the `profile` key in `fhir.toml`,
3. the default profile from your `profiles.toml`.

Credentials never live in `fhir.toml`. It is committed project config: it names
a profile, and the profile store holds the secret.

`d2w fhir validate` does not need a `fhir.toml` at all - it targets an instance,
not a project. Run it anywhere.

## `fhir.toml` reference

`d2w fhir init` writes two files: a minimal `fhir.toml` with just the IG identity,
and `fhir.toml.example` documenting every option with its default. Copy what you
need from the example into `fhir.toml`; anything you omit keeps its default.

### Top level

```toml
profile = "myserver"    # optional: which d2w profile to read metadata from
```

### `[ig]` - SUSHI identity

Straight through to `sushi-config.yaml`. All five keys are required.

```toml
[ig]
id = "org.example.dhis2"                   # IG package id
canonical = "https://example.org/fhir"     # canonical base URL; trailing slash stripped
name = "OrgExampleDhis2"                   # SUSHI name (computational, no spaces)
title = "Example DHIS2 Implementation Guide"
publisher = "Example Organisation"
```

### `[generate]`

```toml
[generate]
identifier_system_base = "http://dhis2.org/fhir"
concept_code_source = "uid"
locales = []
```

**`identifier_system_base`** is the base URI for the DHIS2 identifier systems.
It is live, not decorative: `d2w fhir generate foundation` writes it into
`foundation/d2-aliases.fsh` as the `$DHIS2-OU` / `$DHIS2-OU-CODE` aliases, and
the option-set terminology uses it for the business identifiers on each
CodeSystem/ValueSet. Change it and regenerate, and every reference follows.
It is a local convention, not a registered FHIR NamingSystem.

**`concept_code_source`** picks what a terminology concept's code is:

- `"uid"` (default) - the DHIS2 UID is the concept code, and the DHIS2 code
  rides along as a `dhis2-code` concept property.
- `"code"` - they swap: the DHIS2 code is the concept code (when it is a valid
  FHIR `code`), and the UID rides along as a `dhis2-uid` property.

**The uid-first, then-code workflow.** Start on `"uid"`. UIDs are unique,
stable, and always FHIR-valid, so generation cannot fail on them - you get a
compiling IG on day one, whatever state the instance's codes are in. DHIS2 codes
are the friendlier concept codes, but they are optional in DHIS2, frequently
absent, and frequently not valid FHIR codes (leading spaces, doubled spaces,
tabs). Switching before the instance is clean produces silent UID fall-backs.

Use validate as the readiness probe:

```bash
d2w fhir validate --code-source code
```

That reports what switching would cost right now: every option whose code is
missing, invalid, or duplicated inside its set, at error/warning severity. Fix
those in DHIS2, re-run until the option findings are clean, then set
`concept_code_source = "code"` and regenerate. In the meantime, running plain
`d2w fhir validate` in uid mode reports the same findings as `info` - they are a
readiness signal, not a defect, because generation is not reading those codes yet.

**`locales`** picks which translation locales reach the generated artifacts. It
takes BCP-47 or DHIS2-style tags (`"lo"`, `"km"`, `"pt_BR"`) and an empty list -
the default - emits every locale found on the instance. See
[Locales and translations](#locales-and-translations).

### `[generate.naming]`

```toml
[generate.naming]
source = "uid"
prefix = "D2"
option_set = "OS"
organisation_unit = "OU"
```

**`source`** decides what file names, FHIR ids, and FSH names derive from:

- `"uid"` (default) - stable, collision-free, script-agnostic. DHIS2 names are
  often non-latin or non-unique, so uid-sourced ids never truncate or collide.
  You get `d2-os-qdm5fpk5ra9-cs`.
- `"name"` - human-readable slugs (`d2-os-birth-type-cs`), truncated with a UID
  suffix when a name overflows FHIR's 64-character id limit and disambiguated
  the same way when two names collide. Both are reported as notes.

**The tokens** compose artifact names by concatenation and ids by kebab-joining
each non-empty token. With the defaults, an option set becomes
`D2` + `OS` + `BirthType` + `CS` = `D2OSBirthTypeCS`, id `d2-os-birth-type-cs`.
Rename or drop a token and the whole IG follows consistently.

| Token | Default | Notes |
| --- | --- | --- |
| `prefix` | `D2` | May be empty to drop it entirely. |
| `option_set` | `OS` | May be empty. Try `OptionSet` for a verbose IG. |
| `organisation_unit` | `OU` | Must stay non-empty. `OrgUnit` gives `D2OrgUnitLevelCS`. |

**The empty-prefix caveat.** Setting `prefix = ""` drops the token from
terminology names (`OULevelCS`, id `ou-level-cs`), but the two organisation-unit
profiles and the `D2Period` extension keep a `D2` token anyway. FSH cannot name a
profile identically to its parent core resource, nor an extension identically to
a core datatype: `Profile: Organization` and `Extension: Period` are both
illegal. Those definitions fall back to `D2` rather than fail.

#### The canonical token registry

Keys are added to `[generate.naming]` as each generator lands, with these
defaults. Only `option_set` and `organisation_unit` exist in code today; the rest
are the decided defaults for the generators still to come. Every token composes
as `{prefix}{token}`, and ids derive from the kebab of prefix plus token
(`d2-deg-<uid>-cs`).

| Token | DHIS2 object | Token | DHIS2 object |
| --- | --- | --- | --- |
| `OS` | option set | `CO` | category option |
| `OG` | option group | `CC` | category combo |
| `OGS` | option group set | `COC` | category option combo |
| `OU` | organisation unit | `AOC` | attribute option combo |
| `OUG` | organisation unit group | `COG` | category option group |
| `OUGS` | organisation unit group set | `COGS` | category option group set |
| `DE` | data element | `IND` | indicator |
| `DEG` | data element group | `INDG` | indicator group |
| `DEGS` | data element group set | `INDGS` | indicator group set |
| `DS` | data set | `PR` | program |
| `CAT` | category | `PS` | program stage |
| `PI` | program indicator | `TET` | tracked entity type |
| `PIG` | program indicator group | `TEI` | tracked entity |
| `VR` | validation rule | `TEA` | tracked entity attribute |
| `VRG` | validation rule group | `PRED` | predictor |
| `LS` | legend set | | |

`D2Period` is a fixed name: it takes the prefix and no token of its own.

### `[generate.option_sets]`

```toml
[generate.option_sets]
include_ids = []        # optionSet UIDs to include; absent or empty means all
```

UIDs only - DHIS2 option-set names are not unique. An entry matching nothing is
reported as a note rather than silently ignored.

### `[generate.organisation_units]`

```toml
[generate.organisation_units]
root = ""               # organisation unit root UID; empty means the entire tree
max_level = 0           # 0 means no level cap
terminology = false     # also emit the org-unit CodeSystem/ValueSet
```

`root` filters with DHIS2 `path:like`, so it selects the subtree beneath (and
including) that unit. `max_level` caps the depth. Both are applied server-side.

`terminology = true` additionally emits the whole selection as one
CodeSystem/ValueSet with `level`, `parent`, and `dhis2-code` concept properties -
for flows that want the hierarchy as codes rather than as resources.

## Generate targets

```
d2w fhir generate foundation     Identifier aliases + the D2Period extension
d2w fhir generate option-sets    Option sets -> CodeSystem/ValueSet pairs
d2w fhir generate org-units      Org units -> Organization/Location instances
d2w fhir generate all            All three, in that order
```

Each target owns one subdirectory of `ig/input/fsh/` and syncs it: writes what
changed, leaves what did not, deletes generated files that no longer belong.

### `foundation`

Writes `foundation/`, the part of the IG that depends on `fhir.toml` alone and
never touches DHIS2:

- **`d2-aliases.fsh`** - the `$DHIS2-OU` and `$DHIS2-OU-CODE` aliases, built from
  `identifier_system_base`. The instance files reference these, so this target is
  a prerequisite for a compiling IG.
- **`d2-period.fsh`** - the `D2Period` extension plus its terminology.

### The D2Period extension

DHIS2 reporting periods have no FHIR equivalent: a FHIR `Period` is a pair of
instants, while a DHIS2 period is a *typed* interval - `202401` is not merely
1-31 January, it is the January instance of the `Monthly` period type, and the
type is what makes it comparable, aggregatable, and round-trippable.

`D2Period` carries all three facts:

| Sub-extension | Type | Cardinality | Meaning |
| --- | --- | --- | --- |
| `iso` | `string` | 1..1 | The DHIS2 ISO period identifier, e.g. `202401` |
| `type` | `code` | 1..1 | The period type, bound (required) to `D2PeriodTypeVS` |
| `period` | `Period` | 0..1 | The date range the identifier resolves to |

Its context is `Element`, so it attaches anywhere - the data layer will hang it
off `MeasureReport`, `QuestionnaireResponse`, and `Observation` alike.

The `D2PeriodTypeCS` CodeSystem publishes every period type DHIS2 registers,
each displayed with its ISO format: `Daily (yyyyMMdd)`, `Monthly (yyyyMM)`,
`FinancialApril (yyyyApril)`, and so on through the weekly variants, the
bi-weekly and bi-monthly types, the November-anchored financial types, and the
rest of the twenty-three.

The matching parser lives in `dhis2w_fhir.period`:

```python
from dhis2w_fhir.period import parse_period

parse_period("2024BiW2")
# PeriodValue(iso='2024BiW2', period_type='BiWeekly',
#             start_date=date(2024, 1, 15), end_date=date(2024, 1, 28))
```

### Identifiers

Every FHIR artifact representing a DHIS2 object exposes **both** DHIS2
identifiers - the UID and the code - wherever FHIR gives it a slot. This is the
standing rule for every generator, present and future (Questionnaire, Patient,
EpisodeOfCare, MeasureReport identifiers will follow it).

- **Instances** carry identifier slices discriminated on `system`:
  `{base}/id/<kind>` holds the UID and `{base}/id/<kind>-code` holds the code.
  Both slices are always emitted, on the Organization and on the Location alike.
- **Terminology concepts** carry the complementary identifier as a concept
  property: in uid mode every concept gets `dhis2-code`, in code mode every
  concept gets `dhis2-uid`. No concept goes without the pair.
- **Option-set CodeSystems and ValueSets** carry the source set's own pair as
  `^identifier` business identifiers under `{base}/id/option-set` and
  `{base}/id/option-set-code`.

**The code slot falls back to the UID.** DHIS2 codes are optional, and plenty of
instances have units without one. Rather than emit a half-populated identifier,
the code slot repeats the UID whenever the DHIS2 code is missing or is not a
valid FHIR code. That keeps the profiles conformant (`dhis2code` is `1..1`) and
keeps consumers from special-casing absence. It is a "for now" state, owned by
the instance team: `d2w fhir validate` warns on every organisation unit without a
code precisely so those fall-backs get replaced with real codes over time.

### `option-sets`

One file per option set under `terminology/`: a CodeSystem plus its ValueSet,
the CodeSystem pointing back at the ValueSet through `^valueSet`.

Concept codes are unique within a set by construction. Options are ordered by
`sortOrder`; each one asks for a code, and if that code is already taken the
option falls back to its UID, aggregated into one note. A CodeSystem that
repeats a concept code will not compile, so this is enforced rather than warned
about.

### `org-units`

Under `organization/`:

- **`profiles.fsh`** - the `D2Organization` and `D2Location` profiles.
- **`org-unit-levels.fsh`** - the level CodeSystem/ValueSet backing
  `Organization.type`, covering the levels actually present in the selection.
- **`org-units-level-<n>.fsh`** - one file per hierarchy level. Every unit
  becomes an `Organization` (the legal entity) *and* a `Location` (the physical
  place), with `partOf` mirroring the DHIS2 hierarchy on both. A unit whose
  parent falls outside the selection omits `partOf` and is reported, never
  dropped silently. A unit whose `closedDate` has passed is emitted with
  `active = false` and `status = #inactive`.
- **`org-units-terminology.fsh`** - only with `terminology = true`.

**Geometry is embedded losslessly.** Whatever shape DHIS2 holds, the full GeoJSON
travels into the Location through the standard `location-boundary-geojson`
extension, wrapped in a GeoJSON `Feature` whose properties carry the unit's UID,
name, and level. What varies is only whether a *position* can also be derived:

| DHIS2 geometry | `Location.position` | Boundary extension |
| --- | --- | --- |
| `Point` | the coordinates | yes |
| `Polygon`, `MultiPolygon` | the area-weighted (shoelace) centroid of the largest outer ring | yes |
| any other valid type | none | yes |
| unusable or empty coordinates | none | none |

The centroid is a true shoelace centroid, not a bounding-box midpoint - the
midpoint of a concave district's bounding box frequently falls outside the
district.

The first two rows are nominal behaviour, not warnings: the run's `positions` and
`boundaries` counters say how many units took them. The last two each raise one
aggregate note per run, because something a consumer might expect is genuinely
absent.

## Locales and translations

DHIS2 carries a translation as a `{locale, property, value}` triple, where the
locale is a Java-style tag (`lo`, `km`, `pt_BR`) and the property names what is
translated (`NAME`, `SHORT_NAME`, `DESCRIPTION`). Generation fetches those
triples alongside the objects and lands them in the FHIR artifacts.

```toml
[generate]
locales = []            # BCP-47 or DHIS2-style tags; empty means all found on the instance
```

Tags are normalised to BCP-47 before anything compares or emits them - `pt_BR`
becomes `pt-BR`, `LO` becomes `lo` - so `fhir.toml` may spell them either way.
Within one artifact, translations come out sorted by locale, and a locale that
appears twice keeps its first value; regenerating an unchanged instance produces
an unchanged file.

**What each artifact gets.** FHIR has two places for a translated string, and
which one applies is a property of the target, not a choice:

| Target | Emitted as |
| --- | --- |
| Option CodeSystem concepts | `^designation[+].language` / `^designation[=].value` |
| Option-set CodeSystem and ValueSet titles | `^title.extension` translation extension |
| `Organization.name`, `Location.name` | `name.extension` translation extension |
| Org-unit CodeSystem concepts (`terminology = true`) | `^designation` |

The translation extension is the standard
`http://hl7.org/fhir/StructureDefinition/translation`, with its `lang` and
`content` sub-extensions. Designations are terminology's own mechanism and need
no extension.

**Only `NAME` translations are emitted.** `SHORT_NAME` and `DESCRIPTION`
translations are fetched and ignored; carrying them is roadmap work.

**`fhir validate` does not sweep translations.** The deep option-set pass reads
them, so an option or option-set finding shows the local-language name after the
primary one (`Natural Birth [in Birth type] / ການເກີດແບບທຳມະຊາດ`). The
instance-wide sweep does not: asking `/api/metadata` for every object's
translations is far too heavy for a check that only looks at codes.

## Validation

```
d2w fhir validate [--code-source uid|code] [--report STEM] [--format md,csv,pdf] [--all] [--no-fail]
```

Two passes, one finding shape:

- an **instance-wide sweep** over `GET /api/metadata?fields=id,name,code`
  (`defaults=EXCLUDE`, so DHIS2's auto-generated default category objects stay
  out of it). Every metadata object's code is checked against the R4 `code`
  datatype: invalid codes are errors, per-type duplicates warn. Organisation
  units additionally warn when they carry no code at all.
- a **deep option-set pass** previewing exactly what code-mode generation would
  do, over the same projections the emitter consumes.

### Severity and `--code-source`

The option-pass findings are gated on the effective code source - the
`--code-source` flag when given, otherwise `concept_code_source` from
`fhir.toml`. In `code` mode, `invalid-code`, `missing-code`, and `duplicate-code`
carry their real severities. In `uid` mode they are downgraded to `info` and
their message says so, because generation is not reading those codes yet. The
instance-wide sweep keeps its severities either way.

### Report files

`--report` takes a path **stem** without an extension - by default
`fhir-validate-report` beside `fhir.toml`, or in the working directory when there
is no project. `--format` takes a comma list of `md`, `csv`, `pdf`; all three are
written by default, and each written path is echoed.

- **`.md`** - findings grouped under one section per resource type.
- **`.csv`** - one row per finding, columns
  `severity,category,resource_type,uid,name,code,message`. For spreadsheets and
  for diffing two runs.
- **`.pdf`** - a cover page with the summary counts, a clickable table of
  contents with per-type breakdowns, then one bookmarked section per resource
  type with severity-tinted rows. Typeset in Noto Sans with a Noto Sans Lao
  fallback, so Lao-script DHIS2 names render rather than dropping to boxes.

### Exit codes

Exit 1 when there are errors, which makes it a CI gate. `--no-fail` exits 0
regardless. `--all` lists info findings individually instead of rolling them up
per category.

MCP exposes the same check as the read-only `fhir_validate` tool, taking
`profile`, `project_directory`, and `code_source`. It returns the report; file
writing stays CLI-only.

## The scaffolded Makefile

```
make setup      Build the SUSHI + IG publisher docker image
make upgrade    Rebuild it from scratch, pulling the latest of both
make generate   d2w fhir generate all
make validate   d2w fhir validate
make sushi      Compile FSH to FHIR resources
make build      Run the full IG publisher
make clean      Remove build output
make clean-all  Also remove the package cache
```

`generate` and `validate` call `d2w` through a `D2W` variable, so you can drive
them from a checkout or straight from a git ref without installing anything:

```bash
# From a local checkout of dhis2w-utils:
make generate D2W="uv run --project /path/to/dhis2w-utils d2w"

# Straight from a git ref, nothing installed:
make generate D2W="uvx --from 'git+ssh://git@github.com/winterop-com/dhis2w-utils.git@main#subdirectory=packages/dhis2w-cli' --with 'dhis2w-fhir @ git+ssh://git@github.com/winterop-com/dhis2w-utils.git@main#subdirectory=packages/dhis2w-fhir' d2w"
```

Two build knobs the scaffold sets for you, both because the defaults break on a
real instance's IG:

`ig/fsh.ini` raises the SUSHI timeout to 900 seconds. The IG publisher re-runs
SUSHI internally with a 300-second default, which an IG built from a real DHIS2
instance - hundreds of CodeSystem/ValueSet pairs plus thousands of instances -
overruns, and the publisher dies with exit 143.

`TX_SERVER` picks the terminology server the publisher validates against; it
defaults to `http://tx.fhir.org`. Setting `TX_SERVER=n/a` disables terminology
validation for an offline build, but current IG publisher versions throw a
`NullPointerException` on required bindings that need a server - the
`Attachment.contentType` binding on the GeoJSON boundary extension is one of
them, so an org-unit IG will not build offline. Use `n/a` only when your content
has no such bindings.

## The regeneration contract

Every generated file opens with the header line:

```
// Generated by d2w fhir generate - do not edit
```

A generate run writes its target subdirectory and then deletes only the
header-bearing `.fsh` files in that subdirectory that it did not just produce.
Three consequences worth relying on:

- **Hand-authored FSH is safe.** Drop your own `.fsh` files anywhere in
  `ig/input/fsh/`, including inside a generated subdirectory. Without the header
  they are never touched. `ig/input/fsh/aliases.fsh` is scaffolded as exactly
  this kind of file: a hand-authored stub for your own aliases, which is why the
  DHIS2 aliases are generated into `foundation/d2-aliases.fsh` instead.
- **Re-running converges.** Renaming an option set does not leave the old file
  behind; the run deletes it.
- **Unchanged output is not rewritten.** Files whose content matches keep their
  timestamps, so a no-op regenerate leaves a clean `git status`.

Commit the generated tree. Reviewing the FSH diff after a metadata change is the
point.

## See also

- [FHIR plugin architecture](../architecture/fhir-plugin.md) - how the package is
  laid out and why.
- [`examples/v42/cli/fhir_generate.sh`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/v42/cli/fhir_generate.sh) -
  the same flow as a runnable script.
