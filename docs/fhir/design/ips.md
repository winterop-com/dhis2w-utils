# The IPS document: what a DHIS2 tracker instance can honestly summarise

What an International Patient Summary requires, measured against the published IG,
against what this project's register projection actually holds, and against the two
gaps that stand between them. This is the working paper behind the IPS item in roadmap
[9.3](roadmap.md#93-long-term); the decisions themselves stay with the owner, and this
page is the basis for making them.

Everything asserted about the IPS here was read off **HL7 International Patient Summary
Implementation Guide v2.0.1 (STU 2)**, package `hl7.fhir.uv.ips#2.0.1`, based on FHIR
R4 4.0.1, generated 2026-06-19 and marked "the current published version". Where an
element's cardinality is stated, it is stated because in these decisions the
cardinality is the argument.

## The short version

An IPS is not blocked by anything technical. It is blocked by two things nobody has
said yet: **which tracked entity attribute is a person's name, birth date, and sex**,
and **which DHIS2 data elements belong in which IPS section**. Neither is a fact DHIS2
holds; both are per-instance nominations. Until an owner states them, the honest IPS
this toolchain can build is a valid document with a data-absent name, a data-absent
birth date, and three required sections carrying an empty reason - which the IG
explicitly permits and explicitly says is not conformance with the Creator actor.
Whether that document is worth serving at all is the sharpest question this paper
reserves.

## 1. How to use this document

This paper tees up five owner calls, listed in full in section 10: the identity
nominations that fill `Patient.name` / `birthDate` / `gender`, where section mappings
come from, what the serving surface is called, whether a summary with no mapped
clinical section may be built at all, and in what order the three phases land. It is a
decision document, not a plan of record - the recommendation in
section 9 is a recommendation. It rests throughout on **the record the facade serves**:
a summary is a projection of a record, and `GET /tracked-entities/{uid}/events` is
where that record is read - one entity's events, each as the response its programme
stage's published form describes (section 3).

## 2. What an IPS is

An IPS is one FHIR **document**: a `Bundle` whose first entry is a `Composition` and
whose remaining entries are the resources that `Composition`'s sections point at.
`Bundle-uv-ips` fixes `type` to `document`, requires `identifier` and `timestamp`
(1..1 each), requires at least two entries with `entry:composition` 1..1 and
`entry:patient` 1..1, forbids `entry.search` / `entry.request` / `entry.response`
(0..0), and carries the invariant `bdl-ips-1`: an IPS document has no `Composition`
besides the first.

`Composition-uv-ips` pins `type` to the LOINC pattern `60591-5` ("Patient summary
Document"), constrains `subject` to **1..1 `Reference(Patient-uv-ips)`**, and sets
`section` to **3..\*** with `section.title`, `section.code`, and `section.text` all
1..1 on every section present and `section.section` 0..0 - the section model is flat.

Sixteen sections are defined. The IG states the requirement level as an **obligation on
the Creator actor** rather than as prose, which makes the inventory unambiguous:

| Section | LOINC | Cardinality | Creator obligation | Level |
| --- | --- | --- | --- | --- |
| Problems | `11450-4` | 1..1 | `SHALL:populate` | required |
| Allergies and Intolerances | `48765-2` | 1..1 | `SHALL:populate` | required |
| Medication Summary | `10160-0` | 1..1 | `SHALL:populate` | required |
| Immunizations | `11369-6` | 0..1 | `SHOULD:populate-if-known` | recommended |
| Results | `30954-2` | 0..1 | `SHOULD:populate-if-known` | recommended |
| History of Procedures | `47519-4` | 0..1 | `SHOULD:populate-if-known` | recommended |
| Medical Devices | `46264-8` | 0..1 | `SHOULD:populate-if-known` | recommended |
| Advance Directives | `42348-3` | 0..1 | none on the Creator | optional |
| Alerts | `104605-1` | 0..1 | none on the Creator | optional |
| Functional Status | `47420-5` | 0..1 | none on the Creator | optional |
| History of Past Problems | `11348-0` | 0..1 | none on the Creator | optional |
| History of Pregnancy | `10162-6` | 0..1 | none on the Creator | optional |
| Patient Story | `81338-6` | 0..1 | none on the Creator | optional |
| Plan of Care | `18776-5` | 0..1 | none on the Creator | optional |
| Social History | `29762-2` | 0..1 | none on the Creator | optional |
| Vital Signs | `8716-3` | 0..1 | none on the Creator | optional |

**The absent-and-unknown mechanism, stated precisely, because it is the thing this
project most needs to get right and the thing most likely to be remembered wrong.**
The IG's *Empty Sections and Missing Data* page (page standards status: Informative)
gives three separate rules:

1. **A required section with no entry.** `Composition.section.emptyReason` SHALL be
   populated - the invariant `ips-comp-1` on each of the three required slices reads
   "Either section.entry or emptyReason are present". The IG names `unavailable` and
   `notasked` as the codes generally wanted, from R4's own `list-empty-reason` value
   set. A non-required section may instead simply be omitted.
2. **The `absent-unknown-uv-ips` code system is gone.** In the IG's words: "Prior
   versions of the IPS implementation guide had included a code system for no known
   data assertions, this code system has been removed from the guide and is no longer
   recommended for use." Known absence is now *asserted* with an ordinary resource
   carrying an exceptional concept from the profile's own primary code binding - a
   SNOMED CT no-known-allergy code on an `AllergyIntolerance`, or SNOMED CT
   `1287211007` "No information available" as the general form.
3. **A required data element with no value.** The data-absent-reason extension,
   `http://hl7.org/fhir/StructureDefinition/data-absent-reason`, on the element itself.
   The IG's worked example is `Patient._birthDate` carrying `valueCode "unknown"`,
   which is exactly the case section 4 lands on.

And the sentence that decides how much of this paper is even a problem:

> A system creating an IPS that can never populate data in a section marked with the
> SHALL:populate obligation (i.e. Allergies, Problems and Medications) can produce
> valid IPS Bundle instances, although it cannot comply with the Creator (IPS) actor
> obligations.

So a summary built from an instance with nothing to say about allergies is **valid**
and **not conformant as a Creator**. Those are two claims, and this project has to be
able to make each separately.

**The serving surface already has a name upstream.** `OperationDefinition/summary`
(code `summary`) is defined on `Patient`, at instance level
(`[base]/Patient/[id]/$summary`) and type level (`[base]/Patient/$summary`, where "the
requestor SHALL provide an identifier"), with an optional `profile` input and a
`Bundle` output. The IPS Server CapabilityStatement declares exactly one operation on
exactly one resource: `summary` on `Patient`.

## 3. What this toolchain can honestly supply today

**The register projection publishes identity and refuses to publish anything else.**
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/register/projection.py` states the
doctrine in its own module docstring: `Patient.name`, `Patient.gender`, and
`Patient.birthDate` "are the elements every FHIR client reaches for first, and none of
them is filled in, because DHIS2 has no first-name attribute, no sex attribute, no
date-of-birth attribute. A server that matched on attribute names would be inventing a
semantic mapping and publishing it as fact." What it does carry:

- `id` is the DHIS2 tracked entity UID, so `{resourceType}/<uid>` reads it back.
- `identifier[]` opens with that UID under `{base}/id/tracked-entity`, then one entry
  per value of an attribute DHIS2 declares **unique**, under
  `{base}/tracked-entity-attribute/{uid}` (`foundation/tracked_entity_attribute_values.py`).
- `meta.tag` states the tracked entity type under `{base}/id/tracked-entity-type`.
- `extension[]` carries every remaining attribute value on the
  `D2TrackedEntityAttributeValue` extension - the attribute's UID, the DHIS2 code where
  the instance set one, and the value as the string DHIS2 sent. Untyped on purpose.

Which resource each tracked entity type is served as comes from the published
`D2TET_CM` map, `Patient` being the default and eight other types legal
(`r4/schemas.py`, `DEFAULT_SUBJECT_RESOURCE_TYPE`). The register is dispatched from the
generic read router as `GET /{ResourceType}/{uid}`, `GET /{ResourceType}?identifier=`,
and a paged listing, all gated by `[serve.tracked_entities]` (`config.py`,
`TrackedEntitiesConfig`) and refused with `RegisterDisabledError` /
`NoPublishedSubjectTypeError`.

**The history surface is what an IPS section reads from, and it is served.**
`GET /tracked-entities/{uid}/events` answers one entity's own events - every event of
every enrollment it holds, newest first - each as the `QuestionnaireResponse` its
programme stage's published form describes: the stage's canonical as `questionnaire`,
the entity as `subject`, the enrollment and the reporting unit as extensions, the
event's own instant as `authored`, and one item per data value carrying the codes this
guide publishes. The read is entity-scoped throughout, which is what R3 asks of it -
one read of the tracked entity per request, the events nested under the enrollments
they belong to, no program ever named (BUGS.md 72 and 91) and no organisation-unit
scope (BUGS.md 69). What the record does not carry is a clinical vocabulary: an item's
coding is a DHIS2 option in this guide's own CodeSystem, so a section's semantics still
come from a mapping somebody writes. `dhis2w_fhir_serve.history` is the module; a stage
the guide publishes no form for is counted and named rather than served as something
else.

**The semantic layer stops one step short of clinical vocabulary.** ConceptMaps and
`$translate` ship for option sets (`D2OS_<stem>_CM`), categories (`D2CAT_<stem>_CM`),
attribute option combos, and tracked entity types (`D2TET_CM`) - and every one of them
maps a DHIS2 code onto **another DHIS2 identifier**. Roadmap 9.3 states the missing
piece plainly: option-to-SNOMED/LOINC mappings "need a source that does not exist yet".
An IPS section is a clinical claim in an international vocabulary, so this is the gap
that matters, not the maps that ship.

**The enrollment resource is recommended and not ratified.** `EpisodeOfCare` for
`Patient`-subject enrollments is the recommendation of
[the enrollment resource](enrollment-resource.md); decision
[5.2](roadmap.md#52-the-tracker-shape) is the owner's and is open. An IPS does not
strictly need it - `Composition.encounter` is 0..1 and IPS constrains nothing about
episodes - so this is a sequencing input, not a blocker.

## 4. The identity gap

`Patient-uv-ips` requires more of a person than this project publishes about one.

| Element | IPS constraint | What the projection has |
| --- | --- | --- |
| `identifier` | 0..\*, must-support | The tracked entity UID plus every unique attribute value |
| `name` | **1..\***, invariant `ips-pat-1`: `family`, `given`, or `text` SHALL be present | Nothing |
| `birthDate` | **1..1**, must-support | Nothing |
| `gender` | 0..1, must-support | Nothing |
| `telecom`, `address`, `generalPractitioner` | 0..\*, must-support | Nothing |

Two of those are mandatory and neither can be filled without somebody stating which
attribute means what. The IG's own answer for a required element with no value is the
data-absent-reason extension, and it uses `Patient.birthDate` as the worked example -
so **a nameless, birthDate-less IPS Patient is a valid IPS Patient**, and this project
can build one today without touching its doctrine. What it cannot do is make that
document clinically useful: a summary whose subject has no name and no birth date is a
document about an eleven-character identifier.

### The mapping dial

The dial that closes the gap is a new `fhir.toml` table nominating, per instance, which
tracked entity attribute carries which demographic fact, written the way the existing
selection tables are written (see
[What goes in](../301-what-goes-in.md#tracked_entity_types)):

```toml
[ips.identity]
name = "w75KJ2mc4zz"          # First name
family_name = "zDhUuAYrxNC"   # Last name
birth_date = "iESIqZ0R0R0"    # Date of birth
sex = "cejWyOfXge6"           # Gender
```

**In plain words.** Which tracked entity attribute holds a person's name, birth date,
and sex on *this* instance. DHIS2 has no field that means any of these, so if you want
a patient summary that names its patient, you say which attribute it is. **Only UIDs,
never names** - attribute names are not unique in DHIS2 and change without notice, and
the guide already publishes the names it reads off the instance as `D2TEA_CS`.

**Value-shape validation.** At load, the ids are shape-checked like every other
selection table. At startup, each nominated attribute is looked up in the published
`D2TEA_CS` vocabulary and its `value-type` property checked against what the FHIR
element accepts: `birth_date` demands a DHIS2 `DATE`, `sex` demands `TEXT` with an
option set, `name` and `family_name` demand `TEXT`. A nomination that fails refuses the
run, naming the key and the value type it found - the failure mode
`[generate.tracked_entity_types]` already has for an unknown resource type.

**Honest failure per person, not per instance.** A nominated attribute the instance
holds no value for on *this* person is neither an error nor a guess: the element carries
the data-absent-reason extension with `unknown`, exactly as the IG's example does. An
instance-wide nomination is a statement about the attribute, not a promise about every
row.

**`sex` needs a second nomination.** DHIS2's answer is an option code from an option
set; `Patient.gender` is bound to R4's `administrative-gender` (`male | female | other |
unknown`) with a **required** binding, so the option-to-code step is a ConceptMap, not a
rename. It is the smallest possible instance of the missing clinical-vocabulary source
in section 3, and worth solving here first precisely because it is four codes rather
than forty thousand.

### The alternative, and what each costs

| | Nominate through `[ips.identity]` | Nominate nothing, refuse to build |
| --- | --- | --- |
| Doctrine | Intact - the mapping is the instance's statement, not the server's inference | Intact |
| Config surface | One table, four keys, two validators | None |
| An instance that nominates nothing | A valid summary, data-absent name and birth date | No summary at all |
| Failure mode | Per-person absence, stated in-band | An error naming the missing table |
| Risk | An owner nominates the wrong attribute and a wrong name ships as fact | None |

The wrong-attribute risk is the honest objection to the dial, and it is the risk
`[generate.tracked_entity_types]` already carries. The difference is that a wrong
resource type is visible in the published guide, while a wrong name is visible only to
the clinician reading the summary.

## 5. The section gap

A DHIS2 data element carries a name, a value type, an optional option set, an optional
code, and membership in groups. It carries **no statement that its values are
allergies, or problems, or immunisations**. There is no field to read, no convention to
mine, and no published vocabulary that would answer the question - the maps this
project ships translate DHIS2 codes back to DHIS2 identifiers (section 3), which is the
wrong direction for a section assignment.

So the section content of an IPS is not derivable. It is stated, or it is absent. That
is the no-invented-clinical-content rule the roadmap already names, and its consequence
is worth writing down before any option is weighed: **content this project cannot place
never appears in the summary.** An unmapped stage does not become a free-text
Observation, does not become a `Patient Story` narrative, and does not get swept into
`Results` on the grounds that it was numeric. A required section with nothing mapped
carries `emptyReason` per section 2's rule 1; any other section with nothing mapped is
omitted entirely.

Three sources could carry a mapping, and they are not mutually exclusive.

**Option A - a `fhir.toml` mapping table.** The instance's own operator names the
mapping, keyed by program stage or by data element, valued by the IPS section:

```toml
[ips.sections]
"A03MvHHogjR" = "Immunizations"     # Child Programme - Birth
"ZzYYXq4fJie" = "Immunizations"     # Child Programme - Baby Postnatal
"GieVkTxp4HH" = "Results"           # Height in cm
```

Cheap, legible, offline-checkable, and honest about who is making the claim. Its cost
is that it is per-instance and unshared: ten country guides mapping the same WHO
immunisation schedule write the same table ten times, and nobody can tell whether they
agree.

**Option B - IG-published ConceptMaps.** The section assignment ships as terminology in
the generated guide, the way `D2TET_CM` already ships the resource each tracked entity
type is published as: a map from the data-element CodeSystem onto the IPS section LOINC
codes, resolvable by any consumer over `$translate` without holding `fhir.toml`. This is
the shape the semantic layer already has, and it is the only one that composes across
guides - which is what
[harmonization across country guides](harmonization.md) would need. Its cost is that a
ConceptMap has to be *authored from something*, and the something is either option A or
the SNOMED/LOINC source roadmap 9.3 says does not exist yet.

**Option C - both, in that order.** `fhir.toml` is the input; the ConceptMap is the
published output. The operator states the mapping once in the file they already edit,
`d2w fhir generate` publishes it beside the vocabularies it maps, and the served
summary reads the map rather than the file - so a consumer can audit the assignment
without seeing the project's config, and the same map is what a cross-instance
comparison would later diff.

**Where the first mapping obviously goes.** The fleet is immunisation-heavy and so is
the seeded instance: `Child Programme` (`IpHINAT79UW`) is a `WITH_REGISTRATION` program
with two non-repeatable immunisation stages, the workspace fixtures add a `VACCINE_TYPE`
option set with five fixed-id options and a `SNOMED_CODE` attribute
(`docs/local-setup.md`), and the aggregate demo data set is an immunisation data set.
`Immunization-uv-ips` is also the least demanding of the clinical profiles: `status`,
`vaccineCode`, `patient`, and `occurrence[x]` carry `SHALL:populate-if-known`, and
`vaccineCode`'s binding to `vaccines-uv-ips` is **preferred**, not required - so a dose
recorded against a DHIS2 option can be published with the DHIS2 coding while the
international coding is still missing, without violating the profile. WHO's own ICVP
guide derives its digital vaccine certificate profile from `Immunization-uv-ips`,
corroborating that this is the section a health-programme instance fills first.

## 6. Section by section

Three verdicts, one per row.

| Verdict | Meaning |
| --- | --- |
| `FEEDABLE NOW` | DHIS2 states the facts structurally - dates, statuses, references - so a projection fills it with nobody stating a vocabulary. |
| `WITH A MAPPING` | DHIS2 may hold the facts, but only an owner-stated mapping says which of them belong here. |
| `HONESTLY EMPTY` | DHIS2 holds nothing of the kind. Required means `emptyReason`; anything else means the section is omitted. |

| Section | Level | What a DHIS2 tracker instance could feed it | Verdict | Why |
| --- | --- | --- | --- | --- |
| Problems | required | Data elements or attributes recording a diagnosis or condition, per stage | `WITH A MAPPING` | DHIS2 has diagnosis elements everywhere and marks none of them as such; `Condition.code` also needs a clinical vocabulary this project has no source for |
| Allergies and Intolerances | required | Almost always nothing | `HONESTLY EMPTY` | Allergy capture is rare in DHIS2 tracker programs, and a mis-mapped allergy is the single most dangerous wrong answer a summary can carry |
| Medication Summary | required | Treatment-dispensed elements in a treatment program | `WITH A MAPPING` | The values exist in TB and HIV programs; nothing distinguishes them from any other coded element without a nomination |
| Immunizations | recommended | Dose events in an immunisation program stage, with `occurredAt` as the date | `WITH A MAPPING` | The first and easiest mapping (section 5), and the profile's preferred vaccine binding tolerates a DHIS2 coding |
| Results | recommended | Numeric and coded stage data elements with a `NUMBER` or option-set value type | `WITH A MAPPING` | Value types make an `Observation` shape derivable; only a nomination makes it a *result* rather than a programme indicator input |
| History of Procedures | recommended | Procedure-shaped stage events | `WITH A MAPPING` | Same argument as Problems, with the same missing vocabulary |
| Medical Devices | recommended | Nothing on a person | `HONESTLY EMPTY` | Devices are a tracked entity *type* in DHIS2, not an attribute of a person; nothing links a fridge to a patient |
| Advance Directives | optional | Nothing | `HONESTLY EMPTY` | No DHIS2 concept corresponds; a `Consent` resource has no DHIS2 source |
| Alerts | optional | Nothing | `HONESTLY EMPTY` | The nearest DHIS2 mechanism is a program rule, which is a definition-side artifact about forms, not a `Flag` about a person |
| Functional Status | optional | Assessment-scale data elements | `WITH A MAPPING` | Only where a program collects one, and only if somebody says which |
| History of Past Problems | optional | Same elements as Problems, in a closed enrollment | `WITH A MAPPING` | The past/current split is a second decision on top of the Problems mapping, and DHIS2 states neither |
| History of Pregnancy | optional | Antenatal program enrollment and its visit events | `WITH A MAPPING` | An antenatal enrollment is strong evidence of pregnancy status, but `Observation.value` needs a coded answer nobody has nominated |
| Patient Story | optional | Nothing | `HONESTLY EMPTY` | Free narrative is exactly the content the no-invented-clinical-content rule forbids synthesising |
| Plan of Care | optional | Scheduled tracker events: a stage, a `scheduledAt` date, status `SCHEDULE` | `FEEDABLE NOW` | The only structural plan DHIS2 states - it needs no vocabulary, just the event read. But `CarePlan` is reserved for the `PlanDefinition` / `$apply` line by decision 5.2, so filling this section is a call, not a freebie |
| Social History | optional | Smoking and alcohol elements where a program collects them | `WITH A MAPPING` | The IPS slices are two specific LOINC-coded observations, so this is a two-element nomination rather than a general mapping |
| Vital Signs | optional | Height, weight, blood pressure elements | `WITH A MAPPING` | The most mechanical mapping after immunisations, and the one where a wrong unit is the hazard rather than a wrong code |

**The finding.** Fifteen of sixteen sections need an owner-stated mapping or are
honestly empty, and the sixteenth is a resource this project has reserved for something
else. **There is no section a DHIS2 instance fills by itself.** That is not a defect in
DHIS2 and not a defect in the IPS - it is what it means that DHIS2 is a data collection
platform and the IPS is a clinical vocabulary. It does mean that the first IPS this
project builds is entirely a function of what an owner writes down, which is why
section 10's decisions are not deferrable niceties.

## 7. What the neighbours did

The survey is thin, and thin in an informative way: the projects nearest to this one
have all reached the same conclusion, which is that generating an IPS is somebody
else's engine plus a local mapping.

**OpenMRS has a roadmap and no shipped generator.** The
[International Patient Summary Support in OpenMRS](https://openmrs.atlassian.net/wiki/spaces/docs/pages/169869313/International+Patient+Summary+Support+in+OpenMRS)
page splits the work into MVP 1 - *ingest and display* an IPS somebody else made, with
human adjudication assumed - and MVP 2 - generate one from OpenMRS data, explicitly "in
collaboration with HAPI for IPS generation". It records data-model gaps rather than a
mapping methodology ("Meds summary needs to be done - REQUIRED MVP 2"). So the nearest
precedent put *consumption* first and outsourced *generation*.

**HAPI FHIR is the engine everyone points at.** Its
[IPS generator](https://hapifhir.io/hapi-fhir/docs/server_jpa/ips.html) implements
`$summary` over stored resources through an `IIpsGenerationStrategy`, with
`DefaultJpaIpsGenerationStrategy` defining the sections and per-section narrative
templates fed a Bundle of the matched resources. It presumes the resources already
exist as FHIR, which is precisely the step this project does not have - and it is why
"use HAPI" is not an answer here.

**WHO builds *on* the IPS profiles rather than beside them.** The SMART ICVP guide's
digital vaccine certificate profile
(`http://smart.who.int/icvp/StructureDefinition/Immunization-uv-ips-ICVP`, v0.3.0)
derives from an `Immunization-uv-ips` chain rather than from base R4. For a project
that values SMART Guidelines alignment as a pattern to match, that is the strongest
available signal about which section to map first.

No DHIS2-side prior art was found. The archived DHIS2 FHIR adapter published
`Immunization` as a transformation target but no `Composition` and no document.

## 8. The requirement set

What any accepted design must satisfy, derived from what this repository already does.

**R1 - Honest absence, in the IG's own mechanisms.** No invented name, no invented
birth date, no invented clinical content. Absence is stated the way the IG states it:
data-absent-reason on a required element, `emptyReason` on a required section with no
entry, omission everywhere else. The removed `absent-unknown-uv-ips` code system is not
used.

**R2 - Owner-stated mappings only.** No attribute-name matching, no heuristic on value
types, no "looks like a diagnosis". Every clinical claim in a served summary traces to
a line somebody wrote in `fhir.toml` or to a map published in the guide.

**R3 - Entity-scoped reads throughout.** Every read behind a summary is scoped to one
tracked entity, per the owner-aware discipline BUGS.md 69 forces and the program-scoped
read BUGS.md 72 forbids. A summary is never assembled from a bulk export filtered
client-side.

**R4 - Deterministic regeneration.** Two `$summary` calls against an unchanged instance
produce byte-identical documents apart from `Bundle.timestamp` and `Composition.date` -
sections in a fixed order, entries in a fixed order, ids derived from DHIS2 identifiers
rather than minted per request. The register projection already holds this line, and
the emitters order the registry by `path` for the same reason.

**R5 - Valid without conformance, and able to say which.** The document validates
against `Bundle-uv-ips` and `Composition-uv-ips` in every case the toolchain will
serve, including the all-empty one. Whether it also claims the Creator (IPS) actor's
obligations is a separate, reportable fact the toolchain states rather than leaving a
reader to work out.

**R6 - Served through the facade at a discoverable operation.** Reachable without a
client learning a route this project invented, and declared in the
`CapabilityStatement`. The strawman is `$summary` on the register resource type -
`GET /{RegisterType}/{uid}/$summary` - because the IG defines `$summary` on `Patient` at
both instance and type level and declares it in the IPS Server CapabilityStatement, so a
client that speaks IPS already knows the name. **The naming is the owner's**: the
register serves nine resource types, and `$summary` on a `Specimen` or a `Location` is
either a refusal, a different operation, or a reason to scope the operation to
`Patient`-subject types alone.

**R7 - Gated and additive.** Offered or withheld by a `fhir.toml` key and refused with a
typed `ServeError` naming that key, in the manner of `RegisterDisabledError` and
`NoPublishedSubjectTypeError`; and no change to the capture contract, to the register
projection's published shape, or to anything already published. A summary is a new read
over reads that already exist.

**R8 - Plain R4 plus the published IPS profiles.** `hl7.fhir.uv.ips#2.0.1` as a
vocabulary to conform to, not a dependency the generated country guide takes on. Live
serve mode publishes no StructureDefinitions and resolves none; a validator run against
the IG is a test, not a runtime.

## 9. Recommendation

**Recommendation, in three phases, smallest first.** Each phase is independently
useful and none of them is a prerequisite for reversing an earlier one.

**Phase 1 - the identity dial, alone.** Ship `[ips.identity]` with its value-shape
validation and per-person data-absent failure, and let it fill `Patient.name`,
`Patient.birthDate`, and `Patient.gender` **on the register projection**, before any IPS
exists. It goes first because it is the only phase with a customer today: the register
already serves `Patient` resources a FHIR client cannot use to recognise a person, and a
nominated name fixes that whether or not a summary is ever built. It also front-loads
the riskiest owner decision and is the only phase that exercises the
option-to-`administrative-gender` ConceptMap the whole clinical-vocabulary line needs.

**Phase 2 - the immunisation section, as the first and only mapped section.** The
history surface serves the events it reads: ship `[ips.sections]` restricted to `Immunizations`,
publish the mapping as a ConceptMap beside the vocabularies it maps (option C in
section 5), and serve a document whose three required sections all carry `emptyReason`
and whose one recommended section carries real doses. Small, honest, demonstrably valid,
and the shape the fleet's programmes actually have.

**Phase 3 - the rest, mapping-driven and unranked.** Every further section arrives the
same way: an owner writes a mapping, the generator publishes it, the projection reads
it. No section is built into the code. `Results`, `Vital Signs`, and `Problems` are the
likely order on the fleet as it stands.

**What this recommendation deliberately does not do.** It does not claim
`Plan of Care` from scheduled events, because that spends `CarePlan` on a fact decision
5.2 has not finished allocating. It does not attempt `Allergies` at all. And it derives
no section assignment from anything DHIS2 says about itself.

**What would change this answer.** A published source mapping DHIS2 option codes onto
SNOMED CT or LOINC - the thing roadmap 9.3 says does not exist - would move most of
section 6's `WITH A MAPPING` rows from per-instance nomination to shared terminology,
making phase 3 a generation problem rather than a configuration one. If that source
appears, option B in section 5 wins outright.

## 10. Owner decisions this paper reserves

- **The `[ips.identity]` nominations.** Whether the identity dial exists at all; if it
  does, its key names, whether `sex` is nominated separately from its option-to-code
  map, and whether a family/given split is nominated or a single `text` name is enough
  for `ips-pat-1`.
- **The section mapping source.** `fhir.toml` alone, IG-published ConceptMaps alone, or
  both with the file as input and the map as output (section 5, options A / B / C).
- **The serving surface and its name.** `$summary` on the register resource type is the
  strawman; whether it is scoped to `Patient`-subject types, what it does for the other
  eight, whether type-level `$summary?identifier=` is offered alongside the instance
  form, and what the `fhir.toml` key that gates it is called.
- **Whether an IPS with no mapped clinical section may be built at all.** The IG says
  such a document is valid and is not Creator-conformant. This project can refuse to
  serve it, serve it with a stated caveat, or serve it silently. This is a doctrine
  call, not a technical one.
- **Sequencing.** The record this paper reads from is served, so the phases are free
  to land in any order. Phase 1 needs no record at all, and phase 2 needs the section
  mappings rather than a further read.

## See also

- [FHIR roadmap and review guide](roadmap.md) - the IPS item in 9.3, which this page
  narrows.
- [Consume the FHIR API](../401-consume-the-fhir-api.md) - the record at
  `/tracked-entities/{uid}/events`, which is what a section is fed from.
- [The enrollment resource](enrollment-resource.md) - decision 5.2, whose recommended
  `EpisodeOfCare` is the shape a summary's episodes would hang off.
- [DHIS2 fidelity audit](dhis2-fidelity.md) - what the guide carries about a data
  element, which is the whole of what a section mapping has to work from.
- [Harmonization across country guides](harmonization.md) - why a published mapping
  beats a per-instance one.
- [What goes in: the selection tables](../301-what-goes-in.md) - the style the
  proposed `[ips]` tables are written in.
- [Glossary](../glossary.md) - the register, tracked entity attributes, and the
  extensions that carry them.
