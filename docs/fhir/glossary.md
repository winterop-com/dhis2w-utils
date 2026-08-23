# Glossary

Two vocabularies meet in this series, and `d2w fhir` adds a third of its own.
This page is the dictionary between them, written for someone who knows DHIS2
and is meeting FHIR here for the first time.

It reads in two directions:

- **[DHIS2 terms](#dhis2-terms)** - you know the term; the entry says what
  `d2w fhir` does with it.
- **[FHIR and toolkit terms](#fhir-and-toolkit-terms)** - you met the term in
  these pages or in a published guide; the entry says what it is in DHIS2
  terms.

A third section, **[words that mean two things](#words-that-mean-two-things)**,
names the collisions - a handful of words carry one meaning in DHIS2 and a
different one in FHIR, and mistaking them costs an afternoon.

Entries are one or two sentences. Where a term has a page of its own, the entry
links to it; [FHIR for DHIS2 people](101-fhir-concepts.md) is the long-form
companion to the second section here.

---

## DHIS2 terms

What the toolkit does with each concept you already know.

### Metadata and identity

**UID**
: DHIS2's eleven-character identifier for every metadata object. It is the
default *identity stem* - the thing artifact names and ids are built from - and
it always survives onto the FHIR resource as an `identifier`, whatever else the
naming configuration does. See [Identifiers and the D2
extensions](401-identifiers-and-extensions.md).

**code**
: The optional short human-authored key a DHIS2 object may carry beside its
UID. Every generated artifact exposes *both* DHIS2 identifiers - the UID and
the code - so a consumer holding either can get back to the object.
`[generate.naming] source` decides which one names the artifact; a missing or
FHIR-illegal code falls back to the UID. Not the same as a FHIR `code`
datatype - see [words that mean two things](#words-that-mean-two-things).

**attribute (metadata attribute)**
: The arbitrary key-value pair any DHIS2 metadata object may carry - a national
registry id on a facility, an external warehouse key. It has no natural FHIR
element, so it rides as a `D2AttributeValue` extension on the five resource
types that carry one: Organization, Location, CodeSystem, ValueSet, and
Questionnaire.

**translations**
: The per-locale display names DHIS2 stores beside an object's default name.
They travel onto the R4 translation extension on the element they translate, so
a form served to a French-speaking user reads in French without a second fetch.
`[generate] locales` narrows which ones are emitted; empty means every locale
the instance holds.

**sharing**
: DHIS2's per-object read/write access model. It is **not** carried into the
guide: a published IG is a public document, and the facade serves what the
project generated rather than what a given user may see. Access control belongs
to whatever fronts the served endpoint.

### Aggregate side

**data set**
: The aggregate reporting form. It becomes one `Questionnaire` of form kind
`aggregate`, whose questions are the data set's data elements and whose groups
are its sections. Its period type becomes the `D2PeriodType` extension on the
form, so a client knows what shape of period to answer with.

**section**
: A named block of a data set's entry form. It becomes a `#group` item in the
Questionnaire, in the data set's own order.

**data element**
: The thing measured. It becomes one Questionnaire question, typed from its
DHIS2 `valueType`; an option-set-bound element becomes a `#choice` question
with an `answerValueSet`. Every referenced element is also published as a
concept in the `D2DE_CS` data dictionary CodeSystem, carrying its DHIS2 code,
its domain type, and its value type as concept properties.

**value type**
: The DHIS2 datatype of a data element or tracked entity attribute (`NUMBER`,
`TEXT`, `DATE`, `BOOLEAN`, `TRUE_ONLY`, `MULTI_TEXT`, …). It picks the
Questionnaire item type and is published as a `value-type` concept property so
a consumer can read it off the terminology rather than infer it.

**MULTI_TEXT**
: The DHIS2 value type meaning "several options from one set". It becomes a
`#choice` question with `repeats = true` - that is the whole of what MULTI_TEXT
means in FHIR terms.

**domain type**
: A data element's `AGGREGATE` or `TRACKER` domain. Published as the `domain`
concept property on `D2DE_CS`.

**category**
: One axis of a disaggregation - Sex, Age band. Structurally an option set, so
it becomes a CodeSystem/ValueSet pair exactly as an option set does, under the
`CAT` naming token.

**category option**
: One value along a category's axis. It is a concept inside its category's
CodeSystem, not an artifact of its own, so nothing names it separately.

**category combination (category combo)**
: The set of categories a data element or data set is disaggregated by. It is
not published as an artifact; what is published is the combination's *option
combos*.

**category option combo (COC)**
: One cell of a disaggregation - "Female, 15-19". On an aggregate form a
disaggregated data element becomes a group with one child question per option
combo, `linkId` `<dataElementUid>.<cocUid>` - the same key a DHIS2 data value
carries. Every referenced combo is a concept in `D2COC_CS`, decomposed into one
`Coding` property per category it splits over.

**attribute option combo (AOC)**
: The second key on an aggregate data value - the one that says *which* funding
stream, project, or partner the value belongs to. A data set on a non-default
attribute category combo publishes a `D2AOC_<stem>` CodeSystem/ValueSet pair
naming the combos its responses may be keyed under, and a response names one of
them on the `D2AttributeOptionCombo` extension. A response naming none against
such a form is refused, because DHIS2 answers `E8023`.

**data value**
: One measured number or answer, keyed in DHIS2 by
`(dataElement, period, orgUnit, categoryOptionCombo, attributeOptionCombo)`. It
is one answer item in a `QuestionnaireResponse`; `d2w fhir forward` reassembles
the key from the response's answers, its `D2Period`, its subject, and its
`D2AttributeOptionCombo`.

**period / period type**
: A DHIS2 period is a *typed* interval - `202401` is the January instance of
the `Monthly` type - which a FHIR `Period` (a pair of instants) cannot express.
The `D2Period` extension carries the ISO string, the type, and optionally the
resolved dates. All twenty-three DHIS2 period types are published as a
CodeSystem/ValueSet pair, and the toolkit ships a matching parser and its
inverse on its importable surface.

**completeness (complete data set registration)**
: DHIS2's "this form is finished for this period and unit" flag. `d2w fhir
forward` registers it - and only for values that actually landed, so
completeness is never claimed about an import that partly failed.
`--no-register-completeness` turns it off.

### Tracker side

**program**
: A DHIS2 program is either a *tracker program* (`WITH_REGISTRATION`) or an
*event program* (`WITHOUT_REGISTRATION`), and the two are selected by separate
`fhir.toml` tables because they publish different things.

**event program**
: A program capturing standalone events with no person behind them. It becomes
one `Questionnaire` of form kind `event`, answered for an organisation unit.

**tracker program**
: A program that enrolls a tracked entity and captures stages against that
enrollment. It publishes one registration form plus one form per program stage.

**program stage**
: One repeatable step of a tracker program. It becomes one `Questionnaire` of
form kind `tracker-event`, filed under its program's directory, titled
`<program> - <stage>`, and carrying the program UID as a third identifier so a
plain FHIR search returns a program's whole set of stages.

**registration form**
: The tracker program's own form - the questions asked when a person is
enrolled. Its questions are the program's tracked entity attributes rather than
a stage's data elements. Form kind `tracker`.

**tracked entity**
: The person - or specimen, or commodity - a tracker program follows. The guide
publishes no tracked entity instances; a response names one by *logical*
reference, `subject.identifier` under the tracked-entity identifier system, and
it resolves against DHIS2 rather than against the guide.

**tracked entity type (TET)**
: The kind of thing being tracked. It is a published vocabulary: `D2TET_CM`
maps each type UID onto the FHIR resource type its registrations are served as,
defaulting to `Patient`. `[generate.tracked_entity_types]` is where a type that
is not a person gets mapped to something else - see [Custom subject
types](401-custom-subject-types.md).

**tracked entity attribute (TEA)**
: A field captured about the tracked entity rather than about one event - a
national id, a name, a date of birth. Referenced attributes are published as
concepts in `D2TEA_CS`, carrying `dhis2-code`, `value-type`, and `unique`. On a
registration form each becomes a question; on the register each *unique* one
becomes a searchable identifier.

**unique attribute**
: A tracked entity attribute DHIS2 flags as unique. It is what tells a consumer
the question *identifies* the person rather than describing them, and it is a
default search key for the register.

**enrollment**
: A tracked entity's participation in one tracker program, carrying an
enrollment date and optionally an incident date. A response carries the
enrollment UID on the `D2TrackerEnrollment` extension - a registration response
mints one, a stage response names one that already exists - and the two dates
on `D2EnrolledAt` and `D2IncidentAt`.

**event**
: One occurrence of a program stage, or one standalone capture in an event
program. It is one `QuestionnaireResponse` against the corresponding form.

**organisation unit assignment**
: The subset of the hierarchy a form may be captured against. It is published
as a `List` of Locations, named from the form by the
`D2OrganisationUnitAssignment` extension. `List` rather than `Group` because R4
does not permit a Location to be a Group member.

### Hierarchy

**organisation unit**
: A place in the reporting hierarchy. Each one is published *twice*: as an
`Organization` (the reporting body) and as a `Location` (the place), joined by
the same DHIS2 UID. An aggregate or event form's response names the Location as
its `subject`.

**organisation unit level**
: The depth of a unit in the hierarchy - national, district, facility. Every
registry Location carries it as a `D2OrganisationUnitLevel` extension, so the
level is stated on the resource rather than recovered by counting parent hops.
The Organization half carries the same fact as `Organization.type`.

**geometry**
: The point or polygon DHIS2 holds for an organisation unit. It is emitted as
GeoJSON on the Location for every geometry, points included.

### Options

**option set**
: A DHIS2 coded list. It becomes a CodeSystem/ValueSet pair plus a ConceptMap
back to DHIS2, and a bound question's `answerValueSet` points at the ValueSet.

**option**
: One member of an option set. It becomes a concept in that set's CodeSystem,
carrying both DHIS2 identifiers - the UID as the concept code and the DHIS2
code as a property, or the reverse under `concept_code_source = "code"`.

---

## FHIR and toolkit terms

What each is, in DHIS2 terms.

### The FHIR model

**R4**
: The FHIR version this toolkit publishes and serves. FHIR versions are not
compatible with each other the way DHIS2 majors broadly are; everything here is
R4 and says so.

**resource**
: FHIR's unit of content - roughly "one row of one API endpoint". `Patient`,
`Location`, `Questionnaire` are resource *types*; a served document of that
type is a resource *instance*.

**element**
: One named field on a resource, the way `name` is a field on a DHIS2 data
element. FHIR fixes which elements a resource type has; anything the standard
did not anticipate needs an *extension*.

**extension**
: The standard way to carry a fact FHIR has no element for. Every DHIS2-specific
signal in a published guide rides one, and every one this toolkit defines is
named `D2Something` and declared in the guide itself, so a consumer can look up
what it means. See [Identifiers and the D2
extensions](401-identifiers-and-extensions.md).

**profile**
: A tightened version of a resource type - "a QuestionnaireResponse, but the
period extension is mandatory and the subject must be a Location". It is the
FHIR way of writing down a contract a submission has to meet. Nothing to do
with a `d2w` connection profile; see [words that mean two
things](#words-that-mean-two-things).

**slice / slicing**
: Naming the individual members of a repeating element so a profile can
constrain them one at a time - "the `D2Period` extension exactly once, the
`D2IncidentAt` extension at most once". Slice names are what let an instance
address an extension by name.

**canonical (URL)**
: The permanent URL that identifies a definitional resource - a Questionnaire,
a ValueSet, a profile - independent of where it is hosted. The `[ig] canonical`
setting is the stem every canonical in a project is built from. It is an
identifier, not necessarily a fetchable address.

**`id` versus `identifier`**
: `id` is the resource's key *on the server serving it*. `identifier` is a
business identifier that travels with the resource wherever it goes. A DHIS2
UID is published as both - as the `id` so a read is `GET /Questionnaire/<uid>`,
and as an `identifier` so it survives being copied elsewhere.

**reference**
: A pointer from one resource to another. A *literal* reference names a
resource by URL; a *logical* reference names it by `identifier` alone, which is
what a response uses for a tracked entity the guide does not publish.

**Bundle**
: FHIR's envelope for a collection - a search result, a batch. Every search this
facade answers returns a `searchset` Bundle.

**OperationOutcome**
: FHIR's error and warning body. Every refusal and every accepted-with-warnings
capture comes back as one.

**CapabilityStatement**
: A machine-readable statement of what a server does - which resource types,
which interactions, which profiles it accepts. Served at `GET /metadata`. The
guide also publishes `D2CaptureServer`, a `kind = #requirements` statement
declaring the contract independently of any running server.

**NamingSystem**
: The declaration that a given identifier system URL exists and what it
identifies. The guide declares one per DHIS2 identifier namespace, so a
validator has a definition behind every `identifier.system` an artifact
carries.

### Terminology

**CodeSystem**
: The definition of a set of codes and what they mean - a DHIS2 option set, or
a category, or the data dictionary over the elements a guide's forms reference.

**ValueSet**
: A selection of codes drawn from one or more CodeSystems, used to bind a
question's permitted answers. Each option set and category publishes a
CodeSystem and a ValueSet as a pair.

**Coding / CodeableConcept**
: A `Coding` is one `(system, code)` pair - the FHIR way of saying "this
option, from that set". A `CodeableConcept` is a coding plus free text.

**concept property**
: An extra fact attached to a concept in a CodeSystem, the way a DHIS2 object
carries attributes. This is where a data element's value type, an attribute's
`unique` flag, and the second DHIS2 identifier live.

**ConceptMap**
: A published mapping between two code systems. Beside every terminology pair
the guide writes one that maps each concept back to its DHIS2 identifiers, so a
consumer holding a generated coding can answer "which DHIS2 option is this?"
The served facade exposes it as `GET /ConceptMap/$translate`.

### The capture pair

**Questionnaire**
: The form definition. One is published per DHIS2 data set, per event program,
per tracker program stage, and per tracker program registration.

**QuestionnaireResponse**
: One filled-in form. This is what a capture client posts, what the spool
stores, and what `d2w fhir forward` converts into a DHIS2 payload.

**`linkId`**
: The key joining a response answer to the question it answers. For a
disaggregated aggregate cell it is `<dataElementUid>.<cocUid>` - the DHIS2 data
value key, spelled in FHIR.

**`subjectType` / `subject`**
: Who or what the form is answered *for*. An aggregate or event form's subject
is the organisation unit's Location; a tracker form's subject is the tracked
entity, and the organisation unit moves onto the `D2OrganisationUnit`
extension.

**form kind**
: This toolkit's five capture models, stated on every form and every response
by the `D2FormType` extension: `aggregate` (a data set), `event` (an event
program), `tracker` (a tracker program's registration form), `tracker-event` (a
program stage), and `tracked-entity` (a person-only registration form for a
tracked entity type, enrolling into nothing). It is the one switch the served
index, the conversion gate, the declared profiles, and the load set all read.

**response profile**
: The contract a submission of a given form kind must meet -
`D2AggregateResponse`, `D2EventResponse`, `D2TrackerRegistrationResponse`,
`D2TrackerEventResponse`, `D2TrackedEntityResponse`. Documented at [The capture
contract](401-capture-contract.md).

**`supportedProfile`**
: A server's declaration of which profiles it will accept a submission against.
Declaring a contract is not the same as claiming an interaction, which is why
the guide publishes more response profiles than the facade declares.

**`$generate`**
: The custom operation a served facade offers on a Questionnaire:
`GET /Questionnaire/{id}/$generate` returns a valid synthetic response against
that form. Deliberately not SDC's `$populate`, which means fill-from-real-data.

**`$translate`**
: The standard ConceptMap operation, served at `GET /ConceptMap/$translate` -
the route from a published coding back to its DHIS2 identifiers.

**logical model**
: A `StructureDefinition` describing a shape that is not a FHIR resource - here,
`D2DataValueSet`, which states DHIS2's own `/api/dataValueSets` payload in FHIR
terms: `dataSet`, `period`, `orgUnit`, `attributeOptionCombo`, `completeDate`,
and the data values under it.

**StructureMap**
: A published, machine-readable statement of how one shape becomes another -
`D2AggregateResponseToDataValueSet` maps the aggregate response profile onto
the `D2DataValueSet` logical model. It is a **contract, not an engine**: nothing
in this toolkit executes it, and a third party writing their own bridge in
another language reads it rather than reading the Python. See the [FHIR
conversion layer](design/conversion.md).

### The toolchain

**Implementation Guide (IG)**
: A published, browsable, versioned package of FHIR definitions plus narrative
- the artifact a ministry points integrators at. What `d2w fhir` produces.

**FSH (FHIR Shorthand)**
: The source language IG authors write definitions in, compiled to FHIR JSON.
The toolkit writes FSH for definitional artifacts and pre-built JSON for bulk
instances.

**SUSHI**
: The FSH compiler. It reads `ig/input/fsh/` and writes FHIR JSON.

**IG Publisher**
: The Java tool that takes the compiled resources and produces the browsable
guide - the HTML site, validation, and the downloadable package. The slow half
of a build.

**predefined resource**
: A FHIR JSON document placed in `ig/input/resources/` and loaded verbatim,
with no FSH parse. Every bulk instance - the organisation unit registry, the
terminology pairs - ships this way, which is what keeps a national instance's
artifact count out of the compile.

**`path-resource` glob**
: The `sushi-config.yaml` line that carries a folder of predefined resources
into the published guide. SUSHI recurses into sub-folders on its own; the IG
Publisher does not, so a missing glob is silent at compile time and lossy at
publish time.

**identity stem**
: The string every name and id of one artifact is built from - the DHIS2 UID
under the default `[generate.naming] source = "id"`, the object's code under
the code sources. Changing it reshapes the whole guide consistently.

**naming token**
: The short kind marker in a generated name - `OS` for option set, `CAT` for
category, `DS` for data set, `PR` for program, `PS` for program stage, `TET`
for tracked entity type, `AOC` for attribute option combo, `OU` for
organisation unit - configurable per kind in `[generate.naming]`. The registry
of tokens is in [How things are generated](301-generation.md).

### The toolkit's own words

**profile (`d2w`)**
: A named DHIS2 connection - base URL plus credentials - resolved from
`.dhis2/profiles.toml`. `fhir.toml` may pin one by name; credentials never live
in `fhir.toml`. See [words that mean two
things](#words-that-mean-two-things).

**project**
: One directory scaffolded by `d2w fhir init`, holding one `fhir.toml`, one
IG source tree, and one DHIS2 instance's worth of generated artifacts. Commands
find it by walking up from the working directory.

**target**
: One unit of generation - `foundation`, `option-sets`, `categories`,
`questionnaires`, `examples`, `org-units`, `pages`. A bare `d2w fhir generate`
runs all seven off a single pass over the instance; each is also runnable
alone. `load-set` is an eighth generate subcommand but not part of the full
run, because what it writes is not IG source.

**conversion layer**
: The code that turns a captured `QuestionnaireResponse` into the DHIS2 import
payload its form kind calls for - a data value set, an event, a tracked entity,
an enrollment. **Phase A** is that translator in Python, which is what
`d2w fhir forward` drives and what ships today. **Phase B** is publishing the
same contract *in the guide*, as logical models and StructureMaps, so a bridge
written in another language does not have to read Python to agree with it.

**coded answer tiers**
: The three spellings a submitted coded answer may arrive in, tried in order:
the concept code the guide published, the DHIS2 option UID, then the DHIS2
option code. Lenient is the default and notes which tier answered; `strict
codes` accepts the first tier alone.

**entity level**
: Whether a registration question's answer is written on the tracked entity or
on the enrollment. DHIS2 decides this per program-and-attribute pair, so it is
stated per question on the `D2EntityLevel` extension rather than once in a
dictionary.

**the register**
: The part of a served facade that answers about *tracked entities the instance
holds* - identifier search, paged listing, and one entity's enrollments. It
answers from DHIS2 per request rather than from the loaded store, so it exists
only on a live run. Which FHIR resource type it serves them as is whatever the
published `D2TET_CM` map says, defaulting to `Patient`.

**store**
: Everything the facade loaded at startup and answers reads from. A **compiled**
store is the built IG on disk; a **live** store is the same read set rebuilt off
a DHIS2 instance at startup, which is what `--live` selects. Reads, search,
`$translate`, `$generate`, and capture behave identically either way; the
register and the enrollment listing need live.

**the spool**
: The directory at `.serve/responses` where a served facade files everything it
captured, one file per submission, in four subdirectories that *are* the
lifecycle: `received/`, `forwarded/`, `rejected/`, and `withdrawn/`. The
directory is the index - nothing is cached, because a forward run is a separate
process moving files while the server is up.

**receipt**
: One spooled submission - the response byte-faithfully as it arrived, plus the
id the server stamped on it, its form kind, its questionnaire, when it arrived,
and any warnings it was accepted with. Its lifecycle is which directory it sits
in, which is what makes a forward run a pure rename.

**sidecar**
: The `<id>.report.json` written beside a drained receipt: in `forwarded/` it
says what the import counted, in `rejected/` it says why DHIS2 refused, and in
`withdrawn/` it says what DHIS2 answered when `d2w fhir withdraw` asked for the
event back. Every import writes one.

**forward / drain**
: `d2w fhir forward` reads the spool, converts every received response into the
DHIS2 payload its form kind calls for, and posts it. Dry run is the default;
`--import` is what actually writes. A drain that meets a server error stops and
preserves the rest rather than continuing.

**strict codes**
: The switch that turns four capture gradings from warnings into refusals -
coded answer spelling, an organisation unit outside the published assignment, a
disagreeing attribute option combo, and an unexpected subject resource type.
Off by default, on both `serve` and `forward`.

**doctor**
: `d2w fhir doctor` runs the whole chain against one instance in one command -
connect, scaffold, generate, compile, validate, serve, capture, forward, and
under `--live` an oracle phase - and reports what the instance breaks, with one
verdict. Run it before anything else on an instance you do not know. See [Check
an instance with doctor](201-doctor.md).

**load set**
: A synthetic corpus of responses written into `load/` by `d2w fhir generate
load-set`, for posting at a running facade. Not IG source and not published.

**capture UI**
: The browser form filler a served project offers on the same port the facade
answers on, enabled with `--ui`. See [Capture in the
browser](201-capture-ui.md).

---

## Words that mean two things

**profile**
: In DHIS2 tooling, a named connection to an instance - `d2w profile add`,
`-p myserver`, the `profile` key in `fhir.toml`. In FHIR, a constrained version
of a resource type - `D2AggregateResponse` is a profile on
`QuestionnaireResponse`. These pages say **`d2w` profile** or **connection
profile** for the first when context does not settle it, and plain *profile*
for the FHIR sense.

**code**
: In DHIS2, the optional short key beside an object's UID. In FHIR, a primitive
*datatype* with rules about which characters are legal, and separately the
`code` element inside a `Coding`. A DHIS2 code that is not a legal FHIR `code`
is why `[generate.naming] source = "code"` can refuse a run.

**register**
: In DHIS2, a verb - `d2w tracker register` creates a tracked entity. In this
toolkit, also a noun: *the register* is the served surface over the tracked
entities an instance holds. The served surface is never called "patients", and
its path is `/tracked-entities/{uid}/enrollments`, because what it holds is not
always people.

**record**
: In this toolkit, one tracked entity's events over time, served at
`/tracked-entities/{uid}/events` - each event as the `QuestionnaireResponse` its
programme stage's published form describes. A *record* is what DHIS2 holds now; a
*receipt* is what a client once submitted, and the two are different documents at
different addresses even though both are QuestionnaireResponses.

**identifier**
: In DHIS2, loosely any of UID, code, or name. In FHIR, a specific element with
a `system` and a `value`, and distinct from `id`. When these pages say
identifier they mean the FHIR element unless they say *DHIS2 identifier*, which
means the UID/code pair.

**period**
: In DHIS2, a typed interval with an ISO spelling - `202401`, `2024W03`. In
FHIR, `Period` is a bare start/end pair with no type. The `D2Period` extension
exists precisely because the two are not the same thing.

**event**
: In DHIS2, one occurrence of a program stage. In FHIR, nothing - there is no
`Event` resource; a DHIS2 event is published as a `QuestionnaireResponse`
against the stage's form.

**validate**
: `d2w fhir validate` grades a *DHIS2 instance's* codes by the impact they will
have on a build. The IG Publisher separately validates the *generated FHIR* against
the specification. Two different checks on two different things; `d2w fhir
doctor` runs both.

---

## See also

- [FHIR for DHIS2 people](101-fhir-concepts.md) - the same FHIR concepts at
  length, with the reasoning.
- [Identifiers and the D2 extensions](401-identifiers-and-extensions.md) -
  every identifier system and extension the guide defines.
- [Terminology and ConceptMaps](401-terminology-and-conceptmaps.md) - the
  emitted terminology in full.
- [How things are generated](301-generation.md) - the canonical naming-token
  registry.
