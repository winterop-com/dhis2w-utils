# FHIR for DHIS2 people

A primer on every FHIR concept this toolkit uses, written for someone who knows
DHIS2 - data elements, org units, option sets, tracker - and has never touched
FHIR. Read this once and
[FHIR IG generation with `d2w fhir`](fhir-ig.md) reads as a guide rather than as
a glossary. Depth lives in the linked specification pages; this page says what
each term means, what it is closest to in DHIS2, and what `d2w fhir` does with it.

## The shape of FHIR

### Resources, elements, and R4

FHIR is a health-data exchange standard built out of **resources**: around 145
named document shapes - `Patient`, `Organization`, `Location`, `Questionnaire`,
`CodeSystem` - each with a fixed set of typed **elements**, served over REST at
`/<ResourceType>/<id>` and travelling as JSON. A resource type is close to a DHIS2
metadata class and a resource is close to one object of it, with the same
REST-and-JSON feel as `/api/dataSets/<uid>`. **R4** is FHIR Release 4, the widely
deployed version, and the one this toolkit targets throughout - the models live in
`dhis2w_fhir/r4/`, and the scaffolded project publishes JSON only, because XML and
Turtle would add a file and a rendered page per resource for content everything
reads as JSON anyway.

Further reading: [FHIR R4](https://hl7.org/fhir/R4/),
[the resource list](https://hl7.org/fhir/R4/resourcelist.html).

### `id` versus `identifier`

Every resource has an `id`: the token it is served under, unique within one server
and meaningless outside it. Separately, most resources carry `identifier` - a
repeating element of `{system, value}` pairs holding the business identifiers the
object is known by elsewhere. The distinction is exactly DHIS2's **UID versus
code**, with one addition: FHIR insists the system travels with the value, because
`"HIV001"` alone is ambiguous and
`http://dhis2.org/fhir/id/data-set-code` + `"HIV001"` is not.

This toolkit exposes **both** DHIS2 identifiers wherever FHIR gives it a slot -
`{base}/id/<kind>` for the UID, `{base}/id/<kind>-code` for the DHIS2 code - and
uses the bare UID as the resource `id`, so `Location/ImspTQPwCqd` reads straight
back to the instance.

Further reading: [Resource.id](https://hl7.org/fhir/R4/resource.html#id),
[the Identifier datatype](https://hl7.org/fhir/R4/datatypes.html#Identifier).

### References, including the ones that do not resolve

One resource points at another through a `Reference`. The usual spelling is a
**literal reference** - `"reference": "Location/ImspTQPwCqd"` - which a client can
fetch. But a Reference may instead carry `identifier` and no `reference` at all:
a **logical reference**, naming the thing unambiguously by business identifier
while admitting this server holds no such resource. DHIS2 has no real analogy,
because DHIS2 objects always live in one database; the closest feeling is a UID
pointing at an object in a different instance.

The toolkit uses both. An aggregate or event response's `subject` is a literal
`Reference(Location/<uid>)` into the published registry. A tracker event's is a
logical `Patient` reference - `subject.type = "Patient"`, `subject.identifier.system`
fixed to `{base}/id/tracked-entity`, no `reference` element - because the guide
publishes no `Patient` instances and the tracked entity lives in DHIS2.

Further reading: [References between resources](https://hl7.org/fhir/R4/references.html).

### Canonical URLs

Definitional resources - profiles, extensions, CodeSystems, ValueSets,
Questionnaires - each carry a `url`, their **canonical URL**. It is a globally
unique name, not an address: nothing has to be reachable at
`http://dhis2.org/fhir/CodeSystem/x`. It identifies the artifact so two guides
cannot collide and a binding can name one exactly. The DHIS2 analogy is a UID that
happens to look like a URL - an opaque unique handle - except that a URL is unique
across every FHIR guide on earth, which a UID is not.

Every IG picks a **canonical base** and hangs its artifacts off it. Here that is
`[ig] canonical` in `fhir.toml`, so a generated Questionnaire's `url` is
`<canonical>/Questionnaire/<stem>`, where the stem is the identity stem
`[generate.naming] source` resolves - the DHIS2 id by default. The separate `identifier_system_base` (default
`http://dhis2.org/fhir`) is the base for the DHIS2 *identifier systems* rather than
for artifacts; the two are configured independently.

Further reading: [Canonical URLs](https://hl7.org/fhir/R4/references.html#canonical).

### What an Implementation Guide is

Raw FHIR is deliberately under-specified: it says what a `Questionnaire` may
contain, not what your programme's forms look like. An **Implementation Guide** is
the published document that closes that gap - profiles, extensions, terminology,
examples, and prose, compiled into a website and a downloadable package, saying
"here is how FHIR is used *here*". DHIS2 has no equivalent artifact; the nearest
thing is a metadata package plus its documentation.

That is why this toolkit generates one. `d2w fhir generate` reads a DHIS2 instance
and writes IG source; the toolchain compiles it into a guide a third party can read
without access to your repository, your DHIS2 metadata API, or you.

Further reading: [ImplementationGuide](https://hl7.org/fhir/R4/implementationguide.html).

## Terminology

### CodeSystem

A `CodeSystem` **defines** codes: it is where concepts are declared, each with a
`code`, a `display`, and optional extras. The DHIS2 analogy is exact - an **option
set is the source of its option codes**, and nothing else may mint them.

This toolkit emits one CodeSystem per DHIS2 option set and one per DHIS2 category,
plus `D2DE_CS` over every data element the generated forms reference, `D2COC_CS`
over every category option combo, `D2OU_Level_CS` over the org-unit levels,
`D2PeriodType_CS`, and `D2FormType_CS`. By default the concept code is the DHIS2
UID; `concept_code_source = "code"` swaps in the DHIS2 code.

Further reading: [CodeSystem](https://hl7.org/fhir/R4/codesystem.html).

### ValueSet

A `ValueSet` **selects** codes: it defines nothing, it composes a selection out of
one or more CodeSystems, and it is a ValueSet - never a CodeSystem - that an
element is bound to. DHIS2 collapses the two, because pointing a data element at an
option set both defines and selects. FHIR splits the roles so one field can draw
from several code systems, or from part of one.

Every CodeSystem this toolkit writes ships with a matching ValueSet, and that is
what a question binds to: an option-set-bound data element becomes an item of
`type = #choice` with `answerValueSet = Canonical(D2OS_<UID>_VS)`.

Further reading: [ValueSet](https://hl7.org/fhir/R4/valueset.html),
[terminology bindings](https://hl7.org/fhir/R4/profiling.html#binding).

### Coding and CodeableConcept

A `Coding` is one coded value: a `system` (the CodeSystem's canonical URL), a
`code`, and usually a `display`. A `CodeableConcept` wraps zero or more Codings
plus free text, for when a concept may be expressed in several vocabularies at
once. The DHIS2 lesson is the one identifiers already taught: an option code is
only unique inside its option set, so FHIR carries the system beside the code
everywhere. In a generated example response, an answer to an option-set-bound
question is a `valueCoding` naming a concept in that set's own CodeSystem - the
very concept code the terminology target wrote, fall-backs included.

Further reading: [Using codes in resources](https://hl7.org/fhir/R4/terminologies.html).

### Concept properties and designations

A CodeSystem concept carries two kinds of extra. A **property** is a typed named
fact, declared once on the CodeSystem and valued per concept. A **designation** is
an alternate rendering of the concept's display - which is where translations go.
DHIS2 has both shapes: the option's other identifier is property-shaped, and
`translations` are designation-shaped.

The toolkit uses properties for the complementary DHIS2 identifier on every concept
(`dhis2-code` in id mode, `dhis2-id` in code mode), plus `level` and `parent` on the
org-unit terminology and `domain` on `D2DE_CS`; each gets a
`<identifier_system_base>/property/<code>` URI so it means something outside this
guide. DHIS2 `NAME` translations become designations where the target is a concept,
and the standard
[translation extension](https://hl7.org/fhir/R4/extension-translation.html) where it
is a title or a name.

Further reading:
[concept properties](https://hl7.org/fhir/R4/codesystem-definitions.html#CodeSystem.property).

### ConceptMap

A `ConceptMap` states a relationship between concepts in two different code systems
- "this code over here means that code over there". It is the FHIR-native place for
a crosswalk, and a terminology server can answer `$translate` from one.

This toolkit publishes one ConceptMap per option set and one per category, each
mapping every generated concept code onto the DHIS2 UID and, where the member carries
one, the DHIS2 code - one group per identifier system. An option-set map answers
"which DHIS2 option is this answer?"; a category map answers "which DHIS2 category
option is this disaggregation?". `d2w fhir serve` answers `$translate` over both, so a
client holding a generated coding can ask the server which DHIS2 identifiers it stands
for instead of reading concept properties itself.

Further reading: [ConceptMap](https://hl7.org/fhir/R4/conceptmap.html), and
[ConceptMaps: the route back to DHIS2](fhir-ig.md#conceptmaps-the-route-back-to-dhis2)
for the emitted shape and the `$translate` calls.

## Constraining and extending

### Profiles

A **profile** is a `StructureDefinition` that narrows a base resource: it raises
minimum cardinalities, forbids elements, fixes values, restricts which resource
types a Reference may point at, and binds a coded element to a ValueSet. It never
invents elements - it only says which of the base resource's elements are
acceptable here.

The honest DHIS2 analogy is the constraint layer DHIS2 already puts over a generic
form: `compulsoryDataElementOperands` make a question mandatory, a `valueType`
restricts what may be entered, an option set restricts it further. None of those
change what a data value *is*; they say which data values are acceptable.

This toolkit generates `D2Organization` and `D2Location` over the registry, and
`D2AggregateResponse` / `D2EventResponse` / `D2TrackerEventResponse` over
`QuestionnaireResponse` - the capture contract. Each response profile pins the
extensions its form kind must carry, requires `questionnaire` and `subject`, and
restricts what `subject` may point at.

Further reading: [Profiling FHIR](https://hl7.org/fhir/R4/profiling.html),
[StructureDefinition](https://hl7.org/fhir/R4/structuredefinition.html).

### Extensions

Because a profile cannot add elements, FHIR carries local data in **extensions**: a
`{url, value[x]}` pair hung off any element, where the `url` is the canonical URL of
a StructureDefinition defining it. A **complex** extension nests sub-extensions
instead of carrying a single value, and every extension declares a `context` - the
element types it may legally hang off.

The DHIS2 analogy is excellent, because DHIS2 solved the same problem the same way:
`attributeValues` is exactly an extension mechanism. FHIR prefers extensions over
custom fields for the reason DHIS2 prefers attributes over forking the schema - a
consumer that does not recognise the URL skips it and still reads the rest.

`d2w fhir` defines five of its own, all in `foundation/`:

| Extension | Carries |
| --- | --- |
| `D2Period` | A DHIS2 reporting period: `iso`, `type`, and the resolved date range. |
| `D2FormType` | Which kind of DHIS2 form this is: `#aggregate`, `#event`, `#tracker-event`. |
| `D2AttributeValue` | One DHIS2 attribute value: `attributeId`, `attributeCode`, `value`. |
| `D2OrganisationUnit` | A reference to the `Location` an event was captured at. |
| `D2TrackerEnrollment` | The DHIS2 enrollment UID, as an `Identifier`. |

`D2Period` exists because a FHIR `Period` is a pair of instants while a DHIS2 period
is a *typed* interval - `202401` is the January instance of `Monthly`, and the type
is what makes it comparable and round-trippable.

Further reading: [Extensibility](https://hl7.org/fhir/R4/extensibility.html).

### Slicing, in one breath

A repeating element carries a list, and **slicing** is how a profile names positions
in that list so it can constrain them individually - slice `identifier` on `system`
and you can say "the slice whose system is `{base}/id/org-unit` is mandatory".
Extensions are pre-sliced by their URL, which is why a profile writes
`extension[D2Period] 1..1` and an instance addresses it by name. The toolkit slices
`identifier` into `dhis2id 1..1` and `dhis2code 1..1` on both org-unit profiles, and
slices the extensions each response profile requires - which is what lets an example
write `* extension[D2Period].extension[iso].valueString = "202607"`.

Further reading: [Slicing](https://hl7.org/fhir/R4/profiling.html#slicing).

## The capture pair

### Questionnaire

A `Questionnaire` is a form *definition*: a nested tree of `item`s, each with a
`linkId`, a `text`, and a `type` (`group`, `string`, `integer`, `choice`, `date`,
...). It is the closest thing in FHIR to a DHIS2 **data set** or **program stage
data entry form**.

`d2w fhir generate questionnaires` writes one per aggregate data set, one per event
program, and one per stage of a tracker program. Sections become `#group` items,
data elements become questions typed from their DHIS2 `valueType`, and a non-default
category combo on a data set turns a question into a group with one child per
category option combo.

Further reading: [Questionnaire](https://hl7.org/fhir/R4/questionnaire.html).

### `linkId` and `subjectType`

Each item carries a `linkId`, a string unique within the form; an answer refers back
to its question by repeating it, so it is the join key between a form and every
submission against it. The toolkit uses DHIS2 UIDs, which is what makes a response
readable back into DHIS2 without consulting the form: a section's linkId is the
section UID, a question's is the data element UID, and a disaggregated cell's is
`<deUid>.<cocUid>` - exactly the `(dataElement, categoryOptionCombo)` key a DHIS2
data value carries.

`Questionnaire.subjectType` states what kind of resource the form is answered *for*.
A DHIS2 data set and event program declare `#Location`, because a DHIS2 form is
answered for an organisation unit; a tracker form declares whatever the program's
tracked entity type is, because it is answered for the enrolled entity - and the
organisation unit moves onto the response's `D2OrganisationUnit` extension instead.
That is `#Patient` unless the project says otherwise: a DHIS2 tracked entity type is
not always a person, and a project tracking herds or water points maps its types onto
`#Group` or `#Location` in `fhir.toml`.

### QuestionnaireResponse

A `QuestionnaireResponse` is one *submission*: it points at a Questionnaire through
`questionnaire`, names its `subject`, carries a `status`, and answers item by item on
the same `linkId`s. The DHIS2 analogy is one data value set for a given (org unit,
period, attribute option combo), or one event.

`d2w fhir generate examples` writes one per form so an implementer can see what an
answer looks like, and `d2w fhir serve` receives them - `POST /QuestionnaireResponse`
is the one write the facade accepts.

Further reading:
[QuestionnaireResponse](https://hl7.org/fhir/R4/questionnaireresponse.html).

## The operational resources

### CapabilityStatement

A `CapabilityStatement` declares what a FHIR server supports: which resource types,
which interactions (`read`, `search-type`, `create`), which profiles it accepts.
Every FHIR server answers one at `GET /metadata`. DHIS2 has no equivalent; the
nearest thing is `/api/schemas` plus prose. Two appear here: the IG publishes
`D2CaptureServer` with `kind = #requirements` - what a *conforming* server must
support - and a running `d2w fhir serve` answers `/metadata` with a
`kind = #instance` statement instantiating it, narrowed to the types that store
actually holds.

Further reading: [CapabilityStatement](https://hl7.org/fhir/R4/capabilitystatement.html).

### Bundle

A `Bundle` is a container of resources with a `type` saying what the container means.
A search never returns a bare list: it returns a Bundle of `type = "searchset"`, with
a `total`, a `self` link, and one `entry` per match. `d2w fhir serve` answers every
search that way, and its `self` link echoes back only the parameters the server
actually applied, so a client can see what it got.

Further reading: [Bundle](https://hl7.org/fhir/R4/bundle.html).

### OperationOutcome

An `OperationOutcome` is FHIR's structured error - and structured acknowledgement. It
carries a list of `issue`s, each with a `severity`, a `code`, optional `diagnostics`
prose, and an `expression` locating the problem as a FHIRPath into the submitted
document. The capture facade answers with one on every path: an accepted capture gets
an `information` issue naming the receipt, a refused one gets errors that name the
offending `linkId` through `expression`.

Further reading: [OperationOutcome](https://hl7.org/fhir/R4/operationoutcome.html).

### NamingSystem

A `NamingSystem` declares that an identifier namespace exists and says what
identifiers under it mean. It registers nothing with anybody - it is the guide
stating its own convention, so a validator meeting `{base}/id/org-unit` has a
definition to resolve instead of warning on every artifact carrying one.

`foundation/d2-naming-systems.fsh` emits one per DHIS2 identifier system: a UID and a
code system for the organisation unit, option set, category, data set, program, data
element, category option combo, and program stage, plus a UID system alone for the
tracked entity and the tracker enrollment - DHIS2 gives those two no `code`
attribute, so there is no code system to declare.

Further reading: [NamingSystem](https://hl7.org/fhir/R4/namingsystem.html).

## FSH and the toolchain

### FSH, the FHIR Shorthand language

**FSH** (pronounced "fish") is a compact domain-specific language for authoring FHIR
artifacts. Writing a profile as raw JSON means hand-building a `StructureDefinition`
element by element; FSH is a few lines of text that compile to the same thing. Every
line inside a definition starts with `*` and names a path. Here is a trimmed
generated Questionnaire, one of the shapes `d2w fhir generate` writes:

```fsh
Instance: Questionnaire-BfMAe6Itzgt      // the FSH-level name of this artifact
InstanceOf: Questionnaire                // which resource type it is
Title: "Child Health"
Usage: #definition                       // a definitional artifact, not an example
* id = "BfMAe6Itzgt"                     // the bare DHIS2 UID
* url = "http://example.org/fhir/Questionnaire/BfMAe6Itzgt"
* identifier[+].system = $DHIS2-DS       // $-prefixed names are FSH aliases
* identifier[=].value = "BfMAe6Itzgt"    // [+] opens a new slot, [=] stays in it
* identifier[+].system = $DHIS2-DS-CODE
* identifier[=].value = "DS_359711"
* name = "D2DS_BfMAe6Itzgt"
* status = #draft                        // # marks a code, not a string
* subjectType = #Location                // answered for an organisation unit
* item[+].linkId = "Sec1aaaaaaa"         // a DHIS2 section
* item[=].text = "Immunization"
* item[=].type = #group
* item[=].item[+].linkId = "De1aaaaaaaa" // a data element inside it
* item[=].item[=].code = D2DE_CS#De1aaaaaaaa "BCG doses given"
* item[=].item[=].text = "BCG"
* item[=].item[=].type = #integer        // from the DHIS2 valueType
```

Four pieces of syntax carry most of the weight. `#code` is a code rather than a
string. `$NAME` is an alias, declared once and expanded everywhere - here to a DHIS2
identifier system URL. `[+]` appends a new entry to a repeating element and `[=]`
continues addressing the one just opened, which is how a nested tree is written as a
flat list of paths. And the keyword on line one picks the artifact kind: `Instance:`
for a concrete resource, `Profile:`, `Extension:`, `CodeSystem:`, `ValueSet:` for
definitions.

Further reading: [FHIR Shorthand](https://hl7.org/fhir/uv/shorthand/),
[FSH School](https://fshschool.org/).

### SUSHI and the IG Publisher

Two tools turn that text into a guide, and the scaffolded project runs both through
Docker. **SUSHI** compiles FSH to FHIR JSON; `make sushi` runs it standalone, which
is the fast gate - it says whether the FSH is valid without publishing anything. The
**HL7 IG Publisher** turns the JSON into the website, validating every resource,
rendering a page per artifact, and building the downloadable package; `make build`
runs it. The publisher runs **its own** SUSHI over the same FSH, so a chain that calls
`make sushi` and then `make build` compiles everything twice - iterate on `make sushi`
and run the publisher when you are ready to publish.

Further reading: [SUSHI](https://fshschool.org/docs/sushi/),
[IG Publisher](https://confluence.hl7.org/display/FHIR/IG+Publisher+Documentation).

### `fsh-generated/` versus `input/resources/`

FSH is not the only way into an IG. Anything already in FHIR JSON can be dropped into
`input/resources/` as a **predefined resource**: SUSHI loads it verbatim, with no FSH
parse and no conversion pass. Artifacts SUSHI compiles from FSH land in
`fsh-generated/resources/` instead.

That split is a performance decision here, not a stylistic one. The organisation-unit
registry and the option-set and category terminology are the largest things in a
DHIS2-derived IG and are pure data - so `d2w fhir generate` writes them as pre-built
JSON under `ig/input/resources/`, keeping them out of the compile entirely, while the
forms, profiles, and extensions stay FSH under `ig/input/fsh/`.

## How DHIS2 maps onto FHIR here

Every row is something `d2w fhir generate` actually emits.

| DHIS2 concept | FHIR artifact |
| --- | --- |
| Option set | A `CodeSystem` + `ValueSet` pair |
| Option | A `concept` in that CodeSystem - not an artifact of its own |
| Category, with its category options | The same `CodeSystem` + `ValueSet` pair shape |
| Data element referenced by a generated form | A concept in `D2DE_CS` |
| Category option combo | A concept in `D2COC_CS` |
| Organisation unit | An `Organization` **and** a `Location` instance |
| Organisation unit level | A concept in `D2OU_Level_CS`, bound to `Organization.type` |
| Organisation unit geometry | `Location.position` plus the `location-boundary-geojson` extension |
| Aggregate data set | One `Questionnaire`, `subjectType = #Location` |
| Event program | One `Questionnaire`, `subjectType = #Location` |
| Tracker program stage | One `Questionnaire` per stage, `subjectType` the program's tracked entity type (`#Patient` by default) |
| Section | An `item` of `type = #group` |
| Data element on a form | A child `item`, `linkId` the data element UID |
| Disaggregated data element | A group with one child per option combo, `linkId` `<deUid>.<cocUid>` |
| Data values for one (org unit, period, attribute option combo) | One `QuestionnaireResponse` |
| Event | One `QuestionnaireResponse` |
| Reporting period | The `D2Period` extension - ISO identifier, type, resolved range |
| Which kind of form this is | The `D2FormType` extension, and `Questionnaire.code` |
| Attribute value | One `D2AttributeValue` extension |
| UID and code | Two `identifier` slices: `{base}/id/<kind>` and `{base}/id/<kind>-code` |
| Each identifier system's convention | One `NamingSystem` declaration |
| Tracked entity | A logical subject of the form's own `subjectType` - `subject.identifier`, no `reference` |
| Enrollment | The `D2TrackerEnrollment` extension, as a `valueIdentifier` |
| Organisation unit of a tracker event | The `D2OrganisationUnit` extension |
| `NAME` translation | A concept `designation`, or the standard translation extension |

## Further reading

- [FHIR R4](https://hl7.org/fhir/R4/) - the specification this toolkit targets.
- [The R4 terminology module](https://hl7.org/fhir/R4/terminology-module.html) -
  CodeSystem, ValueSet, ConceptMap, NamingSystem, and how they fit together.
- [Profiling FHIR](https://hl7.org/fhir/R4/profiling.html) and
  [Extensibility](https://hl7.org/fhir/R4/extensibility.html).
- [FHIR Shorthand](https://hl7.org/fhir/uv/shorthand/) - the FSH specification.
- [FSH School](https://fshschool.org/) and
  [SUSHI](https://fshschool.org/docs/sushi/) - tutorials and the compiler.
- [IG Publisher documentation](https://confluence.hl7.org/display/FHIR/IG+Publisher+Documentation).

## See also

- [FHIR IG generation with `d2w fhir`](fhir-ig.md) - the task-oriented guide this
  page prepares you for.
- [FHIR plugin architecture](../architecture/fhir-plugin.md) - how the package is
  laid out and why.
- [The FHIR conversion layer](../project/fhir-conversion.md) - the plan for
  forwarding a captured response into DHIS2.
