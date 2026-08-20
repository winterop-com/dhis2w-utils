# The capture contract

**Who this is for:** the integration developer building a capture client
against a published guide - fluent in FHIR, no DHIS2 knowledge assumed.

**Before you start:** a published IG to read, or a running facade serving
one ([Consume the FHIR API](401-consume-the-fhir-api.md)). No access to this
repository and no access to the DHIS2 instance is needed - that is the
point.

**You will be able to:**

- know which profile a `QuestionnaireResponse` must declare, per form kind
- build the right envelope for each of the five kinds - which elements are
  required, which are optional, and which are not read at all
- carry the DHIS2 context each profile pins - period, unit, entity,
  enrollment - in the right element
- mint the identifiers a registration creates, and know what a server can
  and cannot check about them
- tell a refusal from a warning before you send, and know which of the two a
  server's strictness dial moves
- read the required-question and numeric-bound rules off the Questionnaire
  itself

The whole point of publishing the forms is that somebody else can capture
data against them. Three artifacts make the IG a complete contract for that:
the response profiles, a requirements CapabilityStatement, and a prose
Capture page with validated examples. A third party needs the published
guide and nothing else.

The shapes are deliberately generic FHIR. A capture is a plain
`QuestionnaireResponse`, a vocabulary a standard `CodeSystem` and
`ValueSet`, an organisation unit a `Location`, a summary a standard
document `Bundle` - and everything DHIS2-specific rides in the D2
extensions and identifier conventions, never in the structure. Any FHIR
client reads what the facade serves without knowing DHIS2 exists; the
extensions are there for the round trip home. That layering is also what
makes this contract a pattern: another system could publish its forms the
same way, carrying its own identity in its own extension vocabulary.

## The five profiles

One per form kind, in `foundation/d2-responses.fsh`. "Form kind" is the
DHIS2 object the form was generated from: a routine *data set* reported
per period ("aggregate"), a standalone *event program*, a *tracker
program* - a longitudinal record with a registration form and per-visit
*stage* forms - and a *tracked entity type*, whose own registration form
creates a person and enrols them in nothing.

| Profile | Parent | What it pins |
| --- | --- | --- |
| `D2AggregateResponse` | `QuestionnaireResponse` | `D2Period` 1..1, `D2AttributeOptionCombo` 0..1, `D2FormType` 1..1 fixed to `#aggregate`, `questionnaire` 1..1, `subject` 1..1 restricted to `Reference(D2Location)`. |
| `D2EventResponse` | `QuestionnaireResponse` | `D2FormType` 1..1 fixed to `#event`, `authored` 1..1, `questionnaire` 1..1, `subject` 1..1 restricted to `Reference(D2Location)`. |
| `D2TrackerRegistrationResponse` | `QuestionnaireResponse` | `D2FormType` 1..1 fixed to `#tracker`, `D2OrganisationUnit` 1..1, `D2TrackerEnrollment` 1..1, `D2EnrolledAt` 1..1, `D2IncidentAt` 0..1, `D2SubjectExists` 0..1, `authored` 1..1, `questionnaire` 1..1, `subject` 1..1 with `subject.identifier` 1..1 and its `system` fixed to `{base}/id/tracked-entity`. No `D2Period`. |
| `D2TrackerEventResponse` | `QuestionnaireResponse` | `D2FormType` 1..1 fixed to `#tracker-event`, `D2TrackerEnrollment` 1..1, `D2OrganisationUnit` 1..1, `authored` 1..1, `questionnaire` 1..1, `subject` 1..1 with `subject.identifier` 1..1 and its `system` fixed to `{base}/id/tracked-entity`. No `D2Period`. |
| `D2TrackedEntityResponse` | `QuestionnaireResponse` | `D2FormType` 1..1 fixed to `#tracked-entity`, `D2OrganisationUnit` 1..1, `authored` 1..1, `questionnaire` 1..1, `subject` 1..1 with `subject.identifier` 1..1 and its `system` fixed to `{base}/id/tracked-entity`. No `D2TrackerEnrollment`, no enrollment dates, no `D2Period`. |

The three tracked-entity profiles restrict `subject` to `Reference(Patient)` - plus
every other type the project's
[tracked entity types](401-custom-subject-types.md) name, so a project that
tracks herds beside people publishes `Reference(Patient or Group)`. Which
type a given form's responses actually carry is pinned by that form's own
`subjectType`, and a capture server reads it from the compiled Questionnaire
- the generator's configuration never reaches a running facade.

`foundation/d2-capture-server.fsh` sits beside them: a `D2CaptureServer`
CapabilityStatement of `kind = #requirements`, declaring `create` on
`QuestionnaireResponse` with all five profiles as `supportedProfile`, plus
`read` and `search-type` on the `Questionnaire`, `CodeSystem`, `ValueSet`,
`Location`, `Organization`, and `List` resources a client resolves a form
from - `List` because a form's organisation-unit assignment is published as
one, and a capture client constrains its Location picker by reading it.

## The envelope, per form kind

The profiles above are what the published guide validates against. This is what
a running facade actually reads off the envelope, kind by kind. Each cell says
what the *server* does, which is the stricter of the two readings wherever they
differ.

| Element | `aggregate` | `event` | `tracker` | `tracker-event` | `tracked-entity` |
| --- | --- | --- | --- | --- | --- |
| `questionnaire` | required | required | required | required | required |
| `status` | required, `completed` | required | required | required | required |
| `authored` | not read | required | required | required | required |
| `subject.reference` | required, `Location/<uid>` | required, `Location/<uid>` | ignored, warned | ignored, warned | ignored, warned |
| `subject.identifier` | not read | not read | required | required | required |
| `subject.type` | not read | not read | graded on the dial | graded on the dial | graded on the dial |
| `D2FormType` | required, exactly 1 | required, exactly 1 | required, exactly 1 | required, exactly 1 | required, exactly 1 |
| `D2Period` | required, exactly 1 | not read | not read | not read | not read |
| `D2OrganisationUnit` | not read | not read | required, exactly 1 | required, exactly 1 | required, exactly 1 |
| `D2TrackerEnrollment` | not read | not read | required, exactly 1 | required, exactly 1 | not read |
| `D2EnrolledAt` | not read | not read | required, exactly 1 | not read | not read |
| `D2IncidentAt` | not read | not read | optional, 0..1 | not read | not read |
| `D2SubjectExists` | not read | not read | optional, 0..1 | not read | not read |
| `D2AttributeOptionCombo` | form-driven | form-driven | form-driven | form-driven | form-driven |

Three readings of that table are worth stating out loud.

**"Not read" means exactly that.** An extension outside its kind's column is
neither refused nor warned about - it rides into the receipt untouched. There
is one exception, `D2AttributeOptionCombo`, which is graded against the *form*
rather than the kind and is the only present-but-not-admitted case the server
has an opinion about.

**Where the two tracker kinds meet the person-only one.** A `tracked-entity`
response is the registration envelope with the enrollment half removed: same
subject shape, same organisation unit, and none of the three enrollment
elements. A `tracker-event` response is the registration envelope with the
*dates* removed: it names an enrollment that already exists rather than dating
one it creates.

**`subject` is either a place or an entity, never both.** An aggregate or event
response reports *for a place*, so the Location is the subject and there is no
organisation-unit extension. The three tracker kinds are *about an entity*, so
the subject is the entity and the place moves to `D2OrganisationUnit`. A tracker
response that also carries a `subject.reference` gets an informational warning
saying the reference is ignored, and is stored.

## The aggregate response's third key is per-form

`D2AttributeOptionCombo` is sliced `0..1` rather than `1..1` because whether
a response has to carry it is a fact about the form, not about the kind. A
DHIS2 data set can be reported per *attribute option combo* - a
project/funder dimension that keys the whole submission - and a data set on
the default dimension has exactly one, so naming it would be noise. The rule
the profile documents and a server enforces: a response answering a form
that carries `D2AttributeOptionCombos` has to carry `D2AttributeOptionCombo`,
coded from the ValueSet that extension names.

## `status` is the completeness claim

`QuestionnaireResponse.status` is `1..1` on every one of the five profiles, and
it is not bookkeeping.

**An aggregate response is stored as reported, so its status has to be
`completed`.** A submission is what DHIS2 files as a
`completeDataSetRegistration` for the `(data set, period, organisation unit,
attribute option combo)` tuple its values land under, and a facade that stored
a half-finished one would be holding a receipt for a report nobody made.
Anything else is refused:

```console
$ curl -s -X POST localhost:8389/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' --data-binary @in-progress.json
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"business-rule","diagnostics":"an aggregate response is stored as reported, so its status has to be `completed`, not `in-progress`","expression":["QuestionnaireResponse.status"]}]}
```

A client that lets a reporter save a half-filled form keeps that draft on its
own side and posts once, on the submit that finishes it. Re-posting the same
response later is how a correction is made; the spool keeps both receipts, and
[the data lifecycle](201-forward.md) is where that story continues.

**The other four kinds take any R4 status**, and it is carried through to the
receipt as sent. On an event or tracker-event response it maps onto the DHIS2
event status - [Forward](201-forward.md) has that table.

`authored` is the moment the capture was made. It is `1..1` on the event,
registration, tracker-event, and person-only contracts and graded as an R4
`dateTime`; on the aggregate contract it is not checked at all, because an
aggregate response's *when* is its `D2Period`. Nothing states *who* captured
it - the contract carries no reporter identity, so DHIS2 stores the API user.

## The tracked-entity subject is logical, not resolvable

The guide publishes no `Patient` instances - DHIS2 holds the tracked
entities and the IG describes forms, not people. So a tracker response
carries no `subject.reference` at all: it states `subject.type` and
identifies the entity through `subject.identifier`, whose `system` is fixed
to `{base}/id/tracked-entity` and whose value is the DHIS2 tracked entity
UID. That is the FHIR-native spelling for "this subject is real, and it
lives in a system this document does not contain". As served:

```json
"subject": {
  "type": "Patient",
  "identifier": {
    "system": "http://dhis2.org/fhir/id/tracked-entity",
    "value": "zPde0IgxLd6"
  }
}
```

`subject` being the entity, the unit the event was captured at rides on
`D2OrganisationUnit` as a `valueReference` to that unit's published
`Location`, and `D2TrackerEnrollment` carries the enrollment as a
`valueIdentifier` under `{base}/id/tracker-enrollment` - so the response
names the enrollment the event belongs to without inventing a resource for
it.

**Where a client gets those two UIDs:** from DHIS2 itself, and nowhere in
the guide - `d2w data tracker enrollment list` lists a program's enrollments
and the tracked entity each one registers. Resolving a person to an
enrollment is a DHIS2 operation; the IG's job is to state, unambiguously,
which two UIDs the response has to carry.

## A registration response mints them instead

`D2TrackerRegistrationResponse` carries the same two identifiers in the same
two places - but nothing on the instance holds either UID yet, because the
response is what creates them. The **client** mints both, as DHIS2 UIDs:
eleven characters, the first an ASCII letter, the rest alphanumeric. That is
what lets a client enrol a person and capture the enrollment's first stage
events in one breath, naming the enrollment its stage responses answer
against before any of them is sent. The response dates the enrollment too:
`D2EnrolledAt` 1..1 is when it begins, and `D2IncidentAt` 0..1 is when the
incident it follows occurred - `0..1` because a DHIS2 program states whether
it collects one at all, and the registration form publishes that statement on
`D2CollectsIncidentDate`. So a client knows before it fills anything whether
the response it is about to build carries an incident date, and a form served
from a compiled guide and one served `--live` say the same thing about the
same program.

What a capture server can honestly check about a minted identifier is its
*shape* - and nothing else. A facade holds no instance data, so "does this
person exist" is not a question it can answer, and a registration is
precisely the response for which the answer is meant to be no. Two
consequences the capture path states out loud:

- **Uniqueness is not checked.** A `unique` tracked entity attribute is a
  business identifier, and whether a value is already taken is global
  instance state. The facade stores the receipt; DHIS2 refuses the duplicate
  at import, and the rejection comes back through the forwarder like any
  other.
- **The minted UIDs are checked for shape, not for freedom.** Both
  `subject.identifier.value` and `D2TrackerEnrollment`'s value have to be DHIS2
  UIDs - one ASCII letter followed by ten alphanumeric places - and a value that
  is not one is refused naming which of the two it was. Whether the instance
  already holds that UID is not a question a facade can ask.
- **The incident date is graded on its primitive, and its absence is a
  warning** - see [the three markers](#the-three-markers-and-who-acts-on-each).
  `D2IncidentAt` is 0..1 on the profile, so a response is accepted with it and
  without it, and what capture checks about a carried one is that it reads as an
  R4 `dateTime`.

**Identifier-keyed, and only identifier-keyed.** A registration response
publishes no `Patient`, no `EpisodeOfCare`, and no `CarePlan` - it mints the
DHIS2 identifiers and carries the attribute values. Whether a DHIS2
enrollment additionally maps to an `EpisodeOfCare` or a `CarePlan` is an
open roadmap decision; the resource layer would be an addition on top of the
identifier contract, not a prerequisite for it.

## A person-only registration creates the person and stops

`D2TrackedEntityResponse` is the registration contract without its
enrollment half. It mints the tracked entity the same way - the client draws
the DHIS2 UID, and nothing on the instance holds it until the response is
imported - names the organisation unit the person is owned at, and carries
no `D2TrackerEnrollment`, no `D2EnrolledAt`, and no `D2IncidentAt`, because
the form it answers enrols nobody in anything.

That is not a degraded registration; it is what DHIS2 accepts. A bare
`trackedEntities` import under plain CREATE stands up a person who is
findable without a programme, and enrolling them later is a separate
submission against a tracker programme's own registration form.

Every question of such a form is at the entity level by construction - the
form asks the attributes the *tracked entity type itself* collects, which is
the set DHIS2 imports onto the tracked entity - so the forwarder writes every
answer onto the person and has no enrollment to split them across.

## Enrolling a person the instance already holds

The registration form is also how an *existing* person is enrolled in a
programme, and the response says which of the two it is through
`D2SubjectExists` - a `boolean` extension the registration profile admits
`0..1`. Absent or `false` is the default reading and the one every example in
this guide shows: the client minted `subject.identifier.value`, and the
response creates that person along with the enrollment. `true` says the
opposite - `subject.identifier.value` is the UID of a person the instance
already stores, and the response enrols them.

What changes is the whole import shape. A linked registration is forwarded as
a **top-level `enrollments` array**, under the same plain
`importStrategy=CREATE` every other payload goes under:

```json
{
  "enrollments": [
    {
      "enrollment": "EnAaBbCcDd1",
      "trackedEntity": "TeZzYyXxWw9",
      "program": "IpHINAT79UW",
      "orgUnit": "ImspTQPwCqd",
      "enrolledAt": "2026-01-04T08:00:00",
      "status": "ACTIVE",
      "attributes": [{ "attribute": "TeaHousehld", "value": "4" }]
    }
  ]
}
```

Three things about that payload are load-bearing:

- **No `trackedEntities` wrapper.** Nesting the enrollment inside one forces
  `importStrategy=CREATE_AND_UPDATE`, which silently rewrites the person's
  owning organisation unit to the one on the payload (`BUGS.md` 73). The
  person is not this response's to move, so the wrapper is never written.
- **The enrollment UID is still the client's.** `D2TrackerEnrollment` is
  `1..1` on a linked registration exactly as it is on a creating one, so the
  stage responses of the new enrollment can be captured in the same breath.
- **The program's own attributes ride the enrollment.** DHIS2 answers `E1018`
  to a mandatory program attribute that arrives on nothing, so every question
  the form marks `D2EntityLevel false` is written into `attributes` on the
  enrollment itself.

**An entity-level answer refuses the whole response.** A question the form
marks `D2EntityLevel true` asks the *person's own record*, and an
enrollment-only import has nowhere to put it. The forwarder refuses the
response rather than dropping the answer, naming each question it stumbled on
and stating the fix: answer it on that person's own record, or capture a new
person through the registration form without stating that the subject already
exists. Dropping it silently would be a captured value that reaches no
instance, and writing it would mean rewriting a person this contract does not
own.

A capture server grades the marker on shape alone - at most one, and it
carries a `valueBoolean`. Whether the UID names a person the instance holds is
the instance's answer, and the forwarder is where that is settled.

## The three markers, and who acts on each

Three booleans in this contract change what a submission *means* rather than
what shape it has, and they are acted on at three different points. A client
that knows which is which never waits for the wrong answer.

| Marker | Rides on | Read by | What it changes |
| --- | --- | --- | --- |
| `D2CollectsIncidentDate` | the `Questionnaire` | capture, as a warning | whether a registration is expected to carry `D2IncidentAt` |
| `D2SubjectExists` | the `QuestionnaireResponse` | the forwarder | whether the import creates the person or only enrols them |
| `D2EntityLevel` | the `Questionnaire.item` | the forwarder | whether an answer is written onto the person or onto the enrollment |

**Only the first is graded at capture, and only as a warning.** A registration
answering a form whose `D2CollectsIncidentDate` is `true`, carrying no
`D2IncidentAt`, is accepted with a warning naming the `E1023` DHIS2 will answer
that enrollment with. Refusing a shape the published profile admits `0..1`
would be the server arguing with its own contract.

**`D2SubjectExists` is graded on shape alone at capture** - at most one, and it
carries a `valueBoolean`. `true`, `false`, and absent are otherwise identical to
a capture server: whether the UID names a person the instance holds is a
question only the instance can answer, and it is the forwarder that asks it.

**`D2EntityLevel` is never read at capture at all.** It is a fact the *form*
publishes about its own questions, and the forwarder is what splits a
registration's answers across the person and the enrollment by it.

## What the server refuses, and what it only warns about

A refusal is one HTTP response with every issue that phase found, each locating
itself with a FHIRPath `expression`. A warning never rejects: it rides back on
the accepted capture's OperationOutcome and into the stored receipt.

### The refusals a client meets before any validation runs

| Condition | Status | Diagnostics |
| --- | --- | --- |
| a `Content-Type` that is not JSON | 415 | ``​`text/plain` is not a media type this server reads; send the body as `application/fhir+json` `` |
| a body that is not JSON, or not a JSON object | 400 | `the request body is not valid JSON (...)` |
| a `Bundle` | 400 | `this endpoint accepts one QuestionnaireResponse per request; post each response on its own request` |
| any other `resourceType` | 400 | ``this endpoint receives a QuestionnaireResponse, not a `Observation` `` |

**Every FHIR model on the capture path is closed.** An unknown key anywhere in
the resource - top level, inside `subject`, `item`, `answer`, or an `extension`
- is a 400 naming where it sat, not a silently dropped field:

```console
$ curl -s -X POST localhost:8389/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' --data-binary @extra-key.json
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"structure","diagnostics":"Extra inputs are not permitted","expression":["bogusKey"]}]}
```

That is deliberate: a capture client that misspells `authored` should hear
about it on the first request rather than discover months later that the field
never travelled. Everything past this point is a **422**.

### What is always a warning

Six findings are stated and stored, whatever the server's strictness dial:

- **an ignored subject reference** - a tracker response carrying
  `subject.reference` beside its identifier;
- **a missing incident date** where the form declares one is collected
  (`E1023`);
- **a claimed date range that is not what the ISO period resolves to** - the
  ISO period is what is captured, and the range is decoration;
- **an unanswered required question** - DHIS2 is where compulsoriness is
  enforced, and a partial capture that reaches the instance is better than one
  refused at the door;
- **terminology this project never published** - a coded answer whose ValueSet
  or CodeSystem is not served is stored unchecked rather than refused, because
  "I cannot check this" is not "this is wrong";
- **a code matched by a fall-back** - an answer sent as a DHIS2 option UID or
  DHIS2 code where the contract asks for the concept code.

### What `--strict-codes` turns into a refusal

The operator's dial, off by default, promotes exactly five findings from
warning to 422 ([Serve the guide](201-serve.md#coded-answers-lenient-by-default)):

- a subject typed as something other than what the form is answered about;
- an organisation unit outside the form's published assignment (`E1029`) -
  both on the envelope and on any answer carrying a reference;
- a response naming an attribute option combo against a form declaring no
  vocabulary;
- a response carrying no attribute option combo against a form declaring one
  (`E8023`);
- a coded answer whose code is in none of the served terminology.

Under strict, the fall-back tiers are switched off too: only the concept code
resolves, so an answer sent as a DHIS2 option UID is refused rather than warned
about.

### What is always a refusal

Everything else, and three that stay refusals even when the dial is off, because
leniency has nothing to be lenient about: a `valueCoding` carrying **no code**,
a coding drawn from **a different system than the form declares**, and a code
that **matches more than one option** in the served terminology - a server
cannot pick between two.

**What is never checked at all**: whether the subject exists, whether a `unique`
attribute's value is already taken, whether the Location a response names is one
the project published, and which profile the response's `meta.profile` claims.
The first two are global instance state, and a facade holds none; the third is
graded on the reference's *shape* so that a project publishing no registry still
captures; the fourth is a claim the server has no reason to trust over the
`D2FormType` it reads instead.

## The prose half, and the examples that check it

`pagecontent/capture.md` in the published guide walks an aggregate, an
event, and a tracker event response step by step against forms actually
selected in the project - the canonical URL rule, `D2Period` worked with a
real ISO period, the two `linkId` grammars (`<dataElementId>` and
`<dataElementId>.<categoryOptionComboId>`), the required rules, the event
status map - and closes with a table typing every DHIS2 value type onto its
item type, answer element, and literal spelling. The typing table is built
from the very tables the example emitter answers from, so the page and the
examples cannot disagree about how a value is spelled.

The examples are the contract check: every complete generated example
declares itself `InstanceOf:` the matching profile rather than the bare
resource, so SUSHI and the IG publisher validate each one against the
contract on every run. A profile that stops describing what generation
produces fails the build instead of shipping.

## What the Questionnaire itself tells you

Several things a capture client reads off the form, not the profiles:

- **The reporting frequency.** An aggregate form carries `D2PeriodType`, a
  code out of `D2PeriodType_VS`. It is the period type of the data set the
  form came from, so a client builds the ISO period its `D2Period` will
  carry from the form itself rather than from an example response.
- **What the instance calls the dates.** `D2DateLabels` carries the words
  the instance puts on the dates the form captures - `enrollmentDate` and
  `incidentDate` on a registration form, `eventDate` on a stage or event
  form - each slice present only where DHIS2 states a label, each with its
  own translations. A form carrying no slice is one the instance labelled
  nothing on, and the client uses its own wording.
- **Whether the stage repeats.** A tracker program stage form carries
  `D2Repeatable`, true or false, so a client knows whether an enrollment
  may hold several events of the stage before it offers to add one.
- **Guidance text.** An item carrying `D2Description` states the DHIS2 free
  text about the data element, tracked entity attribute, or section it is
  asked from. It is guidance for the person filling the form, not the
  question's label, which is why it rides an extension rather than `text`.
- **Read-only questions.** A registration or person-only form marks a
  question `readOnly = true` where DHIS2 generates the attribute's value
  itself off a reserved-value pattern. A client renders it, and never asks
  for it; the pattern is published beside the concept in `D2TEA_CS`.
- **Cells the data set never captures.** A greyed operand - DHIS2's
  `sections[].greyedFields` - is not published at all. The cell has no
  `linkId`, so a response answering it is not of the form, which is exactly
  what it is: a cell the instance refuses input on.
- **Required questions.** A data set's compulsory operands become
  `required = true` at the grain DHIS2 states them - an operand naming a
  data element alone marks the whole question and every disaggregated cell
  under it; an operand also naming a category option combo marks only that
  one cell.
- **Numeric bounds.** A value type that *is* a constraint carries it as
  standard `minValue` / `maxValue` extensions on the item:

| DHIS2 value type | Bound carried |
| --- | --- |
| `INTEGER_POSITIVE` | from 1 |
| `INTEGER_ZERO_OR_POSITIVE` | from 0 |
| `INTEGER_NEGATIVE` | up to -1 |
| `PERCENTAGE` | 0 to 100 |
| `UNIT_INTERVAL` | 0 to 1 |
| `INTEGER`, `NUMBER` | none - DHIS2 bounds neither |

Typed `valueInteger` on an integer item and `valueDecimal` on a decimal
one; disaggregated cells share their data element's value type, so they
carry the same bounds.

## Where an aggregate response ends up in DHIS2

The profiles say what a valid submission looks like. Two more artifacts say
what it *becomes*, for the aggregate kind:

- **`D2DataValueSet`** is a `kind = logical` StructureDefinition over the
  DHIS2 `/api/dataValueSets` envelope - the data set, the reporting period,
  and the organisation unit required, the attribute option combo and the
  completeness date optional, and one repeating data value carrying its data
  element, its category option combo, and a `string` value. Every DHIS2 data
  value is a string on the wire whatever its value type, which is why a
  lexical decimal survives the crossing unchanged.
- **`D2AggregateResponseToDataValueSet`** is the StructureMap onto it. Two
  groups: the envelope's facts, then a recursive walk of the item tree
  writing one data value per answered question, splitting
  `<dataElement>.<categoryOptionCombo>` out of the link id.

The map is a **contract, not an engine**. Nothing in this project executes
it, and four of its rules carry `documentation` stating what a transform
cannot: the data set comes off the *Questionnaire's* DHIS2 identifier rather
than off the response, the organisation unit needs the published Location
resolved, the attribute option combo goes through a ConceptMap where the
guide's concept codes are DHIS2 codes, and the wire value is the whole
serialisation table. Read those four before building a bridge from the map
alone.

Next: [Consume the FHIR API](401-consume-the-fhir-api.md) - the running
server that accepts what this contract describes - and
[Custom subject types](401-custom-subject-types.md) when the things being
tracked are not people.

Every envelope this page describes is built in typed Python under
`examples/fhir/client/`, one file per form kind, each printing the JSON it
would send and checking it converts before it claims anything.
