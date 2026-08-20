# The FHIR version binding

**Who this is for:** anyone who has read [FHIRPath](501-fhirpath.md) and
[CQL](501-cql.md) and wants to know why the engine never asks which FHIR release
it is running against - and what would have to happen for it to run against R5.

**Before you start:** nothing beyond the two pages above. This one is about a
seam, not a feature.

**You will be able to:**

- say which parts of the engine are FHIR-version-neutral and which are not
- read a `FhirVersionBinding` and name every fact it carries
- explain why importing the package is enough for R4 to work
- say exactly what an R5 sibling subpackage would have to provide

## The problem a binding solves

FHIRPath is normative and CQL is 1.5. **Neither of them names a FHIR release.**
`Patient.name.given` is the same expression under R4 and R5; `[Immunization]` is
the same retrieve; `Interval[1, 10]` has nothing to do with FHIR at all.

But an engine that runs those expressions cannot be entirely release-blind,
because three questions come up during evaluation that only a release can answer:

1. **Which element on an `Immunization` points at its patient?** The engine needs
   this to narrow a retrieve under `context Patient`. On R4 it is
   `Immunization.patient`; the answer is per resource type, and it is a fact about
   a release rather than about the language.
2. **What is the canonical URL of the base profile for this resource type?**
   `conformsTo()` compares against it.
3. **Which CQL libraries are always resolvable?** `include FHIRHelpers version
   '4.0.1'` must resolve with no library path, and FHIRHelpers is written against a
   specific release.

The naive answer is to put those three facts into the evaluator and add `if
version == "R5"` branches later. The engine does the opposite: it takes them as a
**value**, handed in by the caller.

## The value

`FhirVersionBinding` is the whole of the engine's version knowledge. It is a
frozen pydantic model with six fields and no behaviour beyond two lookups:

| Field | What it carries |
| --- | --- |
| `name` | Short release name - `'R4'`. |
| `fhir_version` | The full version string as it appears in `using FHIR version` - `'4.0.1'`. |
| `patient_reference_paths` | Per resource type, the element paths that reference the subject patient. |
| `default_patient_reference_paths` | The paths tried for resource types with no specific entry. |
| `profile_base_urls` | Per resource type, the canonical base StructureDefinition URL `conformsTo()` compares against. |
| `builtin_libraries` | CQL libraries always resolvable under this binding. |

Two accessors read it:

```python
from dhis2w_fhir_engine import default_binding

binding = default_binding()

binding.name, binding.fhir_version
# ('R4', '4.0.1')

binding.patient_paths_for("Immunization")
# ('patient.reference',)

binding.patient_paths_for("Observation")
# ('subject.reference', 'patient.reference')

binding.patient_paths_for("Whatever")
# ('subject.reference', 'patient.reference')   <- the defaults, for an unlisted type

binding.profile_url_for("Patient")
# 'http://hl7.org/fhir/StructureDefinition/Patient'

binding.profile_url_for("Whatever")
# None

[(library.name, library.version) for library in binding.builtin_libraries]
# [('FHIRHelpers', '4.0.1')]
```

The R4 binding lists 15 resource types with a specific patient-reference path and
10 with a base profile URL. An unlisted type falls back to the defaults rather than
failing, which is why a retrieve over a resource type the binding has never heard of
still narrows sensibly under a patient context.

## What is neutral and what is bound

The split is a directory boundary, and it is worth reading as one:

```
dhis2w_fhir_engine/
  binding.py        FhirVersionBinding and the default-binding registry   <- neutral
  grammars/         the HL7 cql.g4 and fhirpath.g4 grammars               <- neutral
  generated/        ANTLR output for both grammars                        <- neutral
  engine/           context, types, functions, fhirpath/, cql/, elm/, units/  <- neutral
  r4/               binding, data sources, measure evaluation, terminology, FHIRHelpers
```

**Neutral** means: the grammar, the parser, the AST, the evaluators, the function
registry, the type system, the interval and quantity arithmetic, and the ELM
reader and writer. None of that names a FHIR release, and none of it imports
`dhis2w_fhir_engine.r4`. An evaluator receives a binding as a value and never
reaches for a version subpackage.

**Bound** means everything under `r4/`: the binding itself, the data sources that
index R4 resources, the measure evaluator and its `MeasureReport` writer, the
terminology service, and the shipped FHIRHelpers 4.0.1 source.

The one place the two meet outside a caller's own code is the command-line app,
which imports `r4` because a command has to pick a data source for the user.

## Why R4 works with no arguments

Importing `dhis2w_fhir_engine` installs the R4 binding as the default:

```python
from dhis2w_fhir_engine import default_binding
from dhis2w_fhir_engine.r4 import R4_BINDING

default_binding() is R4_BINDING
# True
```

That is one line at the bottom of the package's `__init__` - `set_default_binding(R4_BINDING)` -
and it is the reason nothing on the previous three pages passed a binding anywhere.

You can pass one explicitly, and it is the same object:

```python
from dhis2w_fhir_engine import CQLEvaluator
from dhis2w_fhir_engine.r4 import R4_BINDING

evaluator = CQLEvaluator(fhir_binding=R4_BINDING)
evaluator.fhir_binding.name, evaluator.fhir_binding.fhir_version
# ('R4', '4.0.1')
```

Two other bindings matter. `NEUTRAL_BINDING` carries no version-bound facts at all -
its `fhir_version` is the empty string and it lists no patient reference paths - and
it is what a caller gets when no binding has been registered. `set_default_binding`
installs whichever binding a process should use when a caller passes none.

## What `conformsTo()` does with it

The one FHIRPath function that reads the binding directly:

```python
from dhis2w_fhir_engine import FHIRPathEvaluator, unwrap_primitives

patient = {"resourceType": "Patient", "id": "x"}
evaluator = FHIRPathEvaluator()

unwrap_primitives(evaluator.evaluate("Patient.conformsTo('http://hl7.org/fhir/StructureDefinition/Patient')", patient))
# [True]

unwrap_primitives(
    evaluator.evaluate("Patient.conformsTo('http://hl7.org/fhir/StructureDefinition/Observation')", patient)
)
# [False]
```

Nothing in the evaluator knows that `http://hl7.org/fhir/StructureDefinition` is the
R4 canonical base. It asks the binding for the resource type's profile URL and
compares. Under a different binding with a different base, the same expression
answers against that base instead.

## What an R5 sibling would provide

R5 is not shipped. This section is the contract it would meet, and it is short by
design - the point of the seam is that adding a release is additive.

A release subpackage `dhis2w_fhir_engine.r5` would export:

1. **A `FhirVersionBinding`.** `name='R5'`, `fhir_version='5.0.0'`, the
   patient-reference element paths where R5 moved them, the canonical profile base,
   and the FHIRHelpers written for 5.0.0. This is the required part.
2. **Its own data sources**, where the wire shapes differ enough that indexing an R5
   Bundle is not indexing an R4 one.
3. **Its own measure report writer**, where R5's `MeasureReport` differs from R4's.

And nothing else. Specifically, an R5 subpackage would **not** touch the grammar,
the parser, the AST, the evaluators, or the ELM layer, because none of those names a
release.

A caller would then choose per evaluator:

```python
from dhis2w_fhir_engine import CQLEvaluator
from dhis2w_fhir_engine.r5 import R5_BINDING  # not shipped

CQLEvaluator(fhir_binding=R5_BINDING)
```

or per process, with `set_default_binding(R5_BINDING)`.

## Why this is a repository-level rule, not a package detail

This split is the engine's own version axis, and it sits beside the one this
repository already runs on. `dhis2w-client` and `dhis2w-core` carry a hand-written
tree per DHIS2 major - `v41`, `v42`, `v43` - and a behaviour-changing edit lands in
all three. The engine carries a subpackage per FHIR release, and a new release lands
as a new subpackage.

The two axes are independent. A DHIS2 major says which wire shapes the client reads;
a FHIR release says which element on an `Immunization` points at its patient. Neither
constrains the other, and a change on one never forces a change on the other. That
independence is stated as an architectural axis in the repository's `CLAUDE.md`, so a
future contributor reaches for a sibling subpackage rather than a version branch
inside the evaluator.

## The runnable version

There is no example file for this page, and that is the point: nothing in the three
preceding example groups passes a binding, because importing the package installs
one. The snippets above are the whole of the surface.

The Python surface is documented in
[the `dhis2w_fhir_engine` API reference](api-dhis2w-fhir-engine.md#the-fhir-version-binding).
