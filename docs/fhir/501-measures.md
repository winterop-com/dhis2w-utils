# Quality measures

**Who this is for:** someone who knows DHIS2 indicators and has never scored a
clinical quality measure. Read [CQL](501-cql.md) first: a measure is a CQL library
with four conventions on top, and this page assumes you know what a retrieve and a
context are.

**Before you start:** `uv add dhis2w-fhir-engine`, or `uv sync` inside this
repository. Everything here runs against inline data; the last section needs a
seeded DHIS2 instance.

**You will be able to:**

- name the populations a measure declares and say who is in each
- choose between proportion, ratio, and cohort scoring
- run `MeasureEvaluator` over a population and read the typed report
- render that report as a FHIR R4 `MeasureReport`
- score a measure over a real DHIS2 cohort, and see where the DHIS2 knowledge
  starts and stops

## A measure is a fraction whose halves are logic

A DHIS2 indicator has a numerator expression and a denominator expression. So does
a quality measure. The difference is that a measure is precise about *who* is in
each half, and it says so with named populations rather than with a single
expression per half.

Five names carry almost every measure:

| Population | Who it is |
| --- | --- |
| **Initial population** | Everyone the measure looks at, before any narrowing. |
| **Denominator** | Who the measure holds to account. |
| **Denominator exclusion** | People removed from the denominator outright - they should never have been counted. |
| **Numerator** | The ones who met the measure. |
| **Numerator exclusion** | People removed from the numerator, but *left in* the denominator. |

The two exclusions are the reason this vocabulary exists rather than one fraction.
A child with a documented contraindication belongs in neither half - that is a
denominator exclusion. A dose recorded twice should count once - that is a
numerator exclusion, and the child stays in the denominator either way. Written as
one expression, those two cases look identical; written as populations, they do
not.

## Writing one

A measure is a CQL library with `context Patient` and a definition named for each
population:

```cql
library MeaslesCoverage version '1.0'
using FHIR version '4.0.1'

context Patient

define "Initial Population":
    true

define "Denominator":
    "Initial Population"

define "Denominator Exclusion":
    Patient.gender = 'unknown'

define "Numerator":
    exists [Immunization]
```

`context Patient` is what makes this a measure rather than a report: the library is
evaluated **once per person**, and every retrieve inside it sees only that person's
records. `exists [Immunization]` therefore asks "does *this* child have a dose",
not "does anyone".

`MeasureEvaluator` finds each population by the conventional definition name, so
nothing above needs wiring:

```python
from dhis2w_fhir_engine.r4 import BundleDataSource, MeasureEvaluator, MeasureScoring

data_source = BundleDataSource(bundle)
evaluator = MeasureEvaluator(data_source=data_source)
evaluator.set_scoring(MeasureScoring.PROPORTION)
evaluator.load_measure(MEASURE_SOURCE)
```

When you want the groups declared explicitly rather than by convention -
several groups, or names that do not follow it - `add_population` and
`add_stratifier` state them directly.

## Scoring

The scoring rule says what the counts mean.

| Scoring | What it reports |
| --- | --- |
| `PROPORTION` | Numerator divided by denominator, as a fraction. Coverage measures. |
| `RATIO` | Two counts related to each other, where neither is a subset of the other. |
| `COHORT` | Who qualified. Membership is the whole answer; there is no fraction. |
| `CONTINUOUS_VARIABLE` | An observation aggregated over a measure population. |

The engine computes a `measure_score` for proportion measures. For a cohort the
score is `None`, deliberately - the populations *are* the report:

```
measure MeaslesCoverage, scored as a proportion
  counts    {"initial-population": 4, "denominator": 4, "denominator-exclusion": 0, "numerator": 3}
  score     0.75

the same library scored as a cohort:
  counts    {"initial-population": 4, "denominator": 4, "denominator-exclusion": 0, "numerator": 3}
  score     None   (a cohort reports membership, not a fraction)
```

Same library, same memberships, different question asked of them.

## Running it

`evaluate_population` takes the people to evaluate and returns a typed report:

```python
report = evaluator.evaluate_population(patients, data_source=data_source)
group = report.groups[0]
```

The report carries the counts, and for each population the identifiers of the
people in it:

```
measure MeaslesCoverage, scored as a proportion
4 people evaluated, one at a time under `context Patient`

population              n   who
  initial-population      4   child-1, child-2, child-3, child-4
  denominator             4   child-1, child-2, child-3, child-4
  denominator-exclusion   0   -
  numerator               3   child-1, child-2, child-3

measure score = numerator / denominator = 3 / 4 = 0.75
```

Naming the members, not just counting them, is what makes a measure auditable. A
number that says 3 of 4 is a claim; a number that also names the fourth child is a
worklist.

The report also holds the per-person decision, which is what you read when a count
surprises you:

```
per person, as the evaluator decided it:
  child-1    initial-population, denominator, numerator
  child-2    initial-population, denominator, numerator
  child-3    initial-population, denominator, numerator
  child-4    initial-population, denominator
```

`evaluate_patient` answers the same question for one person, when you want to
explain a single case rather than score a cohort.

## The FHIR MeasureReport

`to_fhir()` renders the typed report as a FHIR R4 `MeasureReport` - the resource an
aggregator, a registry, or a dashboard expects:

```
to_fhir() -> a MeasureReport, status complete, type summary
  measure   MeaslesCoverage
  counts    {"initial-population": 4, "denominator": 4, "denominator-exclusion": 0, "numerator": 3}
  score     0.75
```

That resource is the deliverable. The logic stays in the library, published and
versioned; the answer travels as FHIR, and the receiving system needs no CQL engine
to read it.

## From the command line

`cql measure` scores a measure without Python. **A Bundle behind `--data` supplies
both halves of the run: every `Patient` entry is a person to evaluate, and the whole
Bundle is the data source the numerator retrieves from.** The measure above is
[`examples/fhir/engine/measles-coverage.cql`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/engine/measles-coverage.cql)
and the clinic is
[`clinic.json`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/engine/clinic.json)
beside it:

```console
$ d2w-fhir-engine cql measure measles-coverage.cql --data clinic.json
Measure: measles-coverage.cql
Evaluating 4 patient(s)...

          Group: default
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Population            ┃  Count ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ initial-population    │      4 │
│ denominator           │      4 │
│ denominator-exclusion │      0 │
│ numerator             │      3 │
│ Score                 │ 75.00% │
└───────────────────────┴────────┘
```

Four children, three with a dose recorded: the same 3 of 4 the Python run above
scores, from the command line and against the same clinic.

`--patients` reads a directory of Patient JSON files instead. That names who is
evaluated but supplies no data source, so a numerator written as a retrieve finds
nothing and the measure scores `0.00%` - reach for `--patients` when the people
carry their own answer, and for a Bundle when the numerator has to look something
up. `--output` writes the FHIR `MeasureReport` to disk, and `--verbose` adds the
stratifier results.

## Scoring a real DHIS2 cohort

The engine has no DHIS2 dependency. It evaluates expressions over FHIR-shaped JSON
and knows nothing about programs, stages, or data elements - which is what makes the
end-to-end example worth reading: **everything DHIS2-specific happens above the
engine, and the engine sees only FHIR.**

Three steps:

1. **Read.** One page of Child Programme (`IpHINAT79UW`) tracked entities off the
   instance, with their enrollments and the weight data values recorded on their
   events.
2. **Map.** Each tracked entity becomes a `Patient`; each weight data value becomes
   an `Observation`; both go into one collection `Bundle`.
3. **Score.** A measure whose numerator is "has a weight recorded", evaluated once
   per child.

Against the seeded Sierra Leone demo database:

```console
$ uv run python examples/fhir/engine/e2e_measure_from_dhis2.py
reading Child Programme (IpHINAT79UW) tracked entities from http://localhost:8080
  12 tracked entities, 22 weight data values
  11 of those children carry at least one weight

mapped to a collection Bundle of 34 FHIR resources
  one Patient per tracked entity, one Observation per weight data value

measure Dhis2ChildProgrammeWeightRecorded, scored as a proportion
  denominator  12   every mapped tracked entity
  numerator    11   those with a weight recorded on a DHIS2 event
  score        0.9167

to_fhir() -> a MeasureReport citing measure Dhis2ChildProgrammeWeightRecorded
```

The example recomputes the DHIS2-side answer in Python before asking the engine
anything, and fails loudly if the two disagree - so it is a check on the mapping,
not only a demonstration of it.

One detail in that example is a workaround rather than a design: the tracker read
orders by `createdAt`, not by `trackedEntity`, because ordering by the identifier
answers `409 E7145` with an ambiguous column reference on 2.43.1. See
[`BUGS.md`](https://github.com/winterop-com/dhis2w-utils/blob/main/BUGS.md) entry
97.

## The DHIS2 payoff: indicators as computable measures

That example maps a cohort by hand. The destination is that a guide carries the
measures itself.

Today a DHIS2 indicator's numerator and denominator exist only as DHIS2
expressions, and a generated Implementation Guide carries no computable measure at
all: a consumer receives the forms, the terminology, and the data, and has to
reimplement the arithmetic to know what any of it means.

The target shape is a `generate measures` target beside the existing ones. Each
selected indicator becomes a FHIR `Measure` - percentage indicators scored as
`proportion`, per-thousand as `ratio`, plain sums as `cohort` - whose population
criteria are real CQL in an attached `Library`. A consumer could then evaluate the
indicator without DHIS2's analytics engine, which is the difference between
publishing numbers and publishing a definition.

Everything on this page is the second half of that: the parser, the evaluator, the
population vocabulary, and the `MeasureReport` writer all exist and are what a
generated `Library` would be evaluated by. What does not exist yet is the compiler
from a DHIS2 indicator expression to CQL, and that is the actual work.

The design record for it is the **Mid-term** section of the FHIR roadmap - see
[Computable measures: DHIS2 indicators as FHIR `Measure` + CQL](design/roadmap.md#92-mid-term),
which states the scoring mapping, the doctrine that the parser layer derives from
the official HL7 ANTLR grammars, and the decisions still reserved to the owner.

## The runnable versions

| File | Shows |
| --- | --- |
| [`measure_report.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/engine/measure_report.py) | The populations, both scorings, the per-person decisions, and `to_fhir()` |
| [`e2e_measure_from_dhis2.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/engine/e2e_measure_from_dhis2.py) | Read a DHIS2 cohort, map it to FHIR, score it, check the counts against DHIS2's own records |

The first needs nothing running. The second needs `make dhis2-run` and reads
`DHIS2_URL`, `DHIS2_USERNAME`, and `DHIS2_PASSWORD`.

The Python surface is documented in
[the `dhis2w_fhir_engine` API reference](api-dhis2w-fhir-engine.md).
