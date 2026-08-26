# FHIRPath

**Who this is for:** someone who knows DHIS2 - data elements, programs, tracked
entities - and has never used an expression language. No FHIR fluency assumed
beyond [FHIR for DHIS2 people](101-fhir-concepts.md), and no prior exposure to
FHIRPath, XPath, JSONPath, or anything of that family.

**Before you start:** nothing installed but the engine. `uv add
dhis2w-fhir-engine`, or `uv sync` inside this repository. No DHIS2 instance, no
server, and no generated project: everything on this page runs against JSON you
paste in - with one exception, held to the end.
[Run it against a served project](#run-it-against-a-served-project) needs all
three.

**You will be able to:**

- read a FHIRPath expression and say what it will return before running it
- navigate a resource by path, and a whole `Bundle` by resource type
- filter with `where()` and reshape with the function vocabulary
- explain why every expression answers with a *collection*, and what an empty
  one means
- run an expression from the command line and from three lines of Python

## What FHIRPath is

FHIRPath is a small language for pointing at parts of a FHIR resource. That is
the whole of its job. It has no variables you assign, no loops, and no way to
change anything - an expression names a piece of a document and the engine hands
it back.

You already write something like it. A DHIS2 data value is addressed by a data
element and a category option combo; a program rule condition reads
`#{dataElementUid}` and compares it to something. FHIRPath is that idea with a
navigation syntax, over a document rather than a value table:

```
Patient.name.given
```

Read it left to right: start at the `Patient`, step into its `name` element, step
into each name's `given` element. Every step is an element name, and the dots
join them.

### The one rule that explains everything

**Every FHIRPath expression answers with a collection.** Never a bare value -
always a list, which may hold zero, one, or many entries.

This is not a quirk of the implementation; it is the language's central design
decision, and it exists because FHIR elements are so often repeating. A `Patient`
may carry three names, and each name may carry two given names. If a path
sometimes answered with a string and sometimes with a list, every expression
would need to know which case it was in. So it always answers with a list, and
the special cases disappear:

| What the resource holds | What `Patient.name.given` answers |
| --- | --- |
| Two given names on one name | `['Amara', 'Isata']` |
| One given name | `['Amara']` |
| No `name` element at all | `[]` |

The last row is the one worth pausing on. **A path that matches nothing is not an
error.** `Patient.deceasedBoolean` on a living patient answers `[]`, the same as
`Patient.thisElementDoesNotExist` would. FHIRPath's position is that "this
document does not carry that" is an answer, not a failure - which is exactly what
you want when reading documents from many systems that fill in different fields.

## Navigating one resource

Everything below runs against this Patient - a small immunisation clinic's
Patient record:

```json
{
  "resourceType": "Patient",
  "id": "child-1",
  "active": true,
  "name": [{"use": "official", "given": ["Amara", "Isata"], "family": "Kamara"}],
  "gender": "female",
  "birthDate": "2023-02-11"
}
```

Save it as `patient.json` and the command line will answer any of these:

```console
$ d2w-fhir-engine fhirpath eval "Patient.name.given" --resource patient.json
Results:
  [0] 'Amara'
  [1] 'Isata'
```

```console
$ d2w-fhir-engine fhirpath eval "Patient.deceasedBoolean" --resource patient.json
Empty result ([])
```

The second is the empty collection, printed as itself. Nothing failed.

You can hand the resource in inline instead of writing a file, which is what makes
this usable as a scratchpad:

```console
$ d2w-fhir-engine fhirpath eval "Patient.gender" --json '{"resourceType":"Patient","gender":"female"}'
'female'
```

And `--json-output` prints the collection as JSON, for a script that will read it:

```console
$ d2w-fhir-engine fhirpath eval "Patient.name.given.first()" --resource patient.json --json-output
[
  "Amara"
]
```

## Filtering with `where()`

A path takes every entry. `where(...)` takes the ones a condition holds for, and
the path keeps walking from whatever survived.

Suppose the Patient carries two identifiers - one the DHIS2 tracked entity
identifier, one a paper register number:

```json
"identifier": [
  {"system": "http://example.org/dhis2/trackedEntities", "value": "child-1"},
  {"system": "http://example.org/clinic/register", "value": "REG-1"}
]
```

`Patient.identifier.value` answers with both values, in document order:

```
['child-1', 'REG-1']
```

`where()` picks the one you meant:

```
Patient.identifier.where(system = 'http://example.org/clinic/register').value
```

```
['REG-1']
```

Note what happened to the path. `where()` filtered the `identifier` collection,
and `.value` then stepped into what was left. This composes as far as you like -
each step operates on the collection the previous step produced, and never on the
original resource.

### A boolean element is read for its value

`where(active)` keeps the records whose `active` element says `true`. A record
that says `"active": false` is dropped, the same as `where(active = true)` would
drop it - the element is read for what it says, not for the fact that it is
there. This is FHIRPath's singleton evaluation rule, and it applies wherever a
condition is read: `where()`, `all()`, `exists(...)`, `iif()`, `not()`, and
`and` / `or` / `xor` / `implies`.

The rule has two other halves worth knowing. A single item of any other type
reads as `true`, so `where(id)` keeps every record that has an `id` at all. And
an element the record never states is empty, not false, so `active and true` on
a record with no `active` answers `[]`. When you want presence rather than
value, ask for it: `where(active.exists())` keeps the record that says `false`.

## The function vocabulary

Functions are called with a dot, like a step. They reshape the collection rather
than navigating deeper into it.

| Expression | Answers | What it is for |
| --- | --- | --- |
| `Patient.name.family` | `['Kamara']` | plain navigation, for comparison |
| `Patient.name.given.first()` | `['Amara']` | take the first entry |
| `Patient.identifier.count()` | `[2]` | how many entries |
| `Patient.name.exists()` | `[True]` | did anything match? |
| `Patient.deceased.exists()` | `[False]` | the honest answer for an absent element |
| `Patient.name.select(given.first() & ' ' & family)` | `['Amara Kamara']` | build a new value per entry |
| `Patient.birthDate < @2024-01-01` | `[True]` | compare against a date literal |

Two of those deserve a note.

**`count()` and `exists()` still answer with collections** - `[2]`, not `2`. The
rule holds with no exceptions, which is why `unwrap_primitives` and
`evaluate_boolean` exist in the Python API below.

**`@2024-01-01` is a date literal.** The `@` is how FHIRPath says "what follows is
a date, not a string". `@2024-01-01T00:00:00` is a dateTime. This matters as soon
as you compare an element to a reporting period boundary.

## Navigating a Bundle

A `Bundle` is the shape a FHIR server hands back a set of resources in. Every
resource sits under `entry.resource`, of every type, mixed together and in no
guaranteed order.

So the first move of any expression over a Bundle is to say which type you meant.
That is `ofType()`:

```
Bundle.entry.resource.ofType(Patient).id
```

Against a Bundle of four children, four immunisation doses, two weights and one
organisation:

```
['child-1', 'child-2', 'child-3', 'child-4']
```

Without `ofType()`, `Bundle.entry.resource.id` would walk the `id` of every
resource of every type - all eleven - which is almost never what a question means.

From there the vocabulary is the same, and one expression reaches from the Bundle
down to a field on the resources it selected:

| Question | Expression | Answer |
| --- | --- | --- |
| How many children? | `Bundle.entry.resource.ofType(Patient).count()` | `[4]` |
| How many doses recorded? | `Bundle.entry.resource.ofType(Immunization).count()` | `[4]` |
| How many measles doses? | `Bundle.entry.resource.ofType(Immunization).where(vaccineCode.coding.code = '836383007').count()` | `[2]` |
| Who got them? | `Bundle.entry.resource.ofType(Immunization).where(vaccineCode.coding.code = '836383007').patient.reference` | `['Patient/child-1', 'Patient/child-2']` |
| Every recorded weight | `Bundle.entry.resource.ofType(Observation).valueQuantity.value` | `[9200, 8100]` |
| Family names of the girls | `Bundle.entry.resource.ofType(Patient).where(gender = 'female').name.family` | `['Kamara', 'Sesay', 'Koroma']` |
| Born after a cut-off | `Bundle.entry.resource.ofType(Patient).where(birthDate > @2023-06-01).id` | `['child-3', 'child-4']` |

The runnable version of that table is
[`examples/fhir/engine/fhirpath_over_bundle.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/engine/fhirpath_over_bundle.py),
which prints each question, its expression, and its answer.

## From Python

Three lines, and one of them is the import:

```python
from dhis2w_fhir_engine import FHIRPathEvaluator

patient = {"resourceType": "Patient", "name": [{"given": ["Amara", "Isata"], "family": "Kamara"}]}
FHIRPathEvaluator().evaluate("Patient.name.given", patient)
```

That answers with the collection, but with each FHIR primitive wrapped so its
extensions stay attached to it:

```
[_PrimitiveWithExtension('Amara'), _PrimitiveWithExtension('Isata')]
```

FHIR lets a primitive element carry extensions of its own, and a wrapper is how
that survives evaluation. When you want the plain Python values, unwrap them:

```python
from dhis2w_fhir_engine import FHIRPathEvaluator, unwrap_primitives

unwrap_primitives(FHIRPathEvaluator().evaluate("Patient.name.given", patient))
# ['Amara', 'Isata']
```

And when the question is a yes or a no - which is what a decision rule actually
asks - `evaluate_boolean` collapses the collection for you:

```python
evaluator = FHIRPathEvaluator()
evaluator.evaluate_boolean("Patient.name.exists()", patient)
# True
evaluator.evaluate_boolean("Patient.gender = 'male'", patient)
# None
```

That `None` is the collection rule surfacing one last time, and it is worth
knowing before it surprises you. The patient above carries no `gender`, so
`Patient.gender` is the empty collection, and comparing an empty collection to
anything is empty rather than false. `evaluate_boolean` reports that as `None` -
*the document does not say* - which is a different answer from `False`, *the
document says no*. Where the difference matters, ask `exists()` first.

One evaluator can answer any number of expressions against any number of
resources; nothing about it is bound to a document.

## Run it against a served project

Everything above evaluates a document you already hold. A running facade evaluates
one it holds, which is the difference between checking an expression and asking a
question of real data. `POST /evaluate` takes the expression and a context naming
the one resource it may reach:

```console
$ curl -s -X POST http://127.0.0.1:8123/evaluate \
    -H 'Content-Type: application/json' \
    -d '{"language": "fhirpath", "source": "Questionnaire.item.item.count()",
         "context": {"kind": "stored", "resource_type": "Questionnaire",
                     "resource_id": "BfMAe6Itzgt"}}' | jq -c '.results[0].values'
[31]
```

That is a DHIS2 data set's data elements counted without downloading the form. The
three context kinds are the whole of what an expression can reach: `inline` is the
document you posted, `stored` is one the served guide holds, and `registered` is one
tracked entity read live out of DHIS2. There is no fourth kind, no file path, and no
library directory.

An expression that will not parse answers `200` with the line and the column the
parser stopped on, never a `500` — a bad expression is a person's typing, not a
server failure.

| Run it | What it shows |
| --- | --- |
| [`examples/fhir/client/evaluate_stored_resource.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/evaluate_stored_resource.py) | The `stored` context: one form's sections, data elements and category-combination cells, each from one line, plus the 404 a resource nobody holds earns |
| [`examples/fhir/client/evaluate_via_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/evaluate_via_facade.py) | The `inline` context, a CQL library beside it, and a parse failure keeping its position |
| [`examples/fhir/cli/evaluate.sh`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/cli/evaluate.sh) | The same two addresses from curl, against a facade the script stands up itself |

[Serve the guide](201-serve.md) is how the facade those talk to gets started.

## Where this goes next

FHIRPath answers questions about *one document*. It cannot say "every child in the
district who was vaccinated last year", because it has no way to reach data it was
not handed and no way to name a reporting period.

That is what CQL adds, and CQL is written on top of FHIRPath - the navigation you
have just read is the navigation a CQL expression uses inside a retrieve. Read
[CQL](501-cql.md) next.

## The runnable versions

| File | Shows |
| --- | --- |
| [`examples/fhir/engine/fhirpath_basics.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/engine/fhirpath_basics.py) | Every expression on this page over one Patient, with the reason for each in the margin |
| [`examples/fhir/engine/fhirpath_over_bundle.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/engine/fhirpath_over_bundle.py) | `ofType()` and the Bundle table above, question by question |

Both run with `uv run python examples/fhir/engine/<name>.py` and need nothing
running.

The Python surface is documented in
[the `dhis2w_fhir_engine` API reference](api-dhis2w-fhir-engine.md).
