# The conversion layer: DHIS2 <=> QuestionnaireResponse

How data crosses between DHIS2 and FHIR in both directions - the mechanisms the FHIR
ecosystem offers, what DHIS2's shapes demand of them, and the phased path this project
takes. This is the working plan behind roadmap decision 5.3; the decision itself stays
with the owner, and this page is the basis for making it.

## The two directions, and what already exists

**DHIS2 -> QR** exists in code today: the examples target's instance source reads
`/api/dataValueSets` and `/api/tracker/events` and produces QuestionnaireResponses -
answer typing from the value-type table, option values resolved to codings through the
concept assignment plan, event status mapped, timestamps zoned. It is exercised against
live instances and validated by the IG publisher on every build.

**QR -> DHIS2** ships as `dhis2w_fhir.conversion` behind
[`d2w fhir forward`](../201-forward.md): `d2w fhir serve`
stores validated responses as an outbox, and the forwarder drains it. It covers the three
payload mappings (dataValueSets envelope; event; tracker event), the non-bijective status
inverse, wire-value serialisation (TRUE_ONLY, MULTI_TEXT, decimal lexical preservation,
zoned datetimes), coded-answer resolution with the lenient/strict dial, and the DHIS2
validate-only modes a dry run posts under.

So the question is not whether the mappings are known - both directions are fully
specified against real instances. The question is **where the mapping definition lives**:
in Python alone, or in machine-readable artifacts the IG itself publishes.

## The candidate mechanisms

### 1. Manual: typed Python translators

The mapping lives in code - frozen models, explicit tables, exhaustive tests, golden
fixtures compiled by SUSHI. This is what the DHIS2->QR direction already is.

- For: fastest to ship; debuggable; handles every DHIS2 quirk (BUGS.md #62/#67, COC
  grids, code fallbacks) without fighting a mapping language's expressiveness; the test
  suite is the conformance statement.
- Against: the mapping is invisible to the IG's consumers - a third party building their
  own bridge re-derives it from prose; nothing machine-checks that the published contract
  and the implementation agree; every future runtime (the `fhir build` buildpacks)
  re-implements it by hand, which the project's recorded stance explicitly forbids.

### 2. SDC (Structured Data Capture): `$extract` and `$populate`

The HL7 IG purpose-built for form round-trips. `$populate` fills a QR from existing data;
`$extract` projects a QR into FHIR resources, in four flavours (definition-based,
observation-based, template-based, StructureMap-based).

- Fit: the generated Questionnaires are *already* SDC-shaped on the read side - every item
  carries a `D2DE_CS` coding, which is exactly what observation-based `$extract` keys on.
  A future clinical layer (QR -> coded Observations) is nearly free, and that projection
  is worth having for analytics consumers regardless of DHIS2.
- Misfit: `$extract` targets FHIR resources, and DHIS2's wire is not FHIR. Reaching DHIS2
  through SDC alone means QR -> Observation -> DHIS2, a two-hop pipeline where the second
  hop is the entire original problem again. SDC also has no native carrier for the
  category option combo grid or the reporting-period extension.
- Verdict: adopt SDC's *vocabulary and hooks* (item codes, and eventually an
  observation-based `$extract` for the clinical projection), but it is not the DHIS2
  bridge itself.

### 3. StructureMap + FHIR Mapping Language, over DHIS2 logical models

Define DHIS2's wire shapes as logical models in the IG - `StructureDefinition
kind=logical` for the data value set row and the tracker event - and publish StructureMaps
QR <-> logical model. This is the WHO SMART Guidelines pattern, and the project's recorded
conversion stance (FML as the contract, never a runtime engine).

- For: the mapping becomes a published, validator-testable artifact of the IG - a third
  party can read (or execute) the exact transform; CI can execute the maps with the Java
  validator against the golden examples and fail the build when the Python translator and
  the published map disagree; `fhir build`'s buildpacks codegen from one shared source.
- Against: FML's expressiveness will strain on the hard 20% (the COC linkId grammar is a
  string-split; code fallback chains are conditionals; MULTI_TEXT is a join) - some rules
  end up as invented extension functions the executing engine must know, at which point
  the "standard" map is standard-shaped rather than portable. No production FML engine
  exists for Python or Rust; execution stays confined to CI (Java validator / matchbox).
- Fallback recorded in the stance: if FML cannot express the COC grid cleanly, a
  language-neutral **mapping manifest** (a generated, versioned JSON document the IG
  ships: linkId grammar, per-question value types, code tables, status maps) carries the
  same contract without the language - less standard, equally machine-readable.

### 4. ConceptMap + `$translate` (terminology side, orthogonal)

Concept <-> DHIS2 identifier mappings as generated ConceptMaps - **shipped for both
terminology families**, option sets and categories; see
[phase B item 1](#phase-b-item-1-conceptmaps-per-terminology-family) below. `serve`
answers R4's type-level `ConceptMap/$translate` over the same store, in both compiled
and `--live` mode, so the whole mechanism is live: `system` + `code` in, a `Parameters`
resource carrying the DHIS2 UID and the DHIS2 code out.

## The plan: reference implementation first, contract lifted second

**Phase A - the forwarder. SHIPPED.** QR -> DHIS2 is the typed Python translator the
capture design specifies, draining the serve outbox. The translator is
`dhis2w_fhir.conversion` (`schemas`, `context`, `values`, `payloads`, `translator`, and
`artifacts` reading a project's published guide into a context); the command that drives it
is `d2w fhir forward`, whose dry run - the default - posts every payload to the real
endpoint under that endpoint's own validate-only mode and moves nothing, and whose
`--import` commits and then files each receipt into `forwarded/` or `rejected/`. See
[Forwarding captured responses](../201-forward.md).

This code is the *reference implementation* the later contract is held against - the same
role the FSH emitters played for the JSON builders, where golden parity kept two paths
honest. The gate already exists in both directions:
`packages/dhis2w-fhir/tests/test_fhir_conversion_roundtrip.py` asserts that every example
response of a whole generate run translates back, cell for cell, to the DHIS2 values it was
built from, and `test_fhir_forward.py` runs the whole spool-to-import path over a project on
disk.

**Phase B - lift the contract into the IG.** In order:
1. **ConceptMaps per terminology family** - shipped for option sets and categories,
   described below.
2. **DHIS2 logical models** as `kind=logical` StructureDefinitions - they document the
   wire faithfully and are a prerequisite for any map. `D2DataValueSet` (the aggregate
   envelope) is shipped and described below; the tracker event is the one still owed.
3. **StructureMaps QR -> logical model**, scoped honestly: express what the language
   expresses well, and record what it cannot beside it.
   `D2AggregateResponseToDataValueSet` is shipped, with the CI gate described below.
4. The reverse maps (logical model -> QR) documenting the existing DHIS2->QR direction,
   held to the same gate against the instance-source examples.

**Phase C - buildpacks.** `fhir build` codegens each target language's converter from the
phase-B artifacts (maps + manifest + ConceptMaps). Nothing is hand-written per language;
the CI gate from phase B is what makes the codegen trustworthy.

**SDC hook, parallel:** when the clinical projection is wanted, observation-based
`$extract` over the item codes - additive, not on the DHIS2 path.

## Phase B item 1: ConceptMaps per terminology family

Shipped by both terminology targets. `option-sets` writes one ConceptMap beside every
CodeSystem/ValueSet pair it emits and `categories` does the same for its own pairs, both
into the predefined-resource directory `ig/input/resources/concept-maps/`, named
`ConceptMap-<id-stem><slug>-cm.json` with the FSH-style name `D2OS_<segment>_CM` or
`D2CAT_<segment>_CM`. Each map takes its id, its name, and its URL from the same identity
the pair does, so all three artifacts of one source object carry one slug. Neither target
owns the shared directory outright: each sweeps the file-name prefix its own id stem
produces, which keeps one `path-resource` glob covering the whole mechanism.

**Two groups, both sourced from the source object's own CodeSystem.** The map answers
the one question a consumer holding a generated coding has - *which DHIS2 object is
this?* - and answers it for both DHIS2 identifiers at once. An option set maps onto
`{base}/id/option` and `{base}/id/option-code`; a category maps onto
`{base}/id/category-option` and `{base}/id/category-option-code`:

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

- **`source[x]` is the pair's ValueSet, `target[x]` is absent.** R4 makes both optional and
  types them as value sets; the DHIS2 identifier namespaces are not value sets, so naming
  one there would be a lie. The namespaces appear where R4 wants systems: `group.target`.
- **The identifier is a single element, not a list.** R4 gives `ConceptMap.identifier`
  `0..1` where it gives CodeSystem and ValueSet `0..*`, so the set's UID rides alone.
- **`equivalence = #equal` on every row**, which R4 makes mandatory: the concept and the
  target identifier name the same DHIS2 option under two identifier conventions rather
  than translating between two vocabularies.
- **The UID group is emitted in both concept-code modes**, identity mapping included. A
  consumer should not have to know which `concept_code_source` produced the guide to ask
  what a code's option UID is.
- **The code group is emitted only where there is something to map.** An option DHIS2 left
  uncoded, or coded with something that is not a valid FHIR `code`, has no target code and
  is left out; a set where that is true of every option emits the UID group alone, because
  an R4 group with no element is invalid. A set with no concepts at all emits no map.
- **The rows come from `concept_assignments`**, the same plan the concepts themselves are
  built from, so a mapping can only ever name a concept the CodeSystem really holds - the
  discipline the example answers already follow.

All four DHIS2 identifier namespaces - `{base}/id/option`, `{base}/id/option-code`,
`{base}/id/category-option`, `{base}/id/category-option-code` - are declared as
NamingSystems by the `foundation` target and aliased in `d2-aliases.fsh`, so a validator
meeting one has a definition to resolve.

## Phase B items 2 and 3: the aggregate path, end to end

One conversion is now expressed as FHIR artifacts the guide publishes: an aggregate
QuestionnaireResponse becoming a DHIS2 data value set. Both artifacts come out of the
`foundation` target, so they depend on `fhir.toml` alone and every generated guide carries
them.

### `D2DataValueSet`, the wire shape as a logical model

`foundation/d2-data-value-set.fsh` declares the `/api/dataValueSets` envelope as a
`kind = logical` StructureDefinition - nine elements, exactly what
`translate_aggregate_response` writes:

```
Logical: D2DataValueSet
Id: d2-data-value-set
* dataSet 1..1 string "Data set" "..."
* period 1..1 string "Reporting period" "..."
* orgUnit 1..1 string "Organisation unit" "..."
* attributeOptionCombo 0..1 string "Attribute option combo" "..."
* completeDate 0..1 date "Complete date" "..."
* dataValues 0..* BackboneElement "Data values" "..."
* dataValues.dataElement 1..1 string "Data element" "..."
* dataValues.categoryOptionCombo 0..1 string "Category option combo" "..."
* dataValues.value 1..1 string "Value" "..."
```

The three required elements are the three keys DHIS2 stores every data value under; the
attribute option combo is the fourth key only a data set on a non-default category combo
carries. Every element is a `string` except the completeness date, because every DHIS2 data
value is a string on the wire whatever the data element's value type - which is what lets a
lexical decimal and a DHIS2 option code cross untouched.

The elements are declared once, in Python, as `DATA_VALUE_SET_ELEMENTS`. The FSH template
renders them and the CI gate reads them back; a test asserts the compiled differential equals
the declaration, so the published artifact and the checked one cannot drift apart.

### `D2AggregateResponseToDataValueSet`, the map

`foundation/d2-aggregate-map.fsh` publishes the StructureMap from the response profile onto
that model. Two groups: the envelope, and a recursive one over the item tree.

```
Instance: D2AggregateResponseToDataValueSet
InstanceOf: StructureMap
Usage: #definition
* structure[0].url = "http://hl7.org/fhir/StructureDefinition/QuestionnaireResponse"
* structure[0].mode = #source
* structure[1].url = Canonical(D2DataValueSet)
* structure[1].mode = #target
* group[0].name = "AggregateResponseToDataValueSet"
* group[0].rule[1].name = "period"
* group[0].rule[1].source[0].context = "response"
* group[0].rule[1].source[0].element = "extension"
* group[0].rule[1].source[0].variable = "reportingPeriod"
* group[0].rule[1].source[0].condition = "url = '<canonical>/StructureDefinition/d2-period'"
...
* group[1].name = "ResponseItemToDataValues"
```

Group one takes the five envelope facts and hands the item tree to group two; group two
recurses through the section groups and writes one data value per answered question,
splitting `<dataElement>.<categoryOptionCombo>` out of the link id.

**The authoring form is the load-bearing finding: SUSHI compiles no FHIR Mapping Language.**
A `.fml` file is ignored wherever it is placed in an IG - `input/maps/`, `input/fsh/`,
anywhere - and only `.fsh` under `input/fsh` is read. So the map is authored as an
`Instance:` of StructureMap with its groups and rules written out, which SUSHI compiles to
the same resource an FML compiler would have produced. The contract a consumer reads is the
StructureMap resource either way; the syntax it was written in is not part of it.

**Four rules carry documentation because their meaning exceeds what a transform states.**
This is the FML residue the plan predicted, and it is recorded on the artifact rather than
in prose beside it:

- `dataSet` is a fact about the *form*, not the response - the `$DHIS2-DS` identifier of the
  Questionnaire being answered, which an executing engine needs in scope.
- `orgUnit` is the DHIS2 identifier of the published Location the response is subject to, so
  the Location registry has to be in scope too; reading the UID off the reference's own id
  is only correct where the guide names its Locations by DHIS2 id.
- `attributeOptionCombo` is a coding of the form's own vocabulary, and under
  `concept_code_source = "code"` the combo's ConceptMap is what turns that code into the UID.
- `dataValues.value` is the whole wire-serialisation table: a `TRUE_ONLY` question answered
  false drops the cell, a `MULTI_TEXT` answer is comma-joined, a decimal keeps its lexical
  form, a coded answer resolves through the question's terminology, a zoned timestamp is read
  to the wall clock. `dhis2w_fhir.conversion.values` is the reference implementation of it.

`completeDate` carries a fifth note: the substring is the structural claim, and the zone
arithmetic behind it (BUGS.md #62) is not.

### The CI gate

`packages/dhis2w-fhir/tests/test_fhir_conversion_contract.py` is the gate.
`tests/data/r4/StructureDefinition-d2-data-value-set.json` is what SUSHI compiled the FSH
into, committed and never hand-edited. The test reads the shape claims out of that
differential and holds every data value set the Python forwarder produces from the conversion
corpus - 142 cells across the two aggregate examples - against them.

**What the gate proves.** The forwarder writes no field the published contract does not
declare and omits none it declares required; nothing typed single arrives as a list and
nothing typed repeating arrives as a scalar; every value's JSON type is the one the contract
states. And the emitted FSH and the compiled artifact are one thing, because the differential
is asserted equal to the declaration the template renders.

**What the gate does not prove.** It does not execute the StructureMap: no FML engine runs
here, the map is a contract rather than a runtime, and a full engine execution against these
responses is explicitly out of scope. It does not grade *values* - the contract states shapes,
so it cannot tell a correct data element UID from a wrong one; the round trip
(`test_fhir_conversion_roundtrip.py`) is what grades those, cell for cell, against the DHIS2
data the examples were built from. And it does not prove DHIS2 accepts the payload; only a
real instance grades that, which is what the dry run of `d2w fhir forward` is for.

One coverage boundary is asserted outright rather than left silent: the synthetic aggregate
examples carry no `authored` instant, so no payload of the corpus carries `completeDate`, and
that element's `date` claim is pinned by a unit check instead.

### What phase B still owes

- **The tracker logical models and maps.** `TrackerEvent` (both event kinds),
  `TrackerTrackedEntity`, and `TrackerEnrollment` are four more wire shapes and three more
  maps. The event path is the closer sibling of what shipped; the registration path adds the
  entity-level split and the two enrollment dates.
- **The reverse maps.** Logical model -> QR, documenting the DHIS2->QR direction the instance
  source already performs, held to the same gate against the instance-source examples.
- **The manifest decision point.** The aggregate map's residue turned out to be four rules,
  each expressible as a rule carrying documentation rather than as a gap. That is evidence
  for keeping StructureMaps, not proof: the tracker registration path is where the residue
  gets its real test, because the entity-level split decides *which of two payloads* an
  answer lands in, and a transform has no vocabulary for that. If that rule cannot be written
  as a rule, the language-neutral mapping manifest carries the residue and the maps keep the
  structural remainder - the gate is identical either way.

## Why this order

The alternative - author the StructureMaps first and generate the forwarder from them -
front-loads the riskiest unknown (FML's fit for DHIS2's shapes) onto the critical path of
a feature users are waiting for, and does it without a reference implementation to test
the maps against. Reference-first means the maps are born with an executable conformance
target, exactly how this project has caught every contract drift so far: two independent
paths, one gate that fails when they disagree.

## What decision 5.3 now needs from the owner

Only ratification of the phase-B carrier: StructureMaps-with-residue-manifest versus
manifest-only. Both keep the CI gate and the buildpack story identical; the difference is
how much of the contract is expressed in a standard language versus a project-defined
document.

The aggregate slice is the first evidence. Every element of that conversion is expressible
as a StructureMap rule; four of them need documentation stating what the transform cannot,
and none of them needed an invented extension function. That is a point for keeping the maps.
The counter-evidence, if it comes, comes from the tracker registration path, where an answer's
`D2EntityLevel` decides which of two payloads it lands in - and the decision is best made
after that map is attempted rather than before.
