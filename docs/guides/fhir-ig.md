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
`make clean-all` also drops the caches. See
[Build time and the two caches](#build-time-and-the-two-caches).

`init` also takes `--publisher-url`. Leave it off unless the publisher has a real
home page: the IG publisher links that URL from every generated page, so aiming
it at the canonical of an unpublished IG produces one QA warning per page.

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

Straight through to `sushi-config.yaml`. The five identity keys are required;
`status` defaults to `draft`.

```toml
[ig]
id = "org.example.dhis2"                   # IG package id
canonical = "https://example.org/fhir"     # canonical base URL; trailing slash stripped
name = "OrgExampleDhis2"                   # SUSHI name (computational, no spaces)
title = "Example DHIS2 Implementation Guide"
publisher = "Example Organisation"
status = "draft"                           # draft while building; active for production
```

**`status`** is `draft` or `active`, and it drives three things at once: the
`status` of `sushi-config.yaml`, the publication `status` every generated
definitional resource carries, and their `experimental` flag. A draft IG
publishes its profiles, extensions, CodeSystems, ValueSets, NamingSystems, and
Questionnaires with `status = draft` and `experimental = true`; flip to `active`
and regenerate, and they all read `status = active` and `experimental = false`.
The flag is always populated, because the Shareable profiles require it to be
present; NamingSystem instances take the `status` but no flag, R4 gives them no
`experimental` element. The Organization and Location instances are data, not
definitions: their `active` / `status` states whether the organisation unit is
closed and has nothing to do with this dial. `d2w fhir init --status active`
scaffolds an active project directly.

### `[generate]`

```toml
[generate]
identifier_system_base = "http://dhis2.org/fhir"
concept_code_source = "id"
locales = []
```

**`identifier_system_base`** is the base URI for the DHIS2 identifier systems.
It is live, not decorative: `d2w fhir generate foundation` writes it into
`foundation/d2-aliases.fsh` as the `$DHIS2-OU` / `$DHIS2-OU-CODE` / `$DHIS2-OS` /
`$DHIS2-OS-CODE` aliases every other file references, declares each of those URLs
as a NamingSystem in `foundation/d2-naming-systems.fsh`, and derives the
`<base>/property/<code>` URIs the terminology concept properties carry. Change it
and regenerate, and every reference follows. It is a local DHIS2 convention -
the NamingSystems are what state that convention inside the IG; they are not
registrations with HL7.

**`concept_code_source`** picks what a terminology concept's code is:

- `"id"` (default) - the DHIS2 UID is the concept code, and the DHIS2 code
  rides along as a `dhis2-code` concept property.
- `"code"` - they swap: the DHIS2 code is the concept code (when it is a valid
  FHIR `code`), and the UID rides along as a `dhis2-id` property.

**The id-first, then-code workflow.** Start on `"id"`. UIDs are unique,
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
`d2w fhir validate` in id mode reports the same findings as `info` - they are a
readiness signal, not a defect, because generation is not reading those codes yet.

**`locales`** picks which translation locales reach the generated artifacts. It
takes BCP-47 or DHIS2-style tags (`"lo"`, `"km"`, `"pt_BR"`) and an empty list -
the default - emits every locale found on the instance. See
[Locales and translations](#locales-and-translations).

### `[generate.naming]`

```toml
[generate.naming]
source = "id"
prefix = "D2"
option_set = "OS"
organisation_unit = "OU"
```

**`source`** decides what the **option-set** artifacts are named after - their
file names, FHIR ids, and FSH names:

- `"id"` (default) - stable, collision-free, script-agnostic. DHIS2 names are
  often non-latin or non-unique, so id-sourced ids never truncate or collide.
  You get `terminology/Qdm5fPK5Ra9.fsh`, `D2OS_Qdm5fPK5Ra9_CS`, id
  `d2-os-Qdm5fPK5Ra9-cs`. The UID keeps its own case: FHIR ids and file names
  both permit mixed case, so the id reads straight back to the DHIS2 object.
- `"name"` - human-readable slugs (`terminology/birth-type.fsh`,
  `D2OS_BirthType_CS`, `d2-os-birth-type-cs`), truncated with a UID suffix when a
  name overflows FHIR's 64-character id limit and disambiguated the same way when
  two names collide. Both are reported as notes.

Whichever source is set, the names are assigned once over the whole option-set
selection - a truncation or a collision suffix depends on the peers a set is
assigned against - and every other target reads that assignment. A question's
`answerValueSet` and an example's answer coding therefore name the very CodeSystem
and ValueSet the same run writes, under `"name"` exactly as under `"id"`.

Organisation-unit instances and files are outside `source` by construction:
they are always UID-based (`Organization-<UID>` / `Location-<UID>` in
`org-units-level-<n>.fsh`, each resource `id` the bare UID), because a hierarchy
of thousands of units has neither unique names nor stable ones.

**The tokens** compose artifact names by merging the prefix and kind token and
underscoring the segments after it, and ids by kebab-joining each non-empty token. With the defaults, an option set becomes
`D2` + `OS` + `_Qdm5fPK5Ra9` + `_CS` = `D2OS_Qdm5fPK5Ra9_CS`, id
`d2-os-Qdm5fPK5Ra9-cs`; on `source = "name"` the same set reads `D2OS_BirthType_CS`
/ `d2-os-birth-type-cs`. Rename or drop a token and the whole IG follows
consistently.

| Token | Default | Notes |
| --- | --- | --- |
| `prefix` | `D2` | May be empty to drop it entirely. |
| `option_set` | `OS` | May be empty. Try `OptionSet` for a verbose IG. |
| `organisation_unit` | `OU` | Must stay non-empty. `OrgUnit` gives `D2OrgUnit_Level_CS`. |
| `data_set` | `DS` | May be empty. Names a data set's Questionnaire (`D2DS_BfMAe6Itzgt`). |
| `program` | `PR` | May be empty. Names an event program's Questionnaire (`D2PR_VBqh0ynB2wv`). |

**The empty-prefix caveat.** Setting `prefix = ""` drops the token from
terminology names (`OU_Level_CS`, id `ou-level-cs`), but the two organisation-unit
profiles and the `D2Period` extension keep a `D2` token anyway. FSH cannot name a
profile identically to its parent core resource, nor an extension identically to
a core datatype: `Profile: Organization` and `Extension: Period` are both
illegal. Those definitions fall back to `D2` rather than fail.

#### The canonical token registry

Keys are added to `[generate.naming]` as each generator lands, with these
defaults. Only `option_set` and `organisation_unit` exist in code today; the rest
are the decided defaults for the generators still to come. Every token composes
as `{prefix}{token}_<segment>_CS`, and ids derive from the kebab of prefix plus
token (`d2-deg-<uid>-cs`).

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
| `DS` | data set (in code) | `PR` | program (in code) |
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
# include_ids = ["Qdm5fPK5Ra9"]     # optionSet UIDs to include; absent means all
```

UIDs only - DHIS2 option-set names are not unique. An entry matching nothing is
reported as a note rather than silently ignored. A narrowed list is still unioned
with whatever the selected data sets and event programs bind their data elements
to, so a questionnaire never points at a ValueSet the IG does not contain
(see [Data set and event program forms](#data-set-and-event-program-forms)).

### `[generate.data_sets]` and `[generate.event_programs]`

```toml
[generate.data_sets]
# include_ids = ["BfMAe6Itzgt"]     # data set UIDs; absent means all

[generate.event_programs]
# include_ids = ["VBqh0ynB2wv"]     # event program UIDs; absent means all
```

The data-definition targets. They read like the terminology and registry selections:
an absent or empty list means **all**, a non-empty list filters.
`d2w fhir init --data-set <uid> --event <uid>` seeds these lists while scaffolding,
which is how you narrow a project to the handful of forms you care about.

The two modes differ on the program shapes the Questionnaire target cannot map yet:

- **Absent or empty** (the whole instance): only single-stage
  `WITHOUT_REGISTRATION` programs are picked up. Tracker programs and multi-stage
  event programs are skipped, each shape reported as one aggregate note in the
  generate report (`N tracker programs skipped (tracker generation not
  implemented): ...`). Every data set on the instance is emitted.
- **Non-empty** (an explicit list): a listed tracker or multi-stage program is a
  loud failure naming the program, not a skip - you asked for that UID by name, so
  the run stops instead of quietly leaving it out. UIDs the instance answers
  nothing for stay an aggregate note.

### `[generate.examples]`

```toml
[generate.examples]
per_target = 1          # example QuestionnaireResponses per questionnaire target; 0 disables
source = "synthetic"    # "synthetic" (generated values) or "instance" (real values off the server)
```

How many example responses each questionnaire target gets, and where their
answers come from. See [Example responses](#example-responses).

### `[generate.organisation_units]`

```toml
[generate.organisation_units]
# root = "ImspTQPwCqd"  # organisation unit root UID; absent means the entire tree
# max_level = 4         # absent means no level cap
terminology = false     # also emit the org-unit CodeSystem/ValueSet
```

`root` filters with DHIS2 `path:like`, so it selects the subtree beneath (and
including) that unit. `max_level` caps the depth. Both are applied server-side.

`terminology = true` additionally emits the whole selection as one
CodeSystem/ValueSet with `level`, `parent`, and `dhis2-code` concept properties -
for flows that want the hierarchy as codes rather than as resources.

## Generate targets

```
d2w fhir generate foundation     Identifier aliases + the D2Period / D2FormType extensions
d2w fhir generate option-sets    Option sets -> CodeSystem/ValueSet pairs
d2w fhir generate questionnaires Data sets + event programs -> Questionnaire instances
d2w fhir generate examples       Example QuestionnaireResponses answering those Questionnaires
d2w fhir generate org-units      Org units -> Organization/Location instances
d2w fhir generate pages          Narrative site pages + per-artifact intros
d2w fhir generate all            All six, in that order
```

Each target owns its subdirectories and syncs each one: writes what changed, leaves
what did not, deletes generated files that no longer belong. `questionnaires` owns
three under `ig/input/fsh/` (`data-sets/`, `event-programs/`, `data-dictionary/`);
the other four FSH targets own one each; `pages` owns `ig/input/pagecontent/`, which
holds markdown rather than FSH.

### `foundation`

Writes `foundation/`, the part of the IG that depends on `fhir.toml` alone and
never touches DHIS2:

- **`d2-aliases.fsh`** - the `$DHIS2-OU`, `$DHIS2-OU-CODE`, `$DHIS2-OS`, and
  `$DHIS2-OS-CODE` aliases, built from `identifier_system_base`. The instance and
  terminology files reference these, so this target is a prerequisite for a
  compiling IG.
- **`d2-naming-systems.fsh`** - one `NamingSystem` per alias URL, declaring what
  a DHIS2 identifier under it means. See [Identifiers](#identifiers).
- **`d2-period.fsh`** - the `D2Period` extension plus its terminology.
- **`d2-form-type.fsh`** - the `D2FormType` extension plus its terminology. See
  [Data set and event program forms](#data-set-and-event-program-forms).
- **`d2-responses.fsh`** - the `D2AggregateResponse` and `D2EventResponse` profiles
  every captured `QuestionnaireResponse` has to meet. See
  [The capture contract](#the-capture-contract).
- **`d2-capture-server.fsh`** - the `D2CaptureServer` CapabilityStatement stating
  the interactions a server accepting those responses supports.

### The D2Period extension

DHIS2 reporting periods have no FHIR equivalent: a FHIR `Period` is a pair of
instants, while a DHIS2 period is a *typed* interval - `202401` is not merely
1-31 January, it is the January instance of the `Monthly` period type, and the
type is what makes it comparable, aggregatable, and round-trippable.

`D2Period` carries all three facts:

| Sub-extension | Type | Cardinality | Meaning |
| --- | --- | --- | --- |
| `iso` | `string` | 1..1 | The DHIS2 ISO period identifier, e.g. `202401` |
| `type` | `code` | 1..1 | The period type, bound (required) to `D2PeriodType_VS` |
| `period` | `Period` | 0..1 | The date range the identifier resolves to |

Its context names exactly the two resources that carry it: `QuestionnaireResponse`
(every example response against a data set form) and `MeasureReport` (the later
summary projection). A context of bare `Element` would attach it anywhere, which
the IG publisher's QA calls out as an unbounded extension.

The `D2PeriodType_CS` CodeSystem publishes every period type DHIS2 registers,
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

`recent_periods` is its inverse, and the example target's way of finding a period
worth looking for data in: the most recent periods of a type whose end date is
already past, newest first.

```python
import datetime
from dhis2w_fhir.period import recent_periods

recent_periods("Monthly", 3, datetime.date(2026, 8, 2))
# ['202607', '202606', '202605']
```

It is written as an inverse rather than as a second transcription of the upstream
month offsets: each type declares only how its ISO strings are spelled for a given
year, and `parse_period` decides which of those exist and what dates they cover -
so the two can never disagree.

### Identifiers

Every FHIR artifact representing a DHIS2 object exposes **both** DHIS2
identifiers - the UID and the code - wherever FHIR gives it a slot. This is the
standing rule for every generator, present and future (Questionnaire, Patient,
EpisodeOfCare, MeasureReport identifiers will follow it).

- **Instances** carry identifier slices discriminated on `system`:
  `{base}/id/<kind>` holds the UID and `{base}/id/<kind>-code` holds the code.
  Both slices are always emitted, on the Organization and on the Location alike.
- **Terminology concepts** carry the complementary identifier as a concept
  property: in id mode every concept gets `dhis2-code`, in code mode every
  concept gets `dhis2-id`. No concept goes without the pair.
- **Option-set CodeSystems and ValueSets** carry the source set's own pair as
  `^identifier` business identifiers, referenced through the `$DHIS2-OS` /
  `$DHIS2-OS-CODE` aliases (`{base}/id/option-set` and
  `{base}/id/option-set-code`).

- **Questionnaires** carry the source data set's or event program's pair through
  `$DHIS2-DS` / `$DHIS2-DS-CODE` and `$DHIS2-PROGRAM` / `$DHIS2-PROGRAM-CODE`.

**Every system is declared as a NamingSystem.** `foundation/d2-naming-systems.fsh`
emits one `NamingSystem` per identifier system - a UID system and a code system for
each of the organisation unit, option set, data set, program, data element, and
category option combo - each `kind = #identifier` with a single
preferred `uri` uniqueId and a description of the convention, the code slot's UID
fall-back included. Without them, a validator meeting `{base}/id/org-unit` has no
definition to resolve and warns on every artifact carrying one. Because R4 makes
`NamingSystem.date` mandatory, the declarations carry a pinned date rather than
the time of the run - a generated timestamp would rewrite the file every time.

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

### Data set and event program forms

A DHIS2 data set and a DHIS2 event program are both *data-capture forms*, and FHIR
already has that resource: `Questionnaire`. `d2w fhir generate questionnaires`
writes one file per selected target plus two support CodeSystem/ValueSet pairs,
across three directories named for what they hold:

```
ig/input/fsh/data-sets/<UID>.fsh          One Questionnaire per data set
ig/input/fsh/event-programs/<UID>.fsh     One Questionnaire per event program
ig/input/fsh/data-dictionary/             The shared data-element and
                                          category-option-combo terminology
```

The command keeps the name `questionnaires` - it says what it does, not where the
files land. With no `[generate.data_sets]` / `[generate.event_programs]` table at
all, every data set and every single-stage event program on the instance is a
target; list UIDs to narrow it:

```toml
[generate.data_sets]
include_ids = ["BfMAe6Itzgt"]       # Child Health

[generate.event_programs]
include_ids = ["VBqh0ynB2wv"]       # Malaria case registration
```

```bash
# Or seed those lists while scaffolding - repeatable, and entirely offline:
# the UIDs are written to fhir.toml as given, never checked against an instance.
d2w fhir init my-ig --data-set BfMAe6Itzgt --data-set Nyh6laLdBEJ --event VBqh0ynB2wv
```

**Targets are explicit.** Every other selection defaults to "everything on the
instance"; these two default to nothing. A form is a deliberate addition to a
project, and generating all 26 data sets of a demo database is never what you meant.

**What one form becomes.** The instance is `Usage: #definition` with the bare UID as
its `id` and `<canonical>/Questionnaire/<uid>` as its `url`, `subjectType = #Location`
(a DHIS2 form is answered *for an organisation unit*), and both DHIS2 identifiers -
`$DHIS2-DS` / `$DHIS2-DS-CODE` for a data set, `$DHIS2-PROGRAM` /
`$DHIS2-PROGRAM-CODE` for an event program. `Questionnaire.name` composes from the
naming tokens (`D2DS_BfMAe6Itzgt`, `D2PR_VBqh0ynB2wv`) and `title` is the DHIS2 name.

| DHIS2 | FHIR |
| --- | --- |
| Section | `item` with `type = #group`, `linkId` the section UID |
| Data element | child `item`, `linkId` the DE UID, `text` its form name (else its name) |
| `valueType` | the item `type` (see the table below) |
| Data element with an option set | `type = #choice` plus `answerValueSet` pointing at that set's generated ValueSet |
| Compulsory program-stage element | `required = true` |
| Non-default category combo | the question becomes a `#group` with one child per category option combo, `linkId` `<deUid>.<cocUid>`; each child asks the element's own question, so it repeats the element's item type, `answerValueSet`, `repeats`, and bounds |

Every DHIS2 value type is mapped explicitly - all 28 of them, which is the union of the
`ValueType` enum across v41, v42, and v43 (`TRACKER_ASSOCIATE` exists on v41 and v42 only;
v43 dropped it).

| DHIS2 `valueType` | item `type` | Why |
| --- | --- | --- |
| `TEXT` | `string` | |
| `LONG_TEXT` | `text` | Multi-line free text. |
| `LETTER` | `string` | R4 has no single-character type. |
| `PHONE_NUMBER` | `string` | R4 has no telecom item type. |
| `EMAIL` | `string` | R4 has no email item type. |
| `USERNAME` | `string` | A DHIS2 account name, not a FHIR reference. |
| `MULTI_TEXT` | `choice` + `repeats` | Option-set bound by definition, and multi-select *is* its semantics. |
| `NUMBER` | `decimal` | |
| `PERCENTAGE` | `decimal` | |
| `UNIT_INTERVAL` | `decimal` | |
| `INTEGER` | `integer` | |
| `INTEGER_POSITIVE` | `integer` | |
| `INTEGER_NEGATIVE` | `integer` | |
| `INTEGER_ZERO_OR_POSITIVE` | `integer` | |
| `BOOLEAN` | `boolean` | |
| `TRUE_ONLY` | `boolean` | Only ever `true` in DHIS2. |
| `DATE` | `date` | |
| `DATETIME` | `dateTime` | |
| `TIME` | `time` | |
| `AGE` | `date` | DHIS2 stores the date of birth; the age is rendered from it, so the date is the captured value. |
| `URL` | `url` | |
| `FILE_RESOURCE` | `attachment` | |
| `IMAGE` | `attachment` | |
| `GEOJSON` | `text` | A GeoJSON document, not a coordinate pair. |
| `COORDINATE` | `string` | DHIS2's `[longitude,latitude]` string; no R4 item type expresses it. |
| `ORGANISATION_UNIT` | `reference` | The one value type that resolves to a FHIR resource. |
| `REFERENCE` | `string` | A bare UID until tracker generation lands. |
| `TRACKER_ASSOCIATE` | `string` | v41/v42 only; a bare UID until tracker generation lands. |
| anything else | `string` | Only reachable by a DHIS2 value type newer than the generated enums. |

**The table is guarded, not aspirational.** A test reads the `ValueType` enum out of each of
the three generated client trees and asserts that every member has an explicit entry, and that
the table holds nothing the three trees do not. A codegen refresh that introduces a new DHIS2
value type therefore fails the suite until someone decides what it maps to, instead of silently
becoming a `string`. The `string` fallback stays anyway, so a live instance running ahead of
the generated tree never crashes generation.

**`MULTI_TEXT` carries `repeats = true`.** That is the whole difference between it and a plain
option-set-bound question: DHIS2 stores a comma-separated list of option codes against one data
element, and an example response answers such a question once per selected code.

A section holding a disaggregated data element also carries the standard
`questionnaire-itemControl` extension coded `#gtable`, which is how a renderer knows
to lay that section out as the DHIS2 data-entry grid it is - questions as rows,
category option combos as columns.

**The support terminology.** `data-dictionary/data-elements.fsh` publishes every data
element the generated questionnaires reference as one `D2DE_CS` CodeSystem (plus its
ValueSet), and `data-dictionary/category-option-combos.fsh` does the same for every
category option combo as `D2COC_CS`. Each item's `code` points into them, so a
response can be read back to DHIS2 without consulting the questionnaire. Both live
under `data-dictionary/` rather than `terminology/`, which is what keeps the
option-set target from deleting them on its next run. Each of the three directories
is swept against its own files, so narrowing the data-set selection deletes only the
data-set questionnaires that left it. If you generated with an earlier build, delete
the leftover `ig/input/fsh/questionnaires/` directory by hand - nothing manages it
any more.

**The option-set closure.** When `[generate.option_sets] include_ids` narrows the
terminology and a selected form binds a question to an option set outside that
list, the set is added anyway and the run says so in a note. An empty option-set list
already means every option set, so the union is a no-op there.

**Safeguards, loud when you named the UID.** A UID *listed* under
`[generate.event_programs]` whose live `programType` is `WITH_REGISTRATION` fails the
run by name: tracker programs need `Patient` and `EpisodeOfCare`, not a bare
Questionnaire, and that generator is not written yet. A listed event program with
more than one program stage fails the same way rather than quietly generating the
first stage. A listed UID the instance answers nothing for is reported as a note.
With an absent or empty list the whole instance is the target, so the same two shapes
are skipped with one aggregate note each instead of stopping the run. Data elements
no section references are emitted after the sectioned ones, also with a note.

**`D2FormType`.** Every generated Questionnaire states which kind of DHIS2 form it
came from twice: as `Questionnaire.code` (`D2FormType_CS#aggregate` or `#event`) and
through the `D2FormType` extension, whose context covers `Questionnaire` **and**
`QuestionnaireResponse`. That second context is what
[Example responses](#example-responses) uses: a data value set becomes a
`QuestionnaireResponse` against the form's `Questionnaire`, carrying its DHIS2
reporting period through the `D2Period` extension (`iso`, `type`, the resolved
dates) and its organisation unit through `subject`, and answering item by item on
the same `linkId`s - including the `<deUid>.<cocUid>` link ids the disaggregated
groups define, which is exactly a DHIS2 data value's `(dataElement,
categoryOptionCombo)` key. `MeasureReport` is a later, lossier projection over the
same data - a summary for indicator-shaped consumers - not a replacement for the
response. `D2FormType` on the response is what tells a consumer which of those
shapes it is holding without re-reading the questionnaire.

### Example responses

A `Questionnaire` says what a DHIS2 form asks. A `QuestionnaireResponse` says what
an answer to it looks like, which is the thing an implementer actually reads before
writing an integration. `d2w fhir generate examples` writes one
`Usage: #example` response per example into its own directory:

```
ig/input/fsh/examples/<targetUID>-<n>.fsh
```

```toml
[generate.examples]
per_target = 1          # responses per questionnaire target; 0 disables the target entirely
source = "synthetic"    # "synthetic" or "instance"
```

The targets are the same `[generate.data_sets]` / `[generate.event_programs]`
selection the questionnaires use, with the same all-mode and skip rules - an
example is always generated against a form the IG contains.

**What one response carries.** `questionnaire` points at the target's canonical,
`subject` at a `Location`, and `status` at how far the capture got. The response
states its DHIS2 form kind through the same `D2FormType` extension the
`Questionnaire` carries, and a data-set response additionally carries the full
`D2Period` extension - the ISO identifier, the period type, and the resolved date
range. Event responses carry `authored` instead, taken from the event's
`occurredAt`.

The items **mirror the questionnaire**: section groups nest their questions, and a
disaggregated data element nests one child per category option combo under
`<deUid>.<cocUid>` - the same key a DHIS2 data value carries. Answers are typed
from the data element's `valueType` (integers to `valueInteger`, `NUMBER` /
`PERCENTAGE` / `UNIT_INTERVAL` to `valueDecimal`, `BOOLEAN` / `TRUE_ONLY` to
`valueBoolean`, the temporals to `valueDate` / `valueDateTime` / `valueTime`,
option-set-bound questions to a `valueCoding` into that set's generated
CodeSystem, everything else to `valueString`). A value that will not cast, or an
option code no option carries, is answered as a string and counted in one
aggregate note per run rather than emitted invalid.

#### `source = "synthetic"` (the default)

No data endpoint is called. Values are generated locally from a seed that is the
leading 64 bits of `sha256("<targetUID>:<n>")` - not Python's `hash`, which is
salted per process - so regenerating produces the same file, on any machine, in
any interpreter. Every question is answered, every option combo of a
disaggregated element is filled, `TRUE_ONLY` is always `true`, and an
option-set-bound question picks a real concept from the set the IG publishes.

The one thing that is *not* stable across days is the anchor: a data-set example
takes the newest **completed** period of the data set's period type, and dates
inside the response are drawn from that period's window. Regenerate in a new
month and the period moves; everything else stays byte-identical.

#### `source = "instance"`

Answers come from the values the server actually holds.

- **Data sets** walk back through the six newest completed periods of the data
  set's period type, calling `GET /api/dataValueSets` for the root organisation
  unit and its descendants, and stop at the first period that answers with data
  values. Those values are grouped by their DHIS2 reporting key - `(orgUnit,
  period, attributeOptionCombo)` - richest group first, and each group becomes one
  response with id `<dataSetUID>-<period>-<orgUnitUID>`.
- **Event programs** read the most recent events from `GET /api/tracker/events`
  ordered by `occurredAt:desc`. Each event becomes one response keyed by the event
  UID, with the DHIS2 event status mapped onto the response status (`COMPLETED` to
  `completed`, `ACTIVE` to `in-progress`, `SKIPPED` to `stopped`, and the
  scheduled / overdue / visited states to `completed`).

A target the instance holds nothing for is one aggregate note, never a failure -
a demo database whose newest data predates the six-period window simply yields no
example for that data set.

**The production-instance caveat.** Instance-sourced examples embed real captured
values, real organisation units, and real reporting periods into a document you
are about to publish. That is exactly what you want from a demo server and
exactly what you do not want from a production one. `synthetic` is the default for
that reason: switching to `instance` is a deliberate act, and the generated
`examples/` directory is worth reading before the IG leaves your machine.

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

## The capture contract

The whole point of publishing the forms is that somebody else can capture data
against them. Three artifacts make the IG a complete contract for that, so a third
party needs the published guide and nothing else - no access to this repo, no access
to the DHIS2 instance's metadata API, no conversation.

**Two profiles**, in `foundation/d2-responses.fsh`, one per form kind:

| Profile | Parent | What it pins |
| --- | --- | --- |
| `D2AggregateResponse` | `QuestionnaireResponse` | `D2Period` 1..1, `D2FormType` 1..1 fixed to `#aggregate`, `questionnaire` 1..1, `subject` 1..1 restricted to `Reference(D2Location)`. |
| `D2EventResponse` | `QuestionnaireResponse` | `D2FormType` 1..1 fixed to `#event`, `authored` 1..1, `questionnaire` 1..1, `subject` 1..1 restricted to `Reference(D2Location)`. |

Both follow the `[generate.naming]` prefix, and both take `^status` /
`^experimental` from the `[ig] status` dial like every other definitional artifact.
`foundation/d2-capture-server.fsh` sits beside them: a `D2CaptureServer`
CapabilityStatement of `kind = #requirements`, declaring `create` on
`QuestionnaireResponse` with both profiles as `supportedProfile`, plus `read` and
`search-type` on the `Questionnaire`, `CodeSystem`, `ValueSet`, `Location`, and
`Organization` resources a client resolves a form from. Its `date` is a fixed
literal, for the same byte-stability reason the NamingSystem declarations pin
theirs - R4 makes the element mandatory and a generated timestamp would rewrite the
file on every run.

**The Capture page**, `pagecontent/capture.md`, is the prose half. It walks an
aggregate response and an event response step by step against forms actually
selected in this project - the canonical URL rule, the `D2Period` extension worked
with a real ISO period, the `subject` reference to a real organisation unit, the two
`linkId` grammars (`<dataElementId>` and `<dataElementId>.<categoryOptionComboId>`),
the required rules, the event status map - and closes with a table typing every
DHIS2 value type onto its item type, answer element, and literal spelling, then the
coded-answer rule and the validation workflow. The typing table is built from the
very tables the example emitter answers from, so the page and the examples cannot
disagree about how a value is spelled.

**The examples are the contract check.** Every generated example declares itself
`InstanceOf: D2AggregateResponse` or `InstanceOf: D2EventResponse` rather than the
bare resource, so `make sushi` and the IG publisher validate each one against the
contract on every run. A profile that stops describing what generation produces
fails the build instead of shipping.

Two more things a capture client reads off the Questionnaire itself. **Required
questions**: a data set's `compulsoryDataElementOperands` become `required = true`
at the grain DHIS2 states them - an operand naming a data element alone marks the
whole question and every disaggregated cell under it, an operand also naming a
category option combo marks only that one cell. **Numeric bounds**: a value type
that *is* a constraint carries it as standard `minValue` / `maxValue` extensions on
the item - `INTEGER_POSITIVE` from 1, `INTEGER_ZERO_OR_POSITIVE` from 0,
`INTEGER_NEGATIVE` up to -1, `PERCENTAGE` 0 to 100, `UNIT_INTERVAL` 0 to 1, typed
`valueInteger` on an integer item and `valueDecimal` on a decimal one. `INTEGER` and
`NUMBER` carry none, because DHIS2 bounds neither. Disaggregated cells share their
data element's value type, so they carry the same bounds.

## Site pages and intros

`d2w fhir generate pages` writes the guide's prose. It is the last target `generate
all` runs, and the only one that writes markdown instead of FSH.

```
ig/input/pagecontent/forms.md         Data set + event program catalog
ig/input/pagecontent/registry.md      Organisation unit registry summary
ig/input/pagecontent/terminology.md   Option sets + the support CodeSystems
ig/input/pagecontent/identifiers.md   The two identifier slices + NamingSystems
ig/input/pagecontent/periods.md       D2Period + every DHIS2 period type
ig/input/pagecontent/capture.md       How a third party captures data against the forms
```

Those six are the site menu, which `d2w fhir init` scaffolds as `Home`, `Forms`,
`Registry`, `Terminology`, `Identifiers`, `Periods`, `Capture`, `Artifacts`. There is no
`pages:` block in `sushi-config.yaml` and there does not need to be: SUSHI publishes
every markdown file under `pagecontent/` on its own.

The same run writes the per-artifact intros, which the IG publisher injects into the
top of the matching artifact page:

- **`Questionnaire-<UID>-intro.md`** - one per generated Questionnaire, always. It
  names the DHIS2 data set or event program it came from, carries the DHIS2
  description when there is one, and tabulates the form's sections and question
  counts.
- **`CodeSystem-<id>-intro.md`** - only for an option set that carries a DHIS2
  description.
- **`Organization-<UID>-intro.md`** - only for an organisation unit that carries a
  DHIS2 description. Most units have none, so most units get no file. That is the
  intended outcome, not a gap: an intro page repeating the unit's own title would
  be noise on every one of them.

**What stays hand-authored.** `ig/input/pagecontent/index.md` is scaffolded once by
`d2w fhir init` and is yours - it is the guide's home page, and no generate run ever
rewrites or deletes it. The rule is the same one the FSH tree follows: the sweep only
deletes files carrying the generated header, which for markdown is the HTML comment
`<!-- Generated by d2w fhir generate - do not edit -->`. Drop your own markdown into
`pagecontent/` and it survives every regenerate; to have it in the menu, add it to
`menu:` in `sushi-config.yaml` yourself.

Every DHIS2 name and description on these pages is escaped on the way in. A data set
called "Mortality < 5 years by gender" renders as text rather than aborting the
publisher's HTML parse, and an option called "Fixed, >1y | special" stays inside its
table cell.

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
d2w fhir validate [--code-source id|code] [--report STEM] [--format md,csv,pdf] [--all] [--no-fail]
```

Two passes, one finding shape:

- an **instance-wide sweep** over `GET /api/metadata?fields=id,name,code`
  (`defaults=EXCLUDE`, so DHIS2's auto-generated default category objects stay
  out of it). Every metadata object's code is checked against the R4 `code`
  datatype: invalid codes are errors, per-type duplicates warn. Organisation
  units additionally warn when they carry no code at all.
- a **deep option-set pass** previewing exactly what code-mode generation would
  do, over the same projections the emitter consumes.

Both passes also check the object's **name**, for one thing that has nothing to do
with codes - see below.

### `template-hostile-name`

A warning on any metadata object whose **name** contains `<`, `>`, or `&`.

The IG publisher's `fhir2.base.template` writes a resource's title into breadcrumbs
and change-history headings without HTML-escaping it, and then strict-parses the
page it just produced. A DHIS2 name holding `<` therefore produces a malformed page:
the Sierra Leone demo's `Mortality < 5 years by gender` (`YFTk3VdO9av`) renders
`<h2 id="root">: Mortality < 5 years by gender - Change History</h2>` and the
publisher logs `Unable to Parse HTML - node 'h2' has unexpected content`.

Generation escapes what it owns - the FSH `Title:` and `Description:` lines that
become page metadata all HTML-escape those three characters. It deliberately does
**not** touch the resource's own `title` and `name` elements: those are DHIS2 data,
they are what a consumer reads back, and silently substituting entities into them
would make the IG disagree with the instance. So the change-history surface stays
malformed for such a name, and the fix is to change the name in DHIS2 - which is
what this warning is for.

The check runs in both passes and at warning severity in either code source: it is
about the pages the IG publishes, not about what generation reads. The sweep covers
every metadata object; the deep option-set pass covers option names, which the sweep
excludes and which land in concept displays and page tables. The offending name is
printed through the same renderer the code column uses, so an invisible character in
it is visible on the page.

### Severity and `--code-source`

The option-pass findings are gated on the effective code source - the
`--code-source` flag when given, otherwise `concept_code_source` from
`fhir.toml`. In `code` mode, `invalid-code`, `missing-code`, and `duplicate-code`
carry their real severities. In `id` mode they are downgraded to `info` and
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

The human-facing renderings - the Markdown and PDF reports and the terminal
findings table - print a code with its control characters escaped (`BLUE\nBLUE`
reads on one line) and wrap a code with leading or trailing spaces in double
quotes (`" M "`), so an invisible character is visible; the CSV and the JSON
report carry the raw code.

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
make clean-all  Also remove the terminology cache and the package cache volume
make help       List the targets
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

### Build time and the two caches

A full `make build` on a real instance takes around twenty minutes - the Sierra
Leone demo (171 option sets, 2664 instances) spends 15m on generation, 1m45s on
validation, and 1m25s on Jekyll. Most of what a *repeat* build would otherwise
re-pay is cached, and the scaffold wires both caches up for you:

- **The FHIR package cache** lives at `~/.fhir` inside the container. Because
  `docker run --rm` throws the container away, `make sushi` and `make build`
  mount the named volume `fhir-ig-cache` there. Without it every run
  re-downloads the core packages, `hl7.terminology.r4`, and
  `hl7.fhir.uv.extensions.r4` before doing any work.
- **The terminology cache** is `ig/input-cache/`, written by the publisher and
  ignored by git. `make clean` deliberately leaves it in place; a warm tx cache
  takes the validation phase from minutes to seconds, because every code the
  validator has not seen is a round trip to `TX_SERVER`.

`make clean-all` drops both when you want to reproduce a cold build.

**Do not iterate on `make build`.** `d2w fhir generate all` followed by
`make sushi` compiles the FSH and tells you whether it is valid in seconds. Run
the publisher when you are ready to publish a site, not after every edit.

## The regeneration contract

Every generated file opens with a header line, chosen by extension:

```
// Generated by d2w fhir generate - do not edit
<!-- Generated by d2w fhir generate - do not edit -->
```

A generate run writes its target subdirectory and then deletes only the
header-bearing `.fsh` / `.md` files in that subdirectory that it did not just
produce. Three consequences worth relying on:

- **Hand-authored content is safe.** Drop your own `.fsh` files anywhere in
  `ig/input/fsh/`, or your own markdown in `ig/input/pagecontent/`, including
  beside generated files. Without the header they are never touched.
  `ig/input/fsh/aliases.fsh` is scaffolded as exactly this kind of file: a
  hand-authored stub for your own aliases, which is why the DHIS2 aliases are
  generated into `foundation/d2-aliases.fsh` instead. So is
  `ig/input/pagecontent/index.md`, the guide's home page.
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
