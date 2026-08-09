# FHIR IG generation with `d2w fhir`

`d2w fhir` turns a DHIS2 instance's metadata into a FHIR Implementation Guide
source tree: a [SUSHI](https://fshschool.org/docs/sushi/) project whose FSH
(FHIR Shorthand) definitions and pre-built registry JSON are generated from the
DHIS2 API and published as FHIR resources by the IG publisher.

You get three things:

- **`d2w fhir init`** scaffolds a complete, dockerized SUSHI project - config,
  `sushi-config.yaml`, a `pyproject.toml` pinning the d2w toolchain, a Makefile,
  and a Dockerfile carrying SUSHI plus the IG publisher. Nothing else to install
  but `uv` and Docker. `--refresh` brings an existing project's scaffold-managed
  files up to date; see [Refreshing a project's scaffold](#refreshing-a-projects-scaffold).
- **`d2w fhir generate`** reads DHIS2 metadata and writes the IG source into the
  project: FSH for the definitional artifacts, pre-built FHIR JSON for the
  organisation-unit registry. Re-running converges: generated files are replaced,
  hand-authored FSH beside them is never touched.
- **`d2w fhir validate`** checks the instance's codes for FHIR-safety before you
  generate anything, grades every finding by build impact on your configured IG,
  and writes a report in Markdown, CSV, and PDF.

New to FHIR, or to how a DHIS2 concept lands in it? Read
[FHIR for DHIS2 people](fhir-101.md) first - it names the handful of FHIR resources
this guide keeps using, in DHIS2 terms, and takes about ten minutes.

The plugin is version-neutral - the wire client auto-detects the DHIS2 major on
connect, so one package serves v41, v42, and v43.

## Quickstart

```bash
# 1. Scaffold a project. Any d2w runs this one command - `uv tool install dhis2w-cli`
#    if you have none yet.
d2w fhir init my-ig --id org.example.dhis2 --canonical https://example.org/fhir --publisher "Example Org"
cd my-ig

# 2. Install the project's own toolchain. The scaffolded pyproject.toml declares d2w,
#    and uv sync writes .venv plus the uv.lock that pins it.
uv sync

# 3. Point it at a DHIS2 instance. Either set `profile` in fhir.toml - `d2w fhir init
#    --profile demo` seeds it while scaffolding - or use the environment / flag. See
#    "Which DHIS2 instance" below.
uv run d2w profile add demo --url https://play.im.dhis2.org/stable-2-42-1 --username admin --password district

# 4. Check the instance's codes before generating anything.
make validate

# 5. Generate the IG source.
make generate

# 6. Compile it. `make setup` builds the docker image once; `make build` runs the
#    full IG publisher, which compiles the FSH with its own SUSHI on the way.
#    `make sushi` is the standalone gate when you want the compile without a site.
make setup
make build
```

Every make target drives `d2w` through `uv run`, so `make validate` and
`make generate` are `uv run d2w fhir validate` / `uv run d2w fhir generate`
against the pinned build - spell either form, they do the same thing.

The generated site lands in `ig/output/`. `make clean` removes build output;
`make clean-all` also drops the caches. See
[Build time and the two caches](#build-time-and-the-two-caches).

To point a FHIR client at the guide instead of publishing it, `d2w fhir serve` runs the
compiled project as a read-and-capture endpoint - see [Serving the IG](#serving-the-ig) -
and `d2w fhir forward` posts what that endpoint captured back into DHIS2, closing the loop:
see [Forwarding captured responses](#forwarding-captured-responses).

## Pinned toolchain

The scaffolded project is a `uv` project. `pyproject.toml` declares `dhis2w-cli`,
`dhis2w-fhir`, and `dhis2w-fhir-serve` - the CLI, the generator, and the server
`d2w fhir serve` runs on - `uv sync` resolves them into `.venv`, and **`uv.lock` is
committed** - it is what makes a regenerate reproducible, because the FSH a
project publishes is a function of the d2w build that wrote it. A `.python-version`
file (`3.13`, matching `pyproject.toml`'s `requires-python`) pins the interpreter
`uv` resolves with; an existing project gains it via `d2w fhir init --refresh`.
`.gitignore` covers `.venv/` and deliberately does not cover `uv.lock`.

Move the pin when you want the newer toolchain, not by accident:

```bash
uv lock --upgrade
uv sync
make refresh        # regenerate and rebuild against the new pin
```

`[tool.uv.sources]` points both packages at their subdirectories of this
repository on `main`, and the lock pins a concrete commit. Sourcing the whole
toolchain from one commit is the point: `dhis2w-cli` carries the `d2w` binary
while `dhis2w-fhir` carries the plugin behind `d2w fhir`, and a CLI paired with
a plugin from a different build is not a combination anyone tests. Delete both
entries once the packages are published, and they resolve from PyPI instead.

`init` also takes `--publisher-url`. Leave it off unless the publisher has a real
home page: the IG publisher links that URL from every generated page, so aiming
it at the canonical of an unpublished IG produces one QA warning per page.

## Refreshing a project's scaffold

The scaffold grows. A `path-resource` glob lands in `ig/sushi-config.yaml`, an
entry lands in `.gitignore`, a menu entry lands beside the others - and a project
scaffolded before that carries none of them. `--refresh` re-renders the scaffold
for an existing project and writes what it safely can:

```bash
cd my-ig
d2w fhir init . --refresh
```

**The rule is one sentence: a file is rewritten only when the current scaffold
render reproduces every line already on disk, in order.** So a refresh can only
add what the scaffold gained, and no line you wrote is ever dropped. A file
holding a single line the scaffold would not produce is left byte-identical and
reported instead.

The IG identity comes off the project itself, never from defaults: `[ig]` and the
selection tables from `fhir.toml`, the SUSHI timeout from `ig/fsh.ini`, and the
publisher URL plus the copyright year from `ig/sushi-config.yaml` - the two values
no other file records. So the comparison is against the scaffold *this* project
would produce today.

**`fhir.toml` is never written.** It is your configuration, and a refresh skips it
outright rather than comparing it.

Every file gets one of four outcomes, all of them printed:

| Outcome | Meaning |
| --- | --- |
| `created` | A scaffold file the project did not have. Written. |
| `refreshed` | The render carries every line on disk plus more. Rewritten. |
| `unchanged` | Already byte-identical to the current scaffold. |
| `skipped` | Carries a line the scaffold would not produce. Your version stays. |

**A scaffold line you deliberately deleted comes back.** That is the price of the
rule: deleting a line leaves every remaining line still present in the render, in
order, which is exactly the shape a refresh rewrites. To keep a scaffold line out, change it into
something the scaffold would not produce - comment it out, or edit it - rather
than removing it. To go the other way and take the scaffold's version of a
skipped file, delete the file and refresh again; it comes back as `created`.

`--refresh` and `--force` are mutually exclusive, and the run stops if you pass
both. `--force` rewrites every scaffold file including the ones you edited;
`--refresh` rewrites only what it can rewrite without losing an edit. They are
opposite answers to the same question.

The scaffolded [`make refresh`](#the-scaffolded-makefile) is a different verb on
the same word: it rebuilds the IG from the instance. `init --refresh` touches the
scaffold and never the generated output. The one-command way to bring an older
project up to the current d2w is the scaffolded `make update`: it moves the
toolchain pin (`uv lock --upgrade`), syncs, and runs `init --refresh` - pin
first, so the refresh runs on the d2w it just installed.

The case this exists for is concrete. A project scaffolded before `path-resource`
covered a predefined-resource sub-folder keeps a `sushi-config.yaml` without that
glob. SUSHI loads the pre-built JSON regardless - it recurses into sub-folders of
`input/resources` on its own - so `make sushi` stays green and nothing looks
wrong. The IG Publisher does not recurse, so it drops those resources from the
published guide: an IG silently missing its registry and its terminology. A
refresh adds the glob.

## Which DHIS2 instance

Generation reads its config from the nearest `fhir.toml`, discovered by walking
up from the working directory - the same idiom as `.dhis2/profiles.toml`. The
profile it connects with is resolved in this order, first match wins:

1. the global `-p` / `--profile` option on the `d2w` command,
2. the `DHIS2_PROFILE` environment variable,
3. the `profile` key in `fhir.toml`,
4. the default profile from your `profiles.toml`.

Write step 3 while scaffolding with `d2w fhir init --profile <name>`, or set the
key by hand later - both land in the same place.

Credentials never live in `fhir.toml`. It is committed project config: it names
a profile, and the profile store holds the secret.

`d2w fhir validate` does not need a `fhir.toml` at all - it targets an instance,
not a project. Run it anywhere. Without a project every selection table is empty,
which selects everything of its kind - so the whole instance grades as being on
the build path; inside a project, findings grade against that project's own
selection.

## `fhir.toml` reference

`d2w fhir init` writes two files: a minimal `fhir.toml` with just the IG identity,
and `fhir.toml.example` documenting every option with its default. Copy what you
need from the example into `fhir.toml`; anything you omit keeps its default.

### Top level

```toml
profile = "myserver"    # optional: which d2w profile to read metadata from
```

`d2w fhir init --profile myserver` seeds this key while scaffolding, so the
project points at an instance from the first run. Scaffolding stays offline: the
name is written as given and never resolved against `profiles.toml`. Without the
flag the key is scaffolded commented out, and `d2w fhir generate` falls back to
`--profile` / `DHIS2_PROFILE` / the default profile.

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
# timezone = "Asia/Vientiane"   # IANA zone the instance's zone-less timestamps are read in
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

This dial governs the codes *inside* a CodeSystem and nothing else. What the
artifacts themselves are named after - ids, canonicals, file names - is the
separate [`[generate.naming]` `source`](#the-identity-stem); the two move
independently.

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
missing, invalid, or duplicated inside its set, as warnings on the sets the
configured selection emits (and info on the rest of the instance). Fix
those in DHIS2, re-run until the option findings are clean, then set
`concept_code_source = "code"` and regenerate. In the meantime, running plain
`d2w fhir validate` in id mode reports the same findings as `info` - they are a
readiness signal, not a defect, because generation is not reading those codes yet.

**`timezone`** names the IANA zone the instance's timestamps are wall-clock
readings in. DHIS2 serves `occurredAt` and every `DATETIME` data value without a
zone (`2025-12-30T00:00:00.000`), and an R4 `dateTime` carrying a time must carry
an offset - so something has to decide which moment that string means. Name the
zone (`"Asia/Vientiane"`, `"Europe/Oslo"`) and each emitted timestamp is stamped
with the offset that zone stood at *on that timestamp*, daylight saving included:
an Oslo reading in January comes out `+01:00` and one in July `+02:00`. Leave it
unset - the default - and the wall clock is read as UTC and stamped `Z`, which is
a guess about a server you have not told the generator anything about. The value
is validated on load: a name the tz database does not hold is a config error, not
a silent fall-back. BUGS.md #62 records the upstream shape this works around.

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
category = "CAT"
organisation_unit = "OU"
```

#### The identity stem

**`source`** picks the **identity stem**: the one resolved segment every artifact
of a DHIS2 object derives from. An object's FHIR resource id, its canonical URL,
its file name (`Type-<stem>.json`, `<stem>.fsh`), and its FSH artifact name all
follow that single segment, so the stem is decided once per object per run and
everything else reads the decision. The surfaces it names:

- **option sets** - the CodeSystem, ValueSet, and ConceptMap triple of one set
  share one stem (`CodeSystem-d2-os-<stem>-cs.json`, `-vs`, `-cm`).
- **categories** - the CodeSystem, ValueSet, and ConceptMap triple of one
  category share one stem (`d2-cat-<stem>-cs` / `-vs` / `-cm`).
- **organisation units** - the registry's `Organization-<stem>.json` and
  `Location-<stem>.json`, their resource ids, and every `partOf` and
  `managingOrganization` reference between them.
- **questionnaires** - `data-sets/<stem>.fsh`, `event-programs/<stem>.fsh`,
  `tracker-programs/<program stem>/<stage stem>.fsh`, and the
  `Questionnaire-<stem>` ids and canonicals inside them.
- **examples** - `examples/<target stem>-<n>.fsh`, and every `Location/...`
  reference an example answers with.
- **pages** - `Questionnaire-<stem>-intro.md`, `Organization-<stem>-intro.md`,
  and the artifact links the site pages carry.

Three sources resolve the stem:

- `"id"` (default) - the stem **is** the DHIS2 id: stable, collision-free,
  script-agnostic, always FHIR-valid. You get id `d2-os-Qdm5fPK5Ra9-cs`, name
  `D2OS_Qdm5fPK5Ra9_CS`, file `terminology/CodeSystem-d2-os-Qdm5fPK5Ra9-cs.json`.
  The id keeps its own case: FHIR ids and file names both permit mixed case, so
  the id reads straight back to the DHIS2 object.
- `"code-or-id"` - the object's DHIS2 code when it can serve as a stem, else the
  id, with one aggregate note per surface in the generate report naming every
  fall-back. An option set coded `SEX` gets id `d2-os-SEX-cs`, name
  `D2OS_SEX_CS`, file `terminology/CodeSystem-d2-os-SEX-cs.json`; its uncoded
  peer keeps its id-derived identity.
- `"code"` - the code always. A selected object whose code is missing, unusable,
  or colliding **refuses the run** before a single file is written, with a
  one-line error naming the offenders and the two ways out: fix the codes in
  DHIS2, or use `"code-or-id"` while migrating.

**"Can serve as a stem" is the R4 `id` bar, not the R4 `code` bar.** A stem
becomes a resource id and a canonical URL, so a code must be ASCII letters,
digits, hyphen, or dot, within the surface's stem budget - the R4 64-character
id limit for a bare stem; option sets and categories have tighter budgets
because their ids spend characters on the naming tokens and the `-cs` / `-vs` /
`-cm` suffixes - and unique among the surface's selected peers, where a code
equal to another selected object's id collides too. Peers means the id
namespace: a data set, an event program, and a tracker program stage all become
`Questionnaire-<stem>` resources, so their codes collide across the three
kinds, while a tracker program's stem - which only names its stage directory -
is a namespace of its own. Underscores disqualify:
DHIS2's own demo codes (`OU_525`, `DS_359711`) can never serve as stems. There
is **no truncation, ever** - an over-budget code falls back (or refuses, under
`"code"`) rather than being silently shortened.

**Identity changes; data does not.** Whatever the source, the DHIS2 id and the
DHIS2 code both remain as `identifier` slices on every generated resource, and
the data identifiers inside an instance example - the event's DHIS2 id, the period, the
reporting unit - never move with the naming source. Flipping the mode
re-identifies the IG - every id, canonical, and file name - which is deliberate:
it is a whole-project migration switch, not a per-object drift.

**The migration workflow.** Start on `"id"` - a compiling IG on day one,
whatever state the instance's codes are in. Run `d2w fhir validate` and watch
its **code coverage** line (selection objects whose code can serve as an
identity stem) grow as codes are cleaned up in DHIS2. Switch to `"code-or-id"`:
the filesystem itself now shows the progress, because every object with a
usable code carries a readable name and the rest are still bare ids. Keep
fixing codes - `validate` names every object that still falls back - and when
coverage is complete, set `"code"` so a regression refuses the run instead of
silently falling back. `source` is the artifact-identity dial; the separate
[`concept_code_source`](#generate) governs the concept codes *inside* a
CodeSystem and moves independently.

Whichever source is set, the stems are assigned once over the whole selection
of each surface - whether a code collides depends on the peers it is resolved
against - and every other target reads that assignment. A question's
`answerValueSet` and an example's answer coding therefore name the very
CodeSystem and ValueSet the same run writes, under any source.

The FSH name is load-bearing across the FSH/JSON boundary. A questionnaire binds
its question with `answerValueSet = Canonical(D2OS_Qdm5fPK5Ra9_VS)` - an FSH
name, not a URL - and the ValueSet it resolves to is pre-built JSON that never
enters the FSH compile. That resolves because SUSHI fishes a predefined resource
by its `name` element, and every emitted CodeSystem and ValueSet carries exactly
the FSH name the binding asks for. An id stem rides into the FSH name verbatim
(`D2OS_Qdm5fPK5Ra9_CS`); a code stem may carry hyphens and dots, which an FSH
name cannot, so it is pascal-collapsed (`BIRTH-TYPE` becomes
`D2OS_BIRTHTYPE_CS`) while the id and file name keep the code byte for byte.

**The tokens** compose artifact names by merging the prefix and kind token and
underscoring the segments after it, and ids by kebab-joining each non-empty token. With the defaults, an option set becomes
`D2` + `OS` + `_Qdm5fPK5Ra9` + `_CS` = `D2OS_Qdm5fPK5Ra9_CS`, id
`d2-os-Qdm5fPK5Ra9-cs`; a code-sourced stem rides the same rails
(`D2OS_SEX_CS` / `d2-os-SEX-cs`). Rename or drop a token and the whole IG
follows consistently.

| Token | Default | Notes |
| --- | --- | --- |
| `prefix` | `D2` | May be empty to drop it entirely. |
| `option_set` | `OS` | May be empty. Try `OptionSet` for a verbose IG. |
| `category` | `CAT` | May be empty. Names a category's pair (`D2CAT_Sex_CS` / `_VS`). |
| `organisation_unit` | `OU` | Must stay non-empty. `OrgUnit` gives `D2OrgUnit_Level_CS`. |
| `data_set` | `DS` | May be empty. Names a data set's Questionnaire (`D2DS_BfMAe6Itzgt`). |
| `program` | `PR` | May be empty. Names an event program's Questionnaire (`D2PR_VBqh0ynB2wv`). |
| `program_stage` | `PS` | May be empty. Names a tracker program stage's Questionnaire (`D2PS_A03MvHHogjR`). |

**The empty-prefix caveat.** Setting `prefix = ""` drops the token from
terminology names (`OU_Level_CS`, id `ou-level-cs`), but the two organisation-unit
profiles and the three foundation extensions - `D2Period`, `D2FormType`,
`D2AttributeValue` - keep a `D2` token anyway. FSH cannot name a
profile identically to its parent core resource, nor an extension identically to
a core datatype: `Profile: Organization` and `Extension: Period` are both
illegal. Those definitions fall back to `D2` rather than fail.

#### The canonical token registry

Keys are added to `[generate.naming]` as each generator lands, with these
defaults. `NamingConfig` carries six of them today - `option_set`, `category`,
`organisation_unit`, `data_set`, `program`, and `program_stage`; the rest are the
decided defaults for the generators still to come. Every token composes as
`{prefix}{token}_<segment>_CS`, and ids derive from the kebab of prefix plus
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
| `CAT` | category | `PS` | program stage (in code) |
| `PI` | program indicator | `TET` | tracked entity type |
| `PIG` | program indicator group | `TEI` | tracked entity |
| `VR` | validation rule | `TEA` | tracked entity attribute |
| `VRG` | validation rule group | `PRED` | predictor |
| `LS` | legend set | | |

`D2Period`, `D2FormType`, and `D2AttributeValue` are fixed names: each takes the
prefix and no token of its own.

**`CO` is reserved, and there is deliberately no `category_option` key.** A
category's options are the concepts inside that category's CodeSystem, exactly as
an option set's options are concepts inside its own - and options have no token of
their own either, for the same reason: a concept is not an artifact, so nothing
names it. `CO` stays in the registry above for a future artifact that publishes
category options in their own right. Setting a `category_option` key in
`[generate.naming]` would configure nothing.

### `[generate.option_sets]`

```toml
[generate.option_sets]
# include_ids = ["Qdm5fPK5Ra9"]     # optionSet UIDs to include; absent means all
```

UIDs only - DHIS2 option-set names are not unique. An entry matching nothing is
reported as a note rather than silently ignored. A narrowed list is still unioned
with whatever the selected data sets, event programs, and tracker program stages
bind their data elements to, so a questionnaire never points at a ValueSet the IG
does not contain
(see [Data set, event program, and tracker stage forms](#data-set-event-program-and-tracker-stage-forms)).

### `[generate.categories]`

```toml
[generate.categories]
# include_ids = ["O5P6e8yu1T6"]     # category UIDs to include; absent means all
```

Reads exactly like `[generate.option_sets]`: UIDs only, absent or empty means
every category on the instance, a non-empty list filters, and an entry matching
nothing is reported as a note. There is no closure - nothing generated today
binds a category, so the list stands on its own rather than being unioned with
what the forms reference.

DHIS2's own `default` category is a category like any other here: it is emitted
by default and it can be named in `include_ids` or left out by naming the others.

### `[generate.data_sets]`, `[generate.event_programs]`, and `[generate.tracker_programs]`

```toml
[generate.data_sets]
# include_ids = ["BfMAe6Itzgt"]     # data set UIDs; absent means all

[generate.event_programs]
# include_ids = ["VBqh0ynB2wv"]     # WITHOUT_REGISTRATION program UIDs; absent means all

[generate.tracker_programs]
# include_ids = ["IpHINAT79UW"]     # WITH_REGISTRATION program UIDs; absent means all
```

The data-definition targets: one table per form kind. They read like the terminology
and registry selections: an absent or empty list means **all** of that table's kind, a
non-empty list filters. `d2w fhir init --data-set <uid> --event-program <uid>
--tracker-program <uid>` seeds the three lists while scaffolding, which is how you narrow
a project to the handful of forms you care about.

Each table selects a different DHIS2 shape, and the shapes differ in what comes out:

- **`[generate.data_sets]`** selects aggregate data sets - one Questionnaire each,
  under `data-sets/<stem>.fsh`.
- **`[generate.event_programs]`** selects programs whose `programType` is
  `WITHOUT_REGISTRATION` - one Questionnaire each, under `event-programs/<stem>.fsh`.
  Such a program holds exactly one stage by construction, and that stage supplies the
  questions.
- **`[generate.tracker_programs]`** selects programs whose `programType` is
  `WITH_REGISTRATION` - **one Questionnaire per program stage**, under
  `tracker-programs/<program stem>/<stage stem>.fsh`. A tracker program is a sequence of
  visits rather than a single form, so each stage is its own data-capture form.

Each `<stem>` is the target's [identity stem](#the-identity-stem) - the DHIS2 id
under the default naming source.

The two program tables are read independently, each on its own terms:

- **Absent or empty** (the whole instance): every program of that table's type is a
  target, routed by its live `programType`. With both tables empty one sweep serves
  both, and a `programType` neither table maps is one aggregate note
  (`N programs have a programType the questionnaire target does not map; skipped: ...`).
- **Non-empty** (an explicit list): the table's UIDs are fetched by name and every one
  of them is routed to that table's type. A program of the other type is a loud failure
  naming the program, not a skip - you asked for that UID by name, so the run stops
  instead of quietly leaving it out. The refusal points at the table the program does
  belong under: a `WITH_REGISTRATION` program listed under `[generate.event_programs]`
  reports `a tracker program is selected under [generate.tracker_programs], which emits
  one Questionnaire per stage`, and a `WITHOUT_REGISTRATION` program listed under
  `[generate.tracker_programs]` reports `a WITHOUT_REGISTRATION program is selected
  under [generate.event_programs]`. UIDs the instance answers nothing for stay an
  aggregate note naming the table they were listed in.

### `[generate.examples]`

```toml
[generate.examples]
per_target = 1          # example QuestionnaireResponses per questionnaire target; 0 disables
source = "synthetic"    # "synthetic" (generated values) or "instance" (real values off the server)
```

How many example responses each questionnaire target gets, and where their
answers come from. `per_target` is bounded by `MAXIMUM_EXAMPLES_PER_TARGET` = 10,
so it validates in `0..10` - a larger value is a config error, not a
thousand-file run. See [Example responses](#example-responses).

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

### `[serve]`

```toml
[serve]
host = "127.0.0.1"      # interface to bind
port = 8080             # port to listen on
strict_codes = false    # refuse an answer whose code is outside the served terminology
ui = false              # also serve the capture UI at /
```

The only table `d2w fhir generate` never reads: it configures `d2w fhir serve`, and
`make serve` / `make serve-live` / `make serve-ui` read it too. A command-line flag wins over it.
See [Serving the IG](#serve-in-fhirtoml).

## Generate targets

```
d2w fhir generate                All seven, in that order, off one pass over the instance
d2w fhir generate foundation     Identifier aliases + the D2Period / D2FormType / D2AttributeValue extensions
d2w fhir generate option-sets    Option sets -> CodeSystem/ValueSet pairs
d2w fhir generate categories     Categories -> CodeSystem/ValueSet pairs
d2w fhir generate questionnaires Data sets + event programs + tracker program stages -> Questionnaire instances
d2w fhir generate examples       Example QuestionnaireResponses answering those Questionnaires
d2w fhir generate org-units      Org units -> Organization/Location instances
d2w fhir generate pages          Narrative site pages + per-artifact intros
d2w fhir generate load-set       Synthetic QuestionnaireResponse corpus into load/ (not IG source)
```

The bare `d2w fhir generate` is the one to reach for. It reads the instance once - the
questionnaire targets, the option sets, the categories, the organisation-unit slice, and
the attribute-code join - and every target builds off that single result, where seven
separate commands each open a client of their own. It reports one summary row per target.
Name a target when you want that target alone, which is what a tight edit loop on one
directory wants.

**Notes.** Each target raises aggregate notes - a selection entry that matched nothing,
an option set the closure pulled in, the geometry tally, a form skipped for a `linkId`
collision. A note is not prose: it carries a **kind**, and the kind is what the terminal
reasons about.

| Kind | What it records |
| --- | --- |
| `selection-mismatch` | A `[generate.*] include_ids` entry that matched nothing on the instance. |
| `selection-closure` | An object the selection did not name, pulled in by the closure a form binds. |
| `empty-selection` | The selection resolved to nothing, so the target emitted nothing. |
| `selection-gap` | A reference leaving the selection, so the emitted resource points at something unpublished. |
| `refused-form` | A whole form refused rather than published invalid. |
| `form-structure` | A form reshaped to fit FHIR, with every question kept. |
| `skipped-question` | A question or captured value dropped or left unanswered. |
| `answer-fallback` | An answer emitted in a weaker shape than the question asked for. |
| `instance-data-gap` | The instance holds no usable value where the target needed one. |
| `build-cost` | What the emitted volume costs the IG publisher's own build. |
| `code-fallback` | A DHIS2 code unusable as a concept code, so the UID stands in. |
| `code-collision` | A DHIS2 code claimed twice, so the loser takes the UID or no code at all. |
| `stem-fallback` | A DHIS2 code unusable as an identity stem, so the id stands in. |

The last three are **restatements of what `d2w fhir validate` already reports**: they are
this run's view of the same `missing-code`, `invalid-code`, `template-hostile-code`,
`duplicate-code`, and `code-stem-fallback` findings, on the same objects, and the validate
report says it at length with the scope and the severity attached. Every other kind is
about this project's `fhir.toml` or about a decision taken at emit time, which validate
never reads.

On a national instance eight targets of notes bury the summary table the run is actually
read from, so a bare run **counts** them - the echoes separately - and writes them all to
`reports/fhir-generate-notes.md`, grouped by target:

```
note: 3 note(s) across 2 target(s) (+8 validate echoes); full list in reports/fhir-generate-notes.md (--details to print)
```

Read that as: generation found three things worth your attention, and eight more it would
only be repeating `d2w fhir validate` to tell you about. When a run raises nothing but
echoes the line says so instead (`8 validate echo(es) across 2 target(s)`), and when it
raises no echoes at all the `(+n)` chunk is absent.

Nothing is hidden. The notes file carries every note: a target's own notes first, then its
echoes under a trailing `### Restatements of validate findings` heading, so the file reads
as what generation has to say without losing what it restated.

`--details` prints every note inline instead - both kinds, each labelled by the target that
raised it - and a run that raised none writes nothing and says nothing. A **solo** target
keeps printing all of its notes on the terminal: one target's notes are short, and you
asked for that target by name. `--json` carries the whole model, so a consumer reads the
kind rather than the prose:

```json
{"category": "code-fallback", "message": "1 option codes collided; fell back to the UID: X (Op2aaaaaaaa)", "echoes_validate": true}
```

**Progress.** Every command with an instance behind it - the bare run, each named target,
`load-set`, and `validate` - narrates its steps on stderr as they complete: a spinner with
a `Step k/N` caption on a terminal, one plain `[k/N] label: summary` line per step when
stderr is redirected, which is the form a CI log wants. `--no-progress` turns the
narration off, and `--json` implies it: in JSON mode stderr stays quiet and stdout carries
the payload alone.

Each target owns its subdirectories and syncs each one: writes what changed, leaves
what did not, deletes generated files that no longer belong. `questionnaires` owns
four under `ig/input/fsh/` (`data-sets/`, `event-programs/`, `tracker-programs/`,
`data-dictionary/`) - `tracker-programs/` is the one nested layout, a subdirectory per
program UID, and the sync prunes a subdirectory it emptied;
`foundation` and `examples` own one each under `ig/input/fsh/`; `option-sets` owns
`ig/input/resources/terminology/` for its pre-built CodeSystem and ValueSet JSON and
`categories` owns `ig/input/resources/categories/` for its own; both write their
ConceptMaps into `ig/input/resources/concept-maps/`; `org-units` owns two -
`ig/input/fsh/organization/` for its profiles and
terminology and `ig/input/resources/registry/` for the pre-built instance JSON;
`pages` owns `ig/input/pagecontent/`, which holds markdown rather than FSH.

Each terminology pair gets a directory of its own rather than sharing one, because a
JSON sync owns its target outright: it deletes every `*.json` in that directory the run
did not produce. Two targets pointed at one directory would delete each other's
documents on every run. `concept-maps/` is the one shared directory, so ownership there
is stated by file-name prefix instead: `option-sets` sweeps `ConceptMap-<its id stem>*`
and `categories` sweeps `ConceptMap-<its id stem>*`, which the `OS` / `CAT` naming
tokens keep apart. Both still converge - a dropped object takes its map with it - and
the published guide needs one `path-resource` glob rather than two.

### `foundation`

Writes `foundation/`, the part of the IG that depends on `fhir.toml` alone and
never touches DHIS2:

- **`d2-aliases.fsh`** - the `$DHIS2-OU`, `$DHIS2-OU-CODE`, `$DHIS2-OS`, and
  `$DHIS2-OS-CODE` aliases, built from `identifier_system_base`. The
  organisation-unit profiles and the Questionnaire files reference these, so this
  target is a prerequisite for a compiling IG. The pre-built JSON resolves the
  same URLs itself and writes them out in full.
- **`d2-naming-systems.fsh`** - one `NamingSystem` per alias URL, declaring what
  a DHIS2 identifier under it means. See [Identifiers](#identifiers).
- **`d2-period.fsh`** - the `D2Period` extension plus its terminology.
- **`d2-form-type.fsh`** - the `D2FormType` extension plus its terminology. See
  [Data set, event program, and tracker stage forms](#data-set-event-program-and-tracker-stage-forms).
- **`d2-attribute-value.fsh`** - the `D2AttributeValue` extension every resource
  carrying DHIS2 attribute values points at. See
  [The D2AttributeValue extension](#the-d2attributevalue-extension).
- **`d2-organisation-unit.fsh`** - the `D2OrganisationUnit` extension, a reference to
  the published `Location` of the unit an event was captured at.
- **`d2-organisation-unit-level.fsh`** - the `D2OrganisationUnitLevel` extension, the
  hierarchy level a published `Location` sits at, as a `Coding` of the level CodeSystem.
- **`d2-tracker-enrollment.fsh`** - the `D2TrackerEnrollment` extension, the DHIS2
  enrollment UID an event belongs to, as an `Identifier` pinned to the
  `{base}/id/tracker-enrollment` system.
- **`d2-responses.fsh`** - the `D2AggregateResponse`, `D2EventResponse`, and
  `D2TrackerEventResponse` profiles every captured `QuestionnaireResponse` has to
  meet. See [The capture contract](#the-capture-contract).
- **`d2-generate-operation.fsh`** - the `D2GenerateOperation` OperationDefinition
  defining `$generate`, the instance-level operation that answers a served
  `Questionnaire` with a synthetic response postable straight back. See
  [`$generate`](#generate).
- **`d2-capture-server.fsh`** - the `D2CaptureServer` CapabilityStatement stating
  the interactions a server accepting those responses supports. It stays a
  `kind #requirements` statement of what *any* DHIS2 capture server has to do, so it
  does not declare `$generate` - a server that only receives captures is still
  conformant.

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

### The D2AttributeValue extension

A DHIS2 `Attribute` is the metadata extensibility point: any object can carry
typed key-value pairs under `attributeValues`, and instances use them for the
codes that tie DHIS2 to everything around it - a national registry id on a
facility, an external warehouse key, an ICD-10 code on a data element. Those
pairs are instance-specific by definition, so no FHIR element holds them and they
travel as a complex extension instead.

`D2AttributeValue` carries one such pair:

| Sub-extension | Type | Cardinality | Meaning |
| --- | --- | --- | --- |
| `attributeId` | `string` | 1..1 | The UID of the DHIS2 attribute the value belongs to |
| `attributeCode` | `string` | 0..1 | The attribute's DHIS2 code, absent when the instance left it unset |
| `value` | `string` | 1..1 | The value the object holds, as DHIS2 sends it |

Its `^context` names the five resource types that carry it: `Organization`,
`Location`, `CodeSystem`, `ValueSet`, and `Questionnaire`.

**`attributeCode` is optional because DHIS2 leaves most attributes uncoded.**
On the Lao instance eleven of twelve attributes have no `code` at all. An
uncoded attribute gets no `attributeCode` sub-extension rather than an empty
one - an empty code would claim the instance coded that attribute.

**`value` is a string whatever the attribute declares.** DHIS2 sends every
attribute value as a string regardless of the attribute's `valueType`, and one
real attribute on that instance carries a whole GeoJSON document that way. The
extension takes the wire value as it stands rather than re-typing it.

**The code is a join, resolved once per generate run.** The wire shape of an
attribute value is `{"attribute": {"id": "..."}, "value": "..."}` - an id and
nothing else, with no code, no name, and no value type. So each generate target
calls `resolve_attribute_code_index`, which reads `id,code` for every attribute
off `/api/attributes` **unpaged**: DHIS2 answers 50 attributes to a page by
default, and an instance defining more than one page of them would otherwise
lose the tail of the join silently. Attributes DHIS2 left without a code are
absent from the index rather than present with an empty entry, which is what the
optional `attributeCode` reads from.

**Where the values land today.** Organisation units carry them on both halves of
the registry pair, option sets on both the CodeSystem and the ValueSet, and data
sets, event programs, and tracker program stages on their Questionnaire.
Concept-level attribute values -
those on individual data elements and options - are not emitted: a
`CodeSystem.concept` has no carrier chosen for them yet, and that choice is its
own decision, sized in
[fhir roadmap section 9.2](../project/fhir-roadmap.md#92-mid-term). Nor is a
value promoted to `identifier` when DHIS2 marks its attribute `unique`; every
value rides the extension, and the identifier shape is the other half of that
same roadmap entry.

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
  `identifier` business identifiers, under `{base}/id/option-set` and
  `{base}/id/option-set-code` - the same two URLs the `$DHIS2-OS` /
  `$DHIS2-OS-CODE` aliases name, written out in full because these resources
  ship as JSON rather than FSH.

- **Questionnaires** carry the source object's pair: a data set through `$DHIS2-DS` /
  `$DHIS2-DS-CODE`, an event program through `$DHIS2-PROGRAM` /
  `$DHIS2-PROGRAM-CODE`, and a tracker program stage through `$DHIS2-PS` /
  `$DHIS2-PS-CODE`.
- **Tracker stage Questionnaires carry a third slice**, `$DHIS2-PROGRAM` holding the
  UID of the program the stage belongs to. That slice is the grouping handle: a
  program's stages are one search on any FHIR server, in the order the server returns
  them.

    ```
    GET Questionnaire?identifier=http://dhis2.org/fhir/id/program|IpHINAT79UW
    ```

**A unique attribute's values are identifiers.** A DHIS2 attribute value is an
arbitrary key-value pair, so it normally rides the
[`D2AttributeValue` extension](#the-d2attributevalue-extension). An attribute DHIS2
declares **unique** is a different thing: its value names the object rather than
annotating it, which is what a FHIR `Identifier` is for. Those values leave the
extension and join the resource's identifier list - after the UID and code slices, so
the order stays stable across runs - under a namespace of their own:

```
{base}/attribute/{attributeUid}
```

The namespace keys on the attribute **UID**, not its code: a DHIS2 attribute code may
hold spaces, and a system URI may not. Every emitting surface follows the same rule -
Organization and Location, an option set's and a category's CodeSystem/ValueSet pair,
and a Questionnaire.

These per-attribute namespaces are declared **by convention rather than as
NamingSystems**, and deliberately so: the foundation layer is built from `fhir.toml`
alone and never reads an instance, so it cannot know which attributes exist, let alone
which are unique. A NamingSystem naming an attribute the instance does not have would
be worse than none. What `d2-naming-systems.fsh` declares is the fixed family below.

**Every system is declared as a NamingSystem.** `foundation/d2-naming-systems.fsh`
emits one `NamingSystem` per identifier system - a UID system and a code system for
each of the organisation unit, option set, category, data set, program, data element,
category option combo, and program stage, plus a UID system alone for the tracked
entity and the tracker enrollment. Those last two are data objects rather than
metadata: DHIS2 gives them no `code` attribute, so there is no code system to declare.
Each declaration is `kind = #identifier` with a single
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

Two pre-built FHIR JSON documents per option set, into
`ig/input/resources/terminology/`:

```
ig/input/resources/terminology/CodeSystem-d2-os-<stem>-cs.json
ig/input/resources/terminology/ValueSet-d2-os-<stem>-vs.json
```

`<stem>` is the set's [identity stem](#the-identity-stem) - the DHIS2 UID under
the default `source = "id"`, the set's code under the code sources.

The CodeSystem points back at the ValueSet through `valueSet`, and the ValueSet
includes the CodeSystem's URL through `compose.include`. A 235-option-set
instance emits roughly 470 files; `generate` writes the full output in a few
minutes.

These are predefined resources: the publisher loads them verbatim and they never
enter the FSH compile. `sushi-config.yaml` declares `path-resource:
input/resources/terminology/*` so SUSHI recurses into the sub-folder, and
`ig/input/resources/` is gitignored the way generated output should be. See
[Build time and the two caches](#build-time-and-the-two-caches) for what that is
worth.

**Questionnaires bind by FSH name.** A question reads
`answerValueSet = Canonical(D2OS_<UID>_VS)` and resolves to one of these JSON
documents, because SUSHI fishes a predefined resource by its `name` element and
every emitted CodeSystem and ValueSet carries exactly the FSH name the binding
asks for.

Concept codes are unique within a set by construction. Options are ordered by
`sortOrder`; each one asks for a code, and if that code is already taken the
option falls back to its UID, aggregated into one note. A CodeSystem that
repeats a concept code is invalid, so this is enforced rather than warned
about. The example responses code their answers from the same assignment, so a
`valueCoding` always names a concept this pair really carries.

**Both halves carry the set's DHIS2 attribute values**, as one
[`D2AttributeValue` extension](#the-d2attributevalue-extension) per value on the
CodeSystem and the same list on the ValueSet. The values on the *options* inside
the set are not emitted, because a `CodeSystem.concept` has no carrier chosen for
them.

**A ConceptMap per set takes the concept codes back to DHIS2.** Beside the pair,
the target writes one map into the shared ConceptMap directory:

```
ig/input/resources/concept-maps/ConceptMap-d2-os-<stem>-cm.json
```

It carries the FSH-style name `D2OS_<stem>_CM` and the same identity stem the
pair's ids come from - the triple shares one stem. See
[ConceptMaps: the route back to DHIS2](#conceptmaps-the-route-back-to-dhis2) for
the shape, the two groups, and how `$translate` serves them.

The target owns `terminology/` outright and sweeps it, plus its own `ConceptMap-`
prefix inside `concept-maps/`: JSON left there by a previous run that this run does
not produce is deleted, so renaming or dropping an option set converges rather than
accumulating.

### `categories`

A DHIS2 category is one axis of a disaggregation - Sex, EPI/nutrition age - and
its category options are the values along that axis. That is the shape of an
option set and its options, so a category emits the same pair, built by the same
concept-code assignment, into its own predefined-resource directory:

```
ig/input/resources/categories/CodeSystem-d2-cat-<stem>-cs.json
ig/input/resources/categories/ValueSet-d2-cat-<stem>-vs.json
```

`<stem>` is the category's [identity stem](#the-identity-stem) - the DHIS2 UID
under the default `source = "id"`, the category's code under the code sources.

This is the terminology the disaggregated half of the data layer codes against.
Each pair carries the `CAT` naming token (`D2CAT_Sex_CS` / `D2CAT_Sex_VS`), the
category's own DHIS2 UID and code as `identifier` business identifiers, and the
category's DHIS2 attribute values as
[`D2AttributeValue` extensions](#the-d2attributevalue-extension) on both halves.

**The concepts are the category options.** They keep the category's own
`categoryOptions` order - DHIS2 holds that field as an ordered list, so the order
the instance answers with is the sort order - and each concept carries the
complementary DHIS2 identifier as a `dhis2-code` or `dhis2-id` property, exactly
as an option set's concepts do. Under `concept_code_source = "code"` the same
fall-backs apply: an option whose code is not a valid FHIR code takes its UID with
a note, and an option with no code left to take is skipped with its own note
rather than emitted as a duplicate concept.

**A ConceptMap per category takes the concept codes back to DHIS2**, written
beside the option-set maps in the shared directory:

```
ig/input/resources/concept-maps/ConceptMap-d2-cat-<stem>-cm.json
```

It carries the FSH-style name `D2CAT_<stem>_CM` and the category's own identity
stem, so the triple stays in step. See
[ConceptMaps: the route back to DHIS2](#conceptmaps-the-route-back-to-dhis2).

**A dedicated pair directory, not a shared one.** `categories/` is separate from
`terminology/` because each JSON sync deletes every `*.json` in its target that
the run did not produce. Sharing one directory would have the two targets deleting
each other's documents. `concept-maps/` is the deliberate exception: both families
publish there and each sweeps only the files its own id stem names, so the published
guide needs one `path-resource` glob for the whole terminology-mapping story.

**The scaffolded `sushi-config.yaml` declares the glob.** Its `path-resource`
block names `input/resources/categories/*` alongside the registry and terminology
globs. SUSHI recurses into sub-folders of `input/resources` on its own; the IG
Publisher does not, so without that line the pairs compile fine and are dropped
from the published guide. A project scaffolded before the glob existed picks it up
with [`d2w fhir init --refresh`](#refreshing-a-projects-scaffold).

Narrow the selection with
[`[generate.categories]` `include_ids`](#generatecategories) - absent or empty
means every category, DHIS2's own `default` category included.

### ConceptMaps: the route back to DHIS2

Every concept the generator writes is a DHIS2 object under a FHIR spelling, and a
consumer holding one has exactly one question: **which DHIS2 object is this?** The
concept properties answer it for a reader; a ConceptMap answers it for a machine, and
a terminology server can serve that answer over `$translate`.

Two targets publish maps, one family each, into one directory:

```
ig/input/resources/concept-maps/ConceptMap-d2-os-<stem>-cm.json    option sets
ig/input/resources/concept-maps/ConceptMap-d2-cat-<stem>-cm.json   categories
```

| Family | Written by | Question it answers | Target namespaces |
| --- | --- | --- | --- |
| Option sets | `option-sets` | Which DHIS2 **option** does this answer code name? | `<base>/id/option`, `<base>/id/option-code` |
| Categories | `categories` | Which DHIS2 **category option** does this disaggregation code name? | `<base>/id/category-option`, `<base>/id/category-option-code` |

Each map takes its id, its FSH name, and its URL from the same
[identity stem](#the-identity-stem) its CodeSystem and ValueSet do, carries the source
object's UID as its single `identifier` (`<base>/id/option-set` for a set,
`<base>/id/category` for a category), and points `sourceCanonical` at its own ValueSet.
All four DHIS2 namespaces are declared as NamingSystems by the
[`foundation`](#foundation) target, so a validator meeting one has a definition to
resolve.

#### The two-group shape

A map holds two groups, both sourced from the object's own CodeSystem: one onto the
DHIS2 UID namespace, one onto the DHIS2 code namespace. An option set:

```json
{
  "resourceType": "ConceptMap",
  "id": "d2-os-birth-type-cm",
  "url": "http://example.org/fhir/ConceptMap/d2-os-birth-type-cm",
  "identifier": { "system": "http://dhis2.org/fhir/id/option-set", "value": "Xa1b2c3d4e5" },
  "name": "D2OS_BirthType_CM",
  "title": "Birth type",
  "status": "draft",
  "experimental": true,
  "sourceCanonical": "http://example.org/fhir/ValueSet/d2-os-birth-type-vs",
  "group": [
    {
      "source": "http://example.org/fhir/CodeSystem/d2-os-birth-type-cs",
      "target": "http://dhis2.org/fhir/id/option",
      "element": [
        {
          "code": "kRRUtYaGett",
          "display": "Natural Birth",
          "target": [{ "code": "kRRUtYaGett", "equivalence": "equal" }]
        }
      ]
    },
    {
      "source": "http://example.org/fhir/CodeSystem/d2-os-birth-type-cs",
      "target": "http://dhis2.org/fhir/id/option-code",
      "element": [
        {
          "code": "kRRUtYaGett",
          "display": "Natural Birth",
          "target": [{ "code": "NB", "equivalence": "equal" }]
        }
      ]
    }
  ]
}
```

And a category, the same shape over the category-option namespaces:

```json
{
  "resourceType": "ConceptMap",
  "id": "d2-cat-sex-cm",
  "url": "http://example.org/fhir/ConceptMap/d2-cat-sex-cm",
  "identifier": { "system": "http://dhis2.org/fhir/id/category", "value": "O5P6e8yu1T6" },
  "name": "D2CAT_Sex_CM",
  "title": "Sex",
  "status": "draft",
  "experimental": true,
  "sourceCanonical": "http://example.org/fhir/ValueSet/d2-cat-sex-vs",
  "group": [
    {
      "source": "http://example.org/fhir/CodeSystem/d2-cat-sex-cs",
      "target": "http://dhis2.org/fhir/id/category-option",
      "element": [
        {
          "code": "TNYQzTHdoxL",
          "display": "Female",
          "target": [{ "code": "TNYQzTHdoxL", "equivalence": "equal" }]
        }
      ]
    },
    {
      "source": "http://example.org/fhir/CodeSystem/d2-cat-sex-cs",
      "target": "http://dhis2.org/fhir/id/category-option-code",
      "element": [
        {
          "code": "TNYQzTHdoxL",
          "display": "Female",
          "target": [{ "code": "F", "equivalence": "equal" }]
        }
      ]
    }
  ]
}
```

The rules are the same for both families:

- **`equivalence = #equal` on every row**, which R4 makes mandatory. The concept and
  the target identifier name the same DHIS2 object under two identifier conventions -
  this is not a translation between two vocabularies.
- **The UID group is emitted under either `concept_code_source`**, identity mapping
  included, so a consumer never has to know which mode produced the guide.
- **The code group is emitted only where there is something to map.** A member DHIS2
  left uncoded, or coded with something that is not a valid FHIR `code`, has no target
  code and is left out; an object where that is true of every member emits the UID
  group alone, because an R4 group with no element is invalid. An object with no
  concepts at all emits no map.
- **The rows come from the same concept assignment the CodeSystem's concepts do**, so
  a mapping can only ever name a concept the pair really carries.
- **`source[x]` is the pair's ValueSet and `target[x]` is absent.** R4 types both as
  value sets; the DHIS2 identifier namespaces are not value sets, so naming one there
  would be a lie. They appear where R4 wants systems: `group.target`.
- **`identifier` is a single element, not a list.** R4 gives `ConceptMap.identifier`
  `0..1` where it gives CodeSystem and ValueSet `0..*`.

#### UID targets or code targets?

Both groups are always there to be asked; which one a consumer wants depends on what
it is about to do with the answer.

- **Reach for the UID namespace** (`id/option`, `id/category-option`) when the answer
  is going into a DHIS2 API call. UIDs are what `/api/dataValueSets` and the tracker
  endpoints accept, they are unique instance-wide, and every member has one - the group
  is complete by construction.
- **Reach for the code namespace** (`id/option-code`, `id/category-option-code`) when
  the answer is going in front of a human, into a report, or into a system keyed on the
  instance's business codes. DHIS2 codes are optional and not guaranteed unique, so the
  group can be partial or absent; treat a miss as "this member has no usable code",
  not as an error.

#### The publisher needs the glob

`input/resources/concept-maps/*` sits in the scaffolded `sushi-config.yaml`
`path-resource` block beside the terminology, category, and registry globs - one glob
covers both families, because both write into the one directory. SUSHI recurses into
sub-folders of `input/resources` on its own; the IG Publisher does not, so without it
the maps compile fine and are dropped from the published guide. A project scaffolded
before the glob existed picks it up with
[`d2w fhir init --refresh`](#refreshing-a-projects-scaffold).

Neither target owns the directory outright. A JSON sync normally deletes every `*.json`
in its target the run did not produce, which would have `d2w fhir generate option-sets`
sweeping away the category maps; instead each target sweeps only the file-name prefix
its own id stem produces (`ConceptMap-d2-os-`, `ConceptMap-d2-cat-`). Both still
converge: drop a category from the selection and its map goes with its pair.

### Data set, event program, and tracker stage forms

A DHIS2 data set, a DHIS2 event program, and one stage of a DHIS2 tracker program are
all *data-capture forms*, and FHIR already has that resource: `Questionnaire`.
`d2w fhir generate questionnaires` writes one file per selected target plus two support
CodeSystem/ValueSet pairs, across four directories named for what they hold, and the
[organisation-unit assignment](#organisation-unit-assignment) of every form that has a
narrower one into a fifth:

```
ig/input/fsh/data-sets/<stem>.fsh         One Questionnaire per data set
ig/input/fsh/event-programs/<stem>.fsh    One Questionnaire per event program
ig/input/fsh/tracker-programs/            One Questionnaire per program stage,
  <program stem>/<stage stem>.fsh         nested under the program it belongs to
ig/input/fsh/data-dictionary/             The shared data-element and
                                          category-option-combo terminology
ig/input/resources/assignments/           One List of Locations per form whose
  List-<id>.json                          assignment narrows the registry
```

`<stem>` is each target's [identity stem](#the-identity-stem) - the DHIS2 UID
under the default `source = "id"`, the object's code under the code sources -
and it carries the `Questionnaire-<stem>` resource id and canonical URL inside
the file too.

The command keeps the name `questionnaires` - it says what it does, not where the
files land. Each of the three selection tables reads like every other selection in
`fhir.toml`: absent or empty means all of that kind on the instance, so with none of
the tables written every data set, every event program, and every stage of every
tracker program is a target. List UIDs to narrow it:

```toml
[generate.data_sets]
include_ids = ["BfMAe6Itzgt"]       # Child Health

[generate.event_programs]
include_ids = ["VBqh0ynB2wv"]       # Malaria case registration

[generate.tracker_programs]
include_ids = ["IpHINAT79UW"]       # Child Programme - one Questionnaire per stage
```

```bash
# Or seed those lists while scaffolding - repeatable, and entirely offline:
# the UIDs are written to fhir.toml as given, never checked against an instance.
d2w fhir init my-ig --data-set BfMAe6Itzgt --event-program VBqh0ynB2wv --tracker-program IpHINAT79UW
```

**Narrowing is how a project stays reviewable.** A national instance carries hundreds
of forms and a tracker program multiplies by its stage count, so an IG meant for
review names the handful of UIDs it is about rather than compiling the whole database.

**What one form becomes.** The instance is `Usage: #definition` with the bare UID as
its `id` and `<canonical>/Questionnaire/<uid>` as its `url`, and both DHIS2
identifiers - `$DHIS2-DS` / `$DHIS2-DS-CODE` for a data set, `$DHIS2-PROGRAM` /
`$DHIS2-PROGRAM-CODE` for an event program, `$DHIS2-PS` / `$DHIS2-PS-CODE` for a
tracker program stage. `Questionnaire.name` composes from the naming tokens
(`D2DS_BfMAe6Itzgt`, `D2PR_VBqh0ynB2wv`, `D2PS_A03MvHHogjR`) and `title` is the DHIS2
name.

**A tracker stage form carries its program.** The `id` is the *stage* UID, so a stage
resolves on its own, and three things name the program around it: the `title` reads
`<program name> - <stage name>` ("Child Programme - Birth"), the file sits under
`tracker-programs/<program UID>/`, and a third identifier slice holds the program UID
under `$DHIS2-PROGRAM` - the search handle that selects a whole program's stages (see
[Identifiers](#identifiers)).

**`subjectType` says who the form is answered for.** A data set and an event program
declare `#Location` - a DHIS2 form is answered *for an organisation unit*. A tracker
stage declares `#Patient`: the form is answered for the enrolled person, and the
organisation unit rides the response as an extension instead.

| DHIS2 | FHIR |
| --- | --- |
| Section | `item` with `type = #group`, `linkId` the section UID |
| Data element | child `item`, `linkId` the DE UID, `text` its form name (else its name) |
| `valueType` | the item `type` (see the table below) |
| Data element with an option set | `type = #choice` plus `answerValueSet` pointing at that set's generated ValueSet |
| Compulsory program-stage element | `required = true` |
| Non-default category combo, on a data set form | the question becomes a `#group` with one child per category option combo, `linkId` `<deUid>.<cocUid>`; each child asks the element's own question, so it repeats the element's item type, `answerValueSet`, `repeats`, and bounds |
| Non-default category combo, on a program form | the question stays flat: an event data value carries no `categoryOptionCombo`, so a form must not ask a question the capture endpoint cannot accept an answer to |

**A form whose `linkId`s are not unique is skipped.** Sections and data elements
draw their UIDs from one DHIS2 pool, so a single form can reuse one UID on a group
and on a question - and then two items answer to one `linkId`. R4 forbids that
outright (`que-2`), and a response answering that `linkId` would name two questions
at once, so the whole form is left out of the run with an aggregate note naming it
and the clashing id. Its peers are emitted as usual; the collision is a fact about
one form, not about the target.

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
| `REFERENCE` | `string` | A bare UID - this guide publishes no FHIR resource for the referenced object. |
| `TRACKER_ASSOCIATE` | `string` | v41/v42 only; a bare UID - this guide publishes no FHIR resource for the referenced object. |
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
response can be read back to DHIS2 without consulting the questionnaire. These two
are FSH, under `ig/input/fsh/data-dictionary/` - a different tree from the pre-built
option-set JSON in `ig/input/resources/terminology/`, and two files that carry
enough concepts to dominate what the FSH compile costs (see
[Build time and the two caches](#build-time-and-the-two-caches)). Each of the four
directories is swept against its own files, so narrowing the data-set selection
deletes only the data-set questionnaires that left it. The `tracker-programs/` sweep
walks its per-program subdirectories, and a subdirectory it emptied is removed with
its files - a program dropped from the selection leaves no folder behind.

**The option-set closure.** When `[generate.option_sets] include_ids` narrows the
terminology and a selected form binds a question to an option set outside that
list, the set is added anyway and the run says so in a note. An empty option-set list
already means every option set, so the union is a no-op there.

**Safeguards, loud when you named the UID.** The two program tables select opposite
`programType`s, so a UID listed under the wrong one fails the run by name rather than
being quietly reshaped: a `WITH_REGISTRATION` program under `[generate.event_programs]`
is refused with `a tracker program is selected under [generate.tracker_programs], which
emits one Questionnaire per stage`, and a `WITHOUT_REGISTRATION` program under
`[generate.tracker_programs]` is refused with `a WITHOUT_REGISTRATION program is
selected under [generate.event_programs]`. You named that UID, so silence would be a
lie. A listed UID the instance answers nothing for is reported as a note naming its
table. With an absent or empty list the whole instance is the target, and refusing
would make that mode unusable, so the sweep routes each program by its live
`programType` and collects the types neither table maps into one aggregate note. Data
elements no section references are emitted after the sectioned ones, also with a note.

**`D2FormType`.** Every generated Questionnaire states which kind of DHIS2 form it
came from twice: as `Questionnaire.code` (`D2FormType_CS#aggregate`, `#event`, or
`#tracker-event`) and
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

**Attribute values.** A data set's, event program's, or program stage's DHIS2
attribute values ride onto its Questionnaire as one
[`D2AttributeValue` extension](#the-d2attributevalue-extension) each, in the order
DHIS2 returned them. The data-element attribute values inside the form are not
emitted; the `data-dictionary` CodeSystems carry concepts, which have no chosen
carrier for them.

### Organisation-unit assignment

DHIS2 scopes every data set and every program to the organisation units it is
*assigned to*. A capture against a unit outside that scope is not a malformed
submission - it is a perfectly valid FHIR document DHIS2 refuses at write time with
`E1029`. So the scope is published, as one `List` of Locations per form:

```json
{
  "resourceType": "List",
  "id": "d2-ds-BfMAe6Itzgt-org-units",
  "identifier": [{ "system": "http://dhis2.org/fhir/id/data-set", "value": "BfMAe6Itzgt" }],
  "status": "current",
  "mode": "snapshot",
  "title": "Child Health - assigned organisation units",
  "entry": [{ "item": { "reference": "Location/ImspTQPwCqd" } }]
}
```

The form names it through one extension, `D2OrganisationUnitAssignment`, contexted on
`Questionnaire` and valued as `Reference(List)`:

```
* extension[D2OrganisationUnitAssignment].valueReference = Reference(List/d2-ds-BfMAe6Itzgt-org-units)
```

**`List`, not `Group`.** A group of places is the obvious modelling instinct, and R4
does not allow it: `Group.member.entity` is bound to
`Reference(Patient | Practitioner | PractitionerRole | Device | Medication | Substance | Group)`,
and `Group.type` is a required binding over `person | animal | practitioner | device |
medication | substance`. A Location is neither a legal member nor a legal type, so a
Group of Locations is an artifact the validator rejects. `List.entry.item` is
`Reference(Resource)` and `List.mode` says `snapshot`, which is exactly what an
assignment is.

**Absence means the whole registry.** The artifact is emitted **only when the assignment
is a proper subset of the published organisation-unit selection.** A form assigned to
every unit the registry publishes - the common national case - publishes nothing, and a
consumer meeting a form with no assignment extension may report it for any unit in the
registry. That is what a consumer already assumed before this artifact existed, so the
economy costs nothing in meaning: on an instance where most forms are national, the IG
grows by a handful of small documents rather than by one per form.

The assignment is intersected with the published selection before it is judged, so a
unit DHIS2 assigns but `[generate.organisation_units]` does not publish can never make an
assignment look narrower than it is. A form whose intersection is *empty* publishes an
empty List and one note: no published unit may report it, which is worth being told.

**Tracker stages share their program's List.** DHIS2 hangs the assignment on the
program, not on the stage, so every stage Questionnaire of one program references the
same `d2-pr-<program stem>-org-units` artifact. A data set's List rides the `DS` naming
token and its own stem, a program's the `PR` token and its own.

**What the facade does with it.** `d2w fhir serve` reads the List a submitted form names
and grades the organisation unit the response reports for - the `subject` on an aggregate
or event response, the `D2OrganisationUnit` extension on a tracker event, and every
`ORGANISATION_UNIT` answer - against it. A unit outside the assignment takes the same
dial [a coded answer](#coded-answers-lenient-by-default) takes: a warning on the receipt
by default, a 422 under `--strict-codes`. A form that publishes no List, or one the
facade does not serve, is checked against nothing. `$generate` draws its Location from
the assignment when there is one, so a generated response stays postable and forwardable.

### Example responses

A `Questionnaire` says what a DHIS2 form asks. A `QuestionnaireResponse` says what
an answer to it looks like, which is the thing an implementer actually reads before
writing an integration. `d2w fhir generate examples` writes one
`Usage: #example` response per example into its own directory:

```
ig/input/fsh/examples/<target stem>-<n>.fsh
```

`<target stem>` is the form's [identity stem](#the-identity-stem) - the DHIS2
UID under the default `source = "id"`. The stem also drives every `Location/...`
reference an example answers with; the data identifiers inside the example -
the event's DHIS2 id, the period, the reporting unit - are data, not identity, and
never move with the naming source.

```toml
[generate.examples]
per_target = 1          # responses per questionnaire target; 0 disables the target entirely
source = "synthetic"    # "synthetic" or "instance"
```

The targets are the same `[generate.data_sets]` / `[generate.event_programs]` /
`[generate.tracker_programs]` selection the questionnaires use, with the same
all-mode and routing rules - an example is always generated against a form the IG
contains, and a tracker program contributes one example target per stage.

**What one response carries.** `questionnaire` points at the target's canonical and
`status` at how far the capture got. The response states its DHIS2 form kind through
the same `D2FormType` extension the `Questionnaire` carries. A data-set response
carries `subject` as a `Location` plus the full `D2Period` extension - the ISO
identifier, the period type, and the resolved date range. An event response carries
`subject` as a `Location` and `authored` instead, taken from the event's `occurredAt`.
A tracker-event response carries `authored` the same way, but its `subject` is the
tracked entity as a logical `Patient` reference and its organisation unit rides the
`D2OrganisationUnit` extension - see
[The capture contract](#the-capture-contract) for the full shape.

The items **mirror the questionnaire**: section groups nest their questions, and a
disaggregated data element nests one child per category option combo under
`<deUid>.<cocUid>` - the same key a DHIS2 data value carries. Answers are typed
from the data element's `valueType` (integers to `valueInteger`, `NUMBER` /
`PERCENTAGE` / `UNIT_INTERVAL` to `valueDecimal`, `BOOLEAN` / `TRUE_ONLY` to
`valueBoolean`, the temporals to `valueDate` / `valueDateTime` / `valueTime`,
option-set-bound questions to a `valueCoding` into that set's generated
CodeSystem, everything else to `valueString`). A temporal answer clears the
calendar, the clock, and the R4 offset range before it is emitted, so an
impossible stored value never reaches the compiler. A value that will not cast, or
an option code no option carries, is answered as a string and counted in one
aggregate note per run rather than emitted invalid; an answer selecting an option
the CodeSystem holds no concept for is left unanswered and counted the same way,
and so is an `ORGANISATION_UNIT` answer naming a unit outside
[`[generate.organisation_units]`](#generateorganisation_units) - the IG publishes
no Location for it, so the reference would dangle.

**`authored` and every `DATETIME` answer carry an offset.** DHIS2 serves both
without one, and R4 requires one on any `dateTime` carrying a time, so the
generator supplies it: the offset [`[generate] timezone`](#generate) stood at on
that very timestamp, or `Z` when the project names no zone. Set the zone once and
every emitted timestamp in the IG follows.

#### `source = "synthetic"` (the default)

No data endpoint is called. Values are generated locally from a seed that is the
leading 64 bits of `sha256("<targetUID>:<n>")` - not Python's `hash`, which is
salted per process - so regenerating produces the same file, on any machine, in
any interpreter. Every question is answered, every option combo of a
disaggregated element is filled, `TRUE_ONLY` is always `true`, and an
option-set-bound question picks a real concept from the set the IG publishes.

A tracker-event example draws its tracked entity and enrollment UIDs off the same
seeded generator, so the pair a stage's example points at is stable across runs too -
deterministic placeholders, not identifiers any instance holds.

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
  selected by `program=<uid>` and ordered by `occurredAt:desc`. Each event becomes one
  response keyed by the event UID, with the DHIS2 event status mapped onto the
  response status (`COMPLETED` to `completed`, `ACTIVE` to `in-progress`, `SKIPPED`
  to `stopped`, and the scheduled / overdue / visited states to `completed`).
- **Tracker program stages** read the same endpoint per stage, selected by
  `programStage=<uid>` alongside its `program=<uid>` - DHIS2 answers `400` to a
  `programStage` read that omits the program even though the stage pins it
  ([BUGS.md #67](../project/upstream-quirks.md#67-get-apitrackereventsprogramstageuid-demands-program-even-though-the-stage-pins-it)).
  The `fields` list adds `enrollment` and `trackedEntity`, the two UIDs the tracker-event
  contract demands, and status and `authored` map exactly as they do for an event
  program.

A target the instance holds nothing for is one aggregate note, never a failure -
a demo database whose newest data predates the six-period window simply yields no
example for that data set.

An event the instance answered with no `enrollment` or no `trackedEntity` still
becomes an example: the emitter declares the base `QuestionnaireResponse` instead of
`D2TrackerEventResponse`, because the tracker contract's two required facts are not
there to state, and the run reports how many examples degraded that way in one
aggregate note. The example is never dropped - a form with a real captured answer in
it is worth reading even when its tracker context is incomplete.

**The production-instance caveat.** Instance-sourced examples embed real captured
values, real organisation units, and real reporting periods into a document you
are about to publish. That is exactly what you want from a demo server and
exactly what you do not want from a production one. `synthetic` is the default for
that reason: switching to `instance` is a deliberate act, and the generated
`examples/` directory is worth reading before the IG leaves your machine.

### `org-units`

This target writes two trees. The definitional half is FSH under
`ig/input/fsh/organization/`:

- **`profiles.fsh`** - the `D2Organization` and `D2Location` profiles.
- **`org-unit-levels.fsh`** - the level CodeSystem/ValueSet backing
  `Organization.type` and the Location's `D2OrganisationUnitLevel` extension, covering
  the levels actually present in the selection.
- **`org-units-terminology.fsh`** - only with `terminology = true`.

The registry itself is pre-built FHIR JSON under `ig/input/resources/registry/`,
two files per unit:

- **`Organization-<stem>.json`** - the legal entity.
- **`Location-<stem>.json`** - the physical place.

`<stem>` is the unit's [identity stem](#the-identity-stem) - the DHIS2 UID under
the default `source = "id"`, the unit's code under the code sources - and both
resource ids, the `Location.managingOrganization` reference, and every `partOf`
follow it. `partOf` mirrors the DHIS2 hierarchy on both, as a relative reference
(`Organization/<stem>`, `Location/<stem>`). A unit whose parent falls outside the
selection omits `partOf` and is reported, never dropped silently. A unit whose
`closedDate` has passed carries `active: false` and `status: "inactive"`.

**Both halves carry the unit's DHIS2 attribute values**, as one
[`D2AttributeValue` extension](#the-d2attributevalue-extension) per value. This is
where they are densest on a real instance: 244 of 300 organisation units on the
Lao instance carry at least one. On the Location the order is a contract - the
GeoJSON boundary extension is emitted first, the attribute values follow it in the
order DHIS2 returned them, and the level closes the list, so a regenerate of an
unchanged unit produces a byte-identical file and the sync reports it unchanged.

**Every Location states its level.** The `D2Location` profile requires one
`D2OrganisationUnitLevel` extension, whose `valueCoding` is the `level-<n>` code of the
same `org-unit-levels.fsh` CodeSystem that backs `Organization.type` - so a consumer
reads a place's level off the resource instead of counting `partOf` hops up the tree.
The Organization of the same unit carries no such extension: it states the same coding
as `Organization.type`, and a level is a property of the place in the hierarchy.

**The profiles get one worked example each.** The registry ships as JSON SUSHI never
compiles, so `D2Organization` and `D2Location` would otherwise publish no example at
all. `organization/registry-examples.fsh` fills that gap with a curated pair -
`D2OrganizationExample` and `D2LocationExample`, `Usage: #example`, drawn from the
selection's own **root** unit, so the publisher validates both profiles against a UID,
code, name, and level the instance really holds. They carry what the profiles constrain
and nothing more: no boundary attachment, no attribute values - a base64 GeoJSON blob
illustrates the encoding rather than the contract, and the registry's JSON instances are
where a consumer reads a unit in full. They live beside the profiles in
`organization/`, not under `examples/`, because that directory is swept by the examples
target and its sync deletes every file it did not produce.

**Why JSON rather than FSH.** SUSHI loads `input/resources` and the sub-folders
declared in `sushi-config.yaml` as *predefined resources*: they go into a virtual
package, `sushi-local#LOCAL`, exactly as written, with no FSH parse and no
conversion step. The registry and the option-set terminology are the two largest
things in the IG, and this is what keeps both out of the compile entirely - see
[Registry scale](#registry-scale) for the measurements.

That is also why the scaffolded `sushi-config.yaml` declares a `path-resource`
glob for each predefined-resource sub-folder:

```yaml
parameters:
  path-resource:
    - input/resources/registry/*
    - input/resources/terminology/*
    - input/resources/concept-maps/*
    - input/resources/categories/*
    - input/resources/assignments/*
```

SUSHI recurses into sub-folders of `input/resources` on its own; the IG Publisher
does not. The globs are what put the resources a sub-folder holds into the
published ImplementationGuide, and a project whose `sushi-config.yaml` is missing
one publishes a guide silently short of that sub-folder's resources -
[`d2w fhir init --refresh`](#refreshing-a-projects-scaffold) is what adds a glob
the scaffold gained.

**The pre-built resources are not committed.** The scaffolded `.gitignore` covers
`ig/input/resources/` - the registry, the option-set terminology and its
concept maps, and the categories alike - because it is generated output: thousands of files, and
`make generate` rebuilds them all in a few minutes. `ig/input/fsh/` is committed, so the FSH diff after a metadata
change is still there to review.

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

**Three profiles**, in `foundation/d2-responses.fsh`, one per form kind:

| Profile | Parent | What it pins |
| --- | --- | --- |
| `D2AggregateResponse` | `QuestionnaireResponse` | `D2Period` 1..1, `D2FormType` 1..1 fixed to `#aggregate`, `questionnaire` 1..1, `subject` 1..1 restricted to `Reference(D2Location)`. |
| `D2EventResponse` | `QuestionnaireResponse` | `D2FormType` 1..1 fixed to `#event`, `authored` 1..1, `questionnaire` 1..1, `subject` 1..1 restricted to `Reference(D2Location)`. |
| `D2TrackerEventResponse` | `QuestionnaireResponse` | `D2FormType` 1..1 fixed to `#tracker-event`, `D2TrackerEnrollment` 1..1, `D2OrganisationUnit` 1..1, `authored` 1..1, `questionnaire` 1..1, `subject` 1..1 restricted to `Reference(Patient)` with `subject.identifier` 1..1 and its `system` fixed to `{base}/id/tracked-entity`. No `D2Period`. |

All three follow the `[generate.naming]` prefix, and all three take `^status` /
`^experimental` from the `[ig] status` dial like every other definitional artifact.
`foundation/d2-capture-server.fsh` sits beside them: a `D2CaptureServer`
CapabilityStatement of `kind = #requirements`, declaring `create` on
`QuestionnaireResponse` with all three profiles as `supportedProfile`, plus `read` and
`search-type` on the `Questionnaire`, `CodeSystem`, `ValueSet`, `Location`,
`Organization`, and `List` resources a client resolves a form from - `List` because a
form's [organisation-unit assignment](#organisation-unit-assignment) is published as
one, and a capture client constrains its Location picker by reading it. Its `date` is a fixed
literal, for the same byte-stability reason the NamingSystem declarations pin
theirs - R4 makes the element mandatory and a generated timestamp would rewrite the
file on every run.

**The Patient subject is logical, not resolvable.** This guide publishes no `Patient`
instances - DHIS2 holds the tracked entities and this IG describes forms, not people.
So a tracker-event response carries no `subject.reference` at all: it states
`subject.type = "Patient"` and identifies the person through
`subject.identifier`, whose `system` is fixed to `{base}/id/tracked-entity` and whose
value is the DHIS2 tracked entity UID. That is the FHIR-native spelling for "this
subject is real, and it lives in a system this document does not contain".

**The organisation unit moves to an extension.** `subject` is the patient, so the unit
the event was captured at rides on `D2OrganisationUnit` as a `valueReference` to that
unit's published `Location` - the same registry an aggregate response's `subject`
points at. `D2TrackerEnrollment` carries the second required fact as a
`valueIdentifier` under `{base}/id/tracker-enrollment`, so the response names the
enrollment the event belongs to without inventing a resource for it.

**Where a client gets those two UIDs.** From DHIS2 itself, and nowhere in this guide:
`d2w data tracker enrollment list` lists a program's enrollments and the tracked entity
each one registers. Resolving a person to an enrollment is a DHIS2 operation; the IG's
job is to state, unambiguously, which two UIDs the response has to carry.

**The Capture page**, `pagecontent/capture.md`, is the prose half. It walks an
aggregate response, an event response, and a tracker event response step by step
against forms actually selected in this project - the canonical URL rule, the
`D2Period` extension worked with a real ISO period, the `subject` reference to a real
organisation unit, the logical `Patient` subject and both tracker extensions worked
against a real stage, the two `linkId` grammars (`<dataElementId>` and
`<dataElementId>.<categoryOptionComboId>`), the required rules, the event status
map - and closes with a table typing every
DHIS2 value type onto its item type, answer element, and literal spelling, then the
coded-answer rule and the validation workflow. The typing table is built from the
very tables the example emitter answers from, so the page and the examples cannot
disagree about how a value is spelled.

**The examples are the contract check.** Every complete generated example declares
itself `InstanceOf: D2AggregateResponse`, `D2EventResponse`, or
`D2TrackerEventResponse` rather than the bare resource, so `make sushi` and the IG
publisher validate each one against the contract on every run. A profile that stops
describing what generation produces fails the build instead of shipping. The single
exception is an instance-sourced tracker event the server gave no enrollment or no
tracked entity for: it declares the base `QuestionnaireResponse`, because a document
cannot claim a contract it does not meet.

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

## Serving the IG

`d2w fhir serve` turns a generated project into a running FHIR endpoint: it serves the
resources the IG publishes, and it receives `QuestionnaireResponse` captures against
them. It is the other side of the [capture contract](#the-capture-contract) - the guide
states what a client sends, and this is a server that accepts it.

The server ships as its own package, `dhis2w-fhir-serve`, because it needs FastAPI and
uvicorn while generation needs neither. A scaffolded project already declares it, so
`uv sync` in the project is enough; anywhere else:

```bash
pip install 'dhis2w-cli[serve]'      # or: uv add dhis2w-fhir-serve
```

Without it, `d2w fhir serve` says so and names both install routes rather than failing on
an import.

### Quickstart

```bash
cd demo-ig

# 1. Generate the IG source and compile it. The facade serves what SUSHI wrote,
#    so a project that has never been compiled has nothing to serve.
d2w fhir generate
make sushi

# 2. Serve it. Loopback and port 8080 by default; ctrl-c stops it.
d2w fhir serve
```

Then, from another shell:

```bash
# What this server is: a kind #instance CapabilityStatement that instantiates the
# IG's own D2CaptureServer, narrowed to the types this store actually holds.
curl -s localhost:8080/metadata | jq '.software, .implementation.description'

# Read one resource, byte-faithful to what the project published.
curl -s localhost:8080/Questionnaire/BfMAe6Itzgt | jq .title

# Search: _id, url, and identifier, answered as a searchset Bundle.
curl -s 'localhost:8080/Questionnaire?_id=BfMAe6Itzgt,Nyh6laLdBEJ' | jq .total

# The identifier search is how a program's stages are selected - the same query the
# published guide documents, answered by this server.
curl -s 'localhost:8080/Questionnaire?identifier=http://example.org/fhir/demo/id/program|IpHINAT79UW' \
  | jq '.entry[].resource.title'
```

Seven resource types are served: `Questionnaire`, `CodeSystem`, `ValueSet`, `Location`,
and `Organization` - the read set a capture client resolves a form from - plus
`ConceptMap`, whose maps are published artifacts in the same store, plus
`QuestionnaireResponse`, which is the one type the facade also receives. Anything else
is refused with an OperationOutcome saying this server does not serve that type, rather
than a bare 404 that would read as "no such resource".

Within one search parameter, comma-separated values are alternatives; across parameters
they combine (`?_id=a,b&url=x` matches the resource that is both). An unrecognised
parameter is ignored rather than refused, and the Bundle's `self` link echoes back only
the parameters the server actually applied, so a client can see what it got.

### `$translate`

One of the two operations the facade answers, over [every ConceptMap the project
publishes](#conceptmaps-the-route-back-to-dhis2): R4's type-level
`ConceptMap/$translate`, which takes a generated concept code back to the DHIS2
identifiers it stands for. The store reads `input/resources/` whole and the operation
scans every map it holds, so both families are answered by the same call - the request
differs only in which CodeSystem it names.

```bash
# An option-set concept: both DHIS2 identifiers of one generated answer code.
curl -s 'localhost:8080/ConceptMap/$translate?system=http://example.org/fhir/demo/CodeSystem/d2-os-Qdm5fPK5Ra9-cs&code=Op1aaaaaaaa' \
  | jq '.parameter'

# A category concept: the same call over the disaggregation terminology.
curl -s 'localhost:8080/ConceptMap/$translate?system=http://example.org/fhir/demo/CodeSystem/d2-cat-fMZEcRHuamy-cs&code=qkPbeWaFsnU' \
  | jq '.parameter'

# Narrow either one to a single group by naming the namespace you want back.
curl -s 'localhost:8080/ConceptMap/$translate?system=...&code=qkPbeWaFsnU&targetsystem=http://example.org/fhir/demo/id/category-option-code' \
  | jq '.parameter'
```

The answer is a `Parameters` resource in R4's own `$translate` output shape: `result`
(a boolean), one `match` per mapping carrying `equivalence`, the target `concept` as a
Coding, and the `source` ConceptMap, plus a `message` naming what was not found when
`result` is false. The category call above answers both of its namespaces:

```json
{
  "resourceType": "Parameters",
  "parameter": [
    { "name": "result", "valueBoolean": true },
    {
      "name": "match",
      "part": [
        { "name": "equivalence", "valueCode": "equal" },
        {
          "name": "concept",
          "valueCoding": {
            "system": "http://example.org/fhir/demo/id/category-option",
            "code": "qkPbeWaFsnU",
            "display": "Fixed"
          }
        },
        {
          "name": "source",
          "valueUri": "http://example.org/fhir/demo/ConceptMap/d2-cat-fMZEcRHuamy-cm"
        }
      ]
    },
    {
      "name": "match",
      "part": [
        { "name": "equivalence", "valueCode": "equal" },
        {
          "name": "concept",
          "valueCoding": {
            "system": "http://example.org/fhir/demo/id/category-option-code",
            "code": "FIXED",
            "display": "Fixed"
          }
        },
        {
          "name": "source",
          "valueUri": "http://example.org/fhir/demo/ConceptMap/d2-cat-fMZEcRHuamy-cm"
        }
      ]
    }
  ]
}
```

Pick the match you want by its `concept.system`, or ask for it up front with
`targetsystem` - see [UID targets or code targets?](#uid-targets-or-code-targets) for
which one to reach for. A `targetsystem` naming the other family's namespace matches
nothing and answers `result: false`, because the two families keep their namespaces
apart. `system` and `code` are required - omitting either is a 400
OperationOutcome - and `targetsystem` is optional, selecting one group instead of all
of them. Both R4's lowercase `targetsystem` and the `targetSystem` real clients also
send are read.

The operation is declared at `rest.operation` in the `/metadata` CapabilityStatement -
at rest level rather than on a resource entry, because R4 makes it type-level - and only
when the store actually holds ConceptMaps, because `/metadata` never advertises what the
store cannot answer.

The maps are served as documents too: `GET /ConceptMap/<id>` answers the published map
verbatim and `GET /ConceptMap` searches them like any other type, with the same `_id`,
`url`, and `identifier` parameters. The two are complementary - a read hands over the
whole mapping table for a person to look at, the operation answers the one question a
forwarder has without its caller walking groups and elements.

```bash
# Every map the project published, as a searchset.
curl -s localhost:8080/ConceptMap | jq '.entry[].resource.id'

# One map, byte-faithful: its groups, its elements, and the DHIS2 systems it targets.
curl -s localhost:8080/ConceptMap/d2-os-Qdm5fPK5Ra9-cm | jq '.group[].target'
```

### `$generate`

The other operation: hand it a served form and it answers with a synthetic
`QuestionnaireResponse` filled in against that form's own rules.

```bash
# Instance-level, on the form's own resource id. GET is the everyday spelling.
curl -s 'localhost:8080/Questionnaire/BfMAe6Itzgt/$generate' | jq '.status, .subject'

# Post it straight back. This is the invariant the operation is built around.
curl -s 'localhost:8080/Questionnaire/BfMAe6Itzgt/$generate' \
  | curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8080/QuestionnaireResponse \
      -H 'Content-Type: application/fhir+json' --data-binary @-
# 201
```

**`$generate` output posted back to the same server's `POST /QuestionnaireResponse`
answers 201.** That is the whole point of it, and it is a test rather than a claim -
per form kind, in both modes, and with `--strict-codes` on. Two things follow from it.
A capture UI gets its "fill with test data" button by calling one endpoint and shipping
the answer to the endpoint it was already posting to. And a stress corpus becomes an API
loop rather than a CLI run: `d2w fhir generate load-set` writes a corpus to disk,
`$generate` hands one out per request.

**It is deliberately not SDC's `$populate`.** `$populate` means *fill this form from real
context about a real subject*; `$generate` invents its data. Answering `$populate` with
invented values would mislead every client that knows what it means, so this is a custom
operation with its own `OperationDefinition`, published by the project's own IG at
`{canonical}/OperationDefinition/d2-generate` and declared in `/metadata` on the
`Questionnaire` resource entry (which is where R4 puts an instance-level operation, as
against `$translate`'s type-level `rest.operation`).

**The `seed` parameter makes it reproducible.** Same form, same seed, same bytes - nothing
in the fill reads a clock beyond the calendar day. Name it on the query for the GET
spelling, or in a `Parameters` body for the POST one:

```bash
curl -s 'localhost:8080/Questionnaire/BfMAe6Itzgt/$generate?seed=4242'

curl -s -X POST 'localhost:8080/Questionnaire/BfMAe6Itzgt/$generate' \
  -H 'Content-Type: application/fhir+json' \
  -d '{"resourceType":"Parameters","parameter":[{"name":"seed","valueInteger":4242}]}'
```

A call naming no seed is answered from one the server drew - which is not a lesser mode,
because **the seed comes back on the response**. It rides as the response's business
identifier, under `{canonical}/id/generate-seed`:

```json
{
  "resourceType": "QuestionnaireResponse",
  "meta": { "profile": ["http://example.org/fhir/demo/StructureDefinition/d2-aggregate-response"] },
  "identifier": { "system": "http://example.org/fhir/demo/id/generate-seed", "value": "4242" },
  "questionnaire": "http://example.org/fhir/demo/Questionnaire/BfMAe6Itzgt",
  "status": "completed"
}
```

`identifier` is where R4 puts the business identifier of a response, it survives the post
into the stored receipt, and it needs no out-of-band header - so a corpus you generated
last week can be regenerated exactly by reading the seeds off it. Seeds are R4 `integer`s,
so they run `0` to `2147483647`; anything else is a 400 OperationOutcome.

What gets filled in:

| Question | Generated answer |
| --- | --- |
| integer / decimal | inside the `minValue` / `maxValue` extensions the form pins, and inside `0..1000` when it pins neither |
| boolean | `true` or `false` |
| date / dateTime / time | inside the reporting period an aggregate form reports for, else the last thirty days |
| string / text | `Example <linkId>` |
| url | `https://example.invalid/<linkId>` |
| choice / open-choice | a real concept of the CodeSystem behind the question's `answerValueSet`, in the concept-code spelling the contract asks for - two distinct ones when the question repeats |
| reference | the organisation unit the response reports for |
| a `choice` whose ValueSet this project never published | left unanswered - inventing a code would only make the server warn about its own output |

And the context each form kind's response profile requires: an aggregate response gets a
`D2Period` and a `Location` subject, an event response an `authored` instant, and a
tracker-event response an `authored` instant, an organisation-unit extension, a tracker
enrollment, and a tracked-entity subject. The tracked entity and the enrollment are
**shaped synthetic UIDs** - they name nothing on any instance. That is what makes the form
kind generatable at all: the capture contract checks the shape of those identifiers, not
their existence.

Two facts a compiled `Questionnaire` does not carry, and the rules used instead:

- **The data set's period type.** A generated aggregate response needs a DHIS2 reporting
  period, and the compiled form says nothing about which type its data set reports on. The
  rule is: **the period type declared by a served example response answering the same
  questionnaire** - a compiled IG ships its `Usage: #example` instances, and each aggregate
  one carries the real type on its `D2Period` - and **`Monthly`** when the store holds no
  such example, which is every `--live` store. Whichever type is decided, the response
  carries the newest *completed* period of it, so the value moves with the calendar and
  with nothing else. Serve compiled when the exact period type matters.
- **`TRUE_ONLY` versus `BOOLEAN`.** The questionnaire emitter answers both DHIS2 value
  types as a `boolean` item, so a generated answer to either is a random `true` or `false`.
  A `TRUE_ONLY` data element only ever holds `true` in DHIS2 - a generated `false` for one
  is a value the *form* admits but the instance would not store.

A Questionnaire this server does not hold is a 404 OperationOutcome, the same answer a
read of it gives. One it holds but cannot read as a capture form - no `D2FormType`, an item
type with no answer element - is a 422 saying so.

### The two modes

| Mode | What the store holds | What it needs |
| --- | --- | --- |
| default | `ig/fsh-generated/resources` (what SUSHI compiled) merged with `ig/input/resources/` (the registry, terminology, concept-map, and category JSON the generate targets wrote, which SUSHI never re-emits) | a compiled IG on disk; no DHIS2 connection at all |
| `--live` | the same read set, built straight off a DHIS2 instance at startup | a reachable instance and a resolvable profile; no compile step |

### `[serve]` in `fhir.toml`

Where a project is served from is a property of the project, not of the invocation, so
it is stated once:

```toml
[serve]
host = "127.0.0.1"      # loopback: the facade has no authentication
port = 8080             # a local dev DHIS2 commonly owns 8080; 8090 is the usual way out
strict_codes = false    # true refuses an answer whose code is outside the served terminology
ui = false              # true also serves the capture UI at / (see The capture UI below)
```

`make serve`, `make serve-live`, and `make serve-ui` read the table too, which is the point: a developer
whose DHIS2 stack already holds 8080 states `port = 8090` here and every invocation in
that project honours it. Precedence is **flag beats table beats default** - and
`--strict-codes` has an explicit `--no-strict-codes` twin so all three levels are
reachable from the command line.

The default mode is fully offline. If the project has never been compiled, the server
refuses to start and says what to run:

```
error: no compiled IG at ig/fsh-generated/resources - run `d2w fhir generate`,
then `make sushi` in the project, and serve again.
```

A port something else already holds is refused the same way, before any output that
looks like a start - typically 8080, where a local DHIS2 stack lives:

```
error: port 8080 on 127.0.0.1 is already in use (usually the local DHIS2 instance;
set [serve] port in fhir.toml or pass --port)
```

`--live` skips the compiled-IG check and builds the store through one DHIS2 client, opened during
startup and closed before the first request arrives. Nothing in the request path ever
talks to DHIS2. The profile comes from `--profile/-p`, then `DHIS2_PROFILE`, then the
`profile` key of `fhir.toml` - the same chain `d2w fhir generate` uses. What `--live`
serves is byte-identical to what the compiled store would have served for the same
metadata, because both come out of the same JSON builders.

Live mode serves the read set and not the foundation artifacts: StructureDefinitions,
the extensions, and the IG's own `kind #requirements` CapabilityStatement are authored
as FSH and only exist as JSON once SUSHI has compiled them, and no FSH compiler runs in
the server. `/metadata` still names the IG's statement by canonical, which needs no
artifact to state.

### Stored responses are receipts

This is the one thing to be clear about before pointing a client at it.

A response the facade accepted is stored as a **receipt**: the submission exactly as it
arrived, stamped with the id it is now served under. Reading it back through
`GET /QuestionnaireResponse/{id}` tells you *what was submitted*, never what DHIS2 now
holds. DHIS2 remains the system of record; a receipt is evidence of a submission, not a
view of data.

That matters because two obvious questions have different answers today:

- *"What did this client send me?"* - answered, by reading the spool.
- *"What does DHIS2 currently hold for this form, period, and org unit?"* - not answered
  here. Querying current data through FHIR is a read-proxy this facade does not yet
  implement.

Forwarding a receipt into DHIS2 - turning it into data values, events, and enrollments -
is the next phase, planned in
[the FHIR conversion layer](../project/fhir-conversion.md). Until it lands, accepting a
capture means the submission was understood and kept, and nothing has been written to an
instance. The server says so itself: every accepted capture answers with an
OperationOutcome carrying that sentence, and `/metadata` states it in
`implementation.description`.

### Posting a capture

`POST /QuestionnaireResponse` is the only write. One response per request - a Bundle is
refused with a message saying so.

```bash
curl -s -X POST localhost:8080/QuestionnaireResponse \
  -H 'Content-Type: application/fhir+json' \
  --data-binary @response.json -D -
```

An accepted capture answers `201 Created` with a `Location` header naming where the
receipt is served from, and an OperationOutcome body:

```
HTTP/1.1 201 Created
location: http://localhost:8080/QuestionnaireResponse/6f1c...  (32 hex characters)
content-type: application/fhir+json
```

```json
{
  "resourceType": "OperationOutcome",
  "issue": [
    {
      "severity": "information",
      "code": "informational",
      "diagnostics": "stored response 6f1c...; a stored response is the submission as received - a receipt, not a live view of DHIS2 data"
    }
  ]
}
```

A refused capture answers with the same resource type and a different severity.
Validation runs in phases, and the phase that finds an error is the last one to run, so
a rejection is readable rather than a wall of consequences:

| Phase | What it checks | Status |
| --- | --- | --- |
| 0 | the body is JSON, is a `QuestionnaireResponse`, and parses as one | 400 |
| 1 | the `D2FormType` kind, then the invariants that kind's profile pins | 422 |
| 2 | the `questionnaire` canonical, the served Questionnaire it names, and its item index | 422 |
| 3 | an aggregate response's `D2Period` - its ISO period, its type, and the range it claims | 422 |
| 4 | every answer against the index: link ids, cardinality, value types, terminology | 422 |

Inside one phase every issue is collected, so one round trip reports every problem at
that level. Each issue names where it is with a FHIRPath `expression`:

```json
{
  "resourceType": "OperationOutcome",
  "issue": [
    {
      "severity": "error",
      "code": "not-found",
      "expression": ["QuestionnaireResponse.item.where(linkId = 's46m5MS0hxu')"],
      "diagnostics": "`s46m5MS0hxu` is not a question of this questionnaire"
    }
  ]
}
```

**Warnings never reject.** They record what the server had to interpret or could not
check, and they ride back on the OperationOutcome of the accepted capture *and* into the
stored receipt, so the interpretation is discoverable later.

### Coded answers: lenient by default

The generated CodeSystem carries every DHIS2 option twice - the concept code the
contract asks for, plus the other spelling as a `dhis2-id` or `dhis2-code` property (see
[`concept_code_source`](#generate)). So a client that sends the DHIS2 UID where the
contract wanted the option code has still named exactly one option, unambiguously.

By default the server resolves it, stores the submission, and warns:

```
linkId eY5ehpbEsB7: code 'Op1aaaaaaaa' matched option Op1aaaaaaaa by option-uid;
the contract expects concept code 'MALE'
```

A code the served terminology holds under no spelling is also a warning by default - a
generated IG is compiled from an instance at a point in time, and an option added since
is a fact about the instance rather than a mistake by the client.

`--strict-codes` flips both into refusals: only the concept code is accepted, and
anything else is a 422. One case is refused under either setting - two options matching
one code is an ambiguity the server cannot resolve and leniency cannot paper over.

**The same dial grades the organisation unit.** Where a form publishes an
[organisation-unit assignment](#organisation-unit-assignment), the unit the response
reports for is checked against it: the `subject` on an aggregate or event response, the
`D2OrganisationUnit` extension on a tracker event, and every `ORGANISATION_UNIT` answer.
A unit outside the assignment is a warning by default and a 422 under `--strict-codes`,
for the same reason a drifted code is - the submission is well-formed FHIR, and what it
names is a fact about the instance rather than a mistake in the document. DHIS2 refuses
that write with `E1029`, which the diagnostics say. A form publishing no assignment is
scoped to the whole registry and nothing is checked.

The published contract stays strict either way. Leniency is a property of this server's
runtime, not of what the IG asks for.

### The spool on disk

Receipts are held in memory for reads and mirrored to the project:

```
demo-ig/.serve/responses/received/<id>.json
```

Each file holds the response as received plus the receipt metadata around it - when it
was accepted, which form kind it declared, which questionnaire it answered, and every
warning recorded against it. Writes are atomic (a temporary file, then a rename), so a
crash never leaves a half-written receipt, and a restart rebuilds the index by scanning
the directory.

`ls .serve/responses/received | wc -l` is therefore the pending count, with no extra
bookkeeping: the directory *is* the queue [`d2w fhir forward`](#forwarding-captured-responses)
drains, which is why it is named `received/` rather than `responses/` - `forwarded/` and
`rejected/` are its siblings.

`.serve/` is gitignored by the scaffold. A project scaffolded before the entry existed
gains it from `d2w fhir init . --refresh`.

To read receipts back:

```bash
curl -s localhost:8080/QuestionnaireResponse/6f1c... | jq .
curl -s 'localhost:8080/QuestionnaireResponse?questionnaire=http://example.org/fhir/demo/Questionnaire/BfMAe6Itzgt' \
  | jq .total
```

The spool search takes `_id` and `questionnaire`; the definitional types take `_id`,
`url`, and `identifier`.

### Generating a load set

`d2w fhir generate load-set` writes a synthetic corpus to POST at a running facade:

```bash
d2w fhir generate load-set --per-target 5   # 5 responses per questionnaire target
ls load/                                    # one QuestionnaireResponse JSON per response
```

It is the volume twin of `d2w fhir generate examples` - the same fetch, the same seeded
generator, the same document builder - differing only in count and destination. An IG
publishes one example per form because more stop illustrating; a load set wants as many
as a POST loop can chew through, so `--per-target` (default 25) is not bounded the way
`[generate.examples] per_target` is. Values are seeded from the target UID and the
ordinal, so a rerun over unchanged metadata writes byte-identical files and reports every
one of them unchanged. `--output-dir` relocates the corpus off the project root.

**The references are drawn to be instance-valid.** A load set exists to be forwarded, so
it is measured by what DHIS2 accepts, and two reads make sure it does not spend that
measurement on refusals already known about. Each response is captured at a unit drawn
from the intersection of the published registry selection and its target's own DHIS2
organisation-unit assignment - id-only, one request per kind, and a tracker stage is
placed by its program's assignment because that is where DHIS2 hangs it - so no response
names a unit its data set or program does not report for (`E1029`). And a data set whose
own category combo is non-default is dropped, because a `QuestionnaireResponse` names no
attribute option combo, so DHIS2 would key every response to the default one the data set
does not admit (`E8023`, BUGS.md #41). A target the intersection leaves empty is dropped
the same way. Both drops are reported as notes naming the targets, and
`questionnaire_count` counts what the corpus covers rather than what the selection holds -
a form the corpus cannot exercise is a fact worth reading, not one worth hiding behind
responses nobody can accept.

Then post the lot:

```bash
for response in load/*.json; do
  curl -s -o /dev/null -w '%{http_code} %{url_effective}\n' \
    -X POST localhost:8080/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' \
    --data-binary "@${response}"
done

curl -s 'localhost:8080/QuestionnaireResponse' | jq .total   # every receipt now stored
```

**`load/` is not IG source.** It sits beside `ig/` rather than inside it, the scaffold
gitignores it, and `d2w fhir generate` deliberately does not write it - a load set
is test data, and the IG publisher has no business rendering a page per synthetic
response.

### The capture UI

`d2w fhir serve --ui` serves a browser UI alongside the FHIR routes, same-origin with
them, at the same address:

```bash
d2w fhir serve --ui          # or `make serve-ui` in a scaffolded project
```

Open the address it prints. The UI reads the very endpoint it is served from, so there
is no URL to configure and nothing to point at anything:

- **Overview** is the root route, and answers one question: what is the state of capture
  right now. **The spool pulse** is three counts off `GET /spool` - `Received`,
  `Forwarded`, `Rejected` - with `Received` set large because it is the only one of the
  three that is a task: it is the queue [`d2w fhir forward`](#forwarding-captured-responses)
  drains. Each count is a link into the Responses table already narrowed to that state
  (`#/responses?lifecycle=received`, which is a link you can send someone), and the
  rejected count names the DHIS2 error code most of its receipts share - "Rejected 12" and
  "Rejected 12, mostly E1029 Organisation unit is not assigned" lead to different
  afternoons. The count is per receipt rather than per issue, because DHIS2 states a rule
  once and then names every object that broke it, and one submission carrying forty rows of
  the same code is still one stuck submission. **Capture a response** puts the served forms
  underneath as quick-entry cards - title, DHIS2 kind, question count - each opening the
  form itself, with the first eight by title shown and a link to the full listing past
  that. **This server** closes with one strip: the guide being served and its version, the
  store mode, how many resource types it answers for, and the operations it declares as
  `$translate` / `$generate` badges. A project with nothing captured yet gets an invitation
  to open a form rather than three zeroes, and each section fails on its own - a spool that
  stops answering does not blank the forms beside it.
- **Forms** lists every `Questionnaire` this server publishes, with the DHIS2 object
  kind each one came from (read off the `D2FormType` extension - a form carrying none is
  shown as such, because it is one the facade will refuse to capture against) and how
  many questions it asks. **Open one and you get the form itself** - every question as a
  control its R4 item type asks for: a switch for a yes/no, a bounded number field for a
  percentage, the browser's own date and time pickers, a text box for a comment, and a
  dropdown for an option-set question whose choices come from expanding the ValueSet it
  binds. A question that takes several answers gets add and remove rows. Every question
  is labelled with its DHIS2 uid as well as its text, because that uid is what the
  server's refusals, the spool, and DHIS2 itself all name it by.

    **Fill with test data** answers the whole form from `$generate` and puts the answers
    *into the form* rather than posting them - so you can change one field and submit
    that. The seed it drew is in the toast; the same seed reproduces the same answers, so
    a form that misbehaved can be asked for again. **Clear** empties it. **Submit** posts
    a `QuestionnaireResponse` and takes you to Responses.

    The context that submission carries - the reporting period, the organisation unit,
    the tracked entity and enrollment - comes from `$generate` too, and this is worth
    knowing: the page keeps the skeleton's envelope and replaces only its answers. That
    is why a form filled in here is accepted by the same server's validator without you
    naming a period or an org unit anywhere, and it is also why the submission reports
    for whichever unit and period `$generate` chose. **This is a capture UI for exercising
    a guide, not a data-entry client for a district office.**

    A refused submission does not vanish into a toast: the validator's OperationOutcome
    is rendered issue by issue above the buttons, each with its severity, its code, and
    the question it is about - which is usually enough to fix the form without opening a
    terminal.
- **Responses** is every receipt this server holds, newest first: when it arrived, which
  form it answers, how many answers it carries, its receipt id, and - the column that
  matters - **which lifecycle state it is in**. `Received` is the queue
  [`d2w fhir forward`](#forwarding-captured-responses) drains, `Forwarded` means DHIS2
  took it, and `Rejected` means DHIS2 refused it. Filter by state or by form; the state
  chips carry the counts, so the queue depth is on screen without counting rows. The state
  filter lives in the URL (`#/responses?lifecycle=rejected`), which is what lets the
  Overview's tiles link straight into a narrowed table - and what makes "the ones DHIS2
  refused" a link rather than a set of instructions.

    **A row opens the receipt at `/responses/{id}`**, which is a page rather than a
  dialog - so one receipt is a link you can send someone. It carries the whole receipt:
  the form it answers (linked back to the form itself), its lifecycle badge, the DHIS2
  context it states (reporting period and type, organisation unit, tracked entity,
  enrollment, authored), and - when the receipt came from `$generate` - the seed it was
  drawn from, which is what makes the same answers reproducible.

    **The answers are on it, joined to the questions that were asked.** The page reads
  the served `Questionnaire` as well as the receipt and puts them side by side: the
  question text in the order the form asks it, with its enclosing groups - which is what
  turns a disaggregated cell from `Fixed, <1y` into
  `Immunization / BCG doses given - Fixed, <1y` - the link id beside it, and the value
  rendered as what it is: a coded answer keeps both its display and the code DHIS2 will
  store, a boolean reads as Yes or No, a repeating question shows every answer it was
  given. Questions the submission left unanswered are absent, because the receipt holds
  only the branches that were answered. **A form recompiled since the capture degrades
  rather than blanks**: the receipt still renders against its link ids, with a line
  saying the form is no longer served. Capture warnings get a section, a rejection gets
  the import report the forwarder stored beside the receipt - the error code, the object
  DHIS2 named, what it said - and a collapsible **Raw QuestionnaireResponse** shows the
  stored document itself, so the page can be checked against the bytes.

    The lifecycle is which of `.serve/responses/{received,forwarded,rejected}/` the file
    is in, and the server re-reads that directory to answer. So running
    `d2w fhir forward` in another terminal changes what this page shows with nothing
    restarted - hit **Reload**, or just switch back to the browser, which refetches on
    focus.
- **Org units** is the reporting hierarchy: where a capture may happen, and which forms may
  happen there. The left panel is the tree, folded from `Location.partOf` and expanded
  lazily - a district's two hundred facilities cost one row until you open it. Each row
  carries the unit's DHIS2 level, read off the `D2OrganisationUnitLevel` coding rather than
  counted in `partOf` hops, which matters for the units at the top of a partial selection:
  a project generated with a `root` or a `max_level` publishes a slice, so its own top units
  name parents that were left out, and those are shown as **detached** roots rather than
  dropped. The filter box narrows on name, uid, or org-unit code and keeps the ancestors of
  every match, so a facility three levels down opens with its districts around it.

    **The detail panel is the unit**: its name and description, its identifiers, its level,
    its parent chain as breadcrumbs you can click, its children, and - the section worth
    the page - **Forms reportable here**. That is the assignment join, in DHIS2's own two
    phrases. A form publishing no `D2OrganisationUnitAssignment` is **assigned everywhere**,
    so those collapse to one line ("All N published forms are assigned everywhere", or "N
    more assigned everywhere" when the unit also has some of its own); the forms an
    assignment List *does* name are listed under **Assigned to this unit** and linked. Which
    is the question this page exists to answer, because a submission against a form the unit
    is not assigned to is what DHIS2 refuses with `E1029`.

    **The map draws boundaries and points, and nothing else.** No basemap, no tile server,
    no fonts fetched from anywhere: the style is an empty background painted from the app's
    own theme tokens, and every shape on it was decoded out of the base64 GeoJSON the
    `location-boundary-geojson` extension carries on the Locations this server published. So
    the map works offline, on the same origin as everything else, and tells no tile vendor
    which districts you were looking at. A configurable basemap url is a later opt-in. The
    selected unit is drawn at full strength, the units below it at partial, and every other
    published boundary as a hairline - one hue, three emphases, with a legend, because a map
    has no axis to explain itself with. Clicking a shape selects that unit. The selection
    lives in the address (`#/org-units?unit=DiszpKrYNg8`), so a unit is a link you can send.

    Three things degrade rather than break: a unit DHIS2 holds no geometry for is framed on
    the nearest unit above it that has some, with a note saying so; a boundary attachment
    that does not decode into a polygon is skipped and counted rather than blanking the map;
    and a registry with no coordinates at all gets one sentence instead of an empty grey
    rectangle. The renderer is the frontend's one heavy dependency, so the route lazy-loads
    it - opening a form never downloads a map engine.
- **Terminology** is a browser over all three terminology types. The listing has a
  section per type - code systems, value sets, concept maps - each row carrying the id,
  the DHIS2 identifiers the artifact was generated from, and the concept or mapping
  count, with one filter box narrowing all three at once. Opening a row is where the
  actual codes are:

    - A **code system** shows every concept as a table, with one column per property the
      system declares - which is where the DHIS2 option code sits beside the concept code
      that stands for it. Filter over code, display, and property values; a long system
      (organisation units run to thousands) pages at 200 rows with a shown-of-total line.
    - A **value set** shows what it composes, linked to the code systems it names, and
      expands them by reading those systems - the same two reads a choice question makes,
      because this server publishes no `$expand`.
    - A **concept map** shows every mapping it states, one table per group, so the target
      system, the target code, and the equivalence are on the row.

    Both detail pages carry a **`$translate` tester**: type or click a concept code,
    optionally pick a target system, and the answer comes back from the running server -
    the same operation `d2w fhir forward` resolves a coded answer with. A code the maps
    say nothing about answers with the message the operation states, not an error.
- **Server** renders `/metadata` in full: the declared operations (`$translate`,
  `$generate`), the interactions and search parameters per resource type, and the store
  mode this process is running in.

The header carries a reachability light and, behind it, what the server said about
itself - which is worth a glance before blaming a form: a UI pointed at a stale `--live`
process and one pointed at a freshly compiled IG look identical until you read the
conformance document.

**The UI shadows nothing.** Its bundle is mounted in two pieces around the FHIR routes -
the asset tree ahead of the read catch-alls, the shell after everything - so
`/metadata`, `/Questionnaire`, and every other served path answer exactly as they do
without `--ui`, and a resource type the facade does not serve is still an
OperationOutcome rather than a page. Routing inside the UI is hash-based (`#/responses`),
so a reload on any page works with no server-side rewrite.

An installed wheel ships the built bundle. In a checkout it is a build artifact, so
`--ui` before `make build-frontend` refuses in one line rather than serving a blank page:

```
error: `--ui` needs a built frontend at .../dhis2w_fhir_serve/static, and there is
none. Build it with `make build-frontend` (an installed wheel ships it already).
```

**The one endpoint that is not FHIR.** The Responses page reads `GET /spool`, which
answers plain JSON rather than a Bundle. What it serves is the receipt *envelope* - the
instant the facade accepted the submission, the form kind it was validated as, the
warnings it recorded, the lifecycle state, and DHIS2's import report behind a rejection -
and none of those are elements of a QuestionnaireResponse. The receipts themselves stay
FHIR: `GET /QuestionnaireResponse` lists them and `GET /QuestionnaireResponse/{id}` reads
one back verbatim, in whatever lifecycle state it is in, because forwarding a receipt
must not expire the id its sender was handed.

### What this server is not

- **The UI is not authenticated either.** It is the same process on the same port, so
  everything the "No authentication" note below says applies to it unchanged.
- **One process, one project.** There is no clustering and no shared state. The spool
  assumes a single writing process, which is what `d2w fhir serve` is.
- **The store is a snapshot.** It is read once at startup - from disk, or from the
  instance under `--live` - and never re-read. Regenerate, recompile, or re-fetch, then
  restart the server to serve the new state.
- **No authentication.** That is why the default bind is `127.0.0.1`. Exposing the
  facade beyond loopback with `--host` is a deliberate act, and puts the endpoint behind
  something that authenticates.
- **The server never writes to DHIS2.** A capture is a receipt and nothing more.
  Writing to the instance is a separate, explicit act:
  [`d2w fhir forward`](#forwarding-captured-responses).

## Forwarding captured responses

`d2w fhir forward` is the last leg of the loop, and it closes it:

```
DHIS2 metadata -> d2w fhir generate -> the IG -> d2w fhir serve -> a form a client fills
      ^                                                                     |
      |                                                                     v
      +---------------- d2w fhir forward <------------- a captured QuestionnaireResponse
```

Everything before this point reads DHIS2 or reads the guide. `forward` is the one verb
that writes to the instance, so it is deliberately the one verb you have to ask twice.

```bash
d2w fhir forward            # dry run: validate the whole spool against DHIS2, change nothing
d2w fhir forward --import   # commit
```

### Dry run first, always

**A bare `d2w fhir forward` is a dry run**, and the terminal opens and closes with a
banner saying so. It is not a local simulation: every payload is posted to the real
endpoint on the real instance, under that endpoint's own validate-only mode.

| Payload | Endpoint | Dry run | Import |
| --- | --- | --- | --- |
| Aggregate response | `POST /api/dataValueSets` | `dryRun=true` | *(no extra parameter)* |
| Event / tracker event | `POST /api/tracker` | `importMode=VALIDATE` | *(no extra parameter)* |

Both endpoints run every rule they would run for a committed import and persist nothing,
so a green dry run means DHIS2 itself has agreed to the whole spool. The two spellings
differ because the endpoints do: v42's `/api/tracker` has no `dryRun` parameter at all,
and `/api/dataValueSets` has no `importMode`. Every event post also carries
`importStrategy=CREATE&async=false` - a translated event carries no DHIS2 uid, so it is
always a create, and the synchronous mode is what makes the answer the import report
itself rather than a job to poll.

A dry run **moves nothing**. The queue after it is the queue before it, so the natural
workflow is to run it until it is clean and then run the same command with `--import`.

### What one run does

Six steps, each narrated on stderr:

1. **Read the spool** - every `.serve/responses/received/*.json`, in file-name order.
2. **Read the published guide** - `ig/fsh-generated/resources` merged with
   `ig/input/resources`, exactly the two trees `d2w fhir serve` loads. Forwarding an
   uncompiled project is a one-line refusal naming `d2w fhir generate` and `make sushi`.
3. **Read the value types** - one id-only
   `/api/dataElements?fields=id,valueType&filter=id:in:[...]` for the data elements the
   published forms bind. This is the one fact the compiled IG cannot carry: R4 spells
   DHIS2's `BOOLEAN` and `TRUE_ONLY` as the same `#boolean` item type, and only the value
   type tells them apart. Without it a `TRUE_ONLY` question would be written as `BOOLEAN`.
4. **Translate** - each response through `dhis2w_fhir.conversion`, all-or-nothing.
5. **Post** - one payload per response, through the one client the run opened.
6. **File** - each receipt into what it became (import runs only).

A refusal comes back differently from each endpoint, and the run reads both: `/api/dataValueSets`
answers a `409` whose body is a `WebMessage` wrapping an `ImportSummary`, while `/api/tracker`
answers the `TrackerImportReport` **bare**, with no envelope around it at all. Each family
recognises its own report by the fields only that report carries, so every `errorCode`, object,
and message DHIS2 took the trouble to name survives onto the outcome - and the endpoint's own
generated model (`ImportSummary` / `TrackerImportReport`) rides along untouched beside it.

One POST per response is deliberate. DHIS2 answers a bundle with one report for the
bundle, and a spool whose receipts move individually needs one answer each.

### The three states a receipt can end in

```
.serve/responses/
  received/    captured, not yet forwarded  - the queue
  forwarded/   DHIS2 accepted it
  rejected/    DHIS2 refused it, and <id>.report.json says why
```

Moves are renames within one filesystem, so a receipt is in exactly one state at every
instant. A rejection's report is written before the receipt moves, so a process killed
mid-move leaves a report with no receipt - which the next run overwrites - rather than a
rejected receipt nothing explains.

### Refusal is not rejection

The two failure modes are different jobs, and the terminal never collapses them:

| | Refused | Rejected |
| --- | --- | --- |
| Who said no | the translator, before DHIS2 saw it | DHIS2, on the import |
| Where to look | the response, the guide, or `fhir.toml` | the import summary on the outcome |
| Typical cause | a canonical the guide does not publish, an answer element the question does not answer on, a missing D2Period | a data element outside the data set, an org unit the user cannot write to, a locked period |
| What happens to the file | **stays in `received/`** | moves to `rejected/` with its report |
| How to retry | fix locally, run again - the receipt never left the queue | fix the instance or the data, move the file back, run again |

A refused response stays put precisely because the retry is natural: nothing was written,
nothing was moved, and the same command is the retry once the guide or the data is fixed.

### Coded answers: the same dial the facade captures under

`[serve] strict_codes` is the default. A project that captures strictly forwards
strictly, without stating it twice:

```toml
[serve]
strict_codes = false   # lenient (the default): resolve, and note what was resolved
```

- **Lenient** resolves a coded answer's concept code first, then the DHIS2 option UID,
  then the DHIS2 option code, recording a note naming which tier matched. A code the
  context holds no terminology for is sent to DHIS2 unchecked, with its own note.
- **Strict** accepts only the concept code the served CodeSystem publishes, and refuses
  anything else.

`--strict-codes` / `--no-strict-codes` overrides the table for one run, so all three
levels are reachable from the command line.

### Worked run

```console
$ d2w fhir forward
[1/6] spool: 286 pending response(s)
[2/6] compiled IG: 1,412 resource(s), 7 form(s)
[3/6] value types: 214 of 214 data element(s) typed
[4/6] translate: 284 translated, 2 refused
[5/6] post: 284 payload(s) posted (validate only)
[6/6] spool: 286 spooled, 284 translated, 2 refused, 284 posted, 281 accepted, 3 rejected

dry run: DRY RUN - every payload was posted to DHIS2 under its own validate-only mode
(dataValueSets dryRun=true, tracker importMode=VALIDATE). Nothing was written to the
instance and no receipt moved. Re-run with --import to commit.

        fhir forward
  profile         local (fhir.toml)
  project         /home/me/demo-ig
  mode            DRY RUN (validate only)
  coded answers   lenient
  spooled         286
  translated      284
  refused         2
  posted          284
  accepted        281
  rejected        3

                    rejection reasons
  Code    What DHIS2 said                                          Responses
  E1029   Event OrganisationUnit: `...` and Program: `...`, do             2
          not match.
  E1313   Enrollment `...` requires a TrackedEntity.                       1

note: 286 response(s), 41 note(s); full outcomes in
      /home/me/demo-ig/reports/fhir-forward-report.md (--details to print)
error: 3 response(s) rejected by DHIS2 - read the import summary, fix the instance or the
       data, and forward again
note: 2 response(s) refused by the translator - they stay in the spool, so fixing the
      guide or the data and forwarding again is the retry
```

**The rollup is what makes a large rejection readable.** DHIS2 states a rule once and then
names every object that broke it, so two hundred rejections are usually three causes. The
run groups them by error code plus the message with its quoted identifiers generalised
away - `Event OrganisationUnit: \`ImspTQPwCqd\` and Program: \`IpHINAT79UW\`, do not
match.` and the same sentence about a different pair are one cause, not two - and a
response counts once per distinct cause it met. The written report opens with the same
table and then lists each rejected response with up to five of its own reasons.

`--details` replaces the counted hint with one row per receipt - its form, its DHIS2
target, what became of it, why, and where its file now sits. `--json` puts the whole
`ForwardReport` on stdout and nothing else, import summaries included, so a caller pipes
it into `jq` without filtering the narration out.

### Make targets

The scaffold ships both, reading the same `fhir.toml` every other target does:

```bash
make forward          # the dry run
make forward-import   # the committing run
```

An existing project gains them from `d2w fhir init . --refresh`.

## Site pages and intros

`d2w fhir generate pages` writes the guide's prose. It is the last target `generate
all` runs, and the only one that writes markdown instead of FSH.

```
ig/input/pagecontent/forms.md         Data set + event program + tracker stage catalog
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

- **`Questionnaire-<stem>-intro.md`** - one per generated Questionnaire, always. It
  names the DHIS2 data set, event program, or program stage it came from, carries the
  DHIS2 description when there is one, and tabulates the form's sections and question
  counts. A stage's intro adds a `Program` row naming the tracker program the stage
  belongs to, so a form found on its own says what it is part of.
- **`CodeSystem-<id>-intro.md`** - only for an option set that carries a DHIS2
  description.
- **`Organization-<stem>-intro.md`** - only for an organisation unit that carries a
  DHIS2 description. Most units have none, so most units get no file. That is the
  intended outcome, not a gap: an intro page repeating the unit's own title would
  be noise on every one of them.

Each `<stem>` is the artifact's [identity stem](#the-identity-stem) - the intro
files and the artifact links the site pages carry follow the same stems the
artifacts themselves take, so the publisher's injection matches by construction.

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
| Option CodeSystem concepts | `concept.designation[].language` / `.value` |
| Option-set CodeSystem and ValueSet titles | `_title.extension` translation extension |
| `Organization.name`, `Location.name` | `_name.extension` translation extension |
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
d2w fhir validate [--code-source id|code] [--output-dir DIR] [--format md,csv,pdf] [--details] [--no-fail]
```

Four passes, one finding shape:

- an **instance-wide sweep** over `GET /api/metadata?fields=id,name,code`
  (`defaults=EXCLUDE`, so DHIS2's auto-generated default category objects stay
  out of it). Every metadata object's code is checked against the R4 `code`
  datatype, per-type duplicates are flagged, and organisation units are
  additionally flagged when they carry no code at all - each finding graded by
  build impact, as below.

    Two of those branches cannot fire against an instance DHIS2 itself built, and
    are kept as nets for metadata that reached the database another way. DHIS2
    enforces code uniqueness per class and answers 409 to a bundle carrying two
    objects of one class with the same code, so `duplicate-code` has nothing to
    find; and it stores an empty-string code as no code at all - reporting
    `created: 1` and then returning the object with no `code` key - so the
    `code is empty` defect never reaches the sweep either. Both are recorded as
    upstream quirks (BUGS.md #65, #66).
- a **deep option-set pass** previewing exactly what code-mode generation would
  do, over the same projections the emitter consumes.
- a **code-stem pass** previewing exactly what a code-sourced
  [`[generate.naming]` `source`](#the-identity-stem) does with each in-scope
  object of the naming surfaces - option sets, categories, organisation units,
  data sets, programs, and program stages. Under `"code-or-id"` semantics a
  missing, unusable, or colliding code is a `code-stem-fallback` **warning**:
  this object's artifact ids, canonicals, file names, and FSH names silently
  fall back to the id. Under `source = "code"` the same object is a
  `code-stem-refusal` **error**: `d2w fhir generate` refuses the run through the
  same defect predicate, so a validate error equals a generate refusal. Under
  the default `source = "id"` the pass finds nothing - generation is not reading
  those codes. Collisions are graded per **id namespace**, exactly as generate
  resolves stems: option sets, categories, and organisation units each name
  their own artifacts, while data sets, event programs, and tracker program
  stages pool - they all become `Questionnaire-<stem>` resources - and a
  tracker program's stem, which only names its stage directory, is a namespace
  of its own.
- a **deep attribute pass** over the sweep's own `attributes` collection, naming
  every DHIS2 attribute the instance left uncoded. The emitter omits the
  `attributeCode` sub-extension entirely for such an attribute, so its values ride
  a bare UID on all five contexted resource types - `Organization`, `Location`,
  `CodeSystem`, `ValueSet`, `Questionnaire`. That is the IG working as designed
  and most instances code few of their attributes, so it is `info`: a coverage
  signal about how legible the extension is to a consumer who does not hold the
  DHIS2 instance.

Every pass also checks the object's **name**, for one thing that has nothing to do
with codes - see below.

**The sweep is the broad coverage.** Both the R4 code check and
`template-hostile-name` apply to every object in every
collection `/api/metadata` returns - `dataElements`, `categoryOptionCombos`,
`dataSets`, `programs`, `sections`, `programStageSections`, `organisationUnits`,
`attributes` and the rest. The deep passes exist for what the sweep structurally
cannot see: the objects it excludes (`options`), the outcomes that depend on an
object's peers (a concept code assigned against its set, an identity stem graded
against its selected peers), and the emit-time decisions it does not model (an
attribute value's missing code).

The report carries the counts each pass covered - option sets, options,
attributes, resource types, and objects - in the Markdown and PDF reports and in
the terminal table alike.

### Severity means build impact

Before anything is graded, the run resolves the configured selection into an
**emission scope** - the same selection semantics `generate` uses, so validate and
generate can never disagree about what is on the build path - and every finding
carries the verdict as its `scope`: `selection` for objects the configured IG
emits, `instance` for the rest. An **error** means your build will abort: a
build-aborting `<` code on an in-scope identifier surface, the very codes
`d2w fhir generate` refuses through the same predicate, and the only findings that
gate exit 1. A **warning** is an in-scope degradation the build survives - a code
falling back to the UID, a name malforming its page. An **info** is instance
hygiene: the same defects on objects the build never reads, the code-migration
watchlist rather than build noise. The summary's **code coverage** line (`34/61
(selection objects whose code can serve as an identity stem)`) counts how many
in-scope objects carry a code usable as an identity stem - the R4 `id` bar,
stricter than the R4 `code` datatype - per surface in the report, so it is the
number to watch grow before switching `[generate.naming] source` from `"id"`
toward `"code"`.

### `template-hostile-name`

A warning on any metadata object whose **name** contains `<`, `>`, or `&`.

The IG publisher's `fhir2.base.template` writes a resource's title into breadcrumbs
and change-history headings without HTML-escaping it, and then strict-parses the
page it just produced. A DHIS2 name holding `<` therefore produces a malformed page:
the Sierra Leone demo's `Mortality < 5 years by gender` (`YFTk3VdO9av`) renders
`<h2 id="root">: Mortality < 5 years by gender - Change History</h2>` and the
publisher logs `Unable to Parse HTML - node 'h2' has unexpected content`.

Generation escapes what it owns - every page-facing title and description it writes
HTML-escapes those three characters, the FSH `Title:` and `Description:` lines and
the `title` and `description` of a pre-defined JSON resource alike, because both
shapes reach the same template. It deliberately does
**not** touch the resource's own `title` and `name` elements: those are DHIS2 data,
they are what a consumer reads back, and silently substituting entities into them
would make the IG disagree with the instance. So the change-history surface stays
malformed for such a name, and the fix is to change the name in DHIS2 - which is
what this warning is for.

The check runs in every pass and at warning severity in either code source: it is
about the pages the IG publishes, not about what generation reads. The sweep covers
every metadata object; the deep option-set pass covers option names, which the sweep
excludes and which land in concept displays and page tables. The offending name is
printed through the same renderer the code column uses, so an invisible character in
it is visible on the page.

### `template-hostile-code`

An **error** on an in-scope code containing `<`, a **warning** on an in-scope one
containing `>` or `&`, and `info` on either defect out of scope - raised only on
the collections whose codes become identifier values: `optionSets`, `categories`,
`organisationUnits`, `dataSets`, `programs`, and `programStages`.

Same characters as the sibling above, a much worse outcome, which is why `<` here is
an error and a hostile *name* is only ever a warning. A code from one of those five
collections becomes an identifier value on the resources generated from that object,
and the publisher writes identifier values into a table cell without escaping them
and then strict-parses the page it just produced. A real one - an option set coded
`ENTO - IRS < 6 Months` - fails the build with:

```
Publishing Content Failed: Unable to process page .../CodeSystem-d2-os-csRsm0D7guY-cs.html
Caused by: org.hl7.fhir.exceptions.FHIRFormatError: Unable to Parse HTML - node 'td'
has unexpected content ' ' at line 215 column 197
```

It fails in the publisher's last pass, after every resource has been rendered, so on
a large IG a single hostile code costs you the entire build before it says so. That
is the whole reason to spend a `validate` on it: the same finding takes seconds.

The rest of the DHIS2 text that reaches a page is safe. The publisher escapes concept
displays, concept designations, `dhis2-code` property values, and translation
extensions, all of which carry a raw `<` through a build without complaint. The
identifier table is the one place it does not, and a code is the one DHIS2 field that
reaches it - so this check reads codes and nothing else.

Both restrictions are there to keep the error honest, because an error on this check
means "your build will fail". A dashboard is never generated, so a dashboard coded
`CHAS S&E HIV` costs nothing and is not a finding; a data element carries its code as
a concept code or a `dhis2-code` property, both of which the publisher escapes, so it
is not a finding either. And `<` is the only character seen to abort a build - it
opens a tag - while `>` is text to an HTML parser and a bare `&` is widely tolerated,
so those two are reported without claiming to be fatal. On the national instance this
was found on, the unrestricted form of the check raised 23 errors across dashboards,
data elements, and program indicators; exactly one of them was the object that
actually failed the build.

Generation does not escape its way around this, for the same reason it leaves names
alone: an identifier value is what a consumer matches on to find the DHIS2 object,
and an IG that answers `ENTO - IRS &lt; 6 Months` to a lookup for
`ENTO - IRS < 6 Months` disagrees with the instance it describes. The fix is to
change the code in DHIS2.

**`d2w fhir generate` refuses what validate marks as build-aborting.** Generation
knows before it writes a file that the publisher will die on that code, so it says so
instead of producing an hour of build input:

```
error: optionSets 'Bednet distribution' (csRsm0D7guY) has code 'ENTO - IRS < 6 Months',
which carries '<'. ... Change the code in DHIS2, then run `d2w fhir validate` for the
full report.
```

The **whole run** is refused, not the one object: skipping the option set would leave
every Questionnaire that binds it pointing at a ValueSet nobody wrote, which is a
broken guide published quietly instead of a build that failed loudly. Both the bare
run and the solo targets carry the gate, over the selection each is about to emit -
an object the project does not publish can never refuse a run. Only `<` refuses;
`>` and `&` cost a malformed page rather than an aborted build, so they stay warnings
and generation proceeds. The predicate is one function shared with the finding above,
so the two can never disagree.

### What the terminal says

The default output is a status view, not the finding firehose:

- the **summary table** - profile, the counts each pass covered, the error / warning /
  info totals, a `selection findings` row splitting those totals to the build path
  (`1 error, 12 warnings, 3 infos`), the `code coverage` fraction, the effective
  code source;
- a **rollup table**, one row per (severity, scope, category) with its count -
  errors first, and within one severity the `selection` rows before the `instance`
  rows, which render dimmed so the build path carries the visual weight;
- **every error individually**, because an error is what gates the build and you have
  to know which object holds it without opening a file (an error is always
  `selection` scope by construction);
- one closing line: `ok: passed: N selection warning(s), M selection info(s), K
  instance finding(s); full findings in <reports-dir>/fhir-validate-report.md`, or
  the red `N error(s) found` line with the exit code.

A national instance raises hundreds of warnings, and reading them one row at a time is
what the written report is for. `--details` puts every finding on the terminal too,
warnings and infos included. `--json` is unchanged: the whole report on stdout.

### Severity and `--code-source`

The option-pass findings are gated on the effective code source - the
`--code-source` flag when given, otherwise `concept_code_source` from
`fhir.toml`. In `code` mode, `invalid-code`, `missing-code`, and `duplicate-code`
carry their in-scope severities. In `id` mode they are downgraded to `info` and
their message says so, because generation is not reading those codes yet - they
keep their `selection` scope, so the summary's selection split still counts them.
The instance-wide sweep keeps its severities either way.

### Report files

`--output-dir` names a **directory**, created if it does not exist, and the files
inside it are always `fhir-validate-report.md` / `.csv` / `.pdf`. The default is
`reports/` under the project root, or under the working directory when there is
no project. The scaffolded `.gitignore` covers
`reports/`: the reports are regenerable snapshots of instance state, so they
stay out of git; pin one deliberately (`git add -f`) when handing it over.
`--format` takes a comma list of `md`, `csv`, `pdf`; all three are written by
default, and each written path is echoed.

- **`.md`** - findings grouped under one section per resource type, a Scope
  column on every row.
- **`.csv`** - one row per finding, columns
  `severity,scope,category,resource_type,uid,name,code,message`. For spreadsheets
  and for diffing two runs.
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

Exit 1 when there are errors, which makes it a CI gate - `--fail` is the default.
`--no-fail` exits 0 regardless, and drops the red `N error(s) found` line with it.
`--details` lists info findings individually instead of rolling them up per
category.

Every `d2w fhir` command honours the global `--json` / `-j` flag, emitting that
run's report as JSON on stdout in place of the Rich tables - `d2w --json fhir
generate` gives the per-target file lists and counts, `d2w --json fhir
validate` the full findings list. Tables, notes, and progress are narration and
stay on stderr - in JSON mode none of them is rendered at all, and only
`validate`'s `wrote <path>` lines remain - so stdout is a clean document either way. On `validate` it pairs with the
exit-1 gate: CI reads the findings off stdout and the job still fails on errors.

MCP exposes the same check as the read-only `fhir_validate` tool, taking
`profile`, `project_directory`, and `code_source`. It returns the report; file
writing stays CLI-only.

## The scaffolded Makefile

```
make setup      Build the SUSHI + IG publisher docker image
make upgrade    Rebuild it from scratch, pulling the latest of both
make generate   d2w fhir generate
make update     Move the toolchain pin, sync, and d2w fhir init --refresh
make validate   d2w fhir validate
make cache-init Make the shared package-cache volume writable by the publisher user
make sushi      Compile FSH to FHIR resources
make build      Run the full IG publisher
make serve      Serve the compiled IG as a FHIR endpoint (run generate + sushi first)
make serve-live Serve straight from the DHIS2 instance, no compile needed
make serve-ui   Serve the FHIR endpoint plus the capture UI at /
make refresh    Force-refresh everything: clean-all, upgrade, generate, validate, build
make clean      Remove build output
make clean-all  Also remove the terminology cache and the package cache volume
make help       List the targets
```

`refresh` runs `validate` with a leading dash - `-$(MAKE) validate`. A full
rebuild wants fresh reports out of the instance every time, and validate exits 1
whenever the instance carries code errors, which is by design and must not abort
the rebuild. Every other step stops the chain on failure.

`generate` and `validate` call `d2w` through a `D2W` variable, defaulting to
`uv run d2w` - the [pinned toolchain](#pinned-toolchain). Override it to drive a
checkout or a git ref instead:

```bash
# From a local checkout of dhis2w-utils:
make generate D2W="uv run --project /path/to/dhis2w-utils d2w"

# Straight from a git ref, nothing installed, no uv sync:
make generate D2W="uvx --from 'git+ssh://git@github.com/winterop-com/dhis2w-utils.git@main#subdirectory=packages/dhis2w-cli' --with 'dhis2w-fhir @ git+ssh://git@github.com/winterop-com/dhis2w-utils.git@main#subdirectory=packages/dhis2w-fhir' d2w"
```

Three build knobs the scaffold sets for you, the first two because the defaults
break on a real instance's IG:

`ig/fsh.ini` raises the SUSHI timeout to 1800 seconds, settable at scaffold time
with `d2w fhir init --sushi-timeout`. The IG publisher re-runs SUSHI internally
with a 300-second default, which the FSH an IG built from a real DHIS2 instance
carries overruns easily - a national instance compiles in minutes, not seconds -
and the publisher then dies with exit 143 in its very first phase:

```
Sushi timeout exceeded: 1800 seconds
Exception: Process exited with an error: 143 (Exit value: 143)
```

The generous ceiling is deliberate: the embedded run has been seen to stall in
its export phase, and a timeout that fires kills the whole build after a long
wait rather than letting a slow run finish. Raise it with `--sushi-timeout` for
an instance whose FSH is large enough to need more.

`TX_SERVER` picks the terminology server the publisher validates against; it
defaults to `http://tx.fhir.org`. Setting `TX_SERVER=n/a` disables terminology
validation for an offline build, but current IG publisher versions throw a
`NullPointerException` on required bindings that need a server - the
`Attachment.contentType` binding on the GeoJSON boundary extension is one of
them, so an org-unit IG will not build offline. Use `n/a` only when your content
has no such bindings.

`JAVA_HEAP` is the publisher's JVM heap, `4g` by default. It is the knob to reach
for when `make build` dies with **exit 137**:

```
Generating Summary Outputs (en)
make: *** [build] Error 137
```

137 is `128 + 9` - SIGKILL, from the kernel's OOM killer, not from anything the
publisher decided. The give-away is that `ig/output` is empty afterwards: the
publisher writes the site in one pass at the very end, so a build killed during
`Generate HTML Outputs` or `Generating Summary Outputs` - the peak-memory phases -
leaves nothing behind at all. A real build error looks nothing like this: a Java
stack trace, a different exit code, and partial output still on disk.

The container carries no `--memory` limit, so it inherits whatever the docker VM
has, and a 4 GB heap needs roughly 6 GB of room once metaspace, JVM native memory,
and the OS are counted. Check what the machine actually gives docker:

```bash
docker info --format '{{.MemTotal}}'    # bytes available to the docker VM
```

Raising the VM's memory allocation is the better fix - the publisher wants the
room on a large IG. Where you cannot, lower the heap to fit the box:

```bash
make build JAVA_HEAP=2g
```

The same lever reproduces the failure on a machine with plenty of memory: a
deliberately starved `docker run --memory=3g` kills a 4 GB heap at exactly the
phase above. To confirm a suspected OOM kill directly, drop `--rm` from the
`build` recipe and inspect the dead container:

```bash
docker inspect <container> --format '{{.State.OOMKilled}}'   # true
```

Trimming the IG with the `[generate.data_sets]` / `[generate.event_programs]`
include lists lowers the peak too, and is worth doing when a whole-instance IG is
more than you actually publish.

### Registry scale

The organisation-unit registry is usually the largest thing in the IG by a wide
margin, because every unit emits **two** instances - an Organization and a
Location. A national hierarchy dwarfs everything else put together:

| Source | Instances |
| --- | --- |
| `resources/registry/` (12,581 units) | 25,162 |
| `examples/` | 162 |
| `data-sets/` | 113 |
| `event-programs/` | 49 |
| `foundation/` | 13 |

Every one of those 25,162 is pre-built JSON, which SUSHI loads as a predefined
resource rather than compiling, so the registry stays out of the FSH compile
entirely. What it does reach is the IG publisher, which writes and renders a page
per resource - so the registry is what sets the wall clock of `make build`.

Levels are where the weight sits, because a hierarchy fans out at the bottom. In
that same instance:

| Level | Units | Instances |
| --- | --- | --- |
| 1 | 2 | 4 |
| 2 | 33 | 66 |
| 3 | 447 | 894 |
| 4 | 1,867 | 3,734 |
| 5 | 10,232 | 20,464 |
| **total** | **12,581** | **25,162** |

Level 5 alone is 81% of the registry. Cutting it with `max_level = 4` drops the
IG from 25,162 registry instances to 4,698 - an 81% cut for one line of config:

```toml
[generate.organisation_units]
max_level = 4          # or root = "<uid>" to publish one sub-hierarchy
```

`d2w fhir init --max-level 4` seeds that table while scaffolding, so a project
that already knows its hierarchy is deep never generates the full registry once.
Like the other seeding flags it is offline - the level is written as given and
never checked against an instance - and a level below 1 is rejected rather than
silently producing an empty registry.

`d2w fhir generate org-units` prints a warning once a registry passes 10,000
instances, naming both dials:

```
note: 12581 organisation units emit 25162 instances. They ship as pre-built JSON
so SUSHI never compiles them, but the IG publisher renders a page per resource,
so they set the wall clock of `make build`. Narrow the registry with
`[generate.organisation_units]` max_level or root if the build is longer than you
want.
```

Measure before guessing at a level. `make sushi` runs SUSHI directly instead of
through the publisher, so it has no timeout and tells you what the compile
actually costs:

```bash
time make sushi
```

On the uncapped Lao IG, that is **6m57s** - 25,162 registry instances and 235
option sets, none of which the compile ever sees. The registry dial does not
reach that number at all, because predefined resources are not a compile input.

The counterfactual is what puts a figure on it. Take a `max_level = 4` cut of the
same IG and hold everything else identical, including writing the option-set
terminology as FSH, so the registry is the only variable: its 4,698 registry
instances cost **23m22s** compiled from FSH and **9m40s** loaded as predefined
JSON. [Build time and the two caches](#build-time-and-the-two-caches) has the
rest of the picture.

### Build time and the two caches

Generation is the cheap half; the toolchain is where the minutes go. On the
Sierra Leone demo (171 option sets, 2,664 registry instances, 3,101 resources in
all):

| Step | Time |
| --- | --- |
| `generate` | 16s |
| `validate` | 7s |

A national instance is larger: on the uncapped Lao instance `generate` writes the
full output in a few minutes.

`make sushi` compiles FSH, so what it pays for is the forms and the five
CodeSystems that are FSH. The registry and the option-set terminology reach it as
predefined JSON and cost nothing. On the uncapped Lao instance - 25,162 registry
instances, 235 option sets, warm cache, 0 errors and 0 warnings - `make sushi` is
**6m57s**.

| What ships as predefined JSON | `sushi`, warm cache |
| --- | --- |
| the registry and the option-set terminology | 6m57s |
| the registry alone, with the same 235 option sets written as FSH | 10m15s |

**Predefined terminology is worth 3m18s on this IG**, and predefined registry is
worth more than that again (see [Registry scale](#registry-scale)). Registry size
is not a compile input either way, so `max_level` is not a build-time dial. Reach
for it when you want a smaller *published* IG, because the publisher still renders
a page per resource - not to make the compile finish.

**Five CodeSystems compile from FSH**, and they are what that 6m57s buys:
`D2OU_Level_CS`, `D2PeriodType_CS`, `D2FormType_CS`, `D2DE_CS`, and
`D2COC_CS`. The last two are the `data-dictionary` support pairs - every data
element and every category option combo the generated forms reference. Two files,
2.5MB of FSH between them, which is why predefined option-set terminology saves
3m18s rather than everything SUSHI spends on CodeSystems. The dials that reach
those two are `[generate.data_sets]`, `[generate.event_programs]`, and
`[generate.tracker_programs]`: fewer forms means fewer data elements and fewer
category option combos to publish, and a tracker program contributes the data
elements of every one of its stages.

**Docker is not where the time goes**, which is worth stating because it is the
next thing anyone suspects. The 23m22s all-FSH compile from
[Registry scale](#registry-scale) - three ways:

| Run | Time |
| --- | --- |
| `make sushi` as scaffolded, IG bind-mounted into the container | 23m22s |
| the same container, IG copied onto its internal filesystem | 23m27s |
| SUSHI run natively on the host, warm package cache | 18m16s |

The bind mount costs **5 seconds on a 23-minute run** - SUSHI holds everything in
memory and writes once at the end, so there is no sustained file traffic across
the mount to punish. Dropping the container altogether saves about 22%, and that
figure covers host-vs-VM CPU and a different JS runtime together. The remaining
~78% is SUSHI's own work, so a native toolchain is not the answer to a slow
build.

Two structural facts matter more than any single total. The first is that a cold
package cache costs about three and a half minutes of pure download, which is
what the package cache below buys back. The second is that the publisher runs
**its own** SUSHI over the same FSH, so a chain that calls `make sushi` and then
`make build` compiles everything twice. `make refresh` therefore goes straight
from `validate` to `build`; run `make sushi` on its own when you want the fast
gate without publishing a site.

Terminology *service* time is not where the publisher's time goes, which is worth
stating because it is the natural suspicion: connecting to `TX_SERVER` and
opening the terminology cache cost about fourteen seconds together. A
DHIS2-derived IG codes its concepts in its own CodeSystems, and the publisher
resolves those internally.

What the publisher does pay for is sheer resource count: it writes and renders
every resource, so the registry - 2,664 of the demo's 3,101 resources - sets the
pace. The scaffolded `sushi-config.yaml` therefore publishes JSON only
(`excludexml` and `excludettl`), because the two extra wire formats add a file
and a rendered page per resource for content that consumers and the tooling read
as JSON anyway. On the demo that halves the output: 13,710 files and 466MB
instead of 26,120 and 874MB, with the same 0 errors and 0 warnings.
`[generate.organisation_units] max_level` is the other lever on that pass, and it
is a config change rather than a build flag: fewer levels, proportionally less of
everything.

Most of what a *repeat* build would otherwise re-pay is cached, and the scaffold
wires both caches up for you:

- **The FHIR package cache** lives at `~/.fhir` inside the container. Because
  `docker run --rm` throws the container away, `make sushi` and `make build`
  mount the named volume `fhir-ig-cache` there. Without it every run
  re-downloads the core packages, `hl7.terminology.r4`, and
  `hl7.fhir.uv.extensions.r4` before doing any work. Both targets depend on
  `make cache-init`, which chowns that volume to the publisher's non-root user -
  a fresh docker volume is root-owned, and the publisher cannot write to it.
- **The terminology cache** is `ig/input-cache/`, written by the publisher and
  ignored by git. `make clean` deliberately leaves it in place; a warm tx cache
  takes the validation phase from minutes to seconds, because every code the
  validator has not seen is a round trip to `TX_SERVER`.

`make clean-all` drops both when you want to reproduce a cold build.

**Do not iterate on `make build`.** `d2w fhir generate` followed by
`make sushi` compiles the FSH and tells you whether it is valid without paying
for a published site. Run the publisher when you are ready to publish one, not
after every edit.

### When the publisher stops on `Exit value: <n>`

`Publishing Content Failed: Process exited with an error: 4 (Exit value: 4)` is
not an exit code in the sense 137 and 143 are. The publisher runs SUSHI
internally, SUSHI exits with the number of errors it counted, and the publisher
reports that number and stops. So the digit is a count: read the `Sushi: error`
lines above it, not the number itself. The build produces no pages, and the
publisher's own clock will be short, because it never reached its own work.

Two are worth recognising on sight.

**`Failed to register resource at path: .../input/resources/...`** covers every
way `fhir-package-loader` can fail to read one predefined resource, malformed
JSON and a failed read alike, and it does not say which happened. Check it
against the count SUSHI reports a few lines later - `Loaded virtual package
sushi-local#LOCAL with N resources` - and compare N with the file count under
`ig/input/resources/`. If the named files are valid JSON, the read failed rather
than the content: a file written shortly before the container read it can come
back truncated across a Docker bind mount, and the same bytes register cleanly on
a re-run. Re-run before looking for anything to fix. A genuinely malformed
resource fails every time and on the same files.

**`Unable to process page ...`** is not a SUSHI error at all - it comes from the
publisher's own final pass, so the clock on it is the whole build. Read the
`Caused by:` line under it: `Unable to Parse HTML - node 'td' has unexpected
content` is a DHIS2 code carrying `<` into an identifier value, which
[`template-hostile-code`](#template-hostile-code) reports in seconds instead.

**`Duplicate definition of ...`** means the same identity reached SUSHI twice,
once compiled from FSH and once as a predefined resource. Generation sweeps the
FSH it supersedes, so this points at generated FSH left behind by a version of
the plugin that wrote a target in the other shape. `d2w fhir generate` clears
it and reports the files in `deleted_files`; the count in that report is the
confirmation.

## The regeneration contract

Every generated file opens with a header line, chosen by extension:

```
// Generated by d2w fhir generate - do not edit
<!-- Generated by d2w fhir generate - do not edit -->
```

A generate run writes its target subdirectory and then deletes only the
header-bearing `.fsh` / `.md` files in that subdirectory that it did not just
produce. JSON carries no comment syntax, so none of
`ig/input/resources/registry/`, `ig/input/resources/terminology/`, or
`ig/input/resources/categories/` can be marked that way: each target owns its
directory outright and deletes every `*.json` in it the run did not produce.
That is also why each of the three has a directory to itself. Put nothing of your
own there.

Three consequences worth relying on:

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

Commit `ig/input/fsh/` and `ig/input/pagecontent/`. Reviewing that diff after a
metadata change is the point. `ig/input/resources/` stays out of git - the
scaffolded `.gitignore` covers it, because a national registry plus its
terminology is thousands of JSON files that `make generate` rebuilds from the
instance in a few minutes.

## See also

- [FHIR plugin architecture](../architecture/fhir-plugin.md) - how the package is
  laid out and why.
- [`dhis2w_fhir` API reference](../api/fhir.md) - the importable surface: the period
  grammar, the `fhir.toml` models, and the artifact builders.
- [`dhis2w_fhir_serve` API reference](../api/fhir-serve.md) - the facade behind
  [`d2w fhir serve`](#serving-the-ig): the store, the spool, and the capture path.
- [The FHIR conversion layer](../project/fhir-conversion.md) - why the forwarder is a
  typed Python translator, and what the published mapping contract is held against it.
- [`examples/v42/cli/fhir_generate.sh`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/v42/cli/fhir_generate.sh) -
  the same flow as a runnable script.
- [`examples/v42/cli/fhir_serve.sh`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/v42/cli/fhir_serve.sh) -
  generate, compile, serve, post a load set, read the receipts back.
- [`examples/v42/cli/fhir_forward.sh`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/v42/cli/fhir_forward.sh) -
  the whole loop end to end, dry run first and then the import.
