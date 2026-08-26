# FHIR evaluation engine examples

**Expressions over FHIR data** — `dhis2w-fhir-engine` from your own code: FHIRPath to navigate a
resource, CQL to state clinical logic, ELM to publish that logic, and a measure evaluator to score a
population into a FHIR R4 `MeasureReport`.

Written for someone who knows DHIS2 and has never used an expression language. Start at the top of
the first table and read down: every example states the plain question first and the expression that
answers it second.

The narrative these sit under is the [501 pages of the `d2w fhir` guide
series](../../../docs/fhir/index.md) — [FHIRPath](../../../docs/fhir/501-fhirpath.md),
[CQL](../../../docs/fhir/501-cql.md), [quality measures](../../../docs/fhir/501-measures.md), and
[the FHIR version binding](../../../docs/fhir/501-version-binding.md).

## What every example here is

1. **Small, self-contained, and about one feature.** An example that teaches three things is three
   examples.
2. **Instant, and offline.** The engine has no DHIS2 dependency and no web framework. Eight of the
   nine examples read the inline Bundle in [`_bundle.py`](_bundle.py) and need nothing running — no
   profile, no server, no project on disk.
3. **Verified.** `make verify-examples` runs every file in this directory on every pass.

## Navigate data with FHIRPath

FHIRPath is the smaller language: it points at parts of a resource and answers with a collection.

| File | Shows |
| --- | --- |
| [`fhirpath_basics.py`](fhirpath_basics.py) | Paths, `where()`, `first()`, `count()`, `exists()` over one Patient — and why every answer is a collection |
| [`fhirpath_over_bundle.py`](fhirpath_over_bundle.py) | `ofType()` over a whole Bundle: pick a resource type out of the mix, filter it, and count what is left |

## State clinical logic in CQL

CQL is the bigger language: a named, versioned library of definitions, evaluated against a data
source rather than a single resource.

| File | Shows |
| --- | --- |
| [`cql_library_structure.py`](cql_library_structure.py) | What each header line declares — `library`, `using`, `include`, `codesystem`, `valueset`, `code`, `parameter` — and that nothing runs until a definition is asked for by name |
| [`cql_retrieves.py`](cql_retrieves.py) | `[Patient]` and `[Immunization]`, then the same retrieves under `context Patient`: one evaluation per person, each seeing only their own records |
| [`cql_terminology.py`](cql_terminology.py) | A ValueSet scoping a retrieve, resolved outside the library — plus `$validate-code` and `memberOf` asked of the terminology service directly |
| [`cql_intervals.py`](cql_intervals.py) | Interval literals, closed and open bounds, the timing vocabulary, and a `"Measurement Period"` parameter the caller can replace without touching the library |

## Score a quality measure

| File | Shows |
| --- | --- |
| [`measure_report.py`](measure_report.py) | The populations (initial population, denominator, exclusion, numerator), proportion versus cohort scoring, and `to_fhir()` rendering a FHIR R4 `MeasureReport` |
| [`elm_round_trip.py`](elm_round_trip.py) | CQL compiled to ELM JSON and run back from the ELM — the interchange format, with every answer compared across both evaluators |

## Against a real DHIS2 instance

| File | Shows |
| --- | --- |
| [`e2e_measure_from_dhis2.py`](e2e_measure_from_dhis2.py) | The whole chain: read a seeded Child Programme cohort, map tracked entities to `Patient` and weight data values to `Observation`, score a measure, check the counts against DHIS2's own records |

This is the only example here that talks to DHIS2, and the DHIS2 knowledge lives entirely in the
file — the engine sees FHIR and nothing else. It reads `DHIS2_URL`, `DHIS2_USERNAME`, and
`DHIS2_PASSWORD`; `make verify-examples` sources those from the seeded credentials file, and skips
the example with the missing names stated when they are absent.

## The data

[`_bundle.py`](_bundle.py) holds one inline FHIR R4 collection Bundle: four children, four doses
across three of them, two weights. Those counts are small enough to check the engine's answers by
eye, which is the point — an example that reports 3 of 4 lets you find the fourth child yourself.

[`clinic.json`](clinic.json) is that same Bundle written out, for the command line — the `d2w-fhir-engine`
sub-apps read files, not Python modules. [`coverage.cql`](coverage.cql) counts children and asks
whether any dose was recorded; [`measles-coverage.cql`](measles-coverage.cql) is the quality measure,
one definition per population. Both are the libraries the guide's command-line transcripts run.

## Prerequisites

```bash
uv sync        # the engine is a workspace member; nothing else is needed
```

Then any example runs on its own:

```bash
uv run python examples/fhir/engine/fhirpath_basics.py
```

Only `e2e_measure_from_dhis2.py` needs more:

```bash
make dhis2-run                                       # DHIS2 + seeded auth
set -a; . infra/home/credentials/.env.auth; set +a
uv run python examples/fhir/engine/e2e_measure_from_dhis2.py
```

With no DHIS2 reachable it fails with one sentence naming what is missing and how to supply it —
never a traceback.

## The command line

Everything here has a command-line twin. The engine ships the `d2w-fhir-engine` console script with
`fhirpath`, `cql`, and `elm` sub-apps. Run these from this directory and they read the files beside
them:

```bash
d2w-fhir-engine fhirpath eval "Bundle.entry.resource.ofType(Patient).count()" --resource clinic.json
d2w-fhir-engine cql run coverage.cql --data clinic.json
d2w-fhir-engine cql measure measles-coverage.cql --data clinic.json
d2w-fhir-engine elm convert coverage.cql --quiet
```

`--data` reads by one rule: **a Bundle becomes the data source retrieves reach, any other resource
becomes the context the evaluation is about.** That is why `cql run coverage.cql --data clinic.json`
answers `Child Count 4` rather than `0`.
