# The capture contract

**Who this is for:** the integration developer building a capture client
against a published guide - fluent in FHIR, no DHIS2 knowledge assumed.

**Before you start:** a published IG to read, or a running facade serving
one ([Consume the FHIR API](401-consume-the-fhir-api.md)). No access to this
repository and no access to the DHIS2 instance is needed - that is the
point.

**You will be able to:**

- know which profile a `QuestionnaireResponse` must declare, per form kind
- carry the DHIS2 context each profile pins - period, unit, entity,
  enrollment - in the right element
- mint the identifiers a registration creates, and know what a server can
  and cannot check about them
- read the required-question and numeric-bound rules off the Questionnaire
  itself

The whole point of publishing the forms is that somebody else can capture
data against them. Three artifacts make the IG a complete contract for that:
the response profiles, a requirements CapabilityStatement, and a prose
Capture page with validated examples. A third party needs the published
guide and nothing else.

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

`QuestionnaireResponse.status` is not bookkeeping. On an aggregate response it
is the statement DHIS2 files as a `completeDataSetRegistration`, so a client
picks it deliberately:

| `status` | What a forward run does |
| --- | --- |
| `completed` | imports the values, then registers the data set complete for the `(data set, period, organisation unit, attribute option combo)` tuple those values landed under |
| `in-progress` | imports the values and registers nothing |

There is no extension for this and there does not need to be one: R4 already
has the field, and the two codes already mean what DHIS2 means. A client that
lets a reporter save a half-filled form sends `in-progress`, and switches to
`completed` on the submit that finishes it - re-sending the same response as
`completed` later is what registers it, because a registration DHIS2 already
holds is updated rather than refused.

`authored` rides along as the day claimed: it is the only statement of *when*
the report was finished a response carries. Nothing states *who* finished it -
the contract carries no reporter identity, so DHIS2 stores the API user.

On an event response the same field means something else - it maps onto the
DHIS2 event status - and [Forward](../fhir/201-forward.md) has that table.

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
- **The incident date is graded on its primitive, and its absence is a
  warning.** `D2IncidentAt` is 0..1 on the profile, so a response is accepted
  with it and without it, and what capture checks about a carried one is that
  it reads as an R4 `dateTime`. Where the form's `D2CollectsIncidentDate` says
  true and the response carries no date, the receipt comes back with a warning
  naming the `E1023` DHIS2 will answer that enrollment with - refusing a shape
  the published profile admits would be the server arguing with its own
  contract.

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
resource, so `make sushi` and the IG publisher validate each one against the
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
