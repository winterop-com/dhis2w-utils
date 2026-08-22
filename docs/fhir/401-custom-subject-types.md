# Custom subject types

**Who this is for:** the integration developer or project author whose DHIS2
tracker programs follow things that are not people - herds, water points,
vehicles, lab samples - and who needs the published FHIR to say so.

**Before you start:** [The capture contract](401-capture-contract.md), for
where a tracker response's subject lives and how it is identified.

**You will be able to:**

- map a DHIS2 tracked entity type onto the FHIR resource type it really is
- predict every artifact that one mapping changes
- read the union rule the two tracker response profiles publish under
- know what a running facade checks about a subject's type, and when

## What a tracked entity type is

DHIS2 tracks people most of the time, and buildings, herds, water points,
vehicles, and lab samples the rest of the time - all through the same
registration-and-stages shape. The *tracked entity type* is the DHIS2 object
that owns the nature of the thing being tracked; every tracker program
declares one. FHIR, by contrast, says what a thing is through its resource
type - and a `QuestionnaireResponse` about a vaccination visit for a
livestock herd whose `subject` claims to be a `Patient` is simply wrong.

`[generate.tracked_entity_types]` in `fhir.toml` is where the two meet: it
maps a tracked entity type UID onto the FHIR resource type its registrations
are about.

```toml
[generate.tracked_entity_types]
"Kd6Nk9wnAJa" = "Group"       # a livestock herd tracked through a vaccination programme
"Bx8L1nQ4EiP" = "Location"    # a water point tracked through a maintenance programme
```

The key is the tracked entity type, **not the program**: the type owns the
nature of the thing, so two programs tracking the same type agree by
construction and neither can be configured into disagreeing with the other.
Selecting the programs is still `[generate.tracker_programs]`' job - naming
a type here selects nothing.

A type this table never mentions is a `Patient`. A project that tracks
people configures nothing here, and everything it generates is what it would
have generated without the table at all.

On an instance with many types that default is worth checking rather than
assuming, so `d2w fhir validate` prints the list: one row per tracked entity type
the instance holds that this table does not name, carrying the UID, the name the
instance holds, and the line that would type it. A fifty-type instance gets a
fifty-row checklist instead of silence.

## One entry feeds every artifact that has to say so

- `Questionnaire.subjectType` on the program's registration form **and** on
  every stage form of that program - a stage captures a visit by the very
  entity the registration enrolled, so the two cannot disagree.
- `subject.type` on the generated example responses, and on whatever
  `$generate` mints when the compiled form is served.
- The reference targets the two tracker response profiles admit (next
  section).

## The admitted types

The value must be one of a deliberate subset of R4's resource types - the
types a longitudinal DHIS2 record is plausibly kept about, declared as
`SUBJECT_RESOURCE_TYPES` in `dhis2w_fhir.r4`:

| Resource type | A tracked entity it fits |
| --- | --- |
| `Patient` | the default - a person in care |
| `Person` | a person outside a care relationship |
| `Practitioner` | a health worker |
| `RelatedPerson` | a caregiver or family member |
| `Group` | a herd, a household, a cohort |
| `Device` | a vehicle, a fridge, equipment |
| `Location` | a water point, a building |
| `Organization` | a facility as an administrative thing |
| `Specimen` | a lab sample |

Anything else is refused when `fhir.toml` is read, naming the entry and
listing what it could have been - a typo here would mis-type every form of
every program tracking that type:

```
tracked entity type Kd6Nk9wnAJa is mapped to 'Herd', which is not a FHIR resource
type a tracked entity is published as: name one of Patient, Person, Practitioner,
RelatedPerson, Group, Device, Location, Organization, Specimen
```

For comparison, the non-tracker kinds need no table: an aggregate or event
form is reported *for a place*, so `FORM_KIND_PROFILES` pins their
`subjectType` to `Location` outright, and only the two tracker kinds default
to `Patient` and read this mapping.

## The union rule the profiles publish

A response profile is published once for the whole IG, so it cannot pin the
subject type of one program. `D2TrackerRegistrationResponse` and
`D2TrackerEventResponse` therefore admit the **union** of `Patient` and
every type the table names:

- a project that maps nothing publishes `subject only Reference(Patient)`,
  exactly as it would have without the table;
- the herd-and-people project above publishes
  `subject only Reference(Patient or Group or Location)`.

`Patient` is always in the union - a tracked entity type the project maps to
nothing is a `Patient` - and the published order is the declaration order of
`SUBJECT_RESOURCE_TYPES`, not the order entries were written in `fhir.toml`,
so regenerating an unchanged project publishes unchanged bytes.

Which type a given form's responses actually carry is pinned by that form's
own `subjectType`; the union on the profile is only as wide as the project's
configuration made it. Whatever the type, the subject is identified the same
way - `subject.identifier` under `{base}/id/tracked-entity`, carrying the
DHIS2 UID - because the guide publishes no instances of any of these types.
A herd is as logical a subject as a person.

## Two types, one resource

Nothing says a project maps two types onto different resources. A cold-chain
fridge and a delivery vehicle are both a `Device`; two sample types are both a
`Specimen`. What that becomes when the guide is served is one rule:

**One FHIR resource type is one register serving the union of its tracked entity
types.** `GET /Device` searches, lists, and counts the fridges and the vehicles
together, in the order the guide registers them. Nothing collides, nothing is
refused, and neither type overwrites the other - the published map is read into
one row per type, and the register groups the rows by resource.

Each resource still says which DHIS2 type it is. `meta.tag` carries the tracked
entity type UID under `{identifier_system_base}/id/tracked-entity-type`, which
is R4's own element for classifying a resource, so a page holding both kinds is
a page where every row states which kind it is. `/metadata` states it ahead of
the request too: the register's entry names every tracked entity type behind it.

To ask that register about one of its types, search `_tag` - R4's token search
over exactly the element the type is stated in:

```
GET /Device?_tag=http://dhis2.org/fhir/id/tracked-entity-type|TetFridge01
GET /Device?_tag=TetFridge01
```

It narrows the listing, the identifier search, and the `_count=0` count alike,
and it rides the listing's own `next` and `previous` links so a walk stays inside
the type it started in. See
[The register](301-serving.md#tracked_entities-many-types) for the paging detail
and the fifty-type checklist.

The capture side needs no rule of its own: two types mapped to one resource are
two forms declaring the same `subjectType`, and each form still carries its own
tracked entity type identifier - so `$generate` types both subjects `Device`
while `d2w fhir forward` files each registration under the DHIS2 type its form
names.

## What a running facade checks

The server reads the declared type off the compiled Questionnaire and
nowhere else - `fhir.toml` is the generator's input and never reaches a
running facade. A response typing its subject as something else - a
`Patient` sent to a form asking for a `Group` - is a warning by default and
a 422 under `--strict-codes`, the same dial that grades coded answers
([Serve the guide](201-serve.md#coded-answers-lenient-by-default)).
`Reference.type` is optional in R4 and the profile asks for the subject by
identifier, so a response that carries no type at all is complete, and
nothing is checked.

Next: [Regeneration and hand-authoring](401-regeneration-and-hand-authoring.md)
- which files a re-run owns and where hand-written content lives.
[The capture contract](401-capture-contract.md) covers the rest of what a
tracker response carries.
