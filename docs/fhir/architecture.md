# FHIR plugin

`d2w fhir` turns DHIS2 metadata into a FHIR Implementation Guide, serves that
guide as a read-and-capture endpoint, and posts what it captured back into
DHIS2. This page is the map: which packages exist, what each module owns, and
which decisions are load-bearing. It links to depth rather than repeating it -
the [`d2w fhir` series](index.md) is the task-oriented
companion, and the [glossary](glossary.md) is the vocabulary
either side of the boundary.

## Two packages

| Package | Holds | Needs |
| --- | --- | --- |
| `dhis2w-fhir` | The plugin: scaffold, generate, validate, forward, doctor, and the conversion layer | httpx, pydantic, jinja2 |
| `dhis2w-fhir-serve` | The facade behind `d2w fhir serve` | FastAPI, uvicorn |

The split is the dependency: a generator writes a file tree and needs no web
server, so `pip install dhis2w-cli` stays light and
`pip install 'dhis2w-cli[serve]'` adds the facade. `d2w fhir serve` lives in
`dhis2w-fhir`'s `cli.py` and imports the server behind a guard that raises a
`LookupError` naming both install routes. The arrow points serve -> fhir, never
back.

The plugin mounts through the `dhis2.plugins` entry point - the same mechanism
third-party plugins use - and is version-neutral: the wire client auto-detects
the DHIS2 major on connect, so one package serves v41/v42/v43 with no
per-version trees.

## The command surface

```
d2w fhir init [DIRECTORY]           Scaffold a dockerized SUSHI IG project
d2w fhir init --refresh             Bring an existing project's scaffold-managed files up to date
d2w fhir generate                   All seven IG targets in one run, off a single pass over the instance
d2w fhir generate foundation        Identifier systems, the D2 extensions, the capture contract
d2w fhir generate option-sets       Option sets -> CodeSystem/ValueSet/ConceptMap
d2w fhir generate categories        Categories -> CodeSystem/ValueSet/ConceptMap
d2w fhir generate questionnaires    Data sets, programs, stages, tracked entity types -> Questionnaires
d2w fhir generate examples          Example QuestionnaireResponses against those Questionnaires
d2w fhir generate org-units         Organisation units -> Organization/Location instances
d2w fhir generate pages             Narrative site pages + per-artifact intros
d2w fhir generate load-set          Synthetic response corpus into load/ (not IG source)
d2w fhir validate                   FHIR-safety of the instance's codes (exit 1 on errors; --no-fail)
d2w fhir serve [DIRECTORY]          Serve the project as a FHIR read + capture facade
d2w fhir forward [DIRECTORY]        Drain the capture spool into DHIS2 (dry run by default)
d2w fhir doctor                     Run the whole chain against one instance and report what it breaks
```

`load-set` is the eighth `generate` subcommand and deliberately outside the
full run: what it writes is a load corpus, not IG source.

The whole surface is CLI-only, and the plugin registers nothing on the MCP
server. Most of it could not be anything else: `init`, every `generate` target,
and `doctor` write a file tree onto whatever machine the server runs on, which
is the wrong shape for an agent protocol (the same judgment the browser plugin
and the security audit runner make), and `serve` binds a port and stays up,
which is a process an operator starts rather than a tool call. `validate` and
`forward` could have been tools and were: they mirrored their commands closely
enough to earn nothing, so the command is the one surface for both. What an
agent drives instead is the facade - a served project answers FHIR over HTTP,
which is a protocol of its own.

## The project on disk

`d2w fhir init` renders thirteen files: `fhir.toml` and `fhir.toml.example`,
the project's own `pyproject.toml` + `.python-version` + `Makefile` +
`Dockerfile` + `.gitignore`, and the IG skeleton (`ig/sushi-config.yaml`,
`ig/ig.ini`, `ig/fsh.ini`, `ig/input/fsh/aliases.fsh`,
`ig/input/pagecontent/index.md`, `ig/input/ignoreWarnings.txt`).

The scaffolded project is a `uv` project with a committed `uv.lock`, so the FSH
a project publishes is a function of a pinned d2w build. `.gitignore` covers
the build output, the caches, the generated `ig/input/resources/`, `reports/`,
`.serve/`, `load/`, and `.venv` - never the lock, never `ig/input/fsh/`.

`sushi-config.yaml` carries one `path-resource` glob per predefined-resource
sub-folder. SUSHI recurses into sub-folders of `input/resources` on its own;
the IG Publisher does not, so a missing glob is silent at compile time and
lossy at publish time. That asymmetry is what `d2w fhir init --refresh` exists
to repair.

`--refresh` re-renders the scaffold for an existing project and writes only
where nothing on disk is lost. `preserves_every_line` is the whole decision: it
walks the render as a forward iterator and asks whether every line currently on
disk appears in it, in order. A file that is a strict subsequence of the render
is `refreshed`, because rewriting can only add; one that is not holds something
the scaffold would not produce and is left byte-identical and reported as
`edited`. `fhir.toml` is skipped before any comparison - it is the user's
configuration, not a scaffold-managed file. `--force` and `--refresh` are
opposite answers to the same question and are rejected together.

The full settings reference is the series'
[`fhir.toml` pages](301-fhir-toml.md).

## Generation

`generate_full` opens one client, runs `fetch_live_ig_inputs` once, and hands
the result to seven emitters in order: foundation, option-sets, categories,
questionnaires, examples, org-units, pages. Foundation is first because it
reads nothing; pages is last because it narrates the rest. Each emitter keeps
its own notes and they merge into one report.

The split is deliberate: `_emit_*` takes fetched inputs and owns
build-plus-sync, while `generate_*` fetches for itself, so a solo target run
keeps its fetch verbatim. `_emit_examples` is the one emitter that still reads
the instance during its own step, because `[generate.examples] source =
"instance"` has to.

### What lands where

FSH, compiled by SUSHI, under `ig/input/fsh/`:

```
foundation/          Identifier aliases, NamingSystems, the D2 extensions, the
                     response profiles, the CapabilityStatement, the
                     OperationDefinition, the logical model and StructureMap
data-sets/           One Questionnaire per data set
event-programs/      One Questionnaire per event program
tracker-programs/<program>/<stage>.fsh, registration.fsh
tracked-entity-types/  The person-only registration form of one type
data-dictionary/     D2DE_CS / D2TEA_CS / D2COC_CS and their ValueSets
examples/            One Usage: #example QuestionnaireResponse per example
organization/        The Organization and Location profiles, the level
                     terminology, and curated registry examples
```

Pre-built FHIR JSON, loaded verbatim with no FSH parse, under
`ig/input/resources/`:

```
registry/                    Organization + Location per organisation unit
terminology/                 CodeSystem + ValueSet per option set
categories/                  CodeSystem + ValueSet per category
attribute-option-combos/     CodeSystem + ValueSet per non-default combo
assignments/                 One List of Locations per assigned form
concept-maps/                The route back to DHIS2 for every pair
```

Shipping bulk instances as predefined JSON rather than FSH is what keeps a
national instance's artifact count out of the compile - see [Toolchain
performance](#toolchain-performance).

Narrative markdown goes to `ig/input/pagecontent/`: six generated pages plus
the per-artifact intros the publisher injects. SUSHI publishes every markdown
file under that directory on its own, so `sushi-config.yaml` carries no
`pages:` block and a new page needs no configuration to appear. The
hand-authored `index.md` is never touched.

### The five form kinds

`FormKind` is `aggregate`, `event`, `tracker`, `tracker-event`, and
`tracked-entity`, and every form and every response states its own on the
`D2FormType` extension. It is the one switch the served index, the conversion
gate, the `supportedProfile` declarations, `/metadata`, and the load set all
read.

| Kind | DHIS2 source | Subject | Selection table |
| --- | --- | --- | --- |
| `aggregate` | data set | the organisation unit's Location | `[generate.data_sets]` |
| `event` | `WITHOUT_REGISTRATION` program | the organisation unit's Location | `[generate.event_programs]` |
| `tracker` | a tracker program's registration | the tracked entity | `[generate.tracker_programs]` |
| `tracker-event` | program stage | the tracked entity | `[generate.tracker_programs]` |
| `tracked-entity` | tracked entity type | the tracked entity | `[generate.tracked_entity_forms]` |

Every selection reads the same way: absent or empty means *all*, a non-empty
list filters. When a table's `include_ids` is explicit, a program of the wrong
type raises by name and the message points at the table it does belong under -
the operator named that UID, so silence would be a lie. When the table is empty
the whole instance is its target, so the sweep routes each program by its live
`programType` instead.

A tracker stage's identity is the *stage's*, and the program travels beside it:
the title reads `<program> - <stage>`, the file nests under the program, and a
third identifier carries the program UID so a plain FHIR search
(`Questionnaire?identifier=...|<programUid>`) returns a program's whole capture
surface. Stages are emitted in DHIS2's own sort order, because `programStages`
is a Java `Set` on the wire and its order is neither the form's nor stable
across requests.

Which FHIR resource a tracked entity type's subject is comes from
`[generate.tracked_entity_types]`, keyed by type rather than by program so two
programs tracking one type cannot disagree; an unmapped type is a `Patient`.
That map is itself published, as the `D2TET_CM` ConceptMap onto
`http://hl7.org/fhir/resource-types`, so a consumer can read it. See [Custom
subject types](401-custom-subject-types.md).

### Disaggregation

On an *aggregate* source a data element on a non-default category combo becomes
a group with one child question per option combo, `linkId`
`<dataElementUid>.<cocUid>` - the same key a DHIS2 data value carries. Which
combo that is comes from one resolution point: DHIS2 holds a disaggregation on
the data set element - the join between a data set and an element - as well as
on the element itself, and **the join's wins**. Every reader of a cell is
downstream of that pair: the questionnaire's children, the `D2COC_CS` concepts,
the examples, the load set, and the conversion that writes each answer back.

Disaggregation is aggregate-only by construction. A data set's values land on
`/api/dataValueSets`, where every value carries a category option combo; an
event data value has no `categoryOptionCombo` slot on the wire. So an event or
stage question stays flat whatever combo its data element declares, because a
form must not ask a question the capture endpoint cannot accept an answer to.

The second aggregate key is the *attribute* option combo. A data set on a
non-default attribute category combo publishes a `D2AOC` CodeSystem/ValueSet
pair naming the combos its responses may be keyed under; the form declares the
set and the response names one member. A default-combo data set publishes
nothing, because absence is the default.

### Program rules

A program's rules are resolved once per run by `plan_program_rules`
(`resources/questionnaires/program_rules.py`) into the three tiers R4 can
carry: a single-comparison `SHOWERROR` on a numeric question becomes
`minValue`/`maxValue` on the item, a single-comparison `HIDEFIELD` becomes
`item.enableWhen` with the condition inverted (plus an `exists` arm exactly
where DHIS2's blank-answer semantics require one), and everything else is
published whole on the repeating `d2-program-rule` extension - non-normative,
so a consumer can state the rule without evaluating it. The grammar is
deliberately conservative - one `#{variable}` comparison against a literal,
optionally guarded by `d2:hasValue` on the same variable, resolved through
`programRuleVariables` to a question the same form asks - and the single
resolution point is what keeps the FSH emitter and the JSON twin from
disagreeing about which tier a rule reached. `SHOWWARNING` never becomes a
bound: DHIS2 lets a warned value through on import, and a bound nobody
enforces is a false claim.

### Naming and identity

Artifact names merge a configurable prefix and a kind token and underscore what
follows (`D2` + `OS` + `_Qdm5fPK5Ra9` + `_CS`); ids join the kebab of each
non-empty token with the identity stem kept verbatim (`d2-os-Qdm5fPK5Ra9-cs`).
`[generate.naming] source` picks the stem: the DHIS2 id under the default
`"id"`, the object's code under `"code-or-id"` (falling back to the id with a
note) and `"code"` (refusing the run on a missing, unusable, or colliding
code).

Names are decided **once for the whole selection**, by `resolve_identity_stems`:
whether a code can serve as a stem depends on the peers it is resolved against,
so a per-object name cannot be reconstructed from one object alone. The
resulting identity plan is the boundary object every other target reads names
from, which is what lets a questionnaire's
`answerValueSet = Canonical(D2OS_SEX_VS)` name the ValueSet the same run
writes. Concept codes work the same way: they are assigned once per set, and
every target that names a concept reads that one assignment, so an example
cannot code an answer the CodeSystem has no concept for.

The canonical token registry lives in [How things are
generated](301-generation.md#naming).

## The foundation

`generate foundation` writes the part of the IG that depends on `fhir.toml`
alone and never opens a client. Four families.

**Identifier systems.** `d2-aliases.fsh` declares the `$DHIS2-*` aliases and
`d2-naming-systems.fsh` one `NamingSystem` per system, both built from
`[generate] identifier_system_base`. Fourteen subjects: organisation unit,
option set, option, category, category option, category combo, data set,
program, data element, category option combo, program stage, and tracked entity
type - each with a UID system and a `-code` sibling - plus tracked entity and
tracker enrollment, which get a UID system alone. That split is a property of
the DHIS2 object, not a gap: DHIS2 gives a tracked entity and an enrollment no
`code` attribute, so declaring a code system for them would declare a system
nothing can ever populate. Without these declarations the validator has no
definition behind a DHIS2 `identifier.system` and warns on every artifact
carrying one.

**Extensions**, one per DHIS2 fact FHIR has no element for:

| Extension | Contexted on | Carries |
| --- | --- | --- |
| `D2Period` | QuestionnaireResponse, MeasureReport | the ISO period, its type, optionally the dates |
| `D2PeriodType` | Questionnaire | the reporting frequency responses must use |
| `D2FormType` | Questionnaire, QuestionnaireResponse | which of the five form kinds |
| `D2DateLabels` | Questionnaire | the instance's own words for the enrollment, incident, and event dates |
| `D2CollectsIncidentDate` | Questionnaire | whether the program collects an incident date at all |
| `D2Repeatable` | Questionnaire | whether one enrollment may capture a stage twice |
| `D2Description` | Questionnaire.item | the DHIS2 free text guiding the person filling it |
| `D2EntityLevel` | Questionnaire.item | tracked entity or enrollment, per question |
| `D2AttributeValue` | Organization, Location, CodeSystem, ValueSet, Questionnaire | a DHIS2 metadata attribute value |
| `D2TrackedEntityAttributeValue` | the register's projected subject | a non-unique attribute value |
| `D2OrganisationUnit` | QuestionnaireResponse | where a tracker response was captured |
| `D2OrganisationUnitAssignment` | Questionnaire | the List of Locations a form admits |
| `D2OrganisationUnitLevel` | Location | the hierarchy level |
| `D2AttributeOptionCombos` | Questionnaire | the ValueSet of attribute option combos admitted |
| `D2AttributeOptionCombo` | QuestionnaireResponse | the one combo this response is keyed under |
| `D2TrackerEnrollment` | QuestionnaireResponse | the enrollment UID |
| `D2EnrolledAt` / `D2IncidentAt` | QuestionnaireResponse | the two enrollment dates |
| `D2SubjectExists` | QuestionnaireResponse | the person is already held by the instance |

The plural/singular splits are deliberate throughout: the form declares the
set, the response names one member. `D2AttributeOptionCombos` is a `canonical`
because a ValueSet is definitional and the guide binds those by URL everywhere
else; `D2OrganisationUnitAssignment` is a `Reference` because a `List` is an
instance. `D2Period` exists at all because a FHIR `Period` is a pair of
instants while a DHIS2 period is a *typed* interval - `202401` is the January
instance of the `Monthly` type, and the type is what makes it comparable and
round-trippable.

**The capture contract.** `d2-responses.fsh` declares one profile on
`QuestionnaireResponse` per form kind - `D2AggregateResponse`,
`D2EventResponse`, `D2TrackerRegistrationResponse`, `D2TrackerEventResponse`,
`D2TrackedEntityResponse` - each slicing the extensions its kind must carry.
Five flags on the declaration are what one shared template branches on, so a
further form kind is a declaration rather than a template. The three
tracked-entity profiles make `subject` a *logical* reference - `identifier`
under the tracked-entity system - because the IG publishes no subject instances
and the entity resolves against DHIS2 instead. Beside them,
`d2-capture-server.fsh` declares the `D2CaptureServer` CapabilityStatement
(`kind = #requirements`) and `d2-generate-operation.fsh` the
`D2GenerateOperation` OperationDefinition behind `$generate`.

The profiles are only half the contract. The other half is that every complete
generated example declares `InstanceOf:` the profile rather than the bare
resource, so SUSHI and the publisher validate the examples against the profiles
on every run and a profile that drifts from what generation produces fails the
build.

**The conversion contract.** `d2-aggregate-map.fsh` publishes the
`D2DataValueSet` logical model and the `D2AggregateResponseToDataValueSet`
StructureMap - see [the conversion layer](#the-conversion-layer).

R4 makes `date` mandatory on `NamingSystem`, `CapabilityStatement`, and
`OperationDefinition`, so those carry a pinned literal rather than a run
timestamp: a generated one would rewrite the file on every run.

Every URL family and every extension in full is in [Identifiers and the D2
extensions](401-identifiers-and-extensions.md).

## The regeneration contract

Two sweeps with different ownership rules, because FSH and JSON carry different
evidence.

**FSH and markdown carry a generated header.** A sync writes the target
directory, then deletes only header-bearing files it did not produce. Anything
hand-authored in the same directory survives, and a content-equal file is not
rewritten, so a no-op run leaves the tree byte-identical.
`tracker-programs/` is the one nested layout - a national instance's stage count
is what makes a flat directory unreadable - and the sweep tracks produced files
by path relative to the sync root, removing a subdirectory it emptied.

**JSON carries no header, so the directory is the evidence.**
`sync_json_artifacts` deletes every `*.json` its target did not produce. Two
JSON targets sharing a directory would therefore delete each other's documents,
which is why `registry/`, `terminology/`, `categories/`,
`attribute-option-combos/`, and `assignments/` each own one outright. The
exception is `concept-maps/`, where three targets co-own one directory behind a
single publisher glob: `sync_json_artifacts` takes an `owned_prefix`, so each
sweeps only its own id stem (`ConceptMap-d2-os-`, `-d2-cat-`, `-d2-aoc-`).

A definition SUSHI compiles from FSH and a predefined resource of the same
identity are a duplicate and SUSHI rejects the pair, so a target that emits JSON
also sweeps the FSH directory of the same name.

Every `title` and `description` a resource carries goes through whitespace
flattening and nothing else - those are elements a client reads back, so they
carry the DHIS2 text byte for byte. Escaping belongs to page furniture alone:
the FSH keywords and the generated markdown.

## Validation

`d2w fhir validate` checks the instance's codes for FHIR-safety and grades
severity **by build impact**: an error aborts your build, an info is instance
hygiene on objects the build never reads. That is the scope axis - every
finding carries `scope: "selection" | "instance"`, a finding on an object
outside the configured selection is downgraded rather than dropped, and the
report states the coverage.

Four passes share one finding shape:

1. **The instance-wide sweep** over `GET /api/metadata`: invalid FHIR codes as
   errors, per-type duplicates as warnings, plus `template-hostile-name` for
   names the publisher injects into breadcrumbs unescaped.
2. **The deep option-set pass**, which previews what
   `concept_code_source = "code"` would do - a decision the emitter makes at
   emit time, which the sweep structurally cannot see.
3. **The code-stem pass** over the six naming surfaces whose objects emit a
   resource carrying the code as an identifier value: `optionSets`,
   `categories`, `organisationUnits`, `dataSets`, `programs`, `programStages`.
   A warning under `code-or-id`, an error under `code` - the same defect
   description `resolve_identity_stems` refuses a run with, so validate and
   generate cannot disagree.
4. **The deep attribute pass**, which reads the sweep's own `attributes`
   collection and costs no request of its own.

A deep pass is warranted only where the sweep structurally cannot see the
outcome: a value assigned against an object's peers, or a decision made at emit
time. Nothing is found under the default `source = "id"`, which is the point -
the passes grade a migration you have not made yet.

Reports go to `reports/` in markdown, CSV, and PDF, all named
`fhir-validate-report`. `--no-fail` keeps the exit code at 0, and no
`fhir.toml` is required, because the sweep is a property of the instance rather
than of a project. Detail is in [Validate the
instance](201-validate.md).

## Serving

`d2w fhir serve` loads everything once at startup and holds it frozen on
`app.state.context`, so a request is index lookups and nothing else. The store
is indexed by `(resourceType, id)`, by canonical URL, and by every
`system|value` identifier token; a resource body is passed through
byte-faithfully, and an unreadable file fails loudly naming itself rather than
being skipped.

**Two stores, one axis.** The default is the **compiled** IG on disk - both
`ig/fsh-generated/resources` and `ig/input/resources`, read whole. `--live`
builds the same read set off a DHIS2 instance at startup instead, running the
JSON twins of the generate builders; parity between the two is gated by tests.
A live store holds no FSH-only definitional artifacts - no StructureDefinitions,
no `kind = #requirements` CapabilityStatement - and `/metadata` names the store
mode it is running.

Reads, search, `$translate`, `$generate`, capture, and the spool behave
identically either way. What needs live is the register.

### The routes

| Route | Answers |
| --- | --- |
| `GET /metadata` | the `kind = #instance` CapabilityStatement, pre-rendered at startup |
| `GET /{type}` | search: register dispatch, else the spool for QuestionnaireResponse, else the store |
| `GET /{type}/{id}` | read, dispatched the same way |
| `POST /QuestionnaireResponse` | the only write |
| `GET\|POST /Questionnaire/{id}/$generate` | a synthetic response against that form |
| `GET /ConceptMap/$translate` | a published coding back to its DHIS2 identifiers |
| `GET /spool` | every receipt with its lifecycle, counts, and import rollups |
| `GET /uiconfig` | basemaps, the DHIS2 base URL, the register configuration |
| `GET /tracked-entities/{uid}/enrollments` | one entity's program enrollments |

Fixed paths mount before the read catch-alls and the UI shell mounts last, so a
UI route never shadows a FHIR one. Every GET also answers HEAD. Three of these
are deliberately **not** FHIR - `/spool`, `/uiconfig`, and the enrollment
listing - because no R4 resource says what they say. Everything else, including
every refusal and every 404, is FHIR: errors funnel to an `OperationOutcome`.

`$generate` is a custom operation returning its resource directly rather than
wrapped in `Parameters`, and it is deliberately not SDC's `$populate`, which
means fill-from-real-context where this invents its data. The seed rides back
on the response's `identifier` so a generated document can be reproduced.

### The register

The register is the part of a served facade that answers about *tracked
entities the instance holds*, and the only part that reads DHIS2 per request
rather than from the loaded store. It is therefore live-only; a compiled run
answers a `not-supported` OperationOutcome telling you to restart with
`--live`.

Five modules:

- `index.py` builds `TrackedEntityIndex` at startup **from the published guide,
  never from config** - which types the registration forms register, which FHIR
  resource `D2TET_CM` maps each onto, and which attributes `D2TEA_CS` declares
  unique or searchable.
- `surface.py` narrows that by `[serve.tracked_entities]`:
  `tracked_entity_types` and `search_attributes` are taken verbatim when
  stated, and the published sets are the default.
- `wire.py` is the DHIS2 read against `/api/tracker/trackedEntities`, always
  `ouMode=ACCESSIBLE`, folding "does not exist" into an empty answer.
- `listing.py` is a stateless paging cursor - a base64url token opaque to
  clients, and a page never mixes tracked entity types.
- `projection.py` builds the served resource: the UID as `id` and as the first
  identifier, one identifier per unique attribute value, the type as a
  `meta.tag`, and every remaining attribute value as an extension. It fills no
  `Patient.name`, no `gender`, no `birthDate` - **no demographics are
  invented**, because DHIS2 attribute semantics are per-instance and a guess
  would be indistinguishable from a fact.

`routes/register.py` mounts no path of its own: `routes/read.py` dispatches to
it at request time for whichever resource types the surface serves, so the
served set follows the published map rather than a hardcoded `Patient`.
Refusals are ordered so the message names the real reason - disabled by
configuration, not live, no published type, or not in this surface.

### Capture

`POST /QuestionnaireResponse` runs a phase machine, each phase the last to run
if it errors, collecting every issue within a phase: the body's JSON and R4
shape, then the declared form kind and its profile invariants, then the
questionnaire the response names, then the organisation-unit assignment, the
attribute option combo, the period, and finally every answer item - link ids,
cardinality, `value[x]` types, and terminology.

Four gradings flip from warning to refusal on `--strict-codes`: coded-answer
spelling, an organisation unit outside the published assignment, a disagreeing
attribute option combo, and a subject typed as an unexpected resource. Coded
answers otherwise resolve through three tiers - the published concept code, the
DHIS2 option UID, then the DHIS2 option code - with the fall-back noted;
ambiguity is an error under either setting.

Tracker identifiers are checked for DHIS2 UID *shape* only. Uniqueness is
DHIS2's answer to give, and asking it here would put a read on the capture
path.

**Nothing in `capture/` talks to DHIS2**, and every extension URL, identifier
system, and profile URL it needs is derived from `fhir.toml` alone. Acceptance
is a 201 with a `Location` header and an informational `OperationOutcome`
carrying one issue per warning.

### The spool

Everything captured lands in `<project>/.serve/responses`, one file per
submission, in three subdirectories that *are* the lifecycle: `received/`,
`forwarded/`, `rejected/`. A receipt holds the submission byte-faithfully as it
arrived plus the id the server stamped on it, its form kind, its
questionnaire, its arrival instant, and any warnings it was accepted with.

Lifecycle is not written into the file - it is which directory the file sits
in, which is what makes a forward run a pure rename. Beside a drained receipt
the forwarder writes an `<id>.report.json` sidecar: in `forwarded/` what the
import counted, in `rejected/` why DHIS2 refused.

The spool is the deliberate exception to load-once. It is a path rather than a
loaded index and every read re-reads the directory, because `d2w fhir forward`
is a separate process moving files while the server is up. Writes are atomic,
and a receipt stays readable through `GET /QuestionnaireResponse/{id}` in all
three states.

Configuration and the served contract are in [Serving
it](301-serving.md) and [Consume the FHIR
API](401-consume-the-fhir-api.md).

### The capture UI

`--ui` mounts a browser front end on the same port the facade answers on -
same-origin, so it needs no CORS and no second process. The source is
`packages/dhis2w-fhir-serve/frontend/`; the build output ships in the wheel and
is gitignored in the repository, so `make build-frontend` runs before
`make build` and a missing bundle raises before the server prints its banner.

Eleven pages: Overview, Forms, FormFill, Responses, ResponseDetail,
Organisation units (the hierarchy on a map, which is what `--basemap` exists
for), Terminology, TerminologyDetail, Server, Tracked entities, and
TrackedEntityDetail.

`lib/questionnaire.ts` is the DOM-free half - the flattened form spec, the
`linkId`-keyed reducer, the `enableWhen` predicate, and an item-type table
transcribed from the Python conversion context, so the browser and the
forwarder agree about what an answer element is. `lib/api.ts` guards every path
against the served resource types plus `metadata`, `spool`, `uiconfig`, and
`tracked-entities`, so a typo reaches no network. The frontend make targets sit
outside `make lint` and `make test`; see [The capture
UI](201-capture-ui.md).

## The conversion layer

`dhis2w_fhir.conversion` is one direction only - a captured
`QuestionnaireResponse` into a DHIS2 import payload. The other direction is the
generate targets.

Six modules: `artifacts.py` reads the project's published IG (or the live
documents) into the definitions the translation needs; `context.py` flattens
Questionnaires into form specs, builds option tables from the CodeSystems as
refined by the ConceptMaps, and maps a `Location.id` back to its DHIS2 UID off
the identifier slice rather than by assuming the id is the UID; `values.py`
turns one question's answers into one DHIS2 wire value; `payloads.py` holds one
translator per form kind; `translator.py` dispatches; `schemas.py` holds the
context types and the outcome taxonomy.

Payloads are the **generated OpenAPI models** - `DataValueSet`, `TrackerEvent`,
`TrackerTrackedEntity`, `TrackerEnrollment` - not hand-rolled shapes.

Dispatch asks three ordered questions: which form kind does the submission
declare, does its `questionnaire` name a form the context holds, and do the two
agree. Only then does the kind's translator run. Posting order puts people
first - tracked entity, tracker, enrollment, then data value set, event,
tracker event - because DHIS2 refuses an event whose enrollment it cannot find.

`d2w fhir forward` drives it. A dry run is the default and posts everything
under the endpoint's own validate-only mode, so DHIS2's own rules grade the
whole spool without a write; `--import` commits. A drain that meets a server
error stops and preserves the rest rather than continuing, every import writes
its sidecar, and completeness is registered only for values that actually
landed. A conversion-refused response stays in `received/`, because the fix for
it is local and the next run is the retry.

**Phase A and phase B.** The above is phase A: the reference implementation, in
Python, which is what ships. Phase B lifts the same contract into the guide so
a bridge written in another language does not have to read Python to agree with
it. The `D2DataValueSet` logical model and the
`D2AggregateResponseToDataValueSet` StructureMap are the aggregate leg of that,
authored as FSH instances because SUSHI compiles no FHIR Mapping Language. The
map is a **contract, never an engine**: nothing here executes it, a CI gate
holds the Python to it, and each rule whose meaning exceeds what a transform can
state says so on its own documentation. The tracker logical model and the
reverse maps are still owed. The staged plan is [the FHIR conversion
layer](design/conversion.md).

## The conformance runner

`d2w fhir doctor` runs the whole chain against one instance and reports what
the instance breaks, in nine phases: **connect**, **scaffold** (a throwaway
project on a deliberately coherent probe - one data set, one event program, one
tracker program, and a registry root the selected forms are actually assigned
under), **generate**, **compile** (a real FSH compiler where one exists,
skipped where none does), **validate**, **serve** (the store built in process,
no socket and no subprocess), **capture** (every published form filled by
`$generate` and posted back, holding the endpoint to its own 201 invariant),
**forward** (the spool drained under validate-only), and **oracle**.

The oracle phase needs `--live`: the DHIS2 instance judges the served resources
object by object across four families - organisation units, option sets, data
sets, programs - resolving every served UID in batches and deep-comparing a
seeded sample. It is the only phase that can say the guide is *wrong* rather
than merely unbuildable.

Outcomes are pass, warn, fail, skipped (this machine does not offer it) and
blocked (a dependency produced no input). Only a failure exits 1, so a warning
does not break a pipeline. `doctor` reimplements nothing - it calls
`init_project`, `generate_full`, `validate_codes`, `create_app`, and
`forward_responses` the same way the commands do, which is what makes it a
conformance runner rather than a second implementation. `--workspace` and
`--keep` retain the throwaway project, `--all-targets` skips the probe, and the
report lands at `reports/fhir-doctor-report.md`. See [Check an instance with
doctor](201-doctor.md).

## Code layout

Everything lives in the two members. There is no central models module: each
component owns its own `schemas.py`, so a component's projections, view-models,
and naming sit beside the code that emits them.

`dhis2w_fhir/`:

```
cli.py, mcp.py, plugin.py    The three thin surfaces
config.py                    fhir.toml, composing every selection table
service.py                   The orchestrator: fetch, emit, report
names.py                     Identity stems, slugs, markdown escaping
i18n.py                      Locale normalisation and translation projection
attributes.py                DHIS2 metadata attribute projection + code index
notes.py                     The typed note kinds every target reports through
writer.py                    The two sync sweeps and the generated header
status.py                    [ig] status -> FHIR status + experimental
spool.py                     The read side of .serve/responses
doctor.py                    The nine-phase conformance runner
r4/                          Frozen, alias-aware R4 models; JSON is dumped from these
period/                      The 23 period types, parse_period, recent_periods
scaffold/                    init and --refresh
validation/                  The four passes, the scope axis, the report renderers
foundation/                  Identifier systems, extensions, profiles, the contract
conversion/                  QuestionnaireResponse -> DHIS2 (phase A)
resources/                   One package per DHIS2 domain that emits artifacts:
                             option_sets, categories, attribute_combos,
                             questionnaires, examples, organisation_units, pages
```

`dhis2w_fhir_serve/`:

```
app.py, settings.py          The application and its settings
store.py, live.py            The two stores
capability.py, metadata.py   /metadata
capture/                     naming, index, resolve, validate, outcome
register/                    index, surface, wire, listing, projection
routes/                      capture, read, register, generate, translate,
                             spool, uiconfig, enrollments, context
synthesize.py                $generate
spool.py                     The write side of .serve/responses
errors.py, log.py, ui.py     OperationOutcome handlers, logging, the UI mounts
```

`resources/` is reserved for DHIS2 domains, which is why `scaffold/`,
`validation/`, `conversion/`, and `r4/` stay top-level - they are toolkit
concerns, not DHIS2 ones. No component imports `config.py` at runtime; the
service composes and passes what each needs.

Several components ship a `documents.py` beside their FSH templates - the JSON
twin of the same artifact, which is what live mode builds from and what parity
tests hold to the FSH.

**Nothing is built by string concatenation.** Every emitting component ships a
`templates/` directory under a scoped Jinja loader with `StrictUndefined`, and
every JSON document is a frozen `extra="forbid"` pydantic model dumped with
`exclude_none` and `by_alias`. A missing template variable is a build failure,
not a blank.

The narration surface is uniform: the service takes an optional progress
reporter and never starts or stops it, the CLI owns that lifecycle, stderr
carries every step and stdout carries only the `--json` payload.

## Toolchain performance

The compile scales with the *forms*, not with the instance: the registry and
the terminology pairs are predefined JSON the publisher loads verbatim, so only
the definitional artifacts pass through SUSHI. The publisher's per-resource
rendering then absorbs the volume, and it is the slow half of any build. The
publisher runs its own embedded SUSHI, which is why the scaffolded `make
refresh` goes validate then build rather than compiling twice.

Two caches are worth knowing about. The `fhir-ig-cache` named volume holds the
publisher's package downloads, which dominate a cold machine; `make clean-all`
removes it and `make clean` does not. `ig/input-cache/` holds the terminology
server cache and is left alone by both. `JAVA_HEAP` sizes the publisher JVM -
too large for the docker VM and the kernel OOM-kills the build with exit 137.

The upstream behaviours behind these are catalogued in [the roadmap's quirks
section](design/roadmap.md#4-upstream-dhis2-and-tooling-quirks-that-shape-the-code);
the operator-facing version is [Build and publish the
guide](201-build-and-publish.md).

## Where the rest lives

This page says what the packages are. Where they are going, and why each shape
was chosen, is in the project record:

- [FHIR roadmap and review guide](design/roadmap.md) - the settled and
  open decisions, the four review dimensions, and the build measurements.
- [FHIR conversion layer](design/conversion.md) - the staged plan,
  phases A through C.
- [Corrections and withdrawals](design/data-lifecycle.md) - the data
  lifecycle the spool is the provenance record for.
- [DHIS2 fidelity audit](design/dhis2-fidelity.md) - every concept
  that makes DHIS2 distinctively DHIS2, with a verdict.
- [FHIR harmonization](design/harmonization.md) - how several country
  guides relate.
- [FHIR enrollment resource](design/enrollment-resource.md) - the read
  side's enrollment shape.
