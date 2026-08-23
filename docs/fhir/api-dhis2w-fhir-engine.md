# FHIR evaluation engine (`dhis2w_fhir_engine`)

`dhis2w_fhir_engine` is the package behind the `d2w-fhir-engine` console script: FHIRPath, CQL, and
ELM evaluation over FHIR data, with clinical quality measure evaluation on top, and the R4 resource
models everything else in this repository reads FHIR through. It carries no DHIS2 dependency and no
web framework: it evaluates expressions over FHIR-shaped JSON and returns values.

It is the FHIR foundation of the workspace rather than a leaf of it. `dhis2w-fhir` and
`dhis2w-fhir-serve` both depend on it, and `dhis2w_fhir.r4` is a facade re-exporting the models
defined here - so `Patient` imported from either path is one class, and a document a generator built
is a document an evaluator reads without a conversion step in between.

The grammar, parser, AST, and evaluator layers know nothing about any particular FHIR release.
FHIRPath is normative and CQL is 1.5, and neither names a version. Everything that does bind to a
release lives under `dhis2w_fhir_engine.r4` and reaches the neutral core as a `FhirVersionBinding`
value, so a later release lands as a sibling subpackage rather than a fork of the evaluator. Importing
the package installs R4 as the binding evaluators use when a caller supplies none, which is why every
example below passes no binding at all.

The four guides that teach what these names do are
[FHIRPath](501-fhirpath.md), [CQL](501-cql.md), [Quality measures](501-measures.md), and
[The FHIR version binding](501-version-binding.md). Nine runnable examples live in
[`examples/fhir/engine/`](https://github.com/winterop-com/dhis2w-utils/tree/main/examples/fhir/engine).

## When to reach for it

- Answer a question about one FHIR resource or one Bundle without writing JSON traversal code
  (`FHIRPathEvaluator.evaluate`, `evaluate_boolean`, `unwrap_primitives`) - see
  [FHIRPath](501-fhirpath.md).
- State clinical logic once, as a named and versioned library, and evaluate it against data
  (`CQLEvaluator`, `CQLLibrary`, `compile_library`, `evaluate`) - see [CQL](501-cql.md).
- Give a library data to read, out of a Bundle or a list of resources, with retrieves narrowed to one
  patient (`BundleDataSource`, `PatientBundleDataSource`, `InMemoryDataSource`, `FHIRDataSource`).
- Score a quality measure over a population and get a FHIR R4 `MeasureReport` back
  (`MeasureEvaluator`, `MeasureReport`, `MeasureScoring`, `PopulationType`, `MeasureGroup`,
  `MeasurePopulation`, `GroupResult`, `PatientResult`, `PopulationCount`, `StratifierResult`) - see
  [Quality measures](501-measures.md).
- Publish a library as ELM so another implementation can run it, or run ELM another implementation
  compiled (`ELMSerializer`, `ELMLoader`, `ELMEvaluator`, `ELMLibrary`).
- Resolve a code against a ValueSet, or ask which codes a ValueSet holds, with no server running
  (`InMemoryTerminologyService`, `ValidateCodeRequest`, `MemberOfRequest`, `SubsumesRequest`,
  `ValueSet`, `Coding`, `CodeableConcept`) - or against a real terminology server
  (`FHIRTerminologyService`).
- Build or read an R4 resource as a typed, closed model, and hand it straight to an evaluator
  (`Patient`, `Bundle`, `QuestionnaireResponse`, `Composition`, `Observation`, `Extension`,
  `Reference`, `CodeableConcept`, `Coding`, and the rest of `dhis2w_fhir_engine.r4.resources`).
- Bind the engine to a FHIR release, or ask which release it is bound to (`FhirVersionBinding`,
  `R4_BINDING`, `NEUTRAL_BINDING`, `default_binding`, `set_default_binding`, `BuiltinCqlLibrary`) -
  see [The FHIR version binding](501-version-binding.md).

## Worked example - one expression, one library, one measure

```python
from dhis2w_fhir_engine import CQLEvaluator, FHIRPathEvaluator, unwrap_primitives
from dhis2w_fhir_engine.r4 import BundleDataSource, MeasureEvaluator

patient = {"resourceType": "Patient", "id": "child-1", "gender": "female", "birthDate": "2023-02-11"}

unwrap_primitives(FHIRPathEvaluator().evaluate("Patient.birthDate", patient))
# ['2023-02-11']

bundle = {"resourceType": "Bundle", "type": "collection", "entry": [{"resource": patient}]}
evaluator = CQLEvaluator(data_source=BundleDataSource(bundle))
evaluator.compile("""
    library Coverage version '1.0'
    using FHIR version '4.0.1'
    define "Children": [Patient]
""")
evaluator.evaluate_definition("Children")
# [{'resourceType': 'Patient', 'id': 'child-1', ...}]

measure = MeasureEvaluator(data_source=BundleDataSource(bundle))
measure.load_measure("""
    library Coverage version '1.0'
    using FHIR version '4.0.1'
    context Patient
    define "Initial Population": true
    define "Denominator": "Initial Population"
    define "Numerator": exists [Observation]
""")
measure.evaluate_population([patient]).to_fhir()["resourceType"]
# 'MeasureReport'
```

## Reference

### The FHIR version binding

The whole of the engine's version knowledge, as a value: the patient-reference element paths per
resource type, the canonical base profile URLs `conformsTo()` compares against, and the built-in CQL
libraries. Evaluators receive one and never import a version subpackage.

::: dhis2w_fhir_engine.binding

### Evaluation context and types

What an evaluation carries with it - the resource in scope, the reference resolver, the terminology
provider - and the value types FHIRPath and CQL answer with.

::: dhis2w_fhir_engine.engine.context

::: dhis2w_fhir_engine.engine.types

::: dhis2w_fhir_engine.engine.exceptions

### FHIRPath

The smaller language: paths, filters, and functions over one resource or one collection. Every
expression answers with a collection, which is why `unwrap_primitives` exists - it strips the
extension-carrying wrapper off FHIR primitives and leaves plain Python values.

::: dhis2w_fhir_engine.engine.fhirpath

::: dhis2w_fhir_engine.engine.fhirpath.evaluator

### The function registry

Every FHIRPath and CQL function the engine implements, registered on one shared registry that a
caller can extend.

::: dhis2w_fhir_engine.engine.functions

### CQL

The bigger language: a named, versioned library of definitions evaluated against a data source. The
evaluator compiles source into a `CQLLibrary` and answers definitions by name; the context holds the
subject in scope, the query aliases, the parameters, and the definition cache.

::: dhis2w_fhir_engine.engine.cql

::: dhis2w_fhir_engine.engine.cql.evaluator

::: dhis2w_fhir_engine.engine.cql.library

::: dhis2w_fhir_engine.engine.cql.context

::: dhis2w_fhir_engine.engine.cql.types

### Library resolution and plugins

Where an `include` finds the library it names, and how a caller adds functions of their own.

::: dhis2w_fhir_engine.engine.cql.library_resolver

::: dhis2w_fhir_engine.engine.cql.plugins

### ELM

CQL after compilation, as the standardised JSON tree. The serializer writes it, the loader reads it,
and the evaluator runs it - so a library authored here publishes for other implementations and a
library compiled elsewhere runs here.

::: dhis2w_fhir_engine.engine.elm

::: dhis2w_fhir_engine.engine.elm.serializer

::: dhis2w_fhir_engine.engine.elm.loader

::: dhis2w_fhir_engine.engine.elm.evaluator

::: dhis2w_fhir_engine.engine.elm.models

### Units

UCUM quantity arithmetic and conversion, used wherever a CQL expression compares two measurements.

::: dhis2w_fhir_engine.engine.units

### FHIR R4: the binding

The R4 facts the neutral core consumes, and the binding importing `dhis2w_fhir_engine` installs as
the default.

::: dhis2w_fhir_engine.r4.binding

### FHIR R4: resource models

The typed R4 resources: `Patient`, `Condition`, `AllergyIntolerance`, `Observation`, `Composition`
and the document vocabulary; `Immunization` and `ImmunizationProtocolApplied`, which a patient
summary's one mapped section is built from; `Questionnaire`, `QuestionnaireResponse` and the capture
vocabulary;
`Bundle`, `CapabilityStatement`, `Parameters`, `OperationOutcome`; and the elements they are built
from - `Extension`, `Reference`, `Coding`, `CodeableConcept`, `Identifier`, `Meta`, `Narrative`.

Every model is closed (`extra="forbid"`) and frozen, and every optional field defaults to `None`, so
`model_dump_json(exclude_none=True, by_alias=True)` reproduces the wire document key for key. The
open `JsonResource` is the single exception, for a document carried through verbatim. `dhis2w_fhir.r4`
re-exports this whole family for capture code; the terminology models in
`dhis2w_fhir_engine.r4.terminology` are a separate, open family for the terminology-service
operations, so `Coding`, `CodeableConcept`, and `ValueSet` exist in both places - import each from its
own module.

::: dhis2w_fhir_engine.r4.resources

### The typed-model boundary

Every public entry point that ingests a FHIR resource - `EvaluationContext` and the CQL contexts, the
FHIRPath, CQL, and ELM evaluators, the data sources, `MeasureEvaluator` - accepts either the wire dict
or a pydantic model of it. A model is dumped exactly once, here, and evaluation below the boundary
reads plain dicts. The dump is a fresh structure, so nothing the engine does reaches back into the
caller's model.

```python
from dhis2w_fhir_engine import FHIRPathEvaluator
from dhis2w_fhir_engine.r4.resources import HumanName, Patient

patient = Patient(id="child-1", gender="female", name=[HumanName(family="Kamara", given=["Aminata"])])
FHIRPathEvaluator().evaluate("Patient.name.given", patient)
# ['Aminata']
```

::: dhis2w_fhir_engine.ingest

### FHIR R4: data sources

What a retrieve reads. Each indexes resources by type and answers `[Immunization]` and its narrowed
forms out of memory; under a patient context, each filters to that person's records by the reference
element the binding states for the type.

::: dhis2w_fhir_engine.r4.datasource

### FHIR R4: measure evaluation

Populations, scoring, and the report - the typed result plus `to_fhir()`, which renders it as a FHIR
R4 `MeasureReport`.

::: dhis2w_fhir_engine.r4.measure

### FHIR R4: terminology

Code validation, value set membership, and subsumption - answered in memory from loaded ValueSets, or
against a real terminology server.

::: dhis2w_fhir_engine.r4.terminology

::: dhis2w_fhir_engine.r4.terminology.models

::: dhis2w_fhir_engine.r4.terminology.service

### FHIR R4: built-in libraries

The CQL libraries the R4 binding ships, so `include FHIRHelpers version '4.0.1'` needs no library
path.

::: dhis2w_fhir_engine.r4.builtins

### Command line

The `d2w-fhir-engine` console script: one Typer app mounting `fhirpath`, `cql`, and `elm` over the
same engine.

::: dhis2w_fhir_engine.cli

::: dhis2w_fhir_engine.cli.fhirpath

::: dhis2w_fhir_engine.cli.cql

::: dhis2w_fhir_engine.cli.elm

### Package surface

The names below re-export from `dhis2w_fhir_engine` itself.

::: dhis2w_fhir_engine
    options:
      members: false

::: dhis2w_fhir_engine.r4
    options:
      members: false
