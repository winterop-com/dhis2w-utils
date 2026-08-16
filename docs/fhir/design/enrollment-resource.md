# The enrollment resource: EpisodeOfCare, CarePlan, or neither

What FHIR resource a DHIS2 enrollment is, examined against R4 4.0.1, against what
this project already publishes, and against what three adjacent projects did with the
same question. This is the working paper behind roadmap decision
[5.2](roadmap.md#52-the-tracker-shape); the decision itself stays with the owner,
and this page is the basis for making it.

A reader who knows DHIS2 but not FHIR should be able to follow this end to end. Where a
FHIR element is named, its cardinality and allowed types are stated, because in this
decision the cardinalities are the argument.

## The short version

`EpisodeOfCare` is the enrollment. `CarePlan` is not a rival reading of the enrollment -
it is a different resource that a decision-support layer mints *alongside* one, which is
exactly what the WHO Antenatal Care guide does at its own enrollment step. The framing
that has been carried in the roadmap since this decision opened - "`EpisodeOfCare` **or**
`CarePlan`" - is the first thing to retire, because the two are not alternatives and
choosing between them answers a question nobody asked.

## 1. What is actually being decided

The scope has narrowed twice since the decision opened, and both narrowings are load
bearing.

**The subject *type* is already settled.** `[generate.tracked_entity_types]` maps a DHIS2
tracked entity type UID onto the FHIR resource type its registrations are about, out of
the nine `SUBJECT_RESOURCE_TYPES` a tracked entity can be (`Patient`, `Person`,
`Practitioner`, `RelatedPerson`, `Group`, `Device`, `Location`, `Organization`,
`Specimen`), defaulting to `Patient`. That resolution already drives `subjectType` on
every generated form and the reference targets of the two tracker response profiles.

**The capture contract already ships without either resource.** A registration response
carries a logical subject under `{base}/id/tracked-entity`, the enrollment under
`{base}/id/tracker-enrollment` on the `D2TrackerEnrollment` extension
(`valueIdentifier`), and `D2EnrolledAt` / `D2IncidentAt` dating it. The client mints both
UIDs, because the response is what creates them. Nothing about that changes under any
option below, and the reason is structural rather than a matter of taste: a
`QuestionnaireResponse` is a form submission, not a bundle, so it has nowhere to *put* an
`EpisodeOfCare`. A capture contract that wanted to carry one would have to become a
transaction Bundle, which is a different project.

So what is left is **the read side**: whether, when a FHIR client asks this project's
server what programs a person is in, the answer is a resource of a standard type or the
typed JSON listing that answers today at
`GET /tracked-entities/{uid}/enrollments`. That listing exists in exactly this shape
because of this open decision - it says so in its own module docstring - and it is
deliberately on a lowercase path no FHIR resource type can collide with, so the day a
resource lands nothing has to be un-published.

**One consequence worth stating plainly before the analysis starts:** because the capture
leg is unaffected, this decision is cheap to make and cheap to reverse. It is not
blocking anything, which is the strongest argument for getting it right rather than
quickly.

## 2. What a DHIS2 enrollment is

An enrollment is the DHIS2 record that one tracked entity is in one program, at one
organisation unit, over a period, with a status. Everything it carries:

| DHIS2 field | Meaning | Multiplicity |
| --- | --- | --- |
| `enrollment` | The enrollment's own UID | exactly one |
| `trackedEntity` | Who or what is enrolled | exactly one |
| `program` | Which program | exactly one |
| `orgUnit` | The unit that owns the enrollment | exactly one |
| `enrolledAt` | When the enrollment began | exactly one |
| `occurredAt` (incident date) | When the thing being tracked happened, where the program collects one (`displayIncidentDate`) | zero or one |
| `completedAt` | When it was completed | zero or one |
| `status` | `ACTIVE`, `COMPLETED`, or `CANCELLED` | exactly one |
| `attributes[]` | The values of attributes the *program* collects, as opposed to the ones the tracked entity type collects | zero or more |
| `events[]` | The events captured against it | zero or more |

Four facts about that list shape the rest of this page.

1. **The enrollment owns the program-level attribute values.** DHIS2 splits a
   registration's answers in two: an attribute belonging to the tracked entity type is
   stated on `trackedEntities[].attributes`, and an attribute the program alone collects
   is stated on `enrollments[].attributes`. The conversion layer already splits by
   `D2EntityLevel` for exactly this reason.
2. **A tracked entity may be enrolled more than once in the same program**, unless the
   program sets `onlyEnrollOnce`. Successive pregnancies in an antenatal program are the
   canonical case, and they are separate enrollments, not one enrollment reopened.
3. **The subject is not necessarily a person.** Herds, buildings, water points, and
   specimens are real tracked entity types, and each of them can be enrolled in a program.
4. **`COMPLETED` is not closed.** DHIS2 accepts an event into a completed enrollment with
   no error and no warning (BUGS.md 70). Whatever resource is published has to state a
   status that is descriptive, not enforced.

## 3. The requirement set

Derived from what this repository already does and what it has committed to doing.

**R1 - Fill every element from DHIS2 without inventing anything.** This is the rule the
Patient projection already lives by: it publishes no `name`, no `gender`, and no
`birthDate`, because DHIS2 has no attribute that *means* those things and a wrong gender
on a patient record is worse than no gender. Any element a candidate resource makes
mandatory is a promise that DHIS2 can fill it. Any element it makes optional that DHIS2
cannot fill honestly is simply left out.

**R2 - Survive a subject that is not a person.** The subject type map admits nine
resource types. A resource that cannot represent a `Specimen` enrollment does not thereby
disqualify itself, but the project has to say what happens in that case rather than
discover it later.

**R3 - Do not disturb the capture contract.** Identifier-keyed, client-minted, shipped,
round-tripping at 225/225/0. Nothing here is worth reopening it for.

**R4 - Be the natural successor to the enrollment listing.** The picker feed carries
enrollment UID, program UID and name, status, active flag, enrolment date, organisation
unit UID and name. A resource that cannot carry those is not an upgrade.

**R5 - Serve from `TrackedEntityIndex` joins that already exist.** The index already holds
`{base}/id/program` with program names off the published Questionnaires, and
`{base}/id/org-unit` with organisation unit names off the published registry. A projection
that needs a join the index does not have is a bigger slice than it looks.

**R6 - Leave the SDC and PlanDefinition lines open.** The per-stage Questionnaires carry
`D2DE_CS` codings on every item, which is what SDC `$extract` keys on to project a
response into coded `Observation`s. `PlanDefinition` - the program *as a definition*, one
action per stage - is recorded in the roadmap as the definition-side artifact, and
`$apply` is its operation. Neither should be foreclosed.

**R7 - Plain R4 4.0.1, no derived profiles from IHE mCSD or OpenHIE.** The published
guide is base R4 with this project's own extensions. WHO SMART Guidelines alignment is
valued as a *pattern to match*, not as a dependency to take.

**R8 - Identifier-first.** Every DHIS2 identity is published under a
`{base}/id/<subject>` system, and a fact this project cannot type faithfully rides an
extension carrying DHIS2's own value rather than a FHIR reading of it.

## 4. `EpisodeOfCare` against R4

R4 4.0.1 defines it as "an association between a patient and an organization / healthcare
provider(s) during which time encounters may occur", and states its relationship to
`CarePlan` outright: "The EpisodeOfCare is a tracking resource, rather than a planning
resource. The EpisodeOfCare usually exists before the CarePlan."

Its elements, with what DHIS2 puts in each:

| Element | R4 cardinality and type | What DHIS2 gives it |
| --- | --- | --- |
| `identifier` | 0..* Identifier | The enrollment UID under `{base}/id/tracker-enrollment` |
| `status` | 1..1 code | `ACTIVE` / `COMPLETED` / `CANCELLED` |
| `statusHistory` | 0..* BackboneElement | Nothing - DHIS2 keeps no status history on the enrollment |
| `type` | 0..* CodeableConcept | The program, coded under `{base}/id/program` |
| `diagnosis` | 0..* BackboneElement | Nothing |
| `patient` | **1..1 Reference(Patient)** | The tracked entity |
| `managingOrganization` | 0..1 Reference(Organization) | Nothing directly - see below |
| `period` | 0..1 Period | `start` from `enrolledAt`, `end` from `completedAt` |
| `referralRequest` | 0..* Reference(ServiceRequest) | Nothing |
| `careManager` | 0..1 Reference(Practitioner \| PractitionerRole) | Nothing |
| `team` | 0..* Reference(CareTeam) | Nothing |
| `account` | 0..* Reference(Account) | Nothing |

**One mandatory element beyond `status`, and it is the subject.** Everything else is
optional, which means R1 is satisfiable: the six clinical elements DHIS2 knows nothing
about are all `0..*` or `0..1` and are simply absent. There is no element this project
would have to guess at to produce a valid instance.

**The status machine is a clean three-into-three.** R4's value set is `planned |
waitlist | active | onhold | finished | cancelled | entered-in-error`; DHIS2's `ACTIVE`
maps to `active`, `COMPLETED` to `finished`, `CANCELLED` to `cancelled`. Nothing on the
DHIS2 side is lost, and the four unused FHIR codes are a vocabulary this project simply
never emits - the same relationship the guide already has with the rest of R4.

`statusHistory` stays empty on purpose, and that is the honest answer rather than a gap:
DHIS2 records a current status and a `completedAt`, not a transition log, and a synthesised
history would be a claim about when things changed that nothing supports.

**`managingOrganization` is the one real friction, and it is 0..1.** DHIS2's owning
organisation unit is the natural filler, but this project publishes organisation units as
`Location`, not `Organization` - the registry codes levels, carries point geometry in
`Location.position`, and polygon geometry through the boundary extension. R4's
`managingOrganization` accepts `Reference(Organization)` only, and `EpisodeOfCare` has no
location element at all. So the owning unit rides the existing `D2OrganisationUnit`
extension carrying its UID under `{base}/id/org-unit`, which is exactly the identifier-first
rule (R8) and exactly what the tracker response profiles already do. Corroboration that
this is not a peculiar corner: the WHO ANC guide's own enrollment example leaves
`managingOrganization` as an XML comment reading `<!-- TODO: managingOrganization -->`.

**The subject constraint is the hard one.** `EpisodeOfCare.patient` is `1..1
Reference(Patient)` in R4, and unchanged in R5 - R5's own changes list touches `reason`,
`diagnosis.condition`, `diagnosis.use`, `careTeam` and `diagnosis.rank`, and leaves
`patient` alone. Only the R6 ballot renames it to `subject` and adds `Group` as a target.
So under R4 there is no valid `EpisodeOfCare` for a herd, a water point, or a specimen, and
no amount of profiling creates one: profiles constrain, they never widen.

Against R2, that produces a rule rather than a defeat. The resource layer is offered
where a program's tracked entity type resolves to `Patient`, and the typed listing stays
the universal answer everywhere else. This is not a new concession - it is the rule the
Patient surface already follows, which refuses with `NoPublishedSubjectTypeError` when a
project publishes no `Patient`-subject type at all.

## 5. `CarePlan` against R4

R4 defines it as describing "the intention of how one or more practitioners intend to
deliver care for a particular patient, group or community for a period of time", and is
explicit that it is instance-level: "CarePlan represents a specific plan instance for a
particular patient or group. It is not intended to be used to define generic plans or
protocols that are independent of a specific individual or group. Protocols and order
sets are supported through PlanDefinition."

| Element | R4 cardinality and type | What DHIS2 gives it |
| --- | --- | --- |
| `identifier` | 0..* Identifier | The enrollment UID |
| `instantiatesCanonical` | 0..* canonical | A `PlanDefinition` this project does not generate yet |
| `basedOn` / `replaces` / `partOf` | 0..* Reference(CarePlan) | Nothing DHIS2 states |
| `status` | 1..1 code | `active` / `completed` / `revoked` |
| `intent` | **1..1 code** | Nothing - see below |
| `category` | 0..* CodeableConcept | The program, arguably |
| `title` | 0..1 string | The program name |
| `subject` | **1..1 Reference(Patient \| Group)** | The tracked entity |
| `encounter` | 0..1 Reference(Encounter) | Nothing |
| `period` | 0..1 Period | `enrolledAt` .. `completedAt` |
| `created` / `author` | 0..1 | Nothing faithful |
| `careTeam` / `addresses` / `goal` | 0..* | Nothing |
| `activity` | 0..* BackboneElement | The interesting question |

**`intent` is 1..1 and DHIS2 has no answer to it.** The value set is `proposal | plan |
order | option`. An enrollment is not a proposal, not an order, and not an option; `plan`
is the only survivor, which means every instance this project ever emits carries the same
hard-coded literal because the element is mandatory and DHIS2 has nothing to say. Under R1
that is exactly the shape of thing the Patient projection refuses to do with `gender`. It
is a small lie rather than a large one - but it is a required field filled from nowhere,
and `EpisodeOfCare` has no equivalent.

**`activity` is where the argument for `CarePlan` lives, and DHIS2 does not fill it.** A
DHIS2 enrollment does not carry a schedule. The schedule is program metadata - the stages,
their `minDaysFromStart`, whether they repeat - and it is the same for every enrollment in
the program. That is precisely the definition-side artifact the roadmap already assigns to
`PlanDefinition`. What the enrollment holds is `events[]`: things that already happened.
A `CarePlan` whose `activity[]` is either empty or a rear-view mirror of completed events
is a planning resource carrying no plan, which is a worse statement about the data than
publishing no resource at all.

**Its subject constraint is no better for R2.** `1..1 Reference(Patient | Group)` is
wider than `EpisodeOfCare`'s R4 constraint, so a herd tracked as a `Group` would validate.
But `Group.type` in R4 is bound to `person | animal | practitioner | device | medication |
substance`, and `Group.member.entity` accepts `Patient | Practitioner | PractitionerRole |
Device | Medication | Substance | Group` - so a `Specimen` or a `Location` cannot be a
`Group` member either. `CarePlan` buys one tracked entity kind (an animal herd, as a
`Group`) and no more, at the cost of a mandatory `intent` and an empty `activity[]`.

**The `$apply` loop is real, and it is not this resource.** `PlanDefinition/$apply`
instantiates a definition for one subject, and its canonical output is a `CarePlan`
containing a `RequestGroup`. The roadmap records this as the argument for choosing
`CarePlan` for the enrollment: the enrollment would then carry `instantiatesCanonical`
back to the program's `PlanDefinition` and close the loop. The flaw in that reasoning is
that the `CarePlan` `$apply` mints is a *newly computed plan for a subject* - what should
happen next - while a DHIS2 enrollment is a *record that already exists* - what was
started, and when. Making one resource carry both meanings does not close a loop; it
collapses two facts into one and loses the ability to state either precisely.

## 6. The third option: keep it identifier-shaped

Publish no enrollment resource. The enrollment stays what it is today: an identifier under
`{base}/id/tracker-enrollment`, carried on `D2TrackerEnrollment` in the capture contract,
and served as typed JSON from `GET /tracked-entities/{uid}/enrollments`.

Two sub-variants exist and both are worse than the plain version.

**`Basic`.** R4's escape hatch for a concept with no resource of its own: `code` 1..1,
`subject` 0..1 Reference(Any), everything else in extensions. It would carry a `Specimen`
subject, which nothing else on this page can. But `Basic` is opaque by construction - no
FHIR client has a search parameter, a renderer, or an expectation for it, so "an enrollment
as `Basic`" reaches consumers as an untyped blob wearing a resource wrapper. It buys the
appearance of FHIR without the legibility that is the entire point.

**A `kind=logical` StructureDefinition.** The conversion plan already calls for two of
these (the data value set row, the tracker event) as documentation of DHIS2's wire shapes
and as a prerequisite for any StructureMap. An enrollment logical model would be an honest
*description* of the DHIS2 shape - but a logical model is not an instantiable resource, so
it documents the JSON the listing already serves rather than replacing it. It is a good
thing to have and not an answer to this question.

**What the plain status quo costs.** At capture: nothing, since the capture contract is
unaffected under every option. At the output-leg data half: a FHIR client that wants to
know which programs a person is in has to learn a route this project invented, which is
exactly the outcome the whole guide exists to avoid. The Patient surface's stated bar is a
client that can "round-trip: capture through the guide, read back through the guide,
without ever speaking the DHIS2 API" - and a bespoke JSON route is speaking a DHIS2-shaped
API with different spelling.

## 7. What three adjacent projects did

Read, not recalled. Each of these was fetched while writing this page.

**OpenMRS reached the same conclusion in design and has not shipped it.** The OpenMRS Talk
thread [Mapping episode of care to patient program](https://talk.openmrs.org/t/mapping-episode-of-care-to-patient-program/36828)
settles that OpenMRS's `patient_program` - not `program` - maps to `EpisodeOfCare`, with
Burke Mamlin's reasoning being that "patient_program represents one 'episode' of a patient
entering a program" and is "most analogous to FHIR's EpisodeOfCare". That is the same
per-episode argument that makes repeat enrollments unproblematic in section 8 below. The
thread also records the dissent: Angshuman Sarkar questions whether `patient_program`
aligns with `EpisodeOfCare` semantically and suggests `CarePlan` instead, and notes the
FHIR2 API could not create an `EpisodeOfCare` mapped to a `patient_program`. The
[OpenMRS Core FHIR Implementation Guide](https://fhir.openmrs.org/) lists the seventeen
resources the module supports - Patient, Person, Practitioner, Observation, Location,
AllergyIntolerance, Condition, DiagnosticReport, Encounter, Medication, MedicationRequest,
MedicationDispense, ServiceRequest, Task, Group, Immunization, RelatedPerson - and neither
`EpisodeOfCare` nor `CarePlan` is among them. So the nearest precedent agreed on
`EpisodeOfCare` in the design conversation and shipped nothing.

**The DHIS2 FHIR adapter never published one at all.** The
[DHIS2 FHIR Adapter mapping guide](https://github.com/dhis2/dhis2-fhir-adapter/wiki/DHIS2-FHIR-Adapter-API-Guide-for-Administration-and-Mapping-(1.0))
supports `DIAGNOSTIC_REPORT, IMMUNIZATION, LOCATION, MEDICATION_REQUEST, OBSERVATION,
ORGANIZATION, PATIENT, RELATED_PERSON` on the FHIR side and `ENROLLMENT,
PROGRAM_STAGE_EVENT, TRACKED_ENTITY` on the DHIS2 side. The enrollment is a DHIS2-side
transformation target with no FHIR counterpart - which is, structurally, the status quo
option, arrived at by a project solving the inbound direction only. (The repository is
archived and marked deprecated, pointing at the ITINordic fork.)

**WHO SMART Guidelines publishes both, at the same step, as different things.** The WHO
Antenatal Care guide defines `ANCEpisodeOfCare` (`input/profiles/base/structuredefinition-anc-episodeofcare.json`,
deriving from a `who-episodeofcare` core profile) *and* `ANCCarePlan`, and its worked
scenario has a directory literally named `first-contact/02-enrollment/` containing one of
each. The `EpisodeOfCare` example is the case: `status` `active`, `type` coded `ANC.Case`
from the guide's own CodeSystem beside an HL7 `episodeofcare-type` coding, one `diagnosis`
naming the pregnancy `Condition`, `patient` referencing the woman, `period.start` the date
she was enrolled, and `managingOrganization`, `careManager`, `team` and `account` left as
TODO comments. The `CarePlan` example is the plan: `instantiatesCanonical` pointing at
`PlanDefinition/ANCS01`, `intent` `plan`, `goal`, `addresses` naming the same pregnancy
`Condition`, and an `activity[]` of scheduled contacts each with its own
`instantiatesCanonical` and SNOMED coding.

The detail that settles the framing: WHO's `CarePlan` links to its `EpisodeOfCare` through
an invented extension, `http://smart.who.int/anc/StructureDefinition/careplan-episodeOfCare`,
because R4's `CarePlan` has **no** element referring to an `EpisodeOfCare`. The two
resources are so distinct in R4 that connecting them requires extending the spec - and the
organisation whose alignment this project values needed both, not one.

## 8. The six hard cases

**A subject that is not a person.** `EpisodeOfCare` cannot represent one under R4 or R5,
full stop (`patient` 1..1 Reference(Patient)); R6 renames it to `subject` and admits
`Group`. `CarePlan` admits `Patient | Group`, which covers a herd as a `Group` of type
`animal` and covers nothing else, since `Group.member.entity` excludes `Specimen` and
`Location`. Status quo covers everything, because JSON has no opinion. Under every option
that publishes a resource, the answer is the same rule: publish the resource where the
subject resolves to `Patient`, keep the listing everywhere else, and say so.

**Repeat enrollment in one program (`onlyEnrollOnce = false`).** `EpisodeOfCare` handles it
by construction - one episode per enrollment, each with its own `period`, which is exactly
the argument OpenMRS reached. `CarePlan` handles it too, but invites `replaces` and
`basedOn` questions that DHIS2 states no answer to, so a reader would have to be told the
absence means nothing. Status quo handles it - the listing already returns every
enrollment in DHIS2's own order.

**A `COMPLETED` enrollment that keeps accepting events (BUGS.md 70).** The resource must
describe, never enforce. `EpisodeOfCare` publishes `finished` and lets an `Encounter`
reference it anyway - anomalous in FHIR too, which is the correct outcome: the anomaly is
DHIS2's and should be visible rather than smoothed away. `CarePlan` publishes `completed`
with the same property. The listing already does this deliberately, stating `status`
verbatim and `active` as the graded flag, and its docstring argues why a facade must not
hide a completed enrollment the instance is perfectly willing to be given data for.
Whatever ships, no option should map a completed enrollment to something friendlier than
DHIS2 said.

**The enrollment-only forward target.** A registration whose response states
`D2SubjectExists` produces an enrollment alone - a top-level `enrollments` array naming an
existing tracked entity, posted that way because riding it inside a `trackedEntities` entry
silently rewrites the person's owning organisation unit (BUGS.md 73). This is a capture-leg
mechanism and is untouched by all three options. Worth noting only because it is the place
where "the enrollment is a thing in its own right" is already true in this codebase's
import path - which is a small point in `EpisodeOfCare`'s favour, since that is a resource
in its own right, whereas `CarePlan`'s value would have to come from stage content the
enrollment-only payload does not carry.

**The output-leg data half.** Serving DHIS2's *data* as FHIR is the long-term item, with
the enrollment listing as its first read surface. Under `EpisodeOfCare`, the swap is
mechanical: `GET /EpisodeOfCare?patient=`, `GET /EpisodeOfCare/{uid}`, every element filled
from the same entity read the listing already makes, every join already in `TrackedEntityIndex`
(R5). Under `CarePlan`, the same route exists but each instance carries a fabricated
`intent` and an empty `activity[]`. Under status quo, there is no FHIR route.

**Capture.** Unaffected under all three. Stated once more because it is the fact that makes
this decision low-risk.

## 9. The matrix

| | `EpisodeOfCare` | `CarePlan` | Identifiers only |
| --- | --- | --- | --- |
| Mandatory elements DHIS2 cannot fill | none | `intent` | n/a |
| Status mapping | `active` / `finished` / `cancelled`, 3 into 3 | `active` / `completed` / `revoked`, 3 into 3 | verbatim |
| Program lands on | `type` (0..* CodeableConcept) | `category` or `title` | `program_uid` + `program_name` |
| Owning organisation unit | `D2OrganisationUnit` extension (`managingOrganization` wants `Organization`; this guide publishes `Location`) | same problem, same answer | plain field |
| Non-`Patient` subjects | R4/R5 no, R6 adds `Group` | `Group` only | all nine |
| Repeat enrollments | native | native, with unanswerable `replaces` | native |
| Completed-but-open (BUGS.md 70) | describes it | describes it | describes it |
| Empty-shell risk | low - it is a tracking resource and DHIS2 has the tracking facts | high - a plan with no plan | n/a |
| Forecloses `PlanDefinition` / `$apply` | no; they coexist, as in the WHO ANC guide | yes, by occupying the resource `$apply` mints | no |
| Effort for the first slice | one R4 model, one projection, two routes | same, plus decisions nobody can source | zero |
| Precedent | OpenMRS design thread; WHO ANC ships it at its enrollment step | WHO ANC ships it too, as the *plan*, not the enrollment | DHIS2 FHIR adapter; OpenMRS as shipped |

## 10. Recommendation

**Publish the enrollment as `EpisodeOfCare`, on the read side only, where the subject
resolves to `Patient`. Keep `CarePlan` unclaimed for the definition-side line, where
`PlanDefinition` and `$apply` live. Change nothing about capture.**

The reasoning, laid bare:

1. **`EpisodeOfCare` needs no invention and `CarePlan` needs one on every instance.** R1 is
   the rule this project already enforces on the Patient projection at some cost, and it
   picks a winner here without any further argument: `EpisodeOfCare` has exactly one
   mandatory element beyond `status`, and DHIS2 fills it. `CarePlan.intent` is mandatory,
   and DHIS2 does not.
2. **R4 says which resource this is.** "The EpisodeOfCare is a tracking resource, rather
   than a planning resource." A DHIS2 enrollment is a record of participation that already
   happened. It is not an intention.
3. **The two are not alternatives, and treating them as such is the mistake to avoid.**
   WHO's ANC guide publishes both at its own enrollment step and had to invent an extension
   to connect them. Assigning `CarePlan` to the enrollment does not close the `$apply`
   loop - it spends the resource `$apply` produces on a fact that is not what `$apply`
   produces. Leaving `CarePlan` unclaimed is what keeps the `PlanDefinition` line open (R6).
4. **The subject constraint costs less than it appears to.** `EpisodeOfCare.patient` being
   `1..1 Reference(Patient)` in R4 means non-person enrollments get no resource. But
   `CarePlan` rescues only one further case (a herd as a `Group`) and pays for it with a
   fabricated `intent` on every instance including the person ones. The honest rule -
   *the resource where the subject is a `Patient`, the typed listing everywhere else* - is
   the rule the Patient surface already follows, and it inherits R6's widening for free the
   day this project moves.
5. **Nothing has to be un-published to get there.** The listing lives on a lowercase path
   precisely so a resource can land beside it. Both can be served: the listing is what the
   picker uses and it is the only answer for a non-`Patient` subject; `EpisodeOfCare` is
   what a FHIR client uses.

**What would change this answer.** If a project appears whose tracker programs are mostly
non-person - specimen chains, equipment maintenance - then the identifier-only option wins
for that project, and the right response is to make the resource layer conditional rather
than to pick a different resource, because `CarePlan` does not solve that case either. If
this guide ever targets R6, the recommendation gets strictly stronger: `subject` widens to
`Patient | Group` and the herd case comes inside.

## 11. The first slice, if ratified

Small, and entirely on the read side.

1. **`EpisodeOfCare` in `dhis2w_fhir.r4`** - a hand-written model beside `Patient` and
   `Location`, carrying `identifier`, `status`, `type`, `patient`, `period`, and
   `extension`, and nothing this project does not fill. Re-exported from
   `dhis2w_fhir/__init__.py` with an `::: ` entry in `docs/fhir/api-dhis2w-fhir.md`, per the repo's
   public-symbol rule.
2. **`dhis2w_fhir_serve/enrollments/projection.py`** - one enrollment onto one
   `EpisodeOfCare`, modelled on `patients/projection.py` including its module docstring
   discipline: what it carries, where each fact comes from, and what it deliberately does
   not carry. `id` is the enrollment UID, so `EpisodeOfCare/<uid>` reads back the same
   enrollment. Status map as a frozen table; `period.end` only where `completedAt` exists;
   `type` from `{base}/id/program` with the display off `TrackedEntityIndex.program_names`; the
   owning unit on `D2OrganisationUnit`.
3. **Two routes in live mode** - `GET /EpisodeOfCare/{uid}` and
   `GET /EpisodeOfCare?patient=<tracked-entity-uid>` returning a searchset `Bundle`, both
   read from the same entity-scoped tracker read the listing already uses (never with
   `program=`, per BUGS.md 72), both gated by `[serve.tracked_entities] enabled` and by whether the
   project publishes a `Patient`-subject tracked entity type, refusing with the existing
   `RegisterDisabledError` / `NoPublishedSubjectTypeError`.
4. **`CapabilityStatement` gains the resource**, so a client discovers it rather than
   guessing.
5. **The listing stays exactly as it is**, with its module docstring rewritten from "this
   is not a FHIR resource because 5.2 is open" to "this is the picker's feed, and it is the
   only answer for a subject that is not a `Patient`" - which is a better reason than the
   one it has now.
6. **A `D2EpisodeOfCare` profile in the generated guide** is explicitly *not* in the first
   slice. Serve's live mode publishes no StructureDefinitions and resolves none, and base
   R4 instances are what a client can validate today. The profile is worth adding when the
   guide starts publishing data resources generally, not to bless one projection.

Out of scope for the slice and worth naming so nobody looks for them: no `Encounter` for
DHIS2 events, no `EpisodeOfCare` on the capture leg, no `PlanDefinition`, no `$apply`.

## 12. What this decision does not settle

- **Whether the tracked entity becomes a real `Patient` resource.** It already has: the
  Patient surface serves one per tracked entity, by UID and by search. What 5.2's original
  framing called the subject half is closed.
- **Whether events become `Encounter` or `Observation`s.** That is the SDC `$extract` line,
  and it stays open under every option here.
- **`PlanDefinition` for the program.** Recommended above to be kept open, not opened.
- **The extraction mechanism** - decision [5.3](roadmap.md#53-the-extraction-mechanism),
  which this page does not touch.

## See also

- [FHIR roadmap and review guide](roadmap.md) - decision 5.2, which this page
  narrows.
- [DHIS2 fidelity audit](dhis2-fidelity.md) - the enrollment among every other DHIS2
  concept, with a verdict.
- [Consume the FHIR API](../401-consume-the-fhir-api.md) - what a client can
  read about an enrollment today.
- [Glossary](../glossary.md) - enrollment, the register, and the extensions
  that carry them.
