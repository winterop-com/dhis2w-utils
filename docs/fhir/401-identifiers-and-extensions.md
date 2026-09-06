# Identifiers and the D2 extensions

**Who this is for:** integration developers consuming a generated guide or a
served facade, who need to know exactly where the DHIS2 identity of every
artifact lives and what each `D2*` extension carries.

**Before you start:** read [FHIR for DHIS2 people](101-fhir-concepts.md) for
what an extension and an identifier slice are; have a generated project nearby
([quickstart](101-quickstart.md)) if you want to read real output alongside.

**You will be able to:**

- look up any `D2*` extension you meet and know what it means in DHIS2 terms
- resolve any generated artifact or concept back to its DHIS2 UID and code
- resolve a person, an enrollment, or a form to the DHIS2 object it names
- rely on the fall-back rules instead of special-casing missing codes

Every URL on this page has two variable halves. `{canonical}` is the IG's own
canonical - every `D2*` extension is a StructureDefinition under
`{canonical}/StructureDefinition/<id>`. `{base}` is `[generate]
identifier_system_base`, which every DHIS2 identifier system hangs off. The
worked examples below are real bytes from a facade whose canonical is
`http://localhost:8080/fhir` and whose identifier base is
`http://dhis2.org/fhir`.

The FSH names carry a configurable prefix, `[generate.naming] prefix`, `D2` by
default; the ids are the same tokens lowercased and hyphenated. A project that
sets no prefix still gets `D2` on these, because a definition may not shadow a
core FHIR name like `Period`.

## The extension registry

Nineteen extensions, and every one of them says something DHIS2 states that
FHIR has no element for. They divide by where they ride.

| Extension | Id | Rides on | Value |
| --- | --- | --- | --- |
| [`D2FormType`](#d2formtype) | `d2-form-type` | `Questionnaire`, `QuestionnaireResponse` | `code` |
| [`D2PeriodType`](#d2periodtype) | `d2-period-type` | `Questionnaire` | `code` |
| [`D2AttributeOptionCombos`](#d2attributeoptioncombos) | `d2-attribute-option-combos` | `Questionnaire` | `canonical(ValueSet)` |
| [`D2OrganisationUnitAssignment`](#d2organisationunitassignment) | `d2-organisation-unit-assignment` | `Questionnaire` | `Reference(List)` |
| [`D2DateLabels`](#d2datelabels) | `d2-date-labels` | `Questionnaire` | complex, 3 slices |
| [`D2Repeatable`](#d2repeatable) | `d2-repeatable` | `Questionnaire` | `boolean` |
| [`D2CollectsIncidentDate`](#d2collectsincidentdate) | `d2-collects-incident-date` | `Questionnaire` | `boolean` |
| [`D2Description`](#d2description) | `d2-description` | `Questionnaire.item` | `string` |
| [`D2EntityLevel`](#d2entitylevel) | `d2-entity-level` | `Questionnaire.item` | `boolean` |
| [`D2Period`](#d2period) | `d2-period` | `QuestionnaireResponse`, `MeasureReport` | complex, 3 slices |
| [`D2AttributeOptionCombo`](#d2attributeoptioncombo) | `d2-attribute-option-combo` | `QuestionnaireResponse` | `Coding` |
| [`D2OrganisationUnit`](#d2organisationunit) | `d2-organisation-unit` | `QuestionnaireResponse` | `Reference(D2Location)` |
| [`D2TrackerEnrollment`](#d2trackerenrollment) | `d2-tracker-enrollment` | `QuestionnaireResponse` | `Identifier` |
| [`D2EnrolledAt`](#d2enrolledat-and-d2incidentat) | `d2-enrolled-at` | `QuestionnaireResponse` | `dateTime` |
| [`D2IncidentAt`](#d2enrolledat-and-d2incidentat) | `d2-incident-at` | `QuestionnaireResponse` | `dateTime` |
| [`D2SubjectExists`](#d2subjectexists) | `d2-subject-exists` | `QuestionnaireResponse` | `boolean` |
| [`D2OrganisationUnitLevel`](#d2organisationunitlevel) | `d2-organisation-unit-level` | `Location` | `Coding` |
| [`D2AttributeValue`](#d2attributevalue) | `d2-attribute-value` | `Organization`, `Location`, `CodeSystem`, `ValueSet`, `Questionnaire` | complex, 3 slices |
| [`D2TrackedEntityAttributeValue`](#d2trackedentityattributevalue) | `d2-tracked-entity-attribute-value` | `Patient` | complex, 3 slices |

Each `^context` names exactly the resources that carry the extension. A context
of bare `Element` would attach it anywhere, which the IG publisher's QA calls
out as an unbounded extension - so no `D2*` extension has one.

### What a form declares

These five ride the `Questionnaire` and say what a capture client has to know
before it builds anything.

#### `D2FormType`

`{canonical}/StructureDefinition/d2-form-type`, a `code` bound (required) to
`D2FormType_VS`. The kind of DHIS2 object the form was generated from, and the
one extension that also rides the *response*, where it selects which of the
five response profiles applies. Five codes, and they are the whole vocabulary:

| Code | Display | Generated from |
| --- | --- | --- |
| `aggregate` | Aggregate data set form | a DHIS2 data set |
| `event` | Event program form | a DHIS2 event program |
| `tracker` | Tracker registration form | a DHIS2 tracker program |
| `tracker-event` | Tracker program stage form | a DHIS2 program stage |
| `tracked-entity` | Tracked entity type registration form | a DHIS2 tracked entity type |

```console
$ curl -s localhost:8389/Questionnaire/PsAncVisit1 | jq -c '.extension[0]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-form-type","valueCode":"tracker-event"}
```

#### `D2PeriodType`

`{canonical}/StructureDefinition/d2-period-type`, a `code` bound (required) to
`D2PeriodType_VS`. The reporting frequency of the data set the form came from,
so a client knows which ISO period format the instance will accept before it
builds one. Only an aggregate form declares it - only a data set has a
reporting frequency.

```console
$ curl -s localhost:8389/Questionnaire/TuL8IOPzpHh | jq -c '.extension[1]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-period-type","valueCode":"Monthly"}
```

It is the grain above [`D2Period`](#d2period): the form states the *type*, the
response states one *period* of that type, and both draw on `D2PeriodType_VS`.

#### `D2AttributeOptionCombos`

`{canonical}/StructureDefinition/d2-attribute-option-combos`, a
`valueCanonical` naming a ValueSet. The vocabulary of attribute option combinations
this form's responses may be keyed under. Plural on purpose: its response-side
sibling [`D2AttributeOptionCombo`](#d2attributeoptioncombo) is singular and
carries the one combo a submission chose.

```console
$ curl -s localhost:8389/Questionnaire/TuL8IOPzpHh | jq -c '.extension[2]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-attribute-option-combos","valueCanonical":"http://localhost:8080/fhir/ValueSet/d2-aoc-idcDPkDtepR-vs"}
```

**Absent means the default.** A data set on DHIS2's default category combo has
exactly one attribute option combo, so naming it would be noise; its form
carries no such extension and its responses carry no combo.

#### `D2OrganisationUnitAssignment`

`{canonical}/StructureDefinition/d2-organisation-unit-assignment`, a
`Reference(List)`. The organisation units the form may be captured against, as
the published `List` of their Locations. A capture client constrains its
Location picker by reading it, and a facade validates a submitted unit against
it.

```console
$ curl -s localhost:8389/Questionnaire/PrAncCare01 | jq -c '.extension[3]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-organisation-unit-assignment","valueReference":{"reference":"List/d2-pr-PrAncCare01-org-units"}}
```

**Absent means every unit the registry publishes.** DHIS2 hangs an assignment
on a data set and on a programme, never on a tracked entity type, so a
person-only form never carries one.

#### `D2DateLabels`

`{canonical}/StructureDefinition/d2-date-labels`, complex, three optional
slices - the words *this instance* puts on the dates the form captures:

| Slice | Cardinality | Type | Meaning |
| --- | --- | --- | --- |
| `enrollmentDate` | 0..1 | `string` | what the instance calls the date a tracker enrollment began |
| `incidentDate` | 0..1 | `string` | what the instance calls the date of the incident the enrollment follows |
| `eventDate` | 0..1 | `string` | what the instance calls the date an event was captured on |

Named for the dates rather than for the DHIS2 fields spelling them:
`enrollmentDateLabel`, `incidentDateLabel`, and `executionDateLabel` are three
DHIS2 form-rendering fields on two different objects, and what the contract
states is the words put on three dates.

```console
$ curl -s localhost:8389/Questionnaire/PsAncVisit1 | jq -c '.extension[2]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-date-labels","extension":[{"url":"eventDate","valueString":"Date of visit"}]}
```

**A slice is present only where the instance states a label**, so a form the
instance labelled nothing on carries no extension at all and a client falls
back to its own wording. Each label carries its own translations the way any
other string does.

#### `D2Repeatable`

`{canonical}/StructureDefinition/d2-repeatable`, a `boolean`. Whether one
enrollment may capture this tracker program stage more than once. Only a
`tracker-event` form declares it, and it declares it either way, so a client
never has to guess before offering to add a second visit.

```console
$ curl -s localhost:8389/Questionnaire/PsAncVisit1 | jq -c '.extension[1]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-repeatable","valueBoolean":true}
```

#### `D2CollectsIncidentDate`

`{canonical}/StructureDefinition/d2-collects-incident-date`, a `boolean`.
Whether the tracker program this registration form enrols a person into
collects the date of the incident the enrollment follows. Only a `tracker`
form declares it, and it declares it either way.

```console
$ curl -s localhost:8389/Questionnaire/PrAncCare01 | jq -c '.extension[1]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-collects-incident-date","valueBoolean":false}
```

Named for the fact rather than for the DHIS2 field spelling it -
`displayIncidentDate` is a form-rendering flag, and what the contract states is
that the program collects the incident date. A registration response carrying
[`D2IncidentAt`](#d2enrolledat-and-d2incidentat) is answering exactly this
declaration.

### What a question declares

Two extensions ride `Questionnaire.item`.

#### `D2Description`

`{canonical}/StructureDefinition/d2-description`, a `string`. The free text
DHIS2 holds about the object a question or a group is asked from - the
description of a data element, of a tracked entity attribute, or of a form
section. It is guidance for the person filling the form, which is why it rides
the item rather than the item's `text`, and it is present only where the
instance states one.

```console
$ curl -s localhost:8389/Questionnaire/PsAncVisit1 | jq -c '.item[0].extension'
[{"url":"http://hl7.org/fhir/StructureDefinition/minValue","valueInteger":1},{"url":"http://localhost:8080/fhir/StructureDefinition/d2-description","valueString":"The number of this visit in the pregnancy, counting from one."}]
```

#### `D2EntityLevel`

`{canonical}/StructureDefinition/d2-entity-level`, a `boolean`. Which DHIS2
level a registration question's answer belongs to: `true` for a tracked entity
attribute of the program's tracked entity type, whose answer is written onto
the *person*; `false` for an attribute only the program asks, whose answer is
written onto the *enrollment*.

```console
$ curl -s localhost:8389/Questionnaire/PrAncCare01 | jq -c '.item[] | {linkId, level: (.extension[]|select(.url|endswith("d2-entity-level"))|.valueBoolean)}'
{"linkId":"TeaNationId","level":true}
{"linkId":"TeaBirthDat","level":true}
{"linkId":"TeaSex00001","level":true}
{"linkId":"TeaHousehld","level":false}
{"linkId":"TeaSystemId","level":true}
{"linkId":"TeaConsent1","level":false}
```

It rides the item rather than the data dictionary because membership is a fact
about the attribute *and* the tracked entity type together: one dictionary is
shared by every form of the run, and two programmes on different types can
disagree about one attribute. Every question of a person-only
(`tracked-entity`) form is `true` by construction - there is no enrollment for
an answer to land on. It is also what
[`D2SubjectExists`](#d2subjectexists) interacts with: an entity-level answer
has nowhere to go in an enrollment-only import.

### What a response carries

Seven extensions ride the `QuestionnaireResponse`. Which of them a given
response must, may, or must not carry is the
[capture contract](401-capture-contract.md), per form kind; what each one
*means* is here.

#### `D2Period`

`{canonical}/StructureDefinition/d2-period`, complex. DHIS2 reporting periods
have no FHIR equivalent: a FHIR `Period` is a pair of instants, while a DHIS2
period is a *typed* interval - `202401` is not merely 1-31 January, it is the
January instance of the `Monthly` period type, and the type is what makes it
comparable, aggregatable, and round-trippable. So all three facts travel:

| Slice | Cardinality | Type | Meaning |
| --- | --- | --- | --- |
| `iso` | 1..1 | `string` | the DHIS2 ISO period identifier, e.g. `202401` |
| `type` | 1..1 | `code` | the period type, bound (required) to `D2PeriodType_VS` |
| `period` | 0..1 | `Period` | the date range the identifier resolves to |

```console
$ curl -s 'localhost:8389/Questionnaire/TuL8IOPzpHh/$generate?seed=7' | jq -c '.extension[0]'
{"extension":[{"url":"iso","valueString":"202607"},{"url":"type","valueCode":"Monthly"},{"url":"period","valuePeriod":{"start":"2026-07-01","end":"2026-07-31"}}],"url":"http://localhost:8080/fhir/StructureDefinition/d2-period"}
```

Its context is `QuestionnaireResponse` and `MeasureReport` - the aggregate
capture envelope and the later summary projection.

`D2PeriodType_CS` publishes every period type DHIS2 registers, each displayed
with its ISO format: `Daily (yyyyMMdd)`, `Monthly (yyyyMM)`, `FinancialApril
(yyyyApril)`, and so on through the weekly variants, the bi-weekly and
bi-monthly types, the November-anchored financial types, and the rest of the
twenty-three.

The matching parser lives in `dhis2w_fhir.period`:

```python
from dhis2w_fhir.period import parse_period

parse_period("2024BiW2")
# PeriodValue(iso='2024BiW2', period_type='BiWeekly',
#             start_date=date(2024, 1, 15), end_date=date(2024, 1, 28))
```

`recent_periods` is its inverse, and the example target's way of finding a
period worth looking for data in: the most recent periods of a type whose end
date is already past, newest first.

```python
import datetime
from dhis2w_fhir.period import recent_periods

recent_periods("Monthly", 3, datetime.date(2026, 8, 2))
# ['202607', '202606', '202605']
```

It is written as an inverse rather than as a second transcription of the
upstream month offsets: each type declares only how its ISO strings are spelled
for a given year, and `parse_period` decides which of those exist and what
dates they cover - so the two can never disagree.

#### `D2AttributeOptionCombo`

`{canonical}/StructureDefinition/d2-attribute-option-combo`, a `Coding`. The
one DHIS2 attribute option combo this response's values are keyed under - a
project or funder dimension that keys the whole submission. It is drawn from
the ValueSet the form's [`D2AttributeOptionCombos`](#d2attributeoptioncombos)
extension names.

```console
$ curl -s 'localhost:8389/Questionnaire/TuL8IOPzpHh/$generate?seed=7' | jq -c '.extension[1]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-attribute-option-combo","valueCoding":{"system":"http://localhost:8080/fhir/CodeSystem/d2-aoc-idcDPkDtepR-cs","code":"BqblOcSwGey","display":"Provide access to primary health care"}}
```

Absent means the default attribute option combo, which DHIS2 fills in itself.

#### `D2OrganisationUnit`

`{canonical}/StructureDefinition/d2-organisation-unit`, a
`Reference(D2Location)`. The DHIS2 organisation unit an event was captured at.

An aggregate or event response reports *for a place*, so its `subject` is the
Location and no such extension is needed. A tracker, tracker-event, or
person-only response is *about an entity*, so its `subject` is the person and
the place moves here.

```console
$ curl -s 'localhost:8389/Questionnaire/PsAncVisit1/$generate?seed=7' | jq -c '.extension[0]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-organisation-unit","valueReference":{"reference":"Location/Rp268JB6Ne4"}}
```

#### `D2TrackerEnrollment`

`{canonical}/StructureDefinition/d2-tracker-enrollment`, an `Identifier` under
`{base}/id/tracker-enrollment` carrying the DHIS2 enrollment UID. It names the
enrollment without inventing a resource for it - whether a DHIS2 enrollment is
an `EpisodeOfCare` or a `CarePlan` is an open decision, and the identifier
contract does not wait on it.

```console
$ curl -s 'localhost:8389/Questionnaire/PsAncVisit1/$generate?seed=7' | jq -c '.extension[1]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-tracker-enrollment","valueIdentifier":{"system":"http://dhis2.org/fhir/id/tracker-enrollment","value":"GncfBAepfJB"}}
```

A registration response **mints** the UID of the enrollment it creates; a stage
response **names** the enrollment it was captured under.

#### `D2EnrolledAt` and `D2IncidentAt`

`{canonical}/StructureDefinition/d2-enrolled-at` and
`{canonical}/StructureDefinition/d2-incident-at`, both `dateTime`. The two
moments a DHIS2 enrollment holds: `D2EnrolledAt` is the enrollment's
`enrolledAt`, the moment it began; `D2IncidentAt` is its `occurredAt`, the
moment the incident it follows happened.

```console
$ curl -s 'localhost:8389/Questionnaire/PrAncCare01/$generate?seed=4242' | jq -c '.extension[2]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-enrolled-at","valueDateTime":"2026-07-20T05:00:00Z"}
```

Only a registration response carries them. Whether a response carries
`D2IncidentAt` at all is what the form's
[`D2CollectsIncidentDate`](#d2collectsincidentdate) declares.

#### `D2SubjectExists`

`{canonical}/StructureDefinition/d2-subject-exists`, a `boolean`. Whether the
tracked entity a registration response is subject to is *already held* by the
DHIS2 instance.

- **Absent or `false`** - the default reading and the one every generated
  example shows: the client minted `subject.identifier.value`, and the response
  creates that person along with the enrollment.
- **`true`** - `subject.identifier.value` is the UID of a person the instance
  already stores, and the response enrols that person. It is forwarded as a
  top-level `enrollments` array, with no tracked entity beside it.

Named for the fact it carries rather than for the capture-client gesture that
produced it: a reader of the contract can resolve "the subject exists" without
knowing what a client calls the button. The consequences of `true` - including
why an entity-level answer refuses the whole response - are in
[the capture contract](401-capture-contract.md#enrolling-a-person-the-instance-already-holds).

### What a published resource carries

#### `D2OrganisationUnitLevel`

`{canonical}/StructureDefinition/d2-organisation-unit-level`, a `Coding` into
the published level CodeSystem. The level of the DHIS2 organisation unit
hierarchy a place sits at. It rides every `Location` the registry publishes.

```console
$ curl -s localhost:8389/Location/O6uvpzGd5pu | jq -c '.extension[1]'
{"url":"http://localhost:8080/fhir/StructureDefinition/d2-organisation-unit-level","valueCoding":{"system":"http://localhost:8080/fhir/CodeSystem/d2-ou-level-cs","code":"level-2","display":"District"}}
```

The display is the instance's own name for that depth, read from `/api/organisationUnitLevels`, and `Level <n>` where the instance names no level at that depth. The code stays `level-<n>` either way.

#### `D2AttributeValue`

`{canonical}/StructureDefinition/d2-attribute-value`, complex. A DHIS2
`Attribute` is the metadata extensibility point: any object can carry typed
key-value pairs under `attributeValues`, and instances use them for the codes
that tie DHIS2 to everything around it - a national registry id on a facility,
an external warehouse key, an ICD-10 code on a data element. Those pairs are
instance-specific by definition, so no FHIR element holds them.

| Slice | Cardinality | Type | Meaning |
| --- | --- | --- | --- |
| `attributeId` | 1..1 | `string` | the UID of the DHIS2 attribute the value belongs to |
| `attributeCode` | 0..1 | `string` | the attribute's DHIS2 code, absent when the instance left it unset |
| `value` | 1..1 | `string` | the value the object holds, as DHIS2 sends it |

Its `^context` names five resource types: `Organization`, `Location`,
`CodeSystem`, `ValueSet`, and `Questionnaire`.

```console
$ curl -s localhost:8389/Questionnaire/BfMAe6Itzgt | jq -c '.extension[2]'
{"extension":[{"url":"attributeId","valueString":"AtrFhirDsQ1"},{"url":"value","valueString":"Paper register 12A, revision 2025-03"}],"url":"http://localhost:8080/fhir/StructureDefinition/d2-attribute-value"}
```

**`attributeCode` is optional because DHIS2 leaves most attributes uncoded.**
On the Lao instance eleven of twelve attributes have no `code` at all. An
uncoded attribute gets no `attributeCode` sub-extension rather than an empty
one - an empty code would claim the instance coded that attribute. The example
above is one such attribute.

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
absent from the index rather than present with an empty entry, which is what
the optional `attributeCode` reads from.

**Where the values land today.** Organisation units carry them on both halves
of the registry pair, option sets and categories on both the CodeSystem and the
ValueSet, and data sets, event programs, and tracker program stages on their
Questionnaire. Concept-level attribute values - those on individual data
elements and options - are not emitted: a `CodeSystem.concept` has no carrier
chosen for them yet, and that choice is its own decision, sized in
[fhir roadmap section 9.2](design/roadmap.md#92-mid-term).

**A value of a `unique` attribute is not here.** It is an identifier instead;
see [the per-attribute namespaces](#a-unique-attributes-values-are-identifiers)
below.

#### `D2TrackedEntityAttributeValue`

`{canonical}/StructureDefinition/d2-tracked-entity-attribute-value`, complex,
the same three slices in the same shape, contexted on `Patient` alone - the
projection of a person the register serves.

A tracked entity attribute value is a DHIS2 answer *about a person* - a phone
number, a household size, a consent flag. It is a family of its own rather than
a second context on `D2AttributeValue` because a tracked entity attribute is a
different DHIS2 object from a metadata attribute, and one extension claiming to
carry both would publish a definition that is false of half its instances.

```json
{
  "url": "http://localhost:8080/fhir/StructureDefinition/d2-tracked-entity-attribute-value",
  "extension": [
    {"url": "attributeId", "valueString": "ScTeaComPh1"},
    {"url": "value", "valueString": "+23276111001"}
  ]
}
```

Which attributes are `unique` - and therefore ride as identifiers instead - is
read off the `unique` concept property `D2TEA_CS` publishes, not guessed from
the value. Values collected at the program are carried alongside the ones
collected at the tracked entity type, so a person found by a program
attribute's value comes back holding it.

### Core FHIR extensions the generator also uses

Where R4 already publishes an extension for a fact, that one is used rather
than a `D2*` one of this guide's own.

| Extension | Rides on | What it carries |
| --- | --- | --- |
| `http://hl7.org/fhir/StructureDefinition/minValue` | `Questionnaire.item` | the inclusive lower bound a DHIS2 value type implies |
| `http://hl7.org/fhir/StructureDefinition/maxValue` | `Questionnaire.item` | the inclusive upper bound |
| `http://hl7.org/fhir/StructureDefinition/questionnaire-itemControl` | `Questionnaire.item` | how a group or question is rendered |
| `http://hl7.org/fhir/StructureDefinition/translation` | `_title`, `_name`, `_text` | one locale's rendering of a title, name, or question text |
| `http://hl7.org/fhir/StructureDefinition/location-boundary-geojson` | `Location` | the organisation unit's DHIS2 geometry, as a base64 GeoJSON attachment |

Two of them repay a closer look. The bound extensions are typed to the item -
`valueInteger` on an integer item, `valueDecimal` on a decimal one - and which
DHIS2 value type implies which bound is tabulated in
[the capture contract](401-capture-contract.md#what-the-questionnaire-itself-tells-you).
The boundary extension is named for boundaries and R4 documents it as one, but
DHIS2 keeps a district's polygon and a facility's pin in the same `geometry`
field, so most of a real registry's attachments are `Point` rather than
`Polygon`; a reader treating the attachment as polygon-or-failure reports every
facility as broken. `translation` is covered in full under
[Terminology and ConceptMaps](401-terminology-and-conceptmaps.md#translations-designations-on-a-concept-extensions-on-a-title).

## Program rules

DHIS2 enforces program rules on import, not only in the Capture app: a tracker
payload whose values a `SHOWERROR` rule refuses comes back `E1300` and nothing
lands. A form that stated none of that would ask for answers the server rejects,
so every rule a published program holds reaches its forms - in one of three
tiers, and each rule is in exactly one.

**Tier 1 - a numeric refusal becomes a bound.** A rule whose single action is
`SHOWERROR` and whose condition compares one question against one number becomes
the core `minValue` / `maxValue` extensions on that question, on the `value[x]`
its item type takes. The bound is the complement of what the rule refuses:
`#{hemoglobin} > 99` with `SHOWERROR` admits up to and including 99, so the
question carries `maxValue` 99. A refusal that is strict at the boundary
(`>= 99`) has no inclusive complement in a decimal, so it bounds a whole-number
question one step in (98) and goes to tier 3 on a decimal one. Where the question
already carries a bound from its DHIS2 value type - a percentage admits 0..100 -
the tighter of the two is published, once.

`SHOWWARNING` never becomes a bound. DHIS2 lets a warned value through, and a
`maxValue` a server accepts answers past is a constraint nobody enforces.

**Tier 2 - a single-question hide becomes `enableWhen`.** A rule whose actions
are all `HIDEFIELD` and whose condition compares one *other* question against one
literal becomes core `item.enableWhen` entries on each question it hides. DHIS2
hides when its condition holds and R4 shows when its own does, so the operator is
negated: a hide when the apgar score is over 7 shows when the score is 7 or less.

Two things keep that inversion faithful. A comparison against the empty string is
DHIS2's spelling of "no answer", so it becomes the `exists` operator rather than
an empty `answerString` - which R4 has no valid form for. And DHIS2 evaluates a
rule over a blank question by substituting the value type's empty value, where R4
leaves a question whose `enableWhen` no answer can satisfy hidden. Where the DHIS2
condition is false of a blank answer - so the question starts out shown - the
translation adds the arm that says so, joined by `enableBehavior = #any`:

```
* item[=].enableWhen[+].question = "a3kGcGDCuk6"
* item[=].enableWhen[=].operator = #"<="
* item[=].enableWhen[=].answerDecimal = 7
* item[=].enableWhen[+].question = "a3kGcGDCuk6"
* item[=].enableWhen[=].operator = #exists
* item[=].enableWhen[=].answerBoolean = false
* item[=].enableBehavior = #any
```

**Tier 3 - everything else is published, non-normatively.** Every other rule
becomes a repeating `D2ProgramRule` extension on the Questionnaire:

| Sub-extension | Type | Cardinality | Meaning |
| --- | --- | --- | --- |
| `rule` | `id` | 1..1 | The UID of the DHIS2 program rule |
| `name` | `string` | 1..1 | The name the instance holds it under, with its translations |
| `description` | `string` | 0..1 | The rule's free text, absent when the instance states none |
| `condition` | `string` | 1..1 | The DHIS2 expression the server evaluates, character for character |
| `action` | `code` | 1..1 | What the rule does, from `D2ProgramRuleAction_VS` |

Nothing about tier 3 is normative. It states that the server holds a rule this
form cannot express, so a consumer knows an answer the form admits may still be
refused - and can show the rule to a person even where it cannot evaluate it. A
rule tiers 1 or 2 expressed is never repeated here.

The `condition` is verbatim, spacing included, because it is the string an
administrator searches the instance for. Nothing is prettified.

**The grammar is conservative by construction.** The parser reads one shape and
no other: a single comparison between one `#{variable}` and one literal, in
either order, optionally joined by `&&` to a `d2:hasValue` guard naming that same
variable, with the variable resolved through `programRuleVariables` to a question
the same form asks. Anything else - two variables, an `||` chain, a `d2:` function
beyond `hasValue`, a negation, an `A{...}` attribute reference, a variable reading
another program stage - goes to tier 3 whole. So does a rule whose actions this
form cannot all state: a hide targeting a question on another stage's form is
published rather than half-translated, because a rule half-read publishes a
constraint that is neither what DHIS2 enforces nor nothing.

**Every form of a program carries its program's rules.** A rule belongs to the
program rather than to one stage, so a stage form, its siblings, and the
registration form beside them all state the same list - a consumer holding one
form learns from that form alone which rules the server may refuse its answers
under. An aggregate form carries none: DHIS2 states program rules over programs.

**`d2w fhir forward` reads them back.** DHIS2 names the rule that refused an
import by UID alone, and the guide published that UID beside the rule's name, so
the run's rejection roll-up reads `Generated by ProgramRule (\`Show error for
high hemoglobin value\`)` rather than twelve characters. The UID itself stays
untouched on the response's own `.report.json`, which is where a reader goes for
the machine record.

Only the published rules are nameable that way, which is the set that matters: a
client answering a form cannot trip a rule the form already states, so the
refusals that reach a reader are the ones tier 3 published. A UID the guide holds
no rule for still generalises to `` `...` ``, so one cause stays one row.

## Identifiers

Every FHIR artifact representing a DHIS2 object exposes **both** DHIS2
identifiers - the UID and the code - wherever FHIR gives it a slot. This is the
standing rule for every generator, present and future.

### The base, and what resolves { #identifier-base }

Every identifier system on this page is `{base}` plus a path, and `{base}` is
[`[generate] identifier_system_base`](301-generation.md#identifier_system_base),
`http://dhis2.org/fhir` unless the project sets it.

**The default is a label, not an address.** `dhis2.org` publishes nothing under
`/fhir`, and DHIS2 defines no FHIR namespace there. A FHIR identifier system is a
URI, and a URI need not resolve: what a consumer needs is the definition, and
the guide carries it. `foundation/d2-naming-systems.fsh` declares a NamingSystem
for each of the twenty-six fixed systems below, and for the six that the
generated ConceptMaps target the guide also publishes a CodeSystem enumerating
the identifiers the maps name, so the IG publisher validates a mapped
identifier out of the guide instead of asking a terminology server. Those six
are the `special-url` lines of `ig/sushi-config.yaml`: a canonical outside the
guide's own address has to be declared there or the publisher calls it a
mismatch.

**Set the stem before the first real publish**, under a domain the owning
organisation controls, so identifiers from this DHIS2 are labelled apart from
any other country's. The stem is part of every identifier the guide publishes,
so changing it later relabels all of them, and anyone matching records on the
old labels stops matching.

| Family | What it identifies | Declared by |
| --- | --- | --- |
| `{base}/id/<kind>` and `{base}/id/<kind>-code` | the DHIS2 UID and DHIS2 code of one object of that kind - [the fixed systems](#the-fixed-systems-and-their-namingsystems) | a NamingSystem per system, and a CodeSystem for the six the ConceptMaps target |
| `{base}/attribute/<uid>` | the value of one unique DHIS2 metadata attribute - [a unique attribute's values](#a-unique-attributes-values-are-identifiers) | convention; the foundation layer never reads an instance |
| `{base}/tracked-entity-attribute/<uid>` | the value of one unique tracked entity attribute, which is what names a person | convention, as above |
| `{base}/property/<code>` | a fact about a concept rather than an identifier of one - [the concept-property namespace](#the-concept-property-namespace) | the `property` declarations of each CodeSystem |

- **Instances** carry identifier slices discriminated on `system`:
  `{base}/id/<kind>` holds the UID and `{base}/id/<kind>-code` holds the code.
  Both slices are always emitted, on the Organization and on the Location alike.
- **Option-set and category concepts** carry the complementary identifier as a
  concept property: in id mode every concept gets `dhis2-code`, in code mode
  every concept gets `dhis2-id`. No option goes without the pair - a DHIS2
  option must have a code, so there is always one to carry.
- **Data-dictionary and registry concepts** carry `dhis2-code` only where DHIS2
  states a code. A data element, a tracked entity attribute, a category option
  combo, or an organisation unit may have none, and the concept code is the UID
  already - repeating it under a `dhis2-code` label would publish a code the
  instance does not hold.
- **Option-set and category CodeSystems and ValueSets** carry the source set's
  own pair as `identifier` business identifiers, under `{base}/id/option-set`
  and `{base}/id/option-set-code` (or `{base}/id/category` and
  `{base}/id/category-code`) - the same URLs the `$DHIS2-OS` / `$DHIS2-OS-CODE`
  aliases name, written out in full because these resources ship as JSON rather
  than FSH.

### The fixed systems, and their NamingSystems

`foundation/d2-naming-systems.fsh` emits one `NamingSystem` per identifier
system: a UID system for every DHIS2 object kind below, plus a code system for
every kind that has a `code` attribute. Fourteen kinds, twelve of them coded -
**twenty-six NamingSystems**.

| Object kind | UID system | Code system |
| --- | --- | --- |
| organisation unit | `{base}/id/org-unit` | `{base}/id/org-unit-code` |
| option set | `{base}/id/option-set` | `{base}/id/option-set-code` |
| option | `{base}/id/option` | `{base}/id/option-code` |
| category | `{base}/id/category` | `{base}/id/category-code` |
| category option | `{base}/id/category-option` | `{base}/id/category-option-code` |
| category combo | `{base}/id/category-combo` | `{base}/id/category-combo-code` |
| data set | `{base}/id/data-set` | `{base}/id/data-set-code` |
| program | `{base}/id/program` | `{base}/id/program-code` |
| data element | `{base}/id/data-element` | `{base}/id/data-element-code` |
| category option combo | `{base}/id/category-option-combo` | `{base}/id/category-option-combo-code` |
| program stage | `{base}/id/program-stage` | `{base}/id/program-stage-code` |
| tracked entity type | `{base}/id/tracked-entity-type` | `{base}/id/tracked-entity-type-code` |
| tracked entity | `{base}/id/tracked-entity` | none |
| tracker enrollment | `{base}/id/tracker-enrollment` | none |

The last two are **data** objects rather than metadata: DHIS2 gives them no
`code` attribute, so there is no code system to declare. They are also the two
a *response* carries rather than a definition -
[`subject.identifier`](401-capture-contract.md#the-tracked-entity-subject-is-logical-not-resolvable)
and [`D2TrackerEnrollment`](#d2trackerenrollment) respectively.

Each declaration is `kind = #identifier` with a single preferred `uri`
uniqueId and a description of the convention, the code slot's UID fall-back
included. Without them, a validator meeting `{base}/id/org-unit` has no
definition to resolve and warns on every artifact carrying one. Because R4
makes `NamingSystem.date` mandatory, the declarations carry a pinned date
rather than the time of the run - a generated timestamp would rewrite the file
every time.

**The code slot falls back to the UID.** DHIS2 codes are optional, and plenty
of instances have units without one. Rather than emit a half-populated
identifier, the code slot repeats the UID whenever the DHIS2 code is missing or
is not a valid FHIR code. That keeps the profiles conformant (`dhis2code` is
`1..1`) and keeps consumers from special-casing absence. It is a "for now"
state, owned by the instance team: `d2w fhir validate` warns on every
organisation unit without a code precisely so those fall-backs get replaced
with real codes over time.

### Which identifiers a Questionnaire carries

A Questionnaire carries the source object's own pair, plus - for the two
tracker kinds - a third slice that is the grouping handle.

| Form kind | Own pair | Third slice |
| --- | --- | --- |
| `aggregate` | `{base}/id/data-set` + `-code` | none |
| `event` | `{base}/id/program` + `-code` | none |
| `tracker` | `{base}/id/program` + `-code` | `{base}/id/tracked-entity-type` |
| `tracker-event` | `{base}/id/program-stage` + `-code` | `{base}/id/program` |
| `tracked-entity` | `{base}/id/tracked-entity-type` + `-code` | none |

A tracker program's registration form *is* the program, so its own pair is the
program's. Its third slice names the tracked entity type it enrols a person as
- what a client needs to know before it can name the person its response
creates:

```console
$ curl -s localhost:8389/Questionnaire/PrAncCare01 | jq -c .identifier
[{"system":"http://dhis2.org/fhir/id/program","value":"PrAncCare01"},{"system":"http://dhis2.org/fhir/id/program-code","value":"PR_ANC"},{"system":"http://dhis2.org/fhir/id/tracked-entity-type","value":"TetPerson01"}]
```

A stage form's third slice names the program the stage belongs to, which makes
a program's whole capture surface one search:

```console
$ curl -s 'localhost:8389/Questionnaire?identifier=http://dhis2.org/fhir/id/program|PrAncCare01' \
    | jq -r '.total, (.entry[].resource.title)'
2
Antenatal care
ANC follow-up - ANC visit
```

The registration form and every stage of the program come back together,
because the registration form's *own* identity is that same program pair.

### A unique attribute's values are identifiers

A DHIS2 attribute value is an arbitrary key-value pair, so it normally rides
the [`D2AttributeValue`](#d2attributevalue) extension. An attribute DHIS2
declares **unique** is a different thing: its value names the object rather
than annotating it, which is what a FHIR `Identifier` is for. Those values
leave the extension and join the resource's identifier list - after the UID and
code slices, so the order stays stable across runs - under a namespace of their
own:

```
{base}/attribute/{attributeUid}
```

The namespace keys on the attribute **UID**, not its code: a DHIS2 attribute
code may hold spaces, and a system URI may not. Every emitting surface follows
the same rule - Organization and Location, an option set's and a category's
CodeSystem/ValueSet pair, and a Questionnaire.

**A unique tracked entity attribute's values are identifiers too**, under a
family of their own:

```
{base}/tracked-entity-attribute/{attributeUid}
```

A tracked entity attribute is a different DHIS2 object from a metadata
attribute - it is a question asked about a person, not an annotation on a
metadata object - so it gets its own namespace rather than sharing the one
above, and its own extension
([`D2TrackedEntityAttributeValue`](#d2trackedentityattributevalue)) for the
values that are not identifiers. The rule for which is which is the same: DHIS2
enforces uniqueness on the attribute, so its value names the person. `D2TEA_CS`
publishes that flag as a `unique` concept property, which is what a server
reads to decide. This is the family
[`GET /Patient?identifier=...`](401-consume-the-fhir-api.md#the-register-search-identifier)
searches on.

These per-attribute namespaces are declared **by convention rather than as
NamingSystems**, and deliberately so: the foundation layer is built from
`fhir.toml` alone and never reads an instance, so it cannot know which
attributes exist, let alone which are unique. A NamingSystem naming an
attribute the instance does not have would be worse than none. What
`d2-naming-systems.fsh` declares is the fixed family above.

### The concept-property namespace

Concept properties get URIs of their own, off the same base under a `property`
segment rather than an `id` one - they name a *fact about* a concept, not an
identifier *of* one:

```
{base}/property/{propertyCode}
```

So `dhis2-code`, `value-type`, `unique`, `searchable`, `generated`, `pattern`,
and `display-in-list` are `{base}/property/dhis2-code` and so on, and each
category a combo decomposes over is `{base}/property/category-<stem>`.

```console
$ curl -s localhost:8389/CodeSystem/d2-aoc-idcDPkDtepR-cs | jq -c '.property[]'
{"code":"dhis2-code","uri":"http://dhis2.org/fhir/property/dhis2-code","description":"DHIS2 category option combo code.","type":"string"}
{"code":"category-yY2bQYqNt0o","uri":"http://dhis2.org/fhir/property/category-yY2bQYqNt0o","description":"DHIS2 category Project.","type":"Coding"}
```

The full property set of each vocabulary is in
[Terminology and ConceptMaps](401-terminology-and-conceptmaps.md).

## See also

- [Terminology and ConceptMaps](401-terminology-and-conceptmaps.md) - how a
  consumer holding a generated concept code gets its DHIS2 identifiers back.
- [The capture contract](401-capture-contract.md) - which of the response-side
  extensions each form kind must, may, and must not carry.
- [Generate the IG source](201-generate.md#know-the-eight-targets) - the `foundation` target that
  writes the extensions and NamingSystems described here.
- [How things are generated](301-generation.md#naming) - which DHIS2 identifier
  becomes an artifact's id, name, and file name.

Next: [Terminology and ConceptMaps](401-terminology-and-conceptmaps.md)
