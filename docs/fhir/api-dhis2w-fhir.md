# FHIR IG generation (`dhis2w_fhir`)

`dhis2w_fhir` is the package behind [`d2w fhir`](index.md): the `fhir.toml`
document, the emitters that turn DHIS2 metadata into an Implementation Guide - FSH for the
definitional artifacts, pre-built R4 JSON for the organisation-unit registry, the
option-set terminology, and the category terminology - and the DHIS2 period grammar they
share. It mounts onto the CLI
and the MCP server through the `dhis2.plugins` entry point, and every component symbol
re-exports from the top-level package, so
`from dhis2w_fhir import GenerateConfig, parse_period` keeps working however
the components are arranged internally. The R4 resource models are the one exception: they
live in `dhis2w_fhir.r4`, which is FHIR's own vocabulary rather than part of the plugin
surface.

## When to reach for it

- Read or write a project's `fhir.toml` from Python (`load_project`, `load_fhir_config`,
  `find_project_fhir_config`, `write_fhir_config`).
- Parse a DHIS2 ISO period into its type and date range, or walk backwards from a date
  (`parse_period`, `recent_periods`, `PERIOD_TYPE_DEFINITIONS`).
- Carry DHIS2 attribute values onto a generated resource (`AttributeValueIn`,
  `AttributeCodeIndex`, `resolve_attribute_code_index`, `attribute_value_extensions`).
- Build FSH artifacts without the CLI (`build_foundation_artifacts`,
  `build_questionnaire_artifacts`, `build_page_artifacts`) and sync them to disk
  (`sync_artifacts`).
- Build the pre-built R4 documents - the registry (`dhis2w_fhir.r4.Organization`,
  `dhis2w_fhir.r4.Location`), the option-set terminology
  (`build_option_set_artifacts`), and the category terminology
  (`build_category_artifacts`), the last two on `dhis2w_fhir.r4.CodeSystem` and
  `dhis2w_fhir.r4.ValueSet` - and sync them to disk (`sync_json_artifacts`), one
  owned directory per source.
- Map an option set's generated concept codes back to the DHIS2 option UID and
  option code (`build_option_set_concept_maps` for the `dhis2w_fhir.r4.ConceptMap`
  models, `build_option_set_concept_map_artifacts` for the JSON files that land in
  `CONCEPT_MAP_DIRECTORY`).
- Generate one target, or the whole guide, without the command
  (`generate_foundation`, `generate_option_sets`, `generate_categories`,
  `generate_questionnaires`, `generate_examples`, `generate_organisation_units`,
  `generate_pages`, `generate_full`). Each returns a `GenerateReport`, and each raises
  `BuildAbortingCodeError` or `BuildAbortingNameError` rather than writing a guide the IG
  publisher will die on hours later.
- Scaffold a project, or re-render one that already exists (`init_project`,
  `refresh_project`, `read_project_scaffold_state`, `ProjectScaffoldState`).
- Produce a validation report rather than only rendering one (`validate_codes`, with
  `resolve_validation_context`, `resolve_validation_scope`, and `resolve_code_source` for the
  three things a run has to decide first). `build_aborting_code` and `build_aborting_name`
  are the two predicates the report's error grade and the generate refusal share, so a
  caller can ask the same question either command asks; `display_code` renders a DHIS2 code
  for human eyes the way the report does.
- Ask the same question of the files a build publishes, with no instance behind it
  (`check_publishable_artifacts`, returning an `ArtifactCheckReport` of `ArtifactFinding`s).
  It reads a project's compiled resources, pre-built JSON, and FSH sources through those same
  two predicates, which is what `d2w fhir check-artifacts` and `make build` run.
- Run the conformance chain in process, or grade one phase of it on its own (`run_doctor`,
  `DoctorOptions`, `DoctorReport`, `render_doctor_markdown`, `phase_evidence`,
  `resolve_doctor_profile`, and the graders `grade`, `grade_capture`, `grade_forward`,
  `grade_oracle` over `DoctorFinding`, `CaptureOutcome`, and `FamilyOutcome`). Read
  `run_doctor`'s own docstring first: it writes a workspace, shells out to a compiler, and
  posts a corpus, which the graders do not.
- Assemble one person's International Patient Summary out of a projected subject and the
  doses somebody already read (`build_patient_summary`, `AssembledSummary`, `RecordedDose`,
  `summary_caveat`, `REQUIRED_SECTIONS`, `IpsSection`), and publish the section mapping
  behind it as a ConceptMap (`build_section_concept_map`,
  `build_section_concept_map_artifacts`). The assembly opens no connection and reads no
  store, so a command is as free to call it as a served facade is.
- Record why a spooled response was refused, and read the record back (`record_refusal`,
  `read_refusal_record`, `ForwardRefusalRecord`, `RefusalReason`, `SPOOL_RELATIVE_PATH`).
  `ForwardRefusalRecord` is the declared type of `SpooledReceipt.refusal`, so a caller
  reading receipts holds instances of it either way.
- Talk to a running facade from Python without composing a request (`FacadeClient`, with
  `submit_response` answering a `CaptureReceipt`, `generate`, `read_response`, `read`,
  `search` over a `ResourceQuery`, `resolve` for a canonical, `capability`, and `evaluate`
  answering an `EvaluationOutcome`). Credentials are `BearerToken`, `UsernamePassword`, or
  `PersonalAccessToken`; a refusal raises `FacadeError` carrying the `OperationOutcome` the
  facade stated its reason in.

Every capability above that reads DHIS2 takes the connection as an argument:
`client=` on `validate_codes`, `run_doctor`, and each generate target, with the `Profile`
form kept as the convenience wrapper the commands use. A handed-in client is used as it
stands and left open, so an application already holding an authenticated connection makes
one connection rather than one per call.

## Worked example — parse a period, then walk backwards

```python
import datetime

from dhis2w_fhir import parse_period, recent_periods

parse_period("2024BiW2")
# PeriodValue(iso='2024BiW2', period_type='BiWeekly',
#             start_date=date(2024, 1, 15), end_date=date(2024, 1, 28))

recent_periods("Monthly", 3, datetime.date(2026, 8, 2))
# ['202607', '202606', '202605']
```

## Reference

### Periods

::: dhis2w_fhir.period

### Project configuration

::: dhis2w_fhir.config

### The patient summary

The `[ips]` tables and the document they reach. `dhis2w_fhir.ips` holds the two
nominations an instance makes about a person - which tracked entity attribute carries
their name, birth date, and sex, and which recorded values are doses - because DHIS2
states neither and a guess would be indistinguishable from a fact.
`dhis2w_fhir.summary` assembles those into the IPS document Bundle, as a pure function
of what a caller already read, and states in the document itself what it is and is not.
The section mapping is published beside the vocabularies it maps, as `D2Section_CM`, so a
consumer audits the assignment without ever holding the project's `fhir.toml` -
[Terminology and ConceptMaps](401-terminology-and-conceptmaps.md#the-sections-a-recorded-value-feeds)
covers the shape, and `build_section_concept_map` and
`build_section_concept_map_artifacts` are the builders behind it.

::: dhis2w_fhir.ips

::: dhis2w_fhir.summary

### DHIS2 attribute values

The projection every generated resource carries its DHIS2 attribute values on, plus
the `uid -> code` index a generate run resolves once against `/api/attributes` and
every emitter joins against. DHIS2 sends an attribute value as an attribute UID and a
string, so the code is a lookup rather than part of the value.

::: dhis2w_fhir.attributes

### Generate notes

What a generate target has to say about a run, as a model rather than a sentence. A
`GenerateNote` carries the kind of decision it records (`GenerateNoteCategory`) beside
the human text, and `echoes_validate` says whether the kind only restates a finding
[`d2w fhir validate`](201-validate.md) reports on the instance - which is
what lets a bare run count those apart from what generation itself found.

::: dhis2w_fhir.notes

### FHIR R4 resource schemas

`dhis2w_fhir.r4` is the capture-facing surface over the R4 resource models, which
`dhis2w_fhir_engine` owns and defines at
[`dhis2w_fhir_engine.r4.resources`](api-dhis2w-fhir-engine.md#fhir-r4-resource-models). The
engine is the FHIR foundation package, so one `Patient` and one `Bundle` serve the
generator, the evaluator, and the server alike; this module re-exports that family
under the path capture code imports it from, and every name below is the engine's own
class object rather than a copy of it. `import dhis2w_fhir.r4` keeps working exactly as
written, and a model built through it is an instance of the engine's class.

That family covers the models every pre-built JSON document is serialised from -
`Organization` and `Location` for the registry, `CodeSystem` and `ValueSet` for the
option-set and category terminology, `ConceptMap` for both families' mappings back to
DHIS2. Beside them are the resources a summary document is assembled out of -
`Composition` and its flat `CompositionSection`, `Patient`, `Condition`,
`AllergyIntolerance`, and `Observation`, with `Bundle` carrying the `identifier`
and `timestamp` a document requires; see
[`examples/fhir/client/ips_document.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/ips_document.py)
and [the IPS working paper](design/ips.md).
Every one is frozen, alias-aware, and closed to unknown keys, so
`Model.model_validate(payload).model_dump_json(exclude_none=True, by_alias=True)`
reproduces the input document key for key.

The R4 primitive checks under `dhis2w_fhir.r4.primitives` stay this package's own, and
arrive under the same `dhis2w_fhir.r4` name.

::: dhis2w_fhir.r4.schemas

### Conversion: QuestionnaireResponse to DHIS2

The inverse of the emitters, and the reference implementation
[`docs/fhir/design/conversion.md`](design/conversion.md) holds the later published
StructureMaps against. A caller assembles a `ConversionContext` once from the compiled IG
artifacts - the served Questionnaires, the option-set CodeSystems and their ConceptMaps, the
ValueSets binding the two, and the published Locations - and then translates each captured
response into the DHIS2 import payload its form kind reports: a `DataValueSet` for a data set,
a `TrackerEvent` for an event program or a tracker program stage. A response the translator
cannot read whole answers with typed refusals naming the link id and the reason, never with a
partial payload.

A result carries exactly one payload and its `target_kind` names which, so `ConversionResult.payload`
reads the document off the kind and `payload_of` narrows it to one wire shape. The batch form is
`ConversionReport.payloads_of`, whose four named properties - `data_value_sets`, `events`,
`tracked_entities`, `enrollments` - are the order a drain posts them in.

`conversion.artifacts` is where a project's own files become those models: it reads the
compiled `ig/fsh-generated/resources` merged with the predefined `ig/input/resources` tree -
the same two trees `d2w fhir serve` serves - and `build_project_context` assembles the context
from them plus the project's `[generate]` naming, identifier base, and timezone.

Every public name below is importable from `dhis2w_fhir` itself, which is the package's one
stable import surface; the `dhis2w_fhir.conversion` path answers the same objects.

::: dhis2w_fhir.conversion.schemas

::: dhis2w_fhir.conversion.context

::: dhis2w_fhir.conversion.artifacts

::: dhis2w_fhir.conversion.values

::: dhis2w_fhir.conversion.payloads

::: dhis2w_fhir.conversion.translator

### The conformance runner

What [`d2w fhir doctor`](201-doctor.md) concluded about one instance, as
models rather than as terminal output. A `DoctorReport` carries one `DoctorPhaseResult` per
phase - the outcome, the one line it is read by, the reason a phase that did not run gives,
and every `DoctorFinding` it raised with the field path a mismatch was found at. The graders
are the pure half of the runner: `grade_forward`, `grade_capture`, `grade_oracle`, and
`grade_drift` turn a phase's own report into the verdict it is recorded under, over
`ForwardReport`, `CaptureOutcome`, `FamilyOutcome`, and `DriftReport`, and
`render_doctor_markdown` turns the whole run into the report file a handover is read from.

`run_doctor` is the other half, and what it does to the machine is part of its contract: it
mints a workspace directory (or writes into the one `DoctorOptions.workspace` names) and
removes a minted one unless `keep` is set, runs `sushi` or `docker run` where a compiler is
on the machine, writes compiled resources under `ig/fsh-generated/resources`, runs an ASGI
application in process, and posts a synthetic corpus at the instance under validate-only
mode. A caller that cannot afford that wants the graders rather than the run.

::: dhis2w_fhir.doctor

### Drift between a published guide and the instance

Whether the guide already on disk still describes the instance it was generated from.
`detect_drift` reads the instance for everything one project publishes and names every
organisation unit, option, question, and program stage that moved inside that project's own
selection scope; `read_published_guide` is its offline half, projecting the published
artifacts onto the objects the comparison is about. The three comparators -
`compare_organisation_units`, `compare_option_set`, and `compare_form` - are pure over a
`PublishedGuide` side and an instance side, so a caller can grade a snapshot it holds without
opening a connection. Every finding is a `DriftFinding` naming what moved, which direction it
moved in, and what each side says about it.

::: dhis2w_fhir.drift

### The capture spool

Where `d2w fhir serve` writes a receipt and where `d2w fhir forward` moves it next. The
layout is duplicated rather than imported - `dhis2w-fhir` is a dependency of
`dhis2w-fhir-serve`, so the arrow only points one way and the forwarder reads the files
directly under the same conventions.

::: dhis2w_fhir.spool

### Values a previous submission already sent

The identity of an aggregate data value, and the index a drain reads out of `forwarded/` to
say that a value it is about to send is one an earlier submission already sent. DHIS2 counts
that write exactly as it counts a first entry, so the spool is where the answer lives.

::: dhis2w_fhir.overwrite

### A client for a running facade

`FacadeClient` is the typed path to a `d2w fhir serve` facade: construct it against a base
url, hand `submit_response` a filled form, and read the receipt id off what comes back. The
facade publishes no OpenAPI document - `/metadata` is its contract - so this client is
hand-written against the routes it mounts rather than generated from a schema.

Three shapes are worth knowing before the first call. A `create` answers an
`OperationOutcome` and not the resource, so the id of an accepted submission is the last
segment of the `Location` header - `CaptureReceipt` carries both, plus the warnings the
answer stated. A 201 means the facade stored the submission durably, not that anything
reached DHIS2; `d2w fhir forward` is what drains the queue. And an expression that will not
parse is a 200 carrying its line and column, so `evaluate` answers an `EvaluationOutcome`
rather than raising - `FacadeError` is reserved for a request the facade cannot serve at all.

```python
from dhis2w_fhir import FacadeClient

async with FacadeClient("http://127.0.0.1:8123") as facade:
    draft = await facade.generate("BfMAe6Itzgt", seed=20260)
    receipt = await facade.submit_response(draft)
    print(receipt.response_id, receipt.note)
    stored = await facade.read_response(receipt.response_id)
```

Five runnable examples cover the surface, one method group each.
[`send_with_the_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/send_with_the_client.py)
is the write half above, end to end.
[`search_with_the_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/search_with_the_client.py)
is the read half - `canonical_resource_types` read off `/metadata`, a typed
`ResourceQuery` against the published forms and against the live register, and
`resolve` turning a canonical url into whichever type holds it.
[`evaluate_with_the_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/evaluate_with_the_client.py)
runs FHIRPath over both evaluation contexts and shows the diagnostic an
unparseable expression is answered with.
[`authenticate_with_the_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/authenticate_with_the_client.py)
presents a `BearerToken` to a facade started with `--auth token`, beside the 401
a caller with no credential and a caller with the wrong one get. And
[`handle_refusals_with_the_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/handle_refusals_with_the_client.py)
reads `FacadeError` itself: `status_code`, one typed issue per thing wrong, and
`diagnostics` for the log line that has to say why in one.

::: dhis2w_fhir.facade

### Package surface

The names below re-export from `dhis2w_fhir` itself; the
[generate page](201-generate.md) covers what each emitter
produces.

::: dhis2w_fhir
    options:
      members: false
