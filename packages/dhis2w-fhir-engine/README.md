# dhis2w-fhir-engine

FHIRPath, CQL, and ELM evaluation over FHIR data, with clinical quality measure evaluation.

The grammar, parser, AST, and evaluator layers know nothing about any particular FHIR release —
FHIRPath is normative and CQL is 1.5, and neither names a version. Everything that does bind to a
release lives under `dhis2w_fhir_engine.r4` and reaches the neutral core as a value, so a later
release lands as a sibling subpackage instead of a fork of the engine.

The package depends on `antlr4-python3-runtime`, `pydantic`, `typer`, and `rich`. It has no DHIS2
dependency and no web framework: it evaluates expressions over FHIR-shaped JSON and returns values.

## Install

```bash
uv add dhis2w-fhir-engine        # or: pip install dhis2w-fhir-engine
```

## Quickstart — FHIRPath over a resource

```python
from dhis2w_fhir_engine import FHIRPathEvaluator

patient = {
    "resourceType": "Patient",
    "active": True,
    "name": [{"given": ["Ada"], "family": "Lovelace"}],
    "birthDate": "1815-12-10",
}

evaluator = FHIRPathEvaluator()
print(evaluator.evaluate("Patient.name.given.first()", patient))
print(evaluator.evaluate_boolean("Patient.active and Patient.birthDate < @1900-01-01", patient))
```

## Quickstart — CQL against a Bundle

`retrieve` expressions (`[Patient]`, `[Condition: "Diabetes"]`) read through a data source. The R4
data sources index a Bundle or a list of resources and answer retrieves against it.

```python
from dhis2w_fhir_engine import CQLEvaluator
from dhis2w_fhir_engine.r4 import BundleDataSource

bundle = {
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [
        {"resource": {"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"}},
        {"resource": {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"}}},
    ],
}

evaluator = CQLEvaluator(data_source=BundleDataSource(bundle))
evaluator.compile("""
    library Example version '1.0'
    using FHIR version '4.0.1'

    define Patients: [Patient]
    define HasCondition: exists [Condition]
""")
print(evaluator.evaluate_definition("HasCondition"))
```

`FHIRHelpers` 4.0.1 is resolvable out of the box — `include FHIRHelpers version '4.0.1'` needs no
library path. Pass `include_builtins=False` to leave it out.

## Quickstart — a quality measure

```python
from dhis2w_fhir_engine.r4 import BundleDataSource, MeasureEvaluator

evaluator = MeasureEvaluator(data_source=BundleDataSource(bundle))
evaluator.load_measure("""
    library CoverageMeasure version '1.0'
    using FHIR version '4.0.1'
    context Patient

    define "Initial Population": true
    define "Denominator": "Initial Population"
    define "Numerator": exists [Observation]
""")

report = evaluator.evaluate_population(patients)
print(report.groups[0].populations["numerator"].count)
print(report.to_fhir())  # a FHIR R4 MeasureReport
```

`MeasureEvaluator` finds each population by the conventional CQL definition name (`Initial Population`,
`Denominator`, `Numerator`, the exclusion and exception variants), or you can declare the groups yourself
with `add_population` and `add_stratifier`. `evaluate_patient` returns one patient's population membership;
`evaluate_population` aggregates and computes the measure score.

## ELM

The engine reads and writes ELM, the standardised JSON form of a compiled CQL library, so libraries
compiled elsewhere run here and libraries written here export for other implementations.

```python
from dhis2w_fhir_engine import ELMEvaluator, ELMLoader, ELMSerializer

library = ELMLoader().load_file("library.json")  # run ELM produced by another compiler
result = ELMEvaluator().evaluate_definition("Numerator")

elm_json = ELMSerializer().serialize_library_json(cql_source)  # export CQL as ELM
```

## Command line

The console script `d2w-fhir-engine` mounts three sub-apps over the same engine.

```bash
d2w-fhir-engine fhirpath eval "Patient.name.given" --resource patient.json
d2w-fhir-engine fhirpath parse-file expressions.txt
d2w-fhir-engine fhirpath repl

d2w-fhir-engine cql eval "1 + 2 * 3"
d2w-fhir-engine cql run library.cql --data bundle.json
d2w-fhir-engine cql check library.cql
d2w-fhir-engine cql measure measure.cql --data bundle.json
d2w-fhir-engine cql export library.cql --output library.elm.json
d2w-fhir-engine cql repl

d2w-fhir-engine elm load library.elm.json
d2w-fhir-engine elm run library.elm.json --define Numerator
d2w-fhir-engine elm convert library.cql --output library.elm.json
```

Each sub-app also carries `parse`, `ast`, `tokens`, `show`, and `validate` for inspecting a source
before running it.

## FHIR version binding

`FhirVersionBinding` is the whole of the engine's version knowledge: the patient-reference element
paths per resource type, the canonical base profile URLs `conformsTo()` compares against, and the
built-in CQL libraries. `dhis2w_fhir_engine.r4` builds one for R4 and importing the package installs
it as the default, so nothing has to be passed for R4 work.

```python
from dhis2w_fhir_engine import CQLEvaluator, FhirVersionBinding
from dhis2w_fhir_engine.r4 import R4_BINDING

CQLEvaluator(fhir_binding=R4_BINDING)  # explicit; the same binding is the default
```

An evaluator receives its binding as a value and never imports a version subpackage, so a release
subpackage only has to export a `FhirVersionBinding` and, where the wire shapes differ, its own data
sources and measure report writer.

## Layout

```
dhis2w_fhir_engine/
  binding.py        FhirVersionBinding and the default-binding registry
  cli/              one Typer app: fhirpath, cql, elm
  grammars/         the HL7 cql.g4 and fhirpath.g4 grammars
  generated/        ANTLR output for both grammars (excluded from every linter)
  engine/           version-neutral: context, types, functions, fhirpath/, cql/, elm/, units/
  r4/               FHIR R4: binding, data sources, measure evaluation, terminology, FHIRHelpers
```

## Tests

```bash
cd packages/dhis2w-fhir-engine
uv run pytest -q                        # unit suite plus the HL7 CQL and FHIRPath compliance suites
uv run pytest -q tests/e2e_dhis2 -m slow   # end-to-end against a running local DHIS2 stack
```

The compliance suites under `tests/compliance/` run the official HL7 test XML for CQL and for
FHIRPath R4. The `tests/e2e_dhis2/` group evaluates FHIRPath, CQL retrieves, and a measure over FHIR
resources built from seeded DHIS2 data, and skips with a stated reason when the stack is down.
