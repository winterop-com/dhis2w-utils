# FHIR client examples

**The Python library path for `d2w fhir`** — `dhis2w-fhir` from your own code, plus the plain-HTTP
path that needs no dhis2w package at all. If you know DHIS2 data sets, programs, stages and category
combinations, and you know no FHIR, start at the top of the first table and read down: every example
states the DHIS2 fact first and the FHIR shape that carries it second.

The narrative these sit under is the [`d2w fhir` guide series](../../../docs/fhir/index.md),
and [the capture contract](../../../docs/fhir/401-capture-contract.md) is the document the
response-building examples meet.

## What every example here is

1. **Small, self-contained, and about one feature.** An example that teaches three things is three
   examples.
2. **Verified.** `make verify-examples` runs every file in this directory on every pass. None is
   skipped: the fixture below stands up whatever each one needs.

## Build a response

Constructing a `QuestionnaireResponse` from data you already have. This is the group to read if you
are filling forms from your own system rather than driving the toolchain.

| File | Shows |
| --- | --- |
| [`build_aggregate_response.py`](build_aggregate_response.py) | The minimal aggregate capture: a data set's numbers for one period at one organisation unit, and the five elements that are required |
| [`build_aggregate_disaggregated_response.py`](build_aggregate_disaggregated_response.py) | A data element cut by a category combination — why the link id carries the category option combo after a dot |
| [`build_aggregate_attribute_option_combo_response.py`](build_aggregate_attribute_option_combo_response.py) | A data set on a non-default attribute category combination — the second key DHIS2 files the whole submission under |
| [`build_event_response.py`](build_event_response.py) | One event of a program without registration: no person, an occurrence date, an organisation unit |
| [`build_registration_response.py`](build_registration_response.py) | Registering a person and enrolling them, minting both DHIS2 UIDs client-side |
| [`build_stage_response.py`](build_stage_response.py) | A visit for a person the instance already holds — naming the existing subject and the enrollment it belongs to |
| [`build_person_response.py`](build_person_response.py) | Registering a person who is enrolled in nothing: the registration contract without its enrollment half |

## Read a form

What a published `Questionnaire` tells a client before it fills anything.

| File | Shows |
| --- | --- |
| [`read_form_questions.py`](read_form_questions.py) | Walking a form's items — groups, questions, required flags, numeric bounds |
| [`read_form_dhis2_identity.py`](read_form_dhis2_identity.py) | Which DHIS2 object a form came from, read off the form's own identifiers |
| [`read_form_fidelity.py`](read_form_fidelity.py) | What the form kept from DHIS2 and what it could not carry |
| [`read_form_program_rules.py`](read_form_program_rules.py) | The program rules a form publishes, and the ones it could not express |
| [`answer_value_types.py`](answer_value_types.py) | Every DHIS2 value type onto its item type, answer element, and literal spelling |
| [`answer_coded_question.py`](answer_coded_question.py) | Answering a question bound to an option set, as a `Coding` out of its CodeSystem |

## Convert to DHIS2

What a response becomes on the DHIS2 wire, and why a translator sometimes refuses to say.

| File | Shows |
| --- | --- |
| [`convert_aggregate_to_dhis2.py`](convert_aggregate_to_dhis2.py) | An aggregate response as the `/api/dataValueSets` envelope DHIS2 imports |
| [`convert_event_to_dhis2.py`](convert_event_to_dhis2.py) | An event response as the `/api/tracker` event it becomes |
| [`convert_registration_to_dhis2.py`](convert_registration_to_dhis2.py) | A registration as the tracked entity and enrollment it creates |
| [`translate_codes_to_dhis2.py`](translate_codes_to_dhis2.py) | A coded answer resolved back to the DHIS2 option, and the fall-back tiers that find it |
| [`read_conversion_refusal.py`](read_conversion_refusal.py) | A refusal read as a model — the category, the reason, and the element it locates |
| [`derive_receipt_event_uid.py`](derive_receipt_event_uid.py) | The DHIS2 event UID a receipt derives, so a re-drain writes the same event |

## Send and verify

Posting a response at a running facade, and reading what comes back.

| File | Shows |
| --- | --- |
| [`validate_before_sending.py`](validate_before_sending.py) | Checking a response against the form before a server ever sees it |
| [`send_response.py`](send_response.py) | POSTing one capture and reading the receipt back |
| [`send_without_the_library.py`](send_without_the_library.py) | The same capture as plain JSON over httpx — no dhis2w package imported at all |
| [`read_receipt_verdict.py`](read_receipt_verdict.py) | The accepted capture's `OperationOutcome` — what was stored, and what was warned about |
| [`read_capture_refusal.py`](read_capture_refusal.py) | A refused capture: the 422, its issues, and the FHIRPath each one locates itself with |
| [`find_person_by_identifier.py`](find_person_by_identifier.py) | Resolving a person to a DHIS2 UID through the register a live facade serves |
| [`read_register_as_yourself.py`](read_register_as_yourself.py) | A facade under `auth = "dhis2"`: the register read under the caller's own DHIS2 authorization, and the 401 a read with no credential gets |
| [`register_any_type.py`](register_any_type.py) | Every register a facade serves, walked off `/metadata` with no resource type written down - the type names behind each one, and the tag each resource carries |

## The typed client

`FacadeClient` from `dhis2w_fhir` is the same facade as the group above, with the contract handed to
you rather than reconstructed: no request built by hand, no header spelled twice, no status code
compared against a constant. Every method answers a model, and every refusal arrives as a
`FacadeError` carrying the `OperationOutcome` the facade stated its reason in.

| File | Shows |
| --- | --- |
| [`send_with_the_client.py`](send_with_the_client.py) | The write half: `$generate` a draft, `submit_response` it, read the `CaptureReceipt` id off the `Location` header and the warnings off the body, read the receipt back typed |
| [`search_with_the_client.py`](search_with_the_client.py) | The read half: `canonical_resource_types` off `/metadata`, a typed `ResourceQuery` against the forms and against the register, and `resolve` turning a canonical into the resource that holds it |
| [`evaluate_with_the_client.py`](evaluate_with_the_client.py) | `evaluate` with the typed contexts: `InlineResourceContext.over` a draft that is stored nowhere, `StoredResourceContext` over a form the facade holds, and the diagnostic an unparseable expression is answered with rather than raised on |
| [`authenticate_with_the_client.py`](authenticate_with_the_client.py) | `BearerToken` against a facade of its own started with `--auth token`: the open reads, the 401 with no credential, the 401 with the wrong one, and the receipt the right one earns |
| [`handle_refusals_with_the_client.py`](handle_refusals_with_the_client.py) | `FacadeError` read typed: the 404 a resource nobody holds raises and the 422 a response answering an unpublished form raises, both through `status_code`, `issues`, and `diagnostics` |

## Say who a person is

Which tracked entity attribute means a name, a birth date, a sex, and what a reading of one produces.

| File | Shows |
| --- | --- |
| [`identity_nominations.py`](identity_nominations.py) | `[ips.identity]` read over a real person: a name filled, a sex value the map does not answer for, and a birth date stating its own absence |

## Summarise a record

Reading one person's record back out of DHIS2 and assembling it into a FHIR document.

| File | Shows |
| --- | --- |
| [`ips_document.py`](ips_document.py) | An International Patient Summary assembled by hand: a nominated name, one mapped section of Observations, and the three required sections stating absence the way IPS v2.0.1 states it. The served surface is `$summary` - [`../cli/summary.sh`](../cli/summary.sh) walks it |

## Evaluate over a served guide

Asking a running facade a question in FHIRPath, CQL, or ELM. The evaluation engine
(`dhis2w-fhir-engine`) has no DHIS2 in it and answers over FHIR-shaped data wherever that data came
from; what these examples add is the facade underneath it, which is where the data is. An expression
reaches exactly the resource the request names as its context and nothing else - `inline` is the
document you posted, `stored` is one the served guide holds, and `registered` is one tracked entity
read live out of DHIS2.

Two addresses answer the same evaluation: `POST /evaluate` in this project's own JSON, where a parse
failure keeps its line and column, and `POST /$evaluate` as the FHIR operation, where the answer is
a `Parameters` resource. The engine's own examples, with no server at all, are in
[`../engine/`](../engine/README.md).

| File | Shows |
| --- | --- |
| [`evaluate_via_facade.py`](evaluate_via_facade.py) | Plain httpx against a running facade's `POST /evaluate`: one FHIRPath call, one CQL library, and one expression that will not parse - answered with the line and column, not a 500 |
| [`evaluate_stored_resource.py`](evaluate_stored_resource.py) | The `stored` context: FHIRPath one-liners counting a DHIS2 data set's sections, data elements and category-combination cells off the served `Questionnaire`, and the 404 a resource nobody holds earns |
| [`evaluate_registered_person.py`](evaluate_registered_person.py) | The `registered` context: a chart review of one tracked entity read live out of DHIS2, written as CQL from the guide's own published vocabulary, with the type code checked against the served `CodeSystem` |
| [`evaluate_as_parameters.py`](evaluate_as_parameters.py) | The same evaluation through `POST /$evaluate`, the FHIR operation: one parameter per define, `part` entries where a define answered several values, an `OperationOutcome` part where one refused |
| [`evaluate_operation_contract.py`](evaluate_operation_contract.py) | The operation discovered rather than documented: `/metadata` names it, `OperationDefinition/serve-evaluate` states its parameters and cardinalities, and a request built to that contract answers over a stored form |
| [`evaluate_compiled_library.py`](evaluate_compiled_library.py) | ELM as the interchange format: one library compiled locally with `ELMSerializer` and run on the facade as JSON, compared define by define against its own source - and what the round trip does not carry yet, demonstrated |

## Drive the toolchain

Generating, serving, and draining from Python, rather than from the command line.

| File | Shows |
| --- | --- |
| [`generate_ig.py`](generate_ig.py) | `load_project` + `resolve_generation_profile` + `generate_full`, and the `GenerateFullReport` consumed as a model rather than parsed as text |
| [`consume_facade.py`](consume_facade.py) | Plain httpx against a running facade: `/metadata`, search, `$generate`, POST a capture, read the receipt, read `/spool` |
| [`read_metadata_health.py`](read_metadata_health.py) | `GET /metadata-health` off a live facade: the `d2w fhir validate` findings with the DHIS2 field at fault and what each grade costs, plus how far the selection is translated per locale |
| [`forward_spool.py`](forward_spool.py) | `forward_responses` dry run, and the `ForwardReport` counts, per-receipt outcomes, and rejection reasons rolled up by cause |
| [`minimal_facade.py`](minimal_facade.py) | Facade ladder, level one: one route that translates a capture, posts it to the endpoint its payload names, and hands back DHIS2's verdict under DHIS2's own status |
| [`basic_facade.py`](basic_facade.py) | Facade ladder, level two: one client for the process in a FastAPI lifespan, settings resolved once at startup, `/health` off a cheap DHIS2 read, one log line per verdict |
| [`complex_facade.py`](complex_facade.py) | Facade ladder, level three: the real spool primitives — a receipt written durably, `201` before DHIS2 is asked, a background drain that retries, and a receipt readable by id |
| [`advanced_facade.py`](advanced_facade.py) | Facade ladder, level four: tracker routing, the coded-answer dial as configuration, values an earlier receipt already sent named before the post, and a small `/metadata` — then run `d2w fhir serve` |

## Embed the facade

The headless path: `dhis2w-fhir-serve` as a library in your own process — no server, no port, no UI,
no `d2w` command. The narrative is [Embed the facade](../../../docs/fhir/401-embed-the-facade.md).

| File | Shows |
| --- | --- |
| [`embed_the_facade.py`](embed_the_facade.py) | `create_app` driven over an ASGI transport: `/metadata` and the published forms read as function calls, with no socket bound |
| [`capture_headless.py`](capture_headless.py) | A capture taken in-process: `$generate`, POST, the receipt read back, and the spool file it left on disk |
| [`forward_headless.py`](forward_headless.py) | The drain from inside the same process: the caller's own DHIS2 connection handed in, and every dial stated as an argument rather than read from `[forward]` |
| [`projection_local_store.py`](projection_local_store.py) | The local storage layer: `run_sync` into the project's SQLite projection, then the watermark, a page, an identifier search, and membership read back through `ProjectionStore` |
| [`embed_in_fastapi.py`](embed_in_fastapi.py) | The facade's routers mounted inside a caller's own FastAPI application, guarded by the caller's own authentication dependency |

## The fixture

Every example reads [`_fixture.py`](_fixture.py), which stands up three things once and shares them:

- **A project.** `d2w fhir init` scaffolds it offline, selecting one DHIS2 object of every form kind
  the capture contract has — the `Child Health` and `EPI Stock` data sets, the `Supervision visit`
  event program, and the `Child Programme` tracker program, whose tracked entity type also publishes
  a person-only registration form. Nothing is generated: no example opens a generated file.
- **A translation context.** Built off the DHIS2 instance with `fetch_live_artifacts`, in seconds.
  The other path reads a SUSHI-compiled guide off disk, which means docker and minutes.
- **A facade.** `d2w fhir serve --live` on a port the operating system picks, started on first use
  and stopped at exit. Live, so the tracked entity register is served too.

The project and the context are cached in a directory under the system temporary directory, named
for a digest of the instance, the selection, and the fixture's own revision — so the first example
of a run pays for them and the rest do not. The organisation-unit registry covers one district
rather than the whole country, which is what keeps the live facade a four-second start.

Two environment variables supply your own instead:

| Variable | Effect |
| --- | --- |
| `D2W_FHIR_EXAMPLE_PROJECT` | An existing project root, used as-is. Nothing is scaffolded. |
| `D2W_FHIR_EXAMPLE_FACADE` | A base URL already serving. Nothing is started, and nothing is stopped. |

## Prerequisites

```bash
make dhis2-run                                       # DHIS2 + seeded auth
d2w profile add local --url http://localhost:8080 --auth basic \
    --username admin --password district --default

uv sync --all-extras       # serving needs dhis2w-fhir-serve
```

Then any example runs on its own:

```bash
uv run python examples/fhir/client/build_aggregate_response.py
```

With no DHIS2 reachable, every example fails with one sentence naming what is missing and how to
supply it — never a traceback.
