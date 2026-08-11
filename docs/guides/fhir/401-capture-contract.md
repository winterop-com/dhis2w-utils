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

## The four profiles

One per form kind, in `foundation/d2-responses.fsh`. "Form kind" is the
DHIS2 object the form was generated from: a routine *data set* reported
per period ("aggregate"), a standalone *event program*, and a *tracker
program* - a longitudinal record with a registration form and per-visit
*stage* forms.

| Profile | Parent | What it pins |
| --- | --- | --- |
| `D2AggregateResponse` | `QuestionnaireResponse` | `D2Period` 1..1, `D2AttributeOptionCombo` 0..1, `D2FormType` 1..1 fixed to `#aggregate`, `questionnaire` 1..1, `subject` 1..1 restricted to `Reference(D2Location)`. |
| `D2EventResponse` | `QuestionnaireResponse` | `D2FormType` 1..1 fixed to `#event`, `authored` 1..1, `questionnaire` 1..1, `subject` 1..1 restricted to `Reference(D2Location)`. |
| `D2TrackerRegistrationResponse` | `QuestionnaireResponse` | `D2FormType` 1..1 fixed to `#tracker`, `D2OrganisationUnit` 1..1, `D2TrackerEnrollment` 1..1, `D2EnrolledAt` 1..1, `D2IncidentAt` 0..1, `authored` 1..1, `questionnaire` 1..1, `subject` 1..1 with `subject.identifier` 1..1 and its `system` fixed to `{base}/id/tracked-entity`. No `D2Period`. |
| `D2TrackerEventResponse` | `QuestionnaireResponse` | `D2FormType` 1..1 fixed to `#tracker-event`, `D2TrackerEnrollment` 1..1, `D2OrganisationUnit` 1..1, `authored` 1..1, `questionnaire` 1..1, `subject` 1..1 with `subject.identifier` 1..1 and its `system` fixed to `{base}/id/tracked-entity`. No `D2Period`. |

The two tracker profiles restrict `subject` to `Reference(Patient)` - plus
every other type the project's
[tracked entity types](401-custom-subject-types.md) name, so a project that
tracks herds beside people publishes `Reference(Patient or Group)`. Which
type a given form's responses actually carry is pinned by that form's own
`subjectType`, and a capture server reads it from the compiled Questionnaire
- the generator's configuration never reaches a running facade.

`foundation/d2-capture-server.fsh` sits beside them: a `D2CaptureServer`
CapabilityStatement of `kind = #requirements`, declaring `create` on
`QuestionnaireResponse` with all four profiles as `supportedProfile`, plus
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
it collects one at all.

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
- **The incident date is graded on its primitive alone.** The compiled
  Questionnaire publishes no statement of whether the program collects one,
  so a response is accepted with `D2IncidentAt` and without it; what capture
  does check is that a carried one reads as an R4 `dateTime`.

**Identifier-keyed, and only identifier-keyed.** A registration response
publishes no `Patient`, no `EpisodeOfCare`, and no `CarePlan` - it mints the
DHIS2 identifiers and carries the attribute values. Whether a DHIS2
enrollment additionally maps to an `EpisodeOfCare` or a `CarePlan` is an
open roadmap decision; the resource layer would be an addition on top of the
identifier contract, not a prerequisite for it.

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

Two more things a capture client reads off the form, not the profiles:

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

Next: [Consume the FHIR API](401-consume-the-fhir-api.md) - the running
server that accepts what this contract describes - and
[Custom subject types](401-custom-subject-types.md) when the things being
tracked are not people.
