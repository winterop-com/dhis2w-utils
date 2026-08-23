# Terminology and ConceptMaps

**Who this is for:** integration developers reading or consuming the generated
terminology - the option-set and category CodeSystem/ValueSet pairs - and the
ConceptMaps that take every generated concept code back to DHIS2.

**Before you start:** read [FHIR for DHIS2 people](101-fhir-concepts.md) for
what a CodeSystem, ValueSet, and ConceptMap are; a generated project
([quickstart](101-quickstart.md)) lets you open the JSON this page describes.

**You will be able to:**

- find the emitted terminology files and know what each pair carries
- read a generated ConceptMap and pick the right target group
- predict the fall-back behaviour when DHIS2 codes are missing or unusable
- read a concept's local-language renderings off its designations

## Option sets

`d2w fhir generate option-sets` writes two pre-built FHIR JSON documents per
option set, into `ig/input/resources/terminology/`:

```
ig/input/resources/terminology/CodeSystem-d2-os-<stem>-cs.json
ig/input/resources/terminology/ValueSet-d2-os-<stem>-vs.json
```

`<stem>` is the set's identity stem - the DHIS2 UID under the default
`source = "id"`, the set's code under the code sources (see the
[naming configuration](301-generation.md#naming)).

The CodeSystem points back at the ValueSet through `valueSet`, and the ValueSet
includes the CodeSystem's URL through `compose.include`. A 235-option-set
instance emits roughly 470 files; `generate` writes the full output in a few
minutes.

These are predefined resources: the publisher loads them verbatim and they never
enter the FSH compile. `sushi-config.yaml` declares `path-resource:
input/resources/terminology/*` so SUSHI recurses into the sub-folder, and
`ig/input/resources/` is gitignored the way generated output should be. See
[Build and publish the guide](201-build-and-publish.md#size-the-build) for what that split is worth in build
time.

**Questionnaires bind by FSH name.** A question reads
`answerValueSet = Canonical(D2OS_<UID>_VS)` and resolves to one of these JSON
documents, because SUSHI fishes a predefined resource by its `name` element and
every emitted CodeSystem and ValueSet carries exactly the FSH name the binding
asks for.

Concept codes are unique within a set by construction. Options are ordered by
`sortOrder`; each one asks for a code, and if that code is already taken the
option falls back to its UID, aggregated into one note. A CodeSystem that
repeats a concept code is invalid, so this is enforced rather than warned
about. The example responses code their answers from the same assignment, so a
`valueCoding` always names a concept this pair really carries.

**Both halves carry the set's DHIS2 attribute values**, as one
[`D2AttributeValue` extension](401-identifiers-and-extensions.md#d2attributevalue)
per value on the CodeSystem and the same list on the ValueSet. The values on the
*options* inside the set are not emitted, because a `CodeSystem.concept` has no
carrier chosen for them.

**A ConceptMap per set takes the concept codes back to DHIS2.** Beside the pair,
the target writes one map into the shared ConceptMap directory:

```
ig/input/resources/concept-maps/ConceptMap-d2-os-<stem>-cm.json
```

It carries the FSH-style name `D2OS_<stem>_CM` and the same identity stem the
pair's ids come from - the triple shares one stem. See
[ConceptMaps: the route back to DHIS2](#conceptmaps-the-route-back-to-dhis2) for
the shape, the two groups, and how `$translate` serves them.

The target owns `terminology/` outright and sweeps it, plus its own `ConceptMap-`
prefix inside `concept-maps/`: JSON left there by a previous run that this run does
not produce is deleted, so renaming or dropping an option set converges rather than
accumulating.

## Categories

A DHIS2 category is one axis of a disaggregation - Sex, EPI/nutrition age - and
its category options are the values along that axis. That is the shape of an
option set and its options, so a category emits the same pair, built by the same
concept-code assignment, into its own predefined-resource directory:

```
ig/input/resources/categories/CodeSystem-d2-cat-<stem>-cs.json
ig/input/resources/categories/ValueSet-d2-cat-<stem>-vs.json
```

`<stem>` is the category's identity stem - the DHIS2 UID under the default
`source = "id"`, the category's code under the code sources.

This is the terminology the disaggregated half of the data layer codes against.
Each pair carries the `CAT` naming token (`D2CAT_Sex_CS` / `D2CAT_Sex_VS`), the
category's own DHIS2 UID and code as `identifier` business identifiers, and the
category's DHIS2 attribute values as
[`D2AttributeValue` extensions](401-identifiers-and-extensions.md#d2attributevalue)
on both halves.

**The concepts are the category options.** They keep the category's own
`categoryOptions` order - DHIS2 holds that field as an ordered list, so the order
the instance answers with is the sort order - and each concept carries the
complementary DHIS2 identifier as a `dhis2-code` or `dhis2-id` property, exactly
as an option set's concepts do. Under `concept_code_source = "code"` the same
fall-backs apply: an option whose code is not a valid FHIR code takes its UID with
a note, and an option with no code left to take is skipped with its own note
rather than emitted as a duplicate concept.

**A ConceptMap per category takes the concept codes back to DHIS2**, written
beside the option-set maps in the shared directory:

```
ig/input/resources/concept-maps/ConceptMap-d2-cat-<stem>-cm.json
```

It carries the FSH-style name `D2CAT_<stem>_CM` and the category's own identity
stem, so the triple stays in step. See
[ConceptMaps: the route back to DHIS2](#conceptmaps-the-route-back-to-dhis2).

**A dedicated pair directory, not a shared one.** `categories/` is separate from
`terminology/` because each JSON sync deletes every `*.json` in its target that
the run did not produce. Sharing one directory would have the two targets deleting
each other's documents. `concept-maps/` is the deliberate exception: every map family
publishes there and each sweeps only the files its own id stem names, so the published
guide needs one `path-resource` glob for the whole terminology-mapping story.

**The scaffolded `sushi-config.yaml` declares the glob.** Its `path-resource`
block names `input/resources/categories/*` alongside the registry and terminology
globs. SUSHI recurses into sub-folders of `input/resources` on its own; the IG
Publisher does not, so without that line the pairs compile fine and are dropped
from the published guide. A project scaffolded before the glob existed picks it up
with `d2w fhir init --refresh` (see [Set up an IG project](201-set-up-a-project.md#refresh-an-older-projects-scaffold)).

Narrow the selection with `[generate.categories]` `include_ids` - absent or empty
means every category except DHIS2's built-in `default` placeholder, which
`include_default = true` (or an `include_ids` entry naming it) brings back.

## What a category option combo is made of

A category option combo is a composition. "Fixed, <1y" is the Fixed option of one
category met with the <1y option of another; "Improve access to clean water" is a
single option of the Project category. Two vocabularies publish those combos - the
data dictionary's `D2COC_CS` over every cell the questions split into, and the
`D2AOC_<stem>_CS` pair per non-default attribute category combo - and a reader
holding one of their concepts sees a code and a name with no way to dig into the
parts it was built from.

**Every combo concept carries one concept property per category it splits over.**
The property is valued as a `Coding` into that category's own published CodeSystem:

```json
{
  "code": "Prlt0C1RF0s",
  "display": "Fixed, <1y",
  "property": [
    { "code": "dhis2-code", "valueString": "COC_292" },
    {
      "code": "category-fMZEcRHuamy",
      "valueCoding": {
        "system": "http://localhost:8080/fhir/CodeSystem/d2-cat-fMZEcRHuamy-cs",
        "code": "qkPbeWaFsnU",
        "display": "Fixed"
      }
    },
    {
      "code": "category-YNZyaJHiHYq",
      "valueCoding": {
        "system": "http://localhost:8080/fhir/CodeSystem/d2-cat-YNZyaJHiHYq-cs",
        "code": "btOyqprQ9e8",
        "display": "<1y"
      }
    }
  ]
}
```

The properties read in the category combo's own order - location first, age group
second, which is the order DHIS2 reads the combo's name in.

**The declaration names the category.** Each axis is declared on the CodeSystem with
the category's name as its description, so the vocabulary alone tells a reader which
axis a property is without opening the category:

```json
{
  "code": "category-fMZEcRHuamy",
  "uri": "http://dhis2.org/fhir/property/category-fMZEcRHuamy",
  "description": "DHIS2 category Location Fixed/Outreach.",
  "type": "Coding"
}
```

The property code is `category-<stem>` off the category's identity stem - the DHIS2
UID under the default `source = "id"`, the category's code under the code sources.

**The coding names a concept that CodeSystem really holds.** The codes come from the
same concept-code assignment the category pair builds its own concepts from, so the
two can never disagree: under `concept_code_source = "id"` the coding names the
category option UID, under `"code"` it names the DHIS2 code with the same fall-backs
the category pair applied.

**A category the run does not publish states nothing.** A coding into a CodeSystem
nobody wrote leads a reader nowhere, so an axis whose category is outside
`[generate.categories]` is left off and the run reports it as a selection gap. Leaving
`include_ids` absent - every category except the `default` placeholder - is what keeps
every axis of every published combo resolvable.

**`d2w fhir serve --ui` renders each axis as a link.** The concept table gives every
declared property its own column, headed by the property code as words with the
category's name as the header's tooltip, and a cell valued as a coding links into that
coding's own CodeSystem page with the concept filter preset to the coded concept. The
link is generic: any coding-valued concept property digs down this way, whichever
vocabulary emitted it.

## What the guide says about a tracked entity attribute

The data dictionary publishes one CodeSystem/ValueSet pair per kind of question a
form asks. `D2DE_CS` is over the data elements; `D2TEA_CS` is over the **tracked
entity attributes** that a tracker programme's registration form and a tracked
entity type's person-only form ask about. Its concepts carry seven properties, and
the last five are what a consumer resolving a person needs:

| Property | Type | What it says |
| --- | --- | --- |
| `dhis2-code` | string | The DHIS2 code, where the instance states one. |
| `value-type` | code | The DHIS2 value type the answer is spelled in. |
| `unique` | boolean | Whether DHIS2 declares the attribute a business identifier. |
| `searchable` | boolean | Whether DHIS2 will find a person by it in **any** context this guide publishes. |
| `generated` | boolean | Whether DHIS2 mints the value itself rather than asking anyone for it. |
| `pattern` | string | The reserved-value pattern a generated attribute is minted from, carried only where there is one. |
| `display-in-list` | boolean | Whether DHIS2 shows the attribute in the working lists of **any** context this guide publishes. |

Each is declared on the CodeSystem under
`{identifier_system_base}/property/<code>`, so a served pair states its own
vocabulary before a consumer reads a single concept:

```console
$ curl -s localhost:8389/CodeSystem/d2-tea-cs | jq -c '.property[]'
{"code":"dhis2-code","uri":"http://dhis2.org/fhir/property/dhis2-code","type":"string"}
{"code":"value-type","uri":"http://dhis2.org/fhir/property/value-type","type":"code"}
{"code":"unique","uri":"http://dhis2.org/fhir/property/unique","type":"boolean"}
{"code":"searchable","uri":"http://dhis2.org/fhir/property/searchable","type":"boolean"}
{"code":"generated","uri":"http://dhis2.org/fhir/property/generated","type":"boolean"}
{"code":"pattern","uri":"http://dhis2.org/fhir/property/pattern","type":"string"}
{"code":"display-in-list","uri":"http://dhis2.org/fhir/property/display-in-list","type":"boolean"}
```

A concept carries only the properties that have an answer, so a generated
attribute is the one that carries all of `generated` and `pattern`:

```console
$ curl -s localhost:8389/CodeSystem/d2-tea-cs \
    | jq -c '.concept[] | select(.code=="TeaSystemId")'
{"code":"TeaSystemId","display":"Programme identifier","property":[{"code":"dhis2-code","valueString":"TEA_SYSTEM_ID"},{"code":"value-type","valueCode":"TEXT"},{"code":"unique","valueBoolean":true},{"code":"searchable","valueBoolean":true},{"code":"generated","valueBoolean":true},{"code":"pattern","valueString":"ANC-#######"}]}
```

`unique`, `generated`, and `pattern` are facts about the attribute alone - DHIS2
holds them on the attribute object, so they are the same answer wherever the
attribute is asked. A generated attribute is one DHIS2 writes for you off its
reserved-value pattern - a national identifier, a case number - so the question the
forms publish for it carries the standard R4 `Questionnaire.item.readOnly = true`
rather than an extension of this guide's own: a capture client must not invite a
person to contradict the instance.

`display-in-list` is a join fact the way `searchable` is - DHIS2 holds it on
`programTrackedEntityAttribute` and `trackedEntityTypeAttribute`, not on the
attribute - so the property is the roll-up over every context this run publishes,
and its declaration says so in those words.

**Searchability is not, so the guide publishes it per context.** DHIS2 holds
`searchable` on the *join* between an attribute and the form that asks it, and two
forms genuinely disagree: on the DHIS2 demo database, one programme declares an
attribute searchable while another asking the same attribute does not. A single
boolean would state one of them and lie about the other, so beside the roll-up the
CodeSystem declares one boolean property per context, coded
`searchable-<uid>` - the programme's UID on a registration form, the tracked entity
type's UID on a person-only one - and every concept carries the answer of every
context that asked it:

```json
{
  "code": "Tea1aaaaaaa",
  "display": "National identifier",
  "property": [
    { "code": "dhis2-code", "valueString": "TEA_NATIONAL_ID" },
    { "code": "value-type", "valueCode": "TEXT" },
    { "code": "unique", "valueBoolean": true },
    { "code": "searchable", "valueBoolean": true },
    { "code": "generated", "valueBoolean": false },
    { "code": "display-in-list", "valueBoolean": true },
    { "code": "searchable-Tet1aaaaaaa", "valueBoolean": false },
    { "code": "searchable-Trk1aaaaaaa", "valueBoolean": true }
  ]
}
```

Read it as: this attribute is a business identifier, DHIS2 will find a person by it
somewhere in this guide, and the somewhere is the Child Programme rather than the
Person type's own registration form. Each per-context property is declared with the
context named in words, so the vocabulary is readable without a UID lookup.

**A consumer reads these off the document, not off an operation.** `d2w fhir serve`
publishes no `$lookup`; it serves `GET /CodeSystem/d2-tea-cs` whole, and every
property above is an element of the concept in it
([Consume the FHIR API](401-consume-the-fhir-api.md#translate-generated-codes-back-to-dhis2-identifiers)).
The pair `unique` and `searchable` is what a facade's own register search keys
on, so reading them is how a client predicts which identifiers
[`GET /Patient?identifier=...`](401-consume-the-fhir-api.md#the-register-search-identifier)
will answer to.

A context appears only where it published a form in this run, which is the honest
reading: the roll-up answers for the guide, not for the whole instance.

**Which DHIS2 level an answer belongs to is not here.** That is published as the
`D2EntityLevel` extension on the `Questionnaire.item` instead, because membership is
a fact about the attribute *and* the tracked entity type together - one dictionary is
shared by every form of the run, and two programmes on different types can disagree
about one attribute.

## What the guide says about a tracked entity type

The attribute pair is over the objects a form *asks*. Beside it sits `D2TET_CS`,
over the objects the forms are *about*: one concept per DHIS2 tracked entity type
the run's person-only forms register - the types the selected tracker programmes
follow, or the types `[generate.tracked_entity_forms]` names where it names any.

The concept code is the type's DHIS2 UID, the display is the name the instance
holds for it, and the DHIS2 code rides as a `dhis2-code` property where the
instance states one - the same shape `D2TEA_CS` publishes, over a different kind
of object. Translations land as designations under `[generate] locales` like every
other vocabulary on this page. `D2TET_VS` includes the code system whole.

```json
{
  "code": "nEenWmSyUEp",
  "display": "Person",
  "property": [{ "code": "dhis2-code", "valueString": "TET_PERSON" }],
  "designation": [{ "language": "fr", "value": "Personne" }]
}
```

The names are never written into `fhir.toml`. The instance owns what a type is
called, so the vocabulary reads them off the same fetch the person-only forms are
built from - which is also why a renamed type in DHIS2 shows up in the guide on the
next `d2w fhir generate` with nothing to edit.

### The resource each type is published as

A DHIS2 tracked entity is not always a person, and
[`[generate.tracked_entity_types]`](301-what-goes-in.md#tracked_entity_types) is
exceptions-only: it names the types that are *not* people and says nothing about
the rest. That keeps a person-tracking project's config empty, but it also leaves
the resolution in a file nobody reading the published guide has.

So the guide publishes it. `D2TET_CM` sits in
`ig/input/fsh/data-dictionary/tracked-entity-types.fsh` beside the pair it maps,
and holds one row per published type: source `D2TET_CS`, target the R4
`http://hl7.org/fhir/resource-types` code system, equivalence `equal`.

```json
{
  "resourceType": "ConceptMap",
  "id": "d2-tet-cm",
  "url": "http://example.org/fhir/ConceptMap/d2-tet-cm",
  "name": "D2TET_CM",
  "title": "DHIS2 tracked entity types as FHIR resource types",
  "sourceCanonical": "http://example.org/fhir/ValueSet/d2-tet-vs",
  "targetCanonical": "http://hl7.org/fhir/ValueSet/resource-types",
  "group": [
    {
      "source": "http://example.org/fhir/CodeSystem/d2-tet-cs",
      "target": "http://hl7.org/fhir/resource-types",
      "element": [
        {
          "code": "nEenWmSyUEp",
          "display": "Person",
          "target": [{ "code": "Patient", "equivalence": "equal" }]
        },
        {
          "code": "Tet2aaaaaaa",
          "display": "Specimen batch",
          "target": [{ "code": "Specimen", "equivalence": "equal" }]
        }
      ]
    }
  ]
}
```

Every row is stated, not only the exceptions: a type the project never names is
published with a `Patient` target, so a consumer reads the answer rather than
inferring it from an absence. The row's target is the very resolution the form's
own `subjectType` came out of, so a `Questionnaire` and this map cannot disagree.

The map answers over `$translate` like every other - against a served facade,
not against the DHIS2 instance:

```bash
curl "http://localhost:8389/ConceptMap/\$translate?system=http://example.org/fhir/CodeSystem/d2-tet-cs&code=nEenWmSyUEp"
```

comes back with `Patient` in the `http://hl7.org/fhir/resource-types` system.
A running facade reads the same map at startup to decide which FHIR resources
its register answers over, so the answer a client translates and the endpoint it
then calls cannot disagree - see
[the register](401-consume-the-fhir-api.md#the-register-what-the-instance-holds-one-resource-per-tracked-entity-type).

### The sex values a person is served under { #the-sex-values-a-person-is-served-under }

`D2Sex_CM` is one of the two maps in this guide whose target is not a DHIS2
identifier - [`D2Section_CM`](#the-sections-a-recorded-value-feeds) is the other.
`Patient.gender` is bound to R4's own `administrative-gender` code system - `male`,
`female`, `other`, `unknown` - and the binding is **required**, so a DHIS2 option
code reaches that element through a translation or it does not reach it at all.
DHIS2 publishes no such translation, which makes the rows an instance's own
statement, written in
[`[ips.identity.administrative_gender]`](301-what-goes-in.md#ips-administrative_gender)
and published here.

```json
{
  "resourceType": "ConceptMap",
  "id": "d2-sex-cm",
  "url": "http://example.org/fhir/ConceptMap/d2-sex-cm",
  "name": "D2Sex_CM",
  "title": "DHIS2 sex values as FHIR administrative gender codes",
  "status": "draft",
  "experimental": true,
  "targetCanonical": "http://hl7.org/fhir/ValueSet/administrative-gender",
  "group": [
    {
      "source": "http://dhis2.org/fhir/tracked-entity-attribute/cejWyOfXge6",
      "target": "http://hl7.org/fhir/administrative-gender",
      "element": [
        { "code": "Female", "target": [{ "code": "female", "equivalence": "equal" }] },
        { "code": "Male", "target": [{ "code": "male", "equivalence": "equal" }] }
      ]
    }
  ]
}
```

**The source system is one attribute's own value namespace**, the very system the
register publishes that attribute's values under
([Identifiers and the D2 extensions](401-identifiers-and-extensions.md)). That is
deliberate, and it is what makes the map true of what the server does: the server
holds a person's stored value, not an option-set concept, so the row codes are the
values DHIS2 stores - on an option-set-bound attribute, the option's DHIS2 code. A
map keyed on anything else would publish a step nobody performs.

**Where the server reads it from.** The file, not the map. Which attribute is a
person's sex is not published anywhere - the guide states what an attribute is
called and what type its values are, and no artifact states what one *means* - so
reading half the dial from an artifact and half from `fhir.toml` would be worse
than reading both from one place. The map is what makes the translation auditable
by somebody holding the guide alone; it is not the server's own input. That is the
one way this family differs from `D2TET_CM`, and it closes when the nominations
themselves are published.

The rows are sorted by the DHIS2 value, so regenerating an unchanged `fhir.toml`
writes the same bytes. Nominate no `sex` and no file is written at all - an R4
group needs at least one element, and a map with no group states nothing.

### The sections a recorded value feeds { #the-sections-a-recorded-value-feeds }

`D2Section_CM` is the other map that runs outward. An International Patient
Summary is a document of LOINC-coded sections, and DHIS2 marks no data element as
an immunisation, a problem, or an allergy - so which of an instance's recorded
values belong in which section is that instance's own statement, written in
[`[ips.sections]`](301-what-goes-in.md#ips-sections) and published here for a
consumer to audit.

```json
{
  "resourceType": "ConceptMap",
  "id": "d2-section-cm",
  "url": "http://example.org/fhir/ConceptMap/d2-section-cm",
  "name": "D2Section_CM",
  "title": "DHIS2 program stages and data elements as International Patient Summary sections",
  "status": "draft",
  "experimental": true,
  "group": [
    {
      "source": "http://dhis2.org/fhir/id/program-stage",
      "target": "http://loinc.org",
      "element": [
        {
          "code": "A03MvHHogjR",
          "target": [
            { "code": "11369-6", "display": "History of Immunization Narrative", "equivalence": "equal" }
          ]
        }
      ]
    },
    {
      "source": "http://dhis2.org/fhir/id/data-element",
      "target": "http://loinc.org",
      "element": [
        {
          "code": "bx6fsa0t90x",
          "target": [
            { "code": "11369-6", "display": "History of Immunization Narrative", "equivalence": "equal" }
          ]
        }
      ]
    }
  ]
}
```

**The sources are the DHIS2 identifier namespaces, not the generated concept
codes.** A program stage rides `<base>/id/program-stage` and a data element rides
`<base>/id/data-element` - the very systems the guide publishes those objects
under, and the very ones `[ips.sections]` states its nominations in. A generated
concept code moves with [`[generate.naming]` `source`](301-generation.md#naming)
and a UID namespace never does, so a map keyed on the codes would go stale the
first time a project changed its naming.

**The target is LOINC**, because an IPS section is a LOINC-coded section of a
document and nothing else. `11369-6` is the Immunizations section, which is the
one section a mapping reaches today; another section is another row in these same
two groups rather than a second map.

**Where the server reads it from.** The file, exactly as with the sex values. A
`d2w fhir serve --live` run assembling a summary reads `fhir.toml`, because a
project may edit the file between two generate runs and a server reading a stale
artifact would serve a mapping its operator had already changed. The map is what
makes the claim auditable, not what makes it happen - see
[`$summary`](401-consume-the-fhir-api.md#summary-one-persons-international-patient-summary).

Rows are sorted by the UID, so regenerating an unchanged `fhir.toml` writes the
same bytes, and a namespace the project nominates nothing under gets no group
rather than an empty one. Map no section and no file is written at all.

## Translations: designations on a concept, extensions on a title

Every vocabulary on this page publishes its DHIS2 `NAME` translations, and the
slot each one lands in is decided by what FHIR offers on the element being
translated.

**A concept display is translated by a `designation`.** Every emitted
CodeSystem concept - an option, a category option, a data element, a tracked
entity attribute, an organisation unit - carries one designation per configured
locale beside its properties. The `display` stays the DHIS2 name verbatim,
because that is the data; the designations are the alternate renderings of it:

```json
{
  "code": "s46m5MS0hxu",
  "display": "BCG doses given",
  "property": [
    { "code": "dhis2-code", "valueString": "DE_359706" },
    { "code": "domain", "valueCode": "aggregate" },
    { "code": "value-type", "valueCode": "INTEGER" }
  ],
  "designation": [
    { "language": "fr", "value": "Doses de BCG administrees" },
    { "language": "lo", "value": "ຈຳນວນເຂັມ BCG ທີ່ໃຫ້" }
  ]
}
```

`designation.use` is left off: DHIS2 says which *property* it translated, not
what the translation is for, and a use code chosen here would be one this
toolkit invented rather than one the instance stated.

**A title or a name is translated by the standard extension.** A CodeSystem, a
ValueSet, and a Questionnaire carry their translations on the `_title` sibling
of `title`, an `Organization` and a `Location` on `_name`, and a
`Questionnaire.item` on `_text` - each as one
[`http://hl7.org/fhir/StructureDefinition/translation`](https://hl7.org/fhir/R4/extension-translation.html)
extension per locale, with `lang` and `content` sub-extensions:

```json
"_title": {
  "extension": [
    {
      "url": "http://hl7.org/fhir/StructureDefinition/translation",
      "extension": [
        { "url": "lang", "valueCode": "lo" },
        { "url": "content", "valueString": "ສຸຂະພາບເດັກ" }
      ]
    }
  ]
}
```

**The language tag is BCP-47.** DHIS2 stores a Java locale, so `pt_BR` is
published as `pt-BR`: underscores become hyphens, the language subtag
lowercases, and a two-letter region subtag uppercases. A tag the rule cannot
place is normalised as far as the rule reaches and then published as it stands
rather than dropped, because the words beside it are a translation somebody
wrote into the instance.

**The order is the locale tag, always.** DHIS2 holds translations in a set and
answers them in a different order on every read
([BUGS.md #83](https://github.com/winterop-com/dhis2w-utils/blob/main/BUGS.md)),
so every emitted list is sorted by the normalised tag and deduplicated on it. A
regenerate of unchanged metadata therefore produces an unchanged file.

**Which languages travel is `[generate] locales`.** Absent, every language the
instance holds is published; listed, only those. See
[the `locales` option](301-generation.md#locales) for what a translated guide
gives whom, and for the two cases where a translation the instance holds is
deliberately not published.

`d2w fhir serve` serves all of this without doing anything: the designations
and the extensions are elements of the resources it hands over, so a client
reading `GET /CodeSystem/d2-de-cs` gets them verbatim, Lao script included. The
terminology browser in `serve --ui` does not yet render a language picker - the
concept tables show the primary display - so a reader wanting the local-language
rendering today reads it off the JSON.

## ConceptMaps: the route back to DHIS2

Every concept the generator writes is a DHIS2 object under a FHIR spelling, and a
consumer holding one has exactly one question: **which DHIS2 object is this?** The
concept properties answer it for a reader; a ConceptMap answers it for a machine, and
a terminology server can serve that answer over
[`$translate`](401-consume-the-fhir-api.md#translate-generated-codes-back-to-dhis2-identifiers) -
a running [`d2w fhir serve`](201-serve.md) does exactly that.

Five families publish maps into one directory:

```
ig/input/resources/concept-maps/ConceptMap-d2-os-<stem>-cm.json    option sets
ig/input/resources/concept-maps/ConceptMap-d2-cat-<stem>-cm.json   categories
ig/input/resources/concept-maps/ConceptMap-d2-aoc-<stem>-cm.json   attribute option combos
ig/input/resources/concept-maps/ConceptMap-d2-sex-cm.json          sex values
ig/input/resources/concept-maps/ConceptMap-d2-section-cm.json      patient summary sections
```

| Family | Written by | Question it answers | Target namespaces |
| --- | --- | --- | --- |
| Option sets | `option-sets` | Which DHIS2 **option** does this answer code name? | `<base>/id/option`, `<base>/id/option-code` |
| Categories | `categories` | Which DHIS2 **category option** does this disaggregation code name? | `<base>/id/category-option`, `<base>/id/category-option-code` |
| Attribute option combos | `questionnaires` | Which DHIS2 **category option combo** does this response's attribute combination name? | `<base>/id/category-option-combo`, `<base>/id/category-option-combo-code` |
| Sex values | `questionnaires` | What does this instance's sex value mean, in FHIR's own words? | `http://hl7.org/fhir/administrative-gender` |
| Patient summary sections | `questionnaires` | Which section of a patient summary do this instance's recorded values feed? | `http://loinc.org` |

The last two run outward rather than back: every other map here takes a published
code onto a DHIS2 identifier, and those two take a DHIS2 value onto a vocabulary
somebody else owns. See
[the sex values a person is served under](#the-sex-values-a-person-is-served-under)
and [the sections a recorded value feeds](#the-sections-a-recorded-value-feeds).

`D2TET_CM` is a map too, and the one that runs the other way - from a DHIS2 concept
to a FHIR resource type rather than back to a DHIS2 identifier. It is authored in
FSH beside the vocabulary it maps rather than written as JSON here, so it compiles
out of `data-dictionary/` and needs no glob of its own; see
[the resource each type is published as](#the-resource-each-type-is-published-as).

Each map back to DHIS2 takes its id, its FSH name, and its URL from the same
identity stem its CodeSystem and ValueSet do, carries the source object's UID as its
single `identifier` (`<base>/id/option-set` for a set, `<base>/id/category` for a
category), and points `sourceCanonical` at its own ValueSet. All four DHIS2
namespaces are declared as NamingSystems by the `foundation` target (see
[Generate the IG source](201-generate.md#know-the-eight-targets)), so a validator meeting one has a
definition to resolve.

### The two-group shape

A map holds two groups, both sourced from the object's own CodeSystem: one onto the
DHIS2 UID namespace, one onto the DHIS2 code namespace. An option set:

```json
{
  "resourceType": "ConceptMap",
  "id": "d2-os-birth-type-cm",
  "url": "http://example.org/fhir/ConceptMap/d2-os-birth-type-cm",
  "identifier": { "system": "http://dhis2.org/fhir/id/option-set", "value": "Xa1b2c3d4e5" },
  "name": "D2OS_BirthType_CM",
  "title": "Birth type",
  "status": "draft",
  "experimental": true,
  "sourceCanonical": "http://example.org/fhir/ValueSet/d2-os-birth-type-vs",
  "group": [
    {
      "source": "http://example.org/fhir/CodeSystem/d2-os-birth-type-cs",
      "target": "http://dhis2.org/fhir/id/option",
      "element": [
        {
          "code": "kRRUtYaGett",
          "display": "Natural Birth",
          "target": [{ "code": "kRRUtYaGett", "equivalence": "equal" }]
        }
      ]
    },
    {
      "source": "http://example.org/fhir/CodeSystem/d2-os-birth-type-cs",
      "target": "http://dhis2.org/fhir/id/option-code",
      "element": [
        {
          "code": "kRRUtYaGett",
          "display": "Natural Birth",
          "target": [{ "code": "NB", "equivalence": "equal" }]
        }
      ]
    }
  ]
}
```

And a category, the same shape over the category-option namespaces:

```json
{
  "resourceType": "ConceptMap",
  "id": "d2-cat-sex-cm",
  "url": "http://example.org/fhir/ConceptMap/d2-cat-sex-cm",
  "identifier": { "system": "http://dhis2.org/fhir/id/category", "value": "O5P6e8yu1T6" },
  "name": "D2CAT_Sex_CM",
  "title": "Sex",
  "status": "draft",
  "experimental": true,
  "sourceCanonical": "http://example.org/fhir/ValueSet/d2-cat-sex-vs",
  "group": [
    {
      "source": "http://example.org/fhir/CodeSystem/d2-cat-sex-cs",
      "target": "http://dhis2.org/fhir/id/category-option",
      "element": [
        {
          "code": "TNYQzTHdoxL",
          "display": "Female",
          "target": [{ "code": "TNYQzTHdoxL", "equivalence": "equal" }]
        }
      ]
    },
    {
      "source": "http://example.org/fhir/CodeSystem/d2-cat-sex-cs",
      "target": "http://dhis2.org/fhir/id/category-option-code",
      "element": [
        {
          "code": "TNYQzTHdoxL",
          "display": "Female",
          "target": [{ "code": "F", "equivalence": "equal" }]
        }
      ]
    }
  ]
}
```

The rules are the same for both families:

- **`equivalence = #equal` on every row**, which R4 makes mandatory. The concept and
  the target identifier name the same DHIS2 object under two identifier conventions -
  this is not a translation between two vocabularies.
- **The UID group is emitted under either `concept_code_source`**, identity mapping
  included, so a consumer never has to know which mode produced the guide.
- **The code group is emitted only where there is something to map.** A member DHIS2
  left uncoded, or coded with something that is not a valid FHIR `code`, has no target
  code and is left out; an object where that is true of every member emits the UID
  group alone, because an R4 group with no element is invalid. An object with no
  concepts at all emits no map.
- **The rows come from the same concept assignment the CodeSystem's concepts do**, so
  a mapping can only ever name a concept the pair really carries.
- **`source[x]` is the pair's ValueSet and `target[x]` is absent.** R4 types both as
  value sets; the DHIS2 identifier namespaces are not value sets, so naming one there
  would be a lie. They appear where R4 wants systems: `group.target`.
- **`identifier` is a single element, not a list.** R4 gives `ConceptMap.identifier`
  `0..1` where it gives CodeSystem and ValueSet `0..*`.

### UID targets or code targets?

Both groups are always there to be asked; which one a consumer wants depends on what
it is about to do with the answer.

- **Reach for the UID namespace** (`id/option`, `id/category-option`) when the answer
  is going into a DHIS2 API call. UIDs are what `/api/dataValueSets` and the tracker
  endpoints accept, they are unique instance-wide, and every member has one - the group
  is complete by construction.
- **Reach for the code namespace** (`id/option-code`, `id/category-option-code`) when
  the answer is going in front of a human, into a report, or into a system keyed on the
  instance's business codes. DHIS2 codes are optional and not guaranteed unique, so the
  group can be partial or absent; treat a miss as "this member has no usable code",
  not as an error.

### The publisher needs the glob

`input/resources/concept-maps/*` sits in the scaffolded `sushi-config.yaml`
`path-resource` block beside the terminology, category, and registry globs - one glob
covers both families, because both write into the one directory. SUSHI recurses into
sub-folders of `input/resources` on its own; the IG Publisher does not, so without it
the maps compile fine and are dropped from the published guide. A project scaffolded
before the glob existed picks it up with `d2w fhir init --refresh` (see
[Set up an IG project](201-set-up-a-project.md#refresh-an-older-projects-scaffold)).

No family owns the directory outright. A JSON sync normally deletes every `*.json`
in its target the run did not produce, which would have `d2w fhir generate option-sets`
sweeping away the category maps; instead each family sweeps only the file-name prefix
its own naming tokens produce (`ConceptMap-d2-os-`, `ConceptMap-d2-cat-`,
`ConceptMap-d2-aoc-`, `ConceptMap-d2-sex`, `ConceptMap-d2-section`). Each still
converges: drop a category from the selection and its map goes with its pair, drop
`sex` from [`[ips.identity]`](301-what-goes-in.md#ips-sex) and the sex map goes with
it, and drop [`[ips.sections]`](301-what-goes-in.md#ips-sections) and the section
map goes with that.

## See also

- [Identifiers and the D2 extensions](401-identifiers-and-extensions.md) - the
  identifier slices and concept properties this terminology carries.
- [Serve the guide](201-serve.md) - the facade that answers `$translate` over
  these maps.

Next: [Custom subject types](401-custom-subject-types.md) - what a tracked
entity is published as when it is not a person.
