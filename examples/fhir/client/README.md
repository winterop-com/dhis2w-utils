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

## Summarise a record

Reading one person's record back out of DHIS2 and assembling it into a FHIR document.

| File | Shows |
| --- | --- |
| [`ips_document.py`](ips_document.py) | An International Patient Summary prototype: a nominated name, one mapped section of Observations, and the three required sections stating absence the way IPS v2.0.1 states it |

## Drive the toolchain

Generating, serving, and draining from Python, rather than from the command line.

| File | Shows |
| --- | --- |
| [`generate_ig.py`](generate_ig.py) | `load_project` + `resolve_generation_profile` + `generate_full`, and the `GenerateFullReport` consumed as a model rather than parsed as text |
| [`consume_facade.py`](consume_facade.py) | Plain httpx against a running facade: `/metadata`, search, `$generate`, POST a capture, read the receipt, read `/spool` |
| [`forward_spool.py`](forward_spool.py) | `forward_responses` dry run, and the `ForwardReport` counts, per-receipt outcomes, and rejection reasons rolled up by cause |
| [`minimal_facade.py`](minimal_facade.py) | Facade ladder, rung one: one route that translates a capture, posts it to the endpoint its payload names, and hands back DHIS2's verdict under DHIS2's own status |
| [`basic_facade.py`](basic_facade.py) | Facade ladder, rung two: one client for the process in a FastAPI lifespan, settings resolved once at startup, `/health` off a cheap DHIS2 read, one log line per verdict |
| [`complex_facade.py`](complex_facade.py) | Facade ladder, rung three: the real spool primitives — a receipt written durably, `201` before DHIS2 is asked, a background drain that retries, and a receipt readable by id |
| [`advanced_facade.py`](advanced_facade.py) | Facade ladder, rung four: tracker routing, the coded-answer dial as configuration, values an earlier receipt already sent named before the post, and a small `/metadata` — then run `d2w fhir serve` |

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
