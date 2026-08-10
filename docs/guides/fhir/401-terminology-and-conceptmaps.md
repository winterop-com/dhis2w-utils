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
[`D2AttributeValue` extension](401-identifiers-and-extensions.md#the-d2attributevalue-extension)
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
[`D2AttributeValue` extensions](401-identifiers-and-extensions.md#the-d2attributevalue-extension)
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
each other's documents. `concept-maps/` is the deliberate exception: both families
publish there and each sweeps only the files its own id stem names, so the published
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

## ConceptMaps: the route back to DHIS2

Every concept the generator writes is a DHIS2 object under a FHIR spelling, and a
consumer holding one has exactly one question: **which DHIS2 object is this?** The
concept properties answer it for a reader; a ConceptMap answers it for a machine, and
a terminology server can serve that answer over
[`$translate`](401-consume-the-fhir-api.md#translate-generated-codes-back-to-dhis2-identifiers) -
a running [`d2w fhir serve`](201-serve.md) does exactly that.

Two targets publish maps, one family each, into one directory:

```
ig/input/resources/concept-maps/ConceptMap-d2-os-<stem>-cm.json    option sets
ig/input/resources/concept-maps/ConceptMap-d2-cat-<stem>-cm.json   categories
```

| Family | Written by | Question it answers | Target namespaces |
| --- | --- | --- | --- |
| Option sets | `option-sets` | Which DHIS2 **option** does this answer code name? | `<base>/id/option`, `<base>/id/option-code` |
| Categories | `categories` | Which DHIS2 **category option** does this disaggregation code name? | `<base>/id/category-option`, `<base>/id/category-option-code` |

Each map takes its id, its FSH name, and its URL from the same identity stem its
CodeSystem and ValueSet do, carries the source object's UID as its single
`identifier` (`<base>/id/option-set` for a set, `<base>/id/category` for a
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

Neither target owns the directory outright. A JSON sync normally deletes every `*.json`
in its target the run did not produce, which would have `d2w fhir generate option-sets`
sweeping away the category maps; instead each target sweeps only the file-name prefix
its own id stem produces (`ConceptMap-d2-os-`, `ConceptMap-d2-cat-`). Both still
converge: drop a category from the selection and its map goes with its pair.

## See also

- [Identifiers and the D2 extensions](401-identifiers-and-extensions.md) - the
  identifier slices and concept properties this terminology carries.
- [Serve the guide](201-serve.md) - the facade that answers `$translate` over
  these maps.

Next: [Consume the FHIR API](401-consume-the-fhir-api.md)
