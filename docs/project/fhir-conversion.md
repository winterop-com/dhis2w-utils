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

**QR -> DHIS2** exists as a completed design (the serve capture pipeline's translation
tables) but deliberately not as code: `d2w fhir serve` stores validated responses as an
outbox, and the forwarder that drains it is the next phase. The design covers the three
payload mappings (dataValueSets envelope; event; tracker event), the non-bijective status
inverse, wire-value serialisation (TRUE_ONLY, MULTI_TEXT, decimal lexical preservation,
zoned datetimes), coded-answer resolution with the lenient/strict dial, and the DHIS2
validate-only modes for dry runs.

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

Option <-> DHIS2 identifier mappings as generated ConceptMaps. The emitted CodeSystems
already carry both identifiers as concept properties, so the generator can emit one
ConceptMap per option set mechanically. This is uncontroversial, standard, and useful to
any consumer; `serve` can answer `$translate` from the same store later.

## The plan: reference implementation first, contract lifted second

**Phase A - the forwarder (next).** Build QR -> DHIS2 as the typed Python translator the
capture design specifies, draining the serve outbox. Manual, tested, shipped. This code is
then the *reference implementation* the later contract is held against - the same role the
FSH emitters played for the JSON builders, where golden parity kept two paths honest.

**Phase B - lift the contract into the IG.** In order:
1. **ConceptMaps per option set** (mechanical, immediate consumer value).
2. **Two DHIS2 logical models** (data value set row, tracker event) as
   `kind=logical` StructureDefinitions - they document the wire faithfully and are a
   prerequisite for any map.
3. **StructureMaps QR -> logical model**, scoped honestly: express what FML expresses
   well, and record what it cannot beside it. CI gate: execute the maps over the golden
   example QRs with the Java validator and assert the output equals what the Python
   forwarder produces. If the un-expressible residue is large, pivot to the mapping
   manifest for the residue and keep the maps for the structural 80% - the gate stays
   identical either way.
4. The reverse maps (logical model -> QR) documenting the existing DHIS2->QR direction,
   held to the same gate against the instance-source examples.

**Phase C - buildpacks.** `fhir build` codegens each target language's converter from the
phase-B artifacts (maps + manifest + ConceptMaps). Nothing is hand-written per language;
the CI gate from phase B is what makes the codegen trustworthy.

**SDC hook, parallel:** when the clinical projection is wanted, observation-based
`$extract` over the item codes - additive, not on the DHIS2 path.

## Why this order

The alternative - author the StructureMaps first and generate the forwarder from them -
front-loads the riskiest unknown (FML's fit for DHIS2's shapes) onto the critical path of
a feature users are waiting for, and does it without a reference implementation to test
the maps against. Reference-first means the maps are born with an executable conformance
target, exactly how this project has caught every contract drift so far: two independent
paths, one gate that fails when they disagree.

## What decision 5.3 now needs from the owner

Only ratification of the phase-B carrier once phase A exists and the FML experiment has
run against real shapes: StructureMaps-with-residue-manifest versus manifest-only. Both
keep the CI gate and the buildpack story identical; the difference is how much of the
contract is expressed in a standard language versus a project-defined document.
