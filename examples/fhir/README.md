# FHIR examples

`d2w fhir` turns a DHIS2 instance's metadata into a [FHIR](https://hl7.org/fhir/R4/) Implementation Guide, serves the compiled guide as a read-and-capture endpoint, and posts what that endpoint captured back into DHIS2. It has its own example group because it is its own product surface, in two shapes of caller - the commands and the Python library - plus a catalogue of complete projects those callers drive. Beside them sits the evaluation engine, which computes over FHIR data no matter where it came from.

`dhis2w-fhir`, `dhis2w-fhir-serve` and `dhis2w-fhir-engine` are not per-version packages — the client detects the DHIS2 major from `/api/system/info`, and the engine talks to no DHIS2 at all — so this is one copy that runs against v41, v42, and v43 alike.

The narrative these scripts sit under is the [`d2w fhir` guide series](../../docs/fhir/index.md); [`docs/examples.md`](../../docs/examples.md) is the curated catalogue.

## Prerequisites

```bash
make dhis2-run                                       # DHIS2 + seeded auth
d2w profile add local --url http://localhost:8080 --auth basic \
    --username admin --password district --default

uv sync --all-extras       # `serve` needs dhis2w-fhir-serve; `pip install 'dhis2w-cli[serve]'` outside this repo
```

The compile step (`make setup && make sushi` inside a scaffolded project) needs docker. Generation, spool work, and `serve --live` do not.

## [`cli/`](cli/) — the commands

| File | Commands | Runs in `make verify-examples` |
| --- | --- | --- |
| [`init.sh`](cli/init.sh) | `d2w fhir init` — scaffold a project, offline, with the identity and selection dials | yes |
| [`init_refresh.sh`](cli/init_refresh.sh) | `d2w fhir init --refresh` — update the scaffold-managed files without losing a line | yes |
| [`generate.sh`](cli/generate.sh) | `d2w fhir generate` — the whole IG source from one pass over the instance | yes |
| [`generate_foundation.sh`](cli/generate_foundation.sh) | `d2w fhir generate foundation` — the instance-independent artifacts, no client opened | yes |
| [`generate_option_sets.sh`](cli/generate_option_sets.sh) | `d2w fhir generate option-sets` — one named target alone | yes |
| [`validate.sh`](cli/validate.sh) | `d2w fhir validate` — the FHIR-safety gate, exit 1 on errors | yes |
| [`validate_code_source.sh`](cli/validate_code_source.sh) | `d2w fhir validate --code-source code` — preview a concept-code migration | yes |
| [`spool.sh`](cli/spool.sh) | `d2w fhir spool`, `requeue` — the capture queue, read and rewound offline | yes |
| [`serve.sh`](cli/serve.sh) | `d2w fhir serve` — compile, serve, post a load set, read the receipts | no: docker compile, binds a port |
| [`forward.sh`](cli/forward.sh) | `d2w fhir forward` — drain the spool into DHIS2: dry run, `--import`, the three states | no: docker compile, binds a port, `--import` writes to the instance |
| [`forward_overwrites.sh`](cli/forward_overwrites.sh) | A drain names the values a previous submission already sent | no: the same compile, port, and writes as `forward.sh` |
| [`forward_completeness.sh`](cli/forward_completeness.sh) | Data set completeness: what a `completed` response registers | no: the same compile, port, and writes as `forward.sh` |
| [`doctor.sh`](cli/doctor.sh) | `d2w fhir doctor` — the whole chain against one instance, one verdict | no: the chain includes the docker compile |
| [`doctor_live_oracle.sh`](cli/doctor_live_oracle.sh) | `d2w fhir doctor --live` — the served output judged against the instance | no: the same chain |
| [`doctor_report.sh`](cli/doctor_report.sh) | `d2w fhir doctor --workspace` — keep the workspace, hand over the report | no: the same chain |
| [`doctor_json.sh`](cli/doctor_json.sh) | `d2w --json fhir doctor` — the typed report on stdout, for jq and CI | no: the same chain |

## [`client/`](client/README.md) — the Python library path

Thirty-three examples with [their own README](client/README.md), grouped into five readings:

| Group | What it answers |
| --- | --- |
| Build a response | I have a paper form's numbers, a visit, a new patient — what do I send? |
| Read a form | What does a published `Questionnaire` tell me before I fill anything? |
| Convert to DHIS2 | What does my response become on the DHIS2 wire, and why would that be refused? |
| Send and verify | How do I post it, and what comes back? |
| Drive the toolchain | Generating, serving, and draining from Python rather than the command line |

**Every one runs in `make verify-examples`**, because [`client/_fixture.py`](client/_fixture.py) stands up what each needs: a scaffolded project, a translation context built live off the instance, and a `d2w fhir serve --live` facade on a port the operating system picks, stopped at exit. `D2W_FHIR_EXAMPLE_PROJECT` and `D2W_FHIR_EXAMPLE_FACADE` point the fixture at your own instead - and the verify suite sets exactly those two before its loop, standing the project and the facade up once so every FHIR client example of a batch pass shares one instead of each booting its own.

There are no MCP examples because there are no MCP tools: this surface is driven from the command line and from Python, and what an agent drives is the served facade itself, over HTTP.

## [`engine/`](engine/README.md) - the evaluation engine

Nine examples with [their own README](engine/README.md). `dhis2w-fhir-engine` evaluates FHIRPath, CQL, and ELM over FHIR-shaped data and scores CQL quality measures into a FHIR R4 `MeasureReport`. It has no DHIS2 dependency and no web framework, which is why eight of these nine need nothing running at all.

| Group | What it answers |
| --- | --- |
| Navigate data with FHIRPath | How do I point at a part of this resource, or pick one type out of a Bundle? |
| State clinical logic in CQL | How do I write the question once, as a library, and evaluate it against data? |
| Score a quality measure | How do I turn that into populations, a score, and a FHIR `MeasureReport`? |
| Against a real DHIS2 instance | What does the whole chain look like over seeded tracker data? |

The narrative these sit under is the [501 pages](../../docs/fhir/index.md) of the guide series: [FHIRPath](../../docs/fhir/501-fhirpath.md), [CQL](../../docs/fhir/501-cql.md), [Quality measures](../../docs/fhir/501-measures.md), and [The FHIR version binding](../../docs/fhir/501-version-binding.md).

**Every one runs in `make verify-examples`.** The eight pure-evaluation examples read the inline Bundle in [`engine/_bundle.py`](engine/_bundle.py); `e2e_measure_from_dhis2.py` reads `DHIS2_URL`, `DHIS2_USERNAME`, and `DHIS2_PASSWORD`, which the verify suite sources from the seeded credentials file and skips with the missing names stated when they are absent.

## [`igs/`](igs/README.md) - the full guides

Eight complete `d2w fhir init` project trees, one per feature story, all built against the seeded local instance. Where a script above shows one command or one library call, a tree here is the whole thing: a `fhir.toml` you can read top to bottom, a SUSHI skeleton, a Makefile, and a Dockerfile.

| Guide | The story |
| --- | --- |
| [`aggregate-minimal`](igs/aggregate-minimal/README.md) | The smallest complete guide: the forms, one district, no category axis |
| [`aggregate-disaggregated`](igs/aggregate-disaggregated/README.md) | The same selection with both category axes on - the pairs, the properties, the ConceptMaps |
| [`event-program`](igs/event-program/README.md) | A program without registration, and the program rules riding on its Questionnaire |
| [`tracker-registration`](igs/tracker-registration/README.md) | Registration, enrollment, two stage forms, and the person-only form |
| [`terminology-strict`](igs/terminology-strict/README.md) | Concept codes taken from DHIS2 codes rather than UIDs, and what that trades |
| [`registry-district`](igs/registry-district/README.md) | One district as Organization and Location pairs, boundaries and all |
| [`facility-mixed`](igs/facility-mixed/README.md) | The flagship: one of every capture kind at once |
| [`refused-names`](igs/refused-names/README.md) | The exhibit: a selection `d2w fhir generate` refuses, and why |

Only the inputs are committed - nothing `d2w fhir generate` or SUSHI writes. `make verify-igs` refreshes, validates, generates, and compiles all eight; it needs a reachable DHIS2 instance and docker, so it is an on-demand target rather than part of `make test`. [`igs/README.md`](igs/README.md) has the identity scheme, the refresh doctrine, and what the runner asserts per guide.
