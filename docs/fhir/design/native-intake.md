# Native FHIR resource intake: the capture contract's second door

What it takes for a client that already speaks FHIR clinical resources to post one
straight at `d2w fhir serve` - an `Observation` from a laboratory system, an
`Immunization` from an electronic immunisation registry, a `Patient` from a
registration system, an `Encounter` from an electronic medical record - and have it
land in DHIS2 through the spool, the translator, and the forwarder that already
carry a `QuestionnaireResponse` there. This is the working paper behind the native
intake item in roadmap [9.1](roadmap.md#91-near-term). The recommendation in each
section is a recommendation; the decisions stay with the owner and are listed in
section 8.

Every cardinality quoted below is read off **FHIR R4 4.0.1**, and it is quoted where
the cardinality is the argument. Everything asserted about this repository is read
off the code and the published contract, and the file it came from is named.

## The short version

The second door is not blocked by FHIR and it is not blocked by DHIS2. It is blocked
by one sentence a posted resource does not say: **which form its values answer**. A
`QuestionnaireResponse` says it in one element - `questionnaire` - and everything the
translator does follows from resolving that canonical to a `FormSpec`. An `Observation`
says a code, an `Immunization` says a vaccine, and an `Encounter` says nothing at all.

The vocabulary half of the crossing is already published: `D2DE_CS` is the data
elements, `D2OS_*_CM` takes a coded answer back to its DHIS2 option, `D2COC_CS` is the
disaggregation cells. It is not *reversible through the served operation* -
`$translate` walks a group's source onto its target and never back - but the guide
carries the material, and one thing more that matters most: `$summary` already codes an
immunisation dose by the data element it was recorded against, so a posted
`Immunization` naming a data element is the exact inverse of a document this project
already writes.

What no artifact carries is the destination, because DHIS2 states no such fact. So the
destination is stated or the post is refused - the same answer
[the IPS document](ips.md) reached about section membership, reached again from the
other side. This paper recommends the same mechanism: the reverse index answers it
wherever one form asks the data element, an owner writes the tie-breaker in
`fhir.toml` where more than one does, `d2w fhir generate` publishes the result as a
ConceptMap, and a client that read the guide may name the form itself and skip both. A
code with no destination is a refusal that names the code, the forms that could have
taken it, and the line that would have chosen.

## 1. Why a second door, and what it is not

### 1.1 What the first door costs a client that already speaks FHIR

The capture contract is deliberately generic FHIR, and it is deliberately
questionnaire-shaped:

> A capture is a plain `QuestionnaireResponse`, a vocabulary a standard `CodeSystem`
> and `ValueSet`, an organisation unit a `Location` [...] Any FHIR client reads what
> the facade serves without knowing DHIS2 exists.

That sentence is true of the *read* side and only half true of the write side. A
client reads a `Questionnaire` without knowing DHIS2 exists, and then it has to build
a `QuestionnaireResponse` whose `item[].linkId` values are DHIS2 UIDs, whose answer
elements match a value-type table, and whose envelope carries between two and five D2
extensions depending on the form kind. That is a small amount of work for a client
being written from nothing. It is a rewrite for a client that already exists.

The clients that already exist do not hold questionnaires. A laboratory information
system holds results and emits `Observation`. An electronic immunisation registry
holds doses and emits `Immunization`. A registration desk holds people and emits
`Patient`. Asking each of them to learn a second capture shape - one whose questions
are eleven-character identifiers - is asking them to do the mapping this project
exists to do.

### 1.2 What the second door is not

Four things, stated up front because each is a thing a reader will otherwise assume.

**It is not a general FHIR server.** Nothing about it stores an `Observation`,
answers `GET /Observation/{id}`, offers `_history`, admits `PUT`, admits `DELETE`, or
lets a client search what it posted. The facade's one non-`GET` route imports, and
`DELETE /QuestionnaireResponse/{id}` answers 405 today with
`` `DELETE` is not supported on `/QuestionnaireResponse/abc123` ``. The second door
adds a second body shape to the route that imports. It adds no repository.

**DHIS2 stays the record.** A posted `Observation` becomes a DHIS2 data value, and
the DHIS2 data value is where its value lives afterwards. What reads back from this
project is the receipt - what was submitted, by whom, when, and what DHIS2 answered -
because [the spool is the provenance record](data-lifecycle.md#36-the-spool-is-the-provenance-record-as-a-product-promise)
and a DHIS2 instance holds only the current value of a cell. A client that posts an
`Observation` and then wants to read an `Observation` back is asking for the
[materialized projection](projection.md), which is a different paper and a different
surface.

**The spool stays the buffer.** Four states, lifecycle by directory, one receipt one
payload, `os.replace` as the atomicity mechanism. The second door writes into the same
`received/` and drains through the same `d2w fhir forward`. It does not get a queue of
its own, a delivery mode of its own, or a retry posture of its own.

**It does not widen what DHIS2 can store.** Every value a posted resource carries
lands on a data element or a tracked entity attribute a published form already asks.
A code with no destination is a refusal, never a new data element and never a note
appended to something adjacent. This is the no-invented-content rule
[the IPS paper states for sections](ips.md#5-the-section-gap), applied to the write
side, where it matters more: an unplaceable value that reaches DHIS2 anyway is a
number in a report that nobody asked for.

### 1.3 What any accepted design must satisfy

Derived from what this repository already does, in the manner of
[the IPS requirement set](ips.md#8-the-requirement-set).

**N1 - Owner-stated destinations only.** No matching on data-element names, no
heuristic on value types, no "a LOINC code that looks like a weight lands on the
weight element". Every value a posted resource writes into DHIS2 traces to a line
somebody wrote or to a canonical the client named.

**N2 - One spool, one translator, one forwarder.** The second door produces the same
receipt the first door produces, and everything downstream - `d2w fhir forward`,
`d2w fhir spool`, `d2w fhir requeue`, `d2w fhir withdraw`, the capture UI's Responses
page, the conversion CI gate - is untouched by which door a receipt came through.

**N3 - Refusal before storage, never storage without forwarding.** The
[corrections refusal](../401-capture-contract.md#two-statuses-are-a-decision-this-project-makes)
already sets this line: a receipt accepted and then never forwarded tells a client
"kept" about a fact that never reaches the instance. A resource whose destination
cannot be named is refused at the door, not spooled hopefully.

**N4 - The refusal names what was missing and what would fix it.** One HTTP response
carrying every issue that phase found, each locating itself with a FHIRPath
`expression`, in the voice the capture path already uses.

**N5 - The door is discoverable from the published guide.** A client learns that the
door exists from `CapabilityStatement`, and learns where a code goes from a published
`ConceptMap` - not from reading this project's `fhir.toml` and not from posting and
seeing what happens.

**N6 - Gated and additive.** Offered or withheld by a `fhir.toml` key, refused with a
typed error naming that key, in the manner of `RegisterDisabledError` and the two
lifecycle postures. Nothing about the `QuestionnaireResponse` door changes shape,
and a project that opens no second door generates and serves exactly what it does
today.

**N7 - Plain R4 on the wire.** A posted resource is a base R4 `Observation`,
`Immunization`, `Patient`, or `Encounter`. Whatever DHIS2 context it has to carry
rides the D2 extension vocabulary that already exists, and a client that carries none
of it is refused rather than guessed about.

## 2. The launch set, and what is deliberately excluded

### 2.1 Four resources, four different shapes

The four are not four instances of one problem. They differ in *what part of a form*
they correspond to, and that difference is the whole design.

| Resource | What it is, in form terms | What a route has to state |
| --- | --- | --- |
| `Observation` | **Question-shaped.** `code` is the question, `value[x]` is the answer. | The form. The question is the code. |
| `Immunization` | **Question-shaped, in this project's own spelling.** `vaccineCode` carries the data element, and the dose is the value. | The form. The question is `vaccineCode`. |
| `Encounter` | **Envelope-shaped.** It carries placement - subject, period, location - and no values at all. | The form. Nothing else. |
| `Patient` | **Attribute-shaped.** Its elements are tracked entity attributes, not data elements. | The registration form, plus which attribute each element is. |

The second row is the one that could have gone differently, and the reason it did not
is a decision this project already made in the read direction. In general FHIR,
`Immunization.vaccineCode` is an answer - "which vaccine" - to a question the resource
type states implicitly, and a route for it would have to name both the form and the
question that answer lands on. The IPS section mapping settled it the other way:

> **The data element is the vaccine and the value is the dose.** That is the shape a
> DHIS2 immunisation form has: `MCH BCG dose`, `MCH Measles dose`, `MCH Penta dose`,
> one element per vaccine, with the value saying either that the dose was given or
> which dose of the series it was.

So `$summary` codes each dose by the *data element it was recorded against*, under
`{base}/id/data-element`, and `Immunization-uv-ips` permits it because `vaccineCode`'s
binding is preferred rather than required. Read backwards, that makes `vaccineCode`
a question code exactly as `Observation.code` is, and a posted `Immunization` needs a
route with one column rather than two.

That leaves `Patient` as the only launch-set member whose route is not "which form",
and it is the only one whose values are not data elements at all.

### 2.2 The case for each, against the fleet

**`Observation` - the widest client population and the cleanest lowering.** One code,
one value, one subject, one time is exactly the shape of a DHIS2 data value, and
`dhis2w_fhir.conversion.values` already implements the wire serialisation both
directions. Every laboratory system, every device gateway, and every analyser
integration on the market emits it. Its weakness is precisely section 3's problem: a
code names a data element, a data element is asked by many forms, and nothing on the
resource says which.

Two R4 cardinalities decide how much of this is a problem. `Observation.subject` is
**0..1** and `Observation.effective[x]` is **0..1** - so a fully conformant
`Observation` may state neither who it is about nor when it happened, and DHIS2
requires both of a tracker event. Those are two of the refusals section 4 words.
`Observation.component` is **0..\***, so a blood pressure is one resource carrying two
values, and its route needs a code per component rather than one for the resource.

**`Immunization` - the resource with a named customer, a proven read side, and half its
routing already written.** The fleet is immunisation-heavy and so is the seeded
instance: `Child Programme` (`IpHINAT79UW`) is a `WITH_REGISTRATION` program with two
immunisation stages. An electronic immunisation registry posting doses is the one
client this repository can name.

What makes it more than that is
[`[ips.sections.immunizations]`](../301-what-goes-in.md#ips-sections), which is a table
an owner already writes and which already carries both halves of a route:

```toml
[ips.sections.immunizations]
program_stages = [
    "A03MvHHogjR",     # Child Programme - Birth
    "ZzYYXq4fJie",     # Child Programme - Baby Postnatal
]
dose_data_elements = [
    "bx6fsa0t90x",     # MCH BCG dose
    "ebaJjqltK5N",     # MCH OPV dose
    "FqlgKAG8HOu",     # MCH Measles dose
]
```

`dose_data_elements` is the vocabulary a posted `vaccineCode` resolves into.
`program_stages` is the set of forms a dose can land on. The loader already refuses
either list without the other, naming the omission, and `SectionMappings` is
`extra="forbid"` so a section nobody has built is refused by name rather than ignored.
The read side performs it in `recorded_doses`, filtering events to `program_stages` and
then asking `records_dose(program_stage_uid, item.linkId)` per answered item - where
`item.linkId` **is** the data element UID, which is the same join the second door
needs pointed the other way.

So the immunisation door's routing question is not "what is the table" but "what does
the existing table not say", and the answer is one thing: **which of several stages**,
where more than one is listed. Section 3 is about that residue rather than about a
mechanism built from nothing.

`Immunization.patient` is 1..1 and `occurrence[x]` is 1..1, which is the other good
news - the two elements `Observation` leaves optional are mandatory here, so the two
refusals section 4 words for `Observation` cannot arise. `patient` being
`Reference(Patient)` in R4 also scopes the door: an immunisation is about a person, and
`$summary` already draws that line at `PERSON_RESOURCE_TYPES`.

**`Encounter` - the envelope, and the anchor a batch hangs off.** A DHIS2 event is an
encounter: `Encounter.period` is when, `Encounter.location` is a `Reference(Location)`
and the guide publishes Locations, `Encounter.subject` is who, and `Encounter.status`
maps onto the DHIS2 event status the same way `QuestionnaireResponse.status` does. It
is the only launch-set member that names the organisation unit in a native element
rather than in an extension. Its real use is not on its own - an `Encounter` carrying
no values is an empty DHIS2 event - but as the resource a batch of `Observation`s
reference through `Observation.encounter`, which is how a clinical system already
builds them.

**Naming a reversal honestly.** [The enrollment resource](enrollment-resource.md#11-the-first-slice-if-ratified)
puts "no `Encounter` for DHIS2 events" out of scope for its first slice. That was a
statement about the *read* side - whether the facade publishes an `Encounter` resource
per DHIS2 event - and this paper reopens nothing about it. Accepting a posted
`Encounter` is a capture-side reading of the same resource, and the two can land in
either order.

**`Patient` - the registration door, and the one that needs another dial read
backwards.** A registration system creating a person maps onto
`D2TrackedEntityResponse` when it enrols them in nothing and onto
`D2TrackerRegistrationResponse` when it names an enrollment. Its values are tracked
entity attributes, so it routes through `D2TEA_CS` rather than `D2DE_CS`, and it needs
a mapping this project already has in one direction:
[`[ips.identity]`](../301-what-goes-in.md#ips-identity) nominates which attribute holds
a person's name, birth date, and sex, which is exactly the join a posted
`Patient.name` / `birthDate` / `gender` needs read inward. `Patient` also carries no
`status` element at all - `active` is a 0..1 boolean - so it is the one launch-set
member with no native spelling for a withdrawal.

### 2.3 What is deliberately excluded, and why

**`Condition` - excluded until a clinical vocabulary source exists.** A DHIS2
instance's diagnosis values are option codes in this guide's own CodeSystem, and
`Condition.code` is a clinical claim in SNOMED CT or ICD. Roadmap
[9.3](roadmap.md#93-long-term) states plainly that a source mapping DHIS2 option codes
onto SNOMED CT or LOINC does not exist. A `Condition` posted with a DHIS2 option in
`code` is an `Observation` wearing a diagnosis's clothes, and the resource type would
be asserting a semantics no artifact in the guide supports. Accepting it would break
N1 while appearing to satisfy it.

**`MedicationRequest` - excluded because DHIS2 records what happened.** This is the
argument [the enrollment resource](enrollment-resource.md#10-recommendation) already
made against `CarePlan`, and it is stronger on the capture side: R4 types
`MedicationRequest` as an *order*, and a DHIS2 data value is a record of a fact.
`MedicationAdministration` and `MedicationDispense` are the shapes that record what
happened, and both need a medication vocabulary this project has no more source for
than it has for diagnoses. All three stay out.

**`AllergyIntolerance` - excluded on the sharpest version of the same ground.** The
IPS paper's finding stands unchanged on the write side: a mis-mapped allergy is the
single most dangerous wrong answer a summary can carry, and a mis-*captured* one is
worse, because it becomes the record rather than a rendering of it.

**`DiagnosticReport`, `ServiceRequest`, `Procedure` - excluded as redundant rather
than dangerous.** Each lands on a DHIS2 shape that `Observation` plus `Encounter`
already reaches, and each adds a routing shape without adding a destination. They are
the obvious phase-N additions once the mechanism exists, and none of them is a reason
to widen the launch set.

**`QuestionnaireResponse` inside a `Bundle` - excluded, and it already is.** The door
answers a `Bundle` with 400 today, naming the rule. Section 4.3 is where the second
door's answer to that question is argued; it is not a launch-set question.

## 3. How a posted resource names its DHIS2 destination

### 3.1 What the translator actually needs

This is the whole of it, and stating it exactly is what makes the candidates
comparable. `translate_response(response, context)` in
`packages/dhis2w-fhir/src/dhis2w_fhir/conversion/translator.py` resolves the
response's `questionnaire` canonical to a `FormSpec` through
`ConversionContext.form_for`, and everything after that is mechanical. A `FormSpec`
carries the form kind, the conversion target kind, the DHIS2 object the form was
generated from - `data_set_uid`, `program_uid`, `program_stage_uid`,
`tracked_entity_type_uid` - and a `questions` map keyed by link id. Each
`QuestionSpec` in it carries `data_element_uid`, `category_option_combo_uid`,
`answer_element`, `wire_kind`, `option_system`, `entity_level`, and `required`.

So the destination problem, stated without FHIR in it: **a posted resource has to
yield one `FormSpec` and, per value it carries, one `QuestionSpec` of that form.**
Nothing else about the translator has to change, because nothing else about it reads
the response's resource type.

The vocabulary half of that is already solved and already published, which is worth
saying before the candidates, because it removes a third of the apparent problem:

- **A code to a data element.** `D2DE_CS` is one shared CodeSystem over every data
  element the guide's forms ask, and a `Questionnaire.item.code` is
  `D2DE_CS#<concept code>`. Under `concept_code_source = "id"` the concept code *is*
  the data element UID; under `"code"` the concept carries the UID as its `dhis2-id`
  property. Each concept also carries `domain`, valued `aggregate` or `tracker`.
  `D2DE_CS` has no ConceptMap beside it - the five published families are option sets,
  categories, attribute option combos, sex values, and summary sections - because a
  concept whose code is the identifier needs no map to say so.
- **A coded answer to a DHIS2 option.** `D2OS_<stem>_CM` maps a published concept code
  onto `<base>/id/option` and `<base>/id/option-code`, with `equivalence = #equal` on
  every row, and `serve` answers `ConceptMap/$translate` over it live.
- **A disaggregation to a category option combo.** `D2COC_CS` and
  `D2CAT_<stem>_CM`, the same shape.
- **A tracked entity attribute.** `D2TEA_CS`, carrying `unique` and `searchable` per
  attribute.

**Display strings are not part of any of this, and must not become part of it.** The
generator's [hostile-name substitution](../201-generate.md#answer-the-hostile-name-question)
publishes a rewritten *wording* where a DHIS2 name carries a character the IG
publisher's build cannot survive - `5 to < 15 years, Female` is published as
`5 to under 15 years, Female` while DHIS2 keeps the name it holds. Codes are never
touched, precisely so the ConceptMaps still take a published concept back to the DHIS2
object byte for byte. A second door that resolved a posted `Coding.display` against a
published display would therefore resolve differently depending on whether the run
that built the guide substituted or refused, and would resolve *wrongly* against the
instance's own name in every substituted case. **`Coding.display` is read for nothing.**
A coding carrying a display and no code is the existing
[always-a-refusal](../401-capture-contract.md#what-is-always-a-refusal) case, and it
stays one.

### 3.2 The candidates

**(a) The published ConceptMaps read backwards.** The appeal is real: the maps exist,
`$translate` serves them, and section 3.1 shows they already answer the vocabulary
question. The claim would be that they answer the destination question too - that an
`Observation.code` carrying a published concept resolves to a data element *and its
stage*.

**"Backwards" is not something the served operation does.** `find_translations` matches
a request against `group.source` and `element.code` and nothing else; it never walks a
target back to the sources that point at it. So `D2Section_CM` answers "which section
does this data element feed" and cannot be asked "which data elements feed this
section", and the same is true of every other published map. That is not an oversight
to fix in passing - a ConceptMap group is one-directional by construction, and R4 gives
`ConceptMap.group.unmapped` no inverse.

Even granting a reverse index built server-side rather than served, the mechanism does
not reach. `D2DE_CS` is one CodeSystem for the whole guide; it says which data element
and it says the domain, and
it says nothing about which form asks it. The join from a data element to the forms
that ask it exists - `ConversionContext.forms` holds every served `FormSpec` and every
`QuestionSpec` in them is keyed by a link id that *is* the data element UID - so a
server can build a reverse index `data element -> {(form, link id)}` from the context
it already assembles at startup, at no artifact cost at all.

That index is **one-to-many**, and that is the finding. A guide publishing three
program stages that each ask `s46m5MS0hxu` gives three destinations for one posted
code, and no rule picks between them that is not an invention. Where the index happens
to be one-to-one the mechanism works perfectly and costs nothing; where it is not, it
produces exactly the class of silent mis-placement N1 exists to prevent. A design that
is correct on small guides and wrong on national ones is not a design.

`D2Section_CM` does not rescue it either. Its two groups take a program stage and a
data element onto a LOINC section code, so read backwards they answer "some stage that
feeds Immunizations", which is many-to-one in the wrong direction. What it does prove
is that this project already publishes a destination-shaped claim as terminology, and
that is genuinely useful evidence - for candidate (d).

**Verdict: necessary and not sufficient.** The reverse index is worth building, as the
thing that turns an ambiguity into a refusal that can name all three candidates. It
cannot be the routing mechanism.

**(b) `meta.profile` against published profiles.** The guide would publish one profile
per form over each admitted resource type - `D2Observation_A03MvHHogjR` and so on - and
a posted resource would declare which one it conforms to. The destination is then
exact, discoverable, and validatable by any off-the-shelf FHIR validator without this
project's cooperation.

Two costs, and the second is decisive. The artifact count multiplies: a guide with two
hundred forms and three admitted resource types publishes six hundred profiles, into a
build the [publisher already stalls in](roadmap.md#45-tooling-the-publishers-embedded-sushi-stalls-in-its-export-phase).
And it reverses a settled reading. The capture contract states today, among the things
never checked at all, "which profile the response's `meta.profile` claims", because it
is "a claim the server has no reason to trust over the `D2FormType` it reads instead".
Making `meta.profile` load-bearing on the second door while it is decorative on the
first gives one server two readings of one element.

**Verdict: rejected as the mechanism, worth publishing as a contract.** If the launch
set settles, per-form profiles are a good thing for a guide to carry so a client can
validate before it posts. They are not what the server routes on.

**(c) An extension naming the form.** `D2Form`, a `valueCanonical` to the
`Questionnaire`, on the posted resource. It is precisely the element
`QuestionnaireResponse.questionnaire` is, spelled as an extension because `Observation`
has no place to put a form. One key, no artifact multiplication, no reversal of the
`meta.profile` reading, and it makes the two doors structurally identical: the first
reads `questionnaire`, the second reads `D2Form`, and both hand the same canonical to
`ConversionContext.form_for`.

The objection is the one that matters most to why this door exists: a client that has
to add a D2 extension has learned some of this project's vocabulary, and the whole
argument of section 1.1 was that it should not have to. The counter is a matter of
degree rather than principle - adding one extension to a resource a system already
builds is a change of a few lines, where building a `QuestionnaireResponse` whose
questions are UIDs is a new emitter - but it is a real cost and it falls on the
client rather than on the deployment.

**Verdict: the right override, the wrong default.** A client that read the published
guide should be able to be exact, and nothing should stop it. Most clients will not
have read it.

**(d) Server-side routing, stated by the owner and published as terminology.** The
deployment writes the routing in `fhir.toml`, `d2w fhir generate` publishes it as a
`ConceptMap`, and the server performs the file. The client posts plain R4 with no D2
vocabulary at all, which is the door section 1.1 asked for.

This is the shape this repository has now chosen three times.
[`[generate.tracked_entity_types]`](../401-custom-subject-types.md) states which
resource type a tracked entity type is, because DHIS2 states no such fact, and
publishes it as `D2TET_CM`. [`[ips.identity]`](../301-what-goes-in.md#ips-identity)
states which attribute is a name, and publishes the sex half as `D2Sex_CM`.
[`[ips.sections]`](../301-what-goes-in.md#ips-sections) states which values feed which
section, and publishes it as `D2Section_CM`. The IPS paper argued that choice as
option C - "`fhir.toml` is the input; the ConceptMap is the published output" - on the
grounds that it lets a consumer audit the assignment without seeing the project's
config. Every word of that argument applies here unchanged.

Its costs are the costs that pattern always has, and they should be stated rather than
waved past. It is per-instance and unshared: ten country guides routing the same
immunisation vocabulary write the routing ten times. It is a wrong-line risk - an
owner routes a code to the wrong stage and values land in the wrong place, visible
only in DHIS2 afterwards. And it means a refusal cannot always be predicted from the
published guide alone, unless the map is published, which is exactly why the map is
published.

**Verdict: the mechanism.**

### 3.3 The recommendation

**Route on an owner-stated table published as a ConceptMap; let a client that names
the form beat the table; build the reverse index so an unroutable code can be refused
precisely; read `meta.profile` for nothing, and `Coding.display` for nothing.**

Concretely, three steps in this order, the first two of which already exist:

1. **Resolve the vocabulary.** The posted code goes through the published maps to a
   DHIS2 identifier - a data element for an `Observation.code`, an option for an
   `Immunization.vaccineCode` or any coded value, a tracked entity attribute for a
   `Patient` element. This is the existing three-tier resolution, on the existing
   [`--strict-codes` dial](../201-serve.md#coded-answers-lenient-by-default), with the
   existing tiers `concept-code`, `option-uid`, `option-code`.
2. **Resolve the destination.** `D2Form` if the resource carries it. Otherwise the
   route table. Otherwise refuse.
3. **Resolve the placement.** Subject, organisation unit, occurrence, enrollment -
   section 3.5.

**The table states the ambiguities, and nothing else.** Section 2.1's finding is what
makes this possible: every launch-set resource except `Patient` carries a code that
names a data element, so a route is one fact - which form - and the reverse index
already answers it wherever a data element is asked by exactly one served form. The
table is therefore not a routing table for the whole guide. It is the tie-breaker for
the data elements more than one form asks:

```toml
[intake]
enabled = true

[intake.forms]
"bx6fsa0t90x" = "A03MvHHogjR"   # MCH BCG dose         -> Child Programme - Birth
"GieVkTxp4HH" = "ZzYYXq4fJie"   # Height in cm         -> Child Programme - Baby Postnatal
```

**In plain words.** Which published form a posted value lands on, where more than one
form asks the data element it names. A data element only one form asks needs no line;
absence means the one form, which is the same economy the
[organisation-unit assignment](roadmap.md#54-where-attributeoptioncombo-and-data-set-completeness-live)
and the default attribute option combo already keep. **Only UIDs, never names**, for
the reason [`[ips.identity]`](../301-what-goes-in.md#ips-identity) gives: names are not
unique in DHIS2 and change without notice.

That is the shape every other mapping in this file has - a UID keyed onto a UID - and
it is `[ips.sections]` turned around, keyed the same way and sorted the same way.

**The resource type is not a dimension of it.** `Observation`, `Immunization`, and
`Encounter` all name a data element in the code they carry, and which resource type
carried it is a claim about the *kind* of fact rather than about where it goes. Which
types the door receives at all is a CapabilityStatement question, argued below.
`Patient` is the exception, because its values are tracked entity attributes and its
destination is a registration form; its routing is a phase-4 question and is on the
reserved list rather than in this table.

**The published output.** `D2Intake_CM`, in the two-group shape every map back to
DHIS2 uses, sourced from `<base>/id/data-element` onto `<base>/id/program-stage` and
`<base>/id/data-set` - namespaces the `foundation` target already declares as
NamingSystems, so no new identifier convention is minted. Rows sorted by UID, so
regenerating an unchanged `fhir.toml` writes the same bytes; route nothing and no file
is written at all. The file-name prefix `ConceptMap-d2-intake-` is what the family
sweeps, per the shared-directory rule.

**The resource-type half is a CapabilityStatement fact, not a terminology fact.** A
`ConceptMap` maps codes; it cannot say "this server accepts a posted `Immunization`".
`D2CaptureServer` already declares `create` on `QuestionnaireResponse` with five
`supportedProfile` entries, and the second door adds `create` on each admitted type.
So a client discovers *that* the door exists from the CapabilityStatement and
discovers *where a code goes* from the ConceptMap, using two artifacts that already
exist for exactly those two questions.

### 3.4 What this does not solve, stated plainly

The routing table says which form. It does not say **what value the resource writes**,
and for `Immunization` that is a real question rather than a formality, because the
DHIS2 shape puts the vaccine in the question and leaves the answer to mean something
else. `$summary` reads that answer through `_dose_number`, where a `valueBoolean` of
`false` is not a dose at all, a `valueCoding` is read as its display or code, and
anything else is the stated literal. A posted `Immunization` has to produce the
inverse, and what it produces depends on the routed question's own item type - a
`#boolean` question takes `true`, an `#integer` question takes
`protocolApplied.doseNumber`, and a `#choice` question takes a coding the form's
terminology holds.

The resource does not say which of those the form wants, and it does not have to: the
served `Questionnaire` says it, `QuestionSpec` carries it as `item_type` and
`answer_element`, and the lowering reads it. What *is* worth checking at load is the
pairing - a route whose question is `#choice` and whose posted resources carry no
coding is a route that will refuse every post, and saying so when `fhir.toml` is read
is cheaper than saying it once per submission. That check belongs in the first slice,
in the manner of the `[generate.tracked_entity_types]` unknown-resource-type refusal.

**`Immunization.status = not-done` has no destination and is refused.** The read side
already states this rule from the other end: DHIS2 records that a dose was given and
states no reason when one was not, and FHIR requires a reason on a dose that was not
given, "so no entry is written rather than a reason invented". Read inward, a posted
`not-done` immunisation carries a `statusReason` DHIS2 has nowhere to put, and writing
the dose element `false` would file "not given" as a captured fact the client did not
send. Refused, naming what the form records.

### 3.5 Subject, placement, and enrollment

Four facts beyond the destination, and the launch set carries them very unevenly.

| Fact | `Observation` | `Immunization` | `Encounter` | `Patient` |
| --- | --- | --- | --- | --- |
| Subject | `subject` **0..1** | `patient` 1..1 | `subject` **0..1** | the resource itself |
| Occurrence | `effective[x]` **0..1** | `occurrence[x]` 1..1 | `period` 0..1 | n/a |
| Organisation unit | none | none | `location` 0..\* `Reference(Location)` | none |
| Enrollment | none | none | none | n/a |

**Subject to tracked entity.** Three spellings resolve, in this order.

- `Patient/zPde0IgxLd6` - a literal reference to the register's own resource, which
  `GET /{ResourceType}/{uid}` already serves. Native, needs no instance read, and is
  the spelling a client that browsed the register will hold.
- `identifier` with `system` = `{base}/id/tracked-entity` - the exact shape the QR
  door's `subject.identifier` uses, carrying the DHIS2 tracked entity UID.
- `identifier` under `{base}/tracked-entity-attribute/{uid}` - a *unique* tracked
  entity attribute's value, which is what a national identifier or a medical record
  number actually is on the client's side. The register already searches on it
  (`GET /{ResourceType}?identifier=`), so the machinery exists, but it is an instance
  read: it works under `d2w fhir serve --live` and cannot work against a compiled
  guide, which holds no people. **This is a capability the second door has and the
  first door does not**, and it is the single thing most likely to make an existing
  client able to post at all, because an existing client knows its own identifiers and
  does not know DHIS2 UIDs.

**Subject typing respects `[generate.tracked_entity_types]`.** A posted resource's own
type is a claim about what the subject is, and the destination form's
`Questionnaire.subjectType` is what the project published about it. A `Patient` posted
against a form whose subject type is `Device` is the same finding the QR door already
grades - a warning by default, a 422 under `--strict-codes` - and it should be graded
by the same code path with the same words. Two consequences worth naming: a project
mapping a tracked entity type to `Device` or `Specimen` gets a second door for
`Observation` about a fridge or a sample without any further work, which is a real and
un-obvious win; and `Immunization.patient` being `1..1 Reference(Patient)` in R4 means
the immunisation door is a `Patient`-subject door only, exactly as
[`EpisodeOfCare` is](enrollment-resource.md#10-recommendation).

**Organisation unit and occurrence.** `Encounter.location` resolves natively through
the same `organisation_unit_uids_by_location_id` table the QR door's Location
references resolve through. `Observation` and `Immunization` carry no native element,
so the unit rides `D2OrganisationUnit` - the extension the three tracker response kinds
already use - or is inherited from an `Encounter` the resource references. Occurrence
is `effective[x]` / `occurrence[x]` / `period.start`, graded as an R4 `dateTime`
against the same `FHIR_DATE_TIME_PATTERN` the capture path already checks `authored`
with, and stamped with the project's `[generate] timezone` on the way to DHIS2's
zone-less wire.

**Enrollment.** No launch-set resource has an element for it, and a tracker event
needs one. Two answers, and they are not exclusive: `D2TrackerEnrollment` as a
`valueIdentifier` under `{base}/id/tracker-enrollment`, exactly as the QR door carries
it; or resolved from the instance under `--live`, by reading the subject's enrollments
and taking the one in the destination form's program. The second is what a client
without DHIS2 knowledge needs and it is only unambiguous when the entity holds exactly
one enrollment in that program. Zero and two are both refusals, and section 4 words
them. **The resolution is entity-scoped** - one read of the tracked entity, never with
`program=`, per BUGS.md 72 and the discipline the register and the history surface both
hold.

## 4. Refusals, and what a Bundle means

### 4.1 The refusals the second door adds

The house doctrine is fixed and the second door changes none of it: 415 for a media
type that is not JSON, 400 for a body that is not a JSON object and for a resource
type the door does not receive, 422 for everything past that, every issue of one phase
in one response, each locating itself with a FHIRPath `expression`, every closed model
rejecting an unknown key by name.

**One existing sentence has to change.** The door answers today, verbatim:

```
this endpoint receives a QuestionnaireResponse, not a `Observation`
```

A project that has opened the second door and routed nothing must not say that, and a
project that has not opened it must keep saying something like it. The refusals below
are written on that basis.

**The door is closed.** In the shape the two lifecycle postures already use, naming
the key and the value that opens it:

```json
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"business-rule",
  "diagnostics":"this project receives no native FHIR resources: `[intake] enabled` in fhir.toml is `false`, and a project that receives them sets it to `true`",
  "expression":["Observation"]}]}
```

**The code names no destination.** The refusal names the code, names the table, and
names the line that would have covered it - because the reader of a refusal is an
integration developer who cannot read the deployment's `fhir.toml`:

```
`http://example.org/fhir/CodeSystem/d2-de-cs|GieVkTxp4HH` resolves to DHIS2 data
element GieVkTxp4HH, and this project routes no posted Observation to it: name the
form on `D2Form`, or route the data element to a form in `[intake.forms]`
```

**The code names more than one destination.** This is where section 3.2's reverse
index earns its place: the refusal can list what it found rather than saying it is
confused.

```
DHIS2 data element GieVkTxp4HH is asked by three forms this project serves -
A03MvHHogjR, ZzYYXq4fJie, and BfMAe6Itzgt - and this Observation names none of them:
name one on `D2Form`, or route the data element to one of them in `[intake.forms]`
```

**The code resolves to nothing at all.** Distinct from the two above, because the
answer is different: this is a vocabulary miss, and under a lenient dial it is a
warning on the QR door. On the second door it cannot be, because there is no link id
to fall back to - a code that resolves to no DHIS2 object is a value with no
destination, and N3 refuses it.

```
`http://loinc.org|8867-4` is in none of the terminology this project publishes, so
there is no DHIS2 object to record it against
```

**The subject is missing.** `Observation.subject` being 0..1 makes this a conformant
resource this door cannot use:

```
this Observation states no subject, and a DHIS2 event records a value about a tracked
entity: carry the subject as `Patient/<tracked entity uid>`, or as an identifier under
`http://dhis2.org/fhir/id/tracked-entity`
```

**The subject resolves to nothing, or to several.** The unique-attribute spelling can
miss both ways, and both readings are useful:

```
no tracked entity of this instance holds `http://example.org/id/mrn|A-4471` on a
unique tracked entity attribute this project publishes
```

```
two tracked entities hold `http://example.org/id/mrn|A-4471`, and a submission
records a value about one: name the subject by its DHIS2 tracked entity UID
```

**The enrollment cannot be resolved.** Zero and two, worded as facts:

```
tracked entity zPde0IgxLd6 has no enrollment in the programme this form belongs to,
and a stage event belongs to an enrollment: enrol them first, or name the enrollment
on `D2TrackerEnrollment`
```

```
tracked entity zPde0IgxLd6 has two enrollments in this programme, and a stage event
belongs to one: name it on `D2TrackerEnrollment`
```

**The occurrence is missing.** `effective[x]` being 0..1 is the same class as the
missing subject.

**A stated absence.** `Observation.dataAbsentReason` says a value is known to be
missing. DHIS2 has no wire spelling for that: an empty string is an *erasure*, which
[complete payloads](data-lifecycle.md#34-complete-payloads-never-diffs) makes a
deliberate act, and omitting the cell is silence rather than a stated absence. So a
posted `Observation` carrying `dataAbsentReason` and no value is refused rather than
dropped, because dropping it is the "accepted and never forwarded" failure N3 names.

```
this Observation states its value is absent, and DHIS2 records values rather than
statements about their absence: post the observations that carry a value
```

### 4.2 What is a warning, and what the dial moves

The second door inherits the [existing grading](../401-capture-contract.md#what-is-always-a-warning)
wherever the finding is the same finding. A subject typed as something other than what
the form is answered about, an organisation unit outside the form's published
assignment, a code matched by a fall-back tier, terminology this project never
published on a *coded answer value*: all warn by default and all are promoted by
`--strict-codes`, on the same dial and in the same words.

**What cannot be a warning on this door** is anything that leaves a value without a
destination. The QR door can warn about an unresolvable coded answer and store the
submission unchecked, because the link id already said where the value goes and only
the value's meaning is in doubt. The second door has no link id: an unroutable code is
a value going nowhere, and "I cannot check this" and "I cannot place this" are
different sentences.

### 4.3 One resource per request, and what a `Bundle` would have to mean

The door refuses a `Bundle` today with 400 and the rule
`this endpoint accepts one QuestionnaireResponse per request; post each response on
its own request`. The second door will be asked to relax that, because an
immunisation registry posts a visit's doses together and a laboratory posts a panel
together.

**What the spool can and cannot promise.** One receipt is one response is one DHIS2
payload is one import. Lifecycle is the directory, moved per file with `os.replace`,
and the drain files each receipt the moment its verdict is known, so a run killed
halfway leaves every posted receipt filed and every unposted one queued. There is no
cross-receipt transaction anywhere in that, and there is no place to put one: DHIS2
takes one payload per call, and two calls can land differently.

That decides the shape of the answer.

**A `transaction` Bundle is refused.** R4 says all entries of a transaction succeed or
all fail. This project could honour that at *capture* - accept or refuse the whole
Bundle at the door - and could not honour it at *forward*, where N entries are N
independent posts and one can be rejected while the rest land. Accepting a transaction
would be promising a client atomicity the drain cannot keep, which is precisely the
failure the corrections refusal exists to prevent. Refused, naming why:

```
this project receives no transaction Bundle: each resource of it becomes its own
submission to DHIS2, and a submission can be accepted while another is refused - post
a batch Bundle, or post each resource on its own request
```

**A `batch` Bundle is the shape that fits, and it is capture-time all-or-nothing.**
R4's batch semantics already say the entries are independent, which is true of the
drain. What the door adds is that every entry has to route before any receipt is
written - a batch where one `Observation` resolves and one does not is refused whole,
with one issue per failing entry, each `expression` locating the entry by index. That
is not R4 batch semantics, and the response has to say so rather than let a client
infer it, because "some entries were accepted" is a state this door will not produce.

The reason to be strict here rather than lenient is N3 read at batch scale: a partially
accepted panel is a laboratory result of which some values reached DHIS2 and some did
not, with nothing on either side saying which. Refusing the batch leaves the client
holding all of it, which is the only place it can be fixed.

**Launch with one resource per request.** The rule the door already has, unchanged, and
the smallest thing that can be true. `batch` is designed above so that adding it later
is adding a loop and a refusal, not a decision.

## 5. One pipeline, not two

### 5.1 Lower at the door

The recommendation is that a posted resource is **lowered to the internal response
shape at the door**, before anything is written, and that what the spool holds is a
receipt of exactly the kind the first door produces.

The alternative - spool the native resource and give the translator a second entry
point beside `translate_response` - is the one to argue against, because it looks
cheaper and is not. It doubles the surface at eight places, and every one of them is a
place this repository has already paid to get right:

- `StoredResponseEnvelope` requires `form_kind` and `questionnaire`. A native receipt
  either fills them - in which case the lowering happened anyway, just later and in a
  worse place - or the model grows optional fields and every reader grows a branch.
- `d2w fhir forward` would carry two translation paths and two payload-building paths
  into one drain.
- `receipt_event_uid` and the whole correction identity derivation would need a second
  reading.
- `d2w fhir spool`, `d2w fhir requeue`, and `GET /spool` would page over two receipt
  shapes.
- The capture UI's Responses and ResponseDetail pages would render two.
- `test_fhir_conversion_roundtrip.py` grades every example response cell for cell
  against the emitter that produced it. A native path has no emitter and no corpus, so
  a second translator would ship with no equivalent gate.
- `D2AggregateResponseToDataValueSet` and the logical models are a contract over the
  response shape. A second wire shape means a second map family or a contract that
  covers half the door.
- Corrections and withdrawals are defined on `QuestionnaireResponse.status` and
  `basedOn`. Two shapes means two definitions of what a correction is.

Lowering at the door costs one function per resource type and leaves all eight
untouched. The translator never learns that a second door exists, which is the same
property that lets [the conversion CI gate](conversion.md#the-ci-gate) keep grading one
path against one contract.

### 5.2 The cost of lowering, stated

It is not free, and the cost lands on a promise the spool currently makes.
`StoredResponseEnvelope.response` documents it exactly:

> The facade's contract is byte-faithful: a receipt has to read back as what the client
> sent, so the resource is held verbatim rather than round-tripped through a model that
> would drop the extensions and answer types this repo has no schema for.

A lowered receipt holds a `QuestionnaireResponse` the client never sent. Reading it
back as "what the client sent" would be false, and quietly false, which is worse than
a missing field.

**So the envelope carries both.** The lowered response is what the translator reads and
what `GET /QuestionnaireResponse/{id}` answers; the posted resource is held verbatim
beside it and readable in its own right. Two fields, one receipt, and the byte-faithful
promise stays true of the half it was made about. A receipt then answers two questions
that are genuinely different - *what did the client send* and *what did this project
make of it* - and the second door is the first surface where those two have different
answers. Naming both is also what makes a routing mistake diagnosable: the receipt
shows the code that arrived and the question it was routed to, side by side, without
anyone reconstructing the table's state at the time.

### 5.3 Corrections and withdrawals apply identically, with one gap

[The correction design](data-lifecycle.md#3-the-design) is two conditions: a lifecycle
status of `amended` or `entered-in-error`, and a `basedOn` that resolves to a receipt
this spool already forwarded. The DHIS2 identity then derives from the *corrected*
receipt's id, and the strategy becomes `UPDATE` or `DELETE`.

The launch set carries the statuses and does not carry the pointer.

| | Correction status | Withdrawal status | A pointer to the corrected receipt |
| --- | --- | --- | --- |
| `Observation` | `amended`, `corrected` | `entered-in-error` | `basedOn` admits no `QuestionnaireResponse` |
| `Immunization` | none | `entered-in-error` | no `basedOn` at all |
| `Encounter` | none | `entered-in-error` | no `basedOn` at all |
| `Patient` | none | none - `active` is a boolean | none |

`Observation.status` carries both `amended` and `corrected` where
`QuestionnaireResponse.status` carries only `amended`, and R4 distinguishes them - a
record amended versus a record corrected - which is a distinction DHIS2 has no place
for and the lowering therefore collapses. Three of the four resources carry
`entered-in-error`. `Observation.basedOn` is `Reference(CarePlan | DeviceRequest |
ImmunizationRecommendation | MedicationRequest | NutritionOrder | ServiceRequest)`,
which is not a receipt, so no launch-set resource can point at what it corrects in a
native element.

**The pointer therefore rides an extension: `D2Corrects`, a `valueIdentifier` naming
the receipt.** The lowering writes it into `basedOn` on the internal response, and the
drain's identity derivation is untouched - it still reads a receipt id at the root of a
`basedOn` chain, still calls `receipt_event_uid` on it, and still cannot tell which
door the chain came through. The same two dials gate it, refused at capture with the
same words naming `[forward] corrections` and `[forward] withdrawals`, and a `Patient`
withdrawal has no spelling at all, which is a refusal rather than a gap to paper over.

The status map is a table the lowering owns and states, in the manner of
`EVENT_STATUSES_BY_RESPONSE_STATUS`: `corrected` and `amended` both become `amended`,
with a note recording the collapse where the posted value was `corrected`;
`entered-in-error` stays itself; and an `Observation` whose status is `preliminary` or
`registered` is the completeness question the aggregate door already answers, asked of
a different resource.

## 6. Idempotency and identity

### 6.1 What happens today when the same thing is posted twice

The facts, from [the lifecycle paper's measurements](data-lifecycle.md#23-what-silently-duplicates):

- **Receipt ids are minted server-side**, `uuid4` hex, never taken from the client.
- `receipt_event_uid(response_id)` derives the DHIS2 event UID from the receipt's own
  id, by SHA-256 over `<response id>:event:0`, shaped into a DHIS2 UID.
- **One receipt names one event.** Re-forwarding a receipt collides loudly on `E1030`,
  by design, because `_TRACKER_PARAMS` posts under `importStrategy=CREATE`.
- **One encounter does not name one event.** Two captures of the same visit mint two
  receipt ids, therefore two event UIDs, therefore two DHIS2 events, and nothing DHIS2
  answers says it happened.

That second guarantee's absence is tolerable on the first door and is not on the
second. A human re-submitting a form is a rare accident. A laboratory system retrying
a POST whose response it never saw is the normal operation of every integration ever
built, and a device gateway with an offline buffer will replay by design.

### 6.2 The launch set carries the thing that fixes it

Every one of the four resources carries `identifier`, `0..*`, and a client that has a
business identifier for a result already puts it there. `QuestionnaireResponse` carries
one too, and the first door reads it for nothing - which is a reasonable reading for a
form submission and the wrong one for a clinical resource.

**Derive the DHIS2 event UID from the posted resource's identifier where it carries a
routable one, and from the receipt id where it does not.** The derivation is the same
function over different material: `<system>|<value>:event:0` instead of `<response
id>:event:0`, hashed the same way and shaped by the same drawer. What that buys is
exactly the missing guarantee - the second posting of the same identifier derives the
same event UID, meets `importStrategy=CREATE`, and collides loudly on `E1030` instead
of filing a second copy of one dose.

Three properties of that are worth stating because each is load-bearing:

- **A loud collision is the correct answer, not a failure.** `rejected/` with an import
  report naming `E1030` says "DHIS2 already holds this", which is what a retrying client
  needs to hear. `d2w fhir requeue` is the operator's out if it was wrong.
- **It is derivation, not lookup.** No index, no uniqueness table, no state beyond the
  spool. The same identifier gives the same UID on this machine and the next, forever,
  which is the property `receipt_event_uid` was built for.
- **It needs a namespace decision.** Not every identifier a resource carries is one an
  instance should key on - an internal row id from a system nobody else knows is worse
  than nothing. The deployment nominates which identifier systems count, in the same
  file and the same voice as everything else it nominates, and a resource carrying none
  of them falls back to the receipt id and the existing behaviour.

### 6.3 FHIR ids and DHIS2 UIDs on the way in

Three rules, and the third is the one that will be argued about.

**A posted resource's `id` is read for nothing.** R4 says a server assigns the id on a
create, and a client-supplied one on `POST` is not a request. The receipt id stays
server-minted.

**DHIS2 UIDs are derived, never adopted.** Even where a posted `Observation.id` happens
to be eleven characters shaped like a DHIS2 UID, that is a coincidence, and a server
that acted on it would be letting a client's id space collide with an instance's. The
one place a client legitimately mints DHIS2 UIDs is the registration path, where the
capture contract says so explicitly and checks their shape - and a posted `Patient`
that wants that behaviour states the UID in an identifier under
`{base}/id/tracked-entity`, which is the same spelling the QR door reads, rather than
in `Patient.id`.

**A posted `Patient` is the case where two identity questions collide.** The client's
identifier says "this person, in my system"; `{base}/id/tracked-entity` says "this
person, in DHIS2". A registration creating a person carries the second because it is
minting it; a registration for a person the instance already holds carries the first
and needs a lookup, which is `D2SubjectExists` restated for a door with no
`D2SubjectExists`. This is a large part of why `Patient` is last in section 7.

## 7. Phasing

Smallest useful thing first, each phase independently valuable, none a prerequisite
for reversing an earlier one.

**Phase 1 - `Immunization`, one resource per request.** The reverse index, the
`[intake.forms]` tie-breaker, the published `D2Intake_CM`, the CapabilityStatement
entry, subject by tracked-entity UID or by a unique attribute under `--live`,
organisation unit and enrollment on the two existing extensions, occurrence from
`occurrence[x]`, and the dose value read off the routed question's item type. No
Bundle, no corrections, no withdrawals.

It goes first for four reasons that stack, and the fourth is the one that decided it:

1. It is the one resource with a named customer on the fleet.
2. `$summary` proves the crossing in the read direction, so the phase is a mirror of
   something that already works rather than a new claim.
3. `Immunization.patient` and `occurrence[x]` are both 1..1, so the two refusals
   `Observation`'s optional cardinalities force cannot arise in the first phase.
4. **Half its routing is already written.**
   [`[ips.sections.immunizations]`](../301-what-goes-in.md#ips-sections) names the dose
   data elements and the stages they sit in, an owner serving `$summary` has already
   written it and had it validated at load, and a project whose mapping names one stage
   needs no `[intake.forms]` line at all. Phase 1 therefore ships against an existing
   published table and can be measured before a new one exists.

The Observation-first counter-argument is worth stating, because it was the working
assumption until section 2.1 settled: prove the mechanism on the resource with the
simplest lowering and the largest client population, then widen. It weakens on the
finding that `Immunization`'s lowering is not more complex - `vaccineCode` names a data
element exactly as `Observation.code` does - and on point 4, which no other resource
can claim.
[The sequencing is reserved](#8-owner-decisions-this-paper-reserves) with the
counter-argument on the record.

**Phase 2 - `Observation`.** Adds `component` as several values of one form, the
identifier-derived event UID of section 6.2 and the namespace nomination it needs, and
the two refusals `Observation`'s optional cardinalities force. The route table gains no
new shape and no new key: an `Observation.code` and an `Immunization.vaccineCode` both
name a data element, and `[intake.forms]` cannot tell which resource asked.

**Phase 3 - `Encounter`, and `batch` Bundles.** The envelope resource plus the
capture-time all-or-nothing batch, which is the pair a clinical system actually posts:
one `Encounter` and the `Observation`s that reference it. `Encounter.location`
resolving natively through the published Locations is the one placement fact the door
stops having to be told.

**Phase 4 - `Patient` registration.** Last, for four reasons that compound:
[`[ips.identity]`](../301-what-goes-in.md#ips-identity) has to be read inward as well
as outward; the existing-versus-new subject question has no native spelling; a
registration for a person the instance already holds carries the BUGS.md 73 hazard,
where the wrong wrapper silently rewrites the person's owning organisation unit; and
`Patient` alone has no `entered-in-error`, so a withdrawal has to be refused rather
than mapped.

**Corrections and withdrawals ride whichever phase the drain's own correction path
reaches.** Slices 5 to 9 of [the lifecycle plan](data-lifecycle.md#4-the-slice-plan)
are unbuilt, and the second door should not be the thing that builds them. When they
land, `D2Corrects` is a lowering rule and nothing else.

## 8. Owner decisions this paper reserves

- **Whether the second door is built at all, and where its dial lives.** Recommended:
  built, gated by `[intake] enabled`, defaulting to `false`, refused at capture in the
  shape the two lifecycle postures already use. The call includes whether it is its own
  key or a widening of `[serve] capture`, which today is a boolean deciding whether the
  create route is mounted and whether `/metadata` declares `create` at all. A widened
  `capture` says one true thing about one surface; a separate `[intake] enabled` keeps
  a project able to receive form submissions and refuse native ones, which is the more
  likely posture. The alternative to the whole feature is that a client which cannot
  emit a `QuestionnaireResponse` writes a small adapter, and that is a defensible call
  for a project that would rather have one door than two.

- **The routing mechanism.** Recommended: candidate (d) - `fhir.toml` as the input,
  `D2Intake_CM` as the published output, the server performing the file - with
  candidate (c)'s `D2Form` extension as the client-side override that beats the table,
  and candidate (a)'s reverse index built to make the ambiguity refusal precise rather
  than to route. Candidate (b) is recommended against as a mechanism and recommended
  *for* as a contract a guide may publish so a client can validate before it posts.

- **Whether the table states only the ambiguities, or every route.** Recommended: only
  the ambiguities, because a data element one form asks needs nobody to say which form,
  and a table that restates the guide goes stale against it. The alternative - every
  routed code written down - is auditable without the reader holding the compiled guide,
  which is a real property and the reason `[ips.sections]` lists its stages explicitly
  rather than deriving them.

- **Whether the immunisation door reads `[ips.sections.immunizations]` or its own
  table.** Recommended: it reads that table, because it is the same claim, already
  written, already validated at load, and already published as `D2Section_CM` -
  duplicating it into `[intake.forms]` would let one project state two different
  answers to "which stages record doses". The counter is that a read-side mapping
  acquiring write-side authority is a widening an owner should agree to explicitly,
  which is why it is on this list rather than assumed.

- **Whether a route is validated against the form at load.** Recommended: yes - a route
  naming a form that does not ask the data element, or a question whose item type no
  posted resource of the admitted types can answer, is refused when `fhir.toml` is read,
  naming both, in the manner of the `[generate.tracked_entity_types]`
  unknown-resource-type refusal.

- **Bundle posture.** Recommended: one resource per request at launch; `transaction`
  refused permanently, naming the reason; `batch` admitted later with capture-time
  all-or-nothing and the response stating that it is not R4 batch semantics. The
  alternative on the last point - true per-entry independence, some entries accepted -
  is defensible for a high-volume device feed and indefensible for a laboratory panel,
  and the door cannot have two postures without a dial nobody has asked for.

- **The idempotency key, and which identifier systems count.** Recommended: derive the
  event UID from a nominated identifier where the resource carries one, fall back to the
  receipt id where it does not, and nominate the systems in `fhir.toml`. The call
  includes whether nominating nothing means "no identifier is trusted" - the
  conservative reading, and the recommended one - or "any identifier is trusted", which
  is friendlier and lets an unknown client's internal row id key an instance's data.

- **Whether the receipt holds the posted resource beside the lowered response.**
  Recommended: yes, as two fields of one envelope, because the byte-faithful promise is
  made about what the client sent and a lowered response is not that. The alternative -
  hold only the lowered response and narrow the promise - is cheaper and gives up the
  one artifact that makes a routing mistake diagnosable after the fact.

- **Sequencing.** Recommended: `Immunization`, `Observation`, `Encounter` with batches,
  `Patient`. Section 7 records the Observation-first argument in full, and it is a real
  argument rather than a strawman: it proves the mechanism on the resource whose
  lowering is one item. The call is whether the fleet's named customer or the smallest
  mechanism goes first.

- **What the 400 says when the door is open.** The refusal
  ``this endpoint receives a QuestionnaireResponse, not a `Observation` `` is wrong on a
  project that has opened the second door and right on one that has not. Recommended: it
  becomes a sentence naming what this project receives, built from the CapabilityStatement
  the project actually publishes, so the two configurations each say something true. It
  is on this list because it is user-facing copy, and copy is a review dimension.

## See also

- [The capture contract](../401-capture-contract.md) - the first door, whose five
  profiles, five refusal classes, and grading dial this one inherits whole.
- [Corrections and withdrawals](data-lifecycle.md) - the spool's guarantees, the
  `basedOn` identity derivation, and the two dials a marked submission is read against.
- [The conversion layer](conversion.md) - `dhis2w_fhir.conversion` and the CI gate that
  grades one translation path, which is what section 5 argues for keeping singular.
- [The IPS document](ips.md) - the owner-stated-mapping doctrine and its option C, read
  here in the opposite direction, and `[ips.sections]` as the immunisation vocabulary's
  proof of crossing.
- [The enrollment resource](enrollment-resource.md) - the intent-versus-record argument
  that excludes `MedicationRequest`, and the `Patient`-subject scoping the immunisation
  door inherits.
- [Custom subject types](../401-custom-subject-types.md) - `[generate.tracked_entity_types]`,
  which decides what a posted resource's own type is allowed to claim.
- [Terminology and ConceptMaps](../401-terminology-and-conceptmaps.md) - the maps back
  to DHIS2, their two-group shape, and the namespaces `D2Intake_CM` would publish into.
- [Generate the IG source](../201-generate.md#answer-the-hostile-name-question) - why a
  published display string is not an identifier, and codes are never rewritten.
