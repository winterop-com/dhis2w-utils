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
| [`init_from_template.sh`](cli/init_from_template.sh) | `d2w fhir init --list-templates` / `--template` — scaffold from a guide already generated against an instance, so the project compiles and serves without reaching one | yes |
| [`init_refresh.sh`](cli/init_refresh.sh) | `d2w fhir init --refresh` — update the scaffold-managed files without losing a line | yes |
| [`generate_full_run.sh`](cli/generate_full_run.sh) | `d2w fhir generate` — every target of the IG source off one pass over the instance | yes |
| [`generate_json_report.sh`](cli/generate_json_report.sh) | `d2w --json fhir generate` — the typed `GenerateFullReport` on stdout, read with jq | yes |
| [`generate_foundation.sh`](cli/generate_foundation.sh) | `d2w fhir generate foundation` — the instance-independent artifacts, no client opened | yes |
| [`generate_option_sets.sh`](cli/generate_option_sets.sh) | `d2w fhir generate option-sets` — one named target alone | yes |
| [`generate_stale_compile.sh`](cli/generate_stale_compile.sh) | `d2w fhir generate` — a run that rewrites a FSH source removes the compile of the sources before it | yes |
| [`generate_hostile_names.sh`](cli/generate_hostile_names.sh) | `d2w fhir generate --substitute-hostile-names` — publish a DHIS2 name the IG publisher cannot build, in wording it can | yes |
| [`generate_spaced_codes.sh`](cli/generate_spaced_codes.sh) | `d2w fhir generate --substitute-hostile-names` — publish a DHIS2 code carrying a space with the space hyphenated, the DHIS2 code stated beside it | yes |
| [`validate.sh`](cli/validate.sh) | `d2w fhir validate` — the FHIR-safety gate, exit 1 on errors | yes |
| [`validate_code_source.sh`](cli/validate_code_source.sh) | `d2w fhir validate --code-source code` — preview a concept-code migration | yes |
| [`validate_hostile_names.sh`](cli/validate_hostile_names.sh) | `d2w fhir validate --hostile-names` — grade the same instance under each hostile-names posture | yes |
| [`spool.sh`](cli/spool.sh) | `d2w fhir spool`, `requeue` — the capture queue, read and rewound offline | yes |
| [`serve.sh`](cli/serve.sh) | `d2w fhir serve` — compile, serve, post a load set, read the receipts | no: docker compile, binds a port |
| [`serve_auth_postures.sh`](cli/serve_auth_postures.sh) | `d2w fhir serve --auth` - the four postures: the bind refusal an absent key earns, `token`, `dhis2` read as the caller, `jwt` and its issuer | yes |
| [`evaluate.sh`](cli/evaluate.sh) | `POST /evaluate` and `POST /$evaluate` over a served guide, from curl - the OperationDefinition the contract lives in, FHIRPath over a stored form, a parse failure answered 200, and the `Parameters` a CQL library comes back as | yes |
| [`serve_projection_search.sh`](cli/serve_projection_search.sh) | `[serve.search] backend = "projection"` - `_content` and the as-of header from the synced copy, and the refusal without one | yes |
| [`serve_attribute_filter.sh`](cli/serve_attribute_filter.sh) | `d2-attribute={attributeUid}\|{value}` - the register filtered by a value: what each register declares as filterable, equality forgiving only case, two filters ANDed, and the same records from both backends | yes |
| [`serve_record.sh`](cli/serve_record.sh) | `GET /tracked-entities/{uid}/events` - one entity's own record as the responses its stage forms describe, one event on its own, and the `events` dial that withholds it | yes |
| [`summary.sh`](cli/summary.sh) | `GET /Patient/{uid}/$summary` - one person's International Patient Summary: the sections that state their own emptiness, the doses read off their own events, the identifier form, and the `[ips] enabled` dial that withholds the lot | yes |
| [`registers_many_types.sh`](cli/registers_many_types.sh) | Many tracked entity types, two of them one `Device` register: the union, `_tag`, and the checklist for the types nobody typed | no: creates and removes tracked entity types, programmes, and entities |
| [`corrections.sh`](cli/corrections.sh) | `[forward] corrections` / `withdrawals` - a marked submission refused at the capture door, then received | yes |
| [`forward_dry_run.sh`](cli/forward_dry_run.sh) | `d2w fhir forward` — the default: DHIS2 judges every payload validate-only, nothing moves | no: docker compile, binds a port |
| [`forward_import.sh`](cli/forward_import.sh) | `d2w fhir forward --import` — the committing drain, and the three states it files a receipt into | no: docker compile, binds a port, writes to the instance |
| [`forward_overwrites.sh`](cli/forward_overwrites.sh) | The two postures a drain takes towards a value already sent - `allow` names it, `refuse` queues the response | no: the same compile, port, and writes as `forward_import.sh` |
| [`forward_completeness.sh`](cli/forward_completeness.sh) | Data set completeness: what a `completed` response registers | no: the same compile, port, and writes as `forward_import.sh` |
| [`doctor_probe.sh`](cli/doctor_probe.sh) | `d2w fhir doctor` — the whole chain against one instance over a small representative selection, one verdict | no: the chain includes the docker compile |
| [`doctor_all_targets.sh`](cli/doctor_all_targets.sh) | `d2w fhir doctor --all-targets` — the same chain over every data set, every program, and every level | no: the same chain |
| [`doctor_live_oracle.sh`](cli/doctor_live_oracle.sh) | `d2w fhir doctor --live` — the served output judged against the instance | no: the same chain |
| [`doctor_report.sh`](cli/doctor_report.sh) | `d2w fhir doctor --workspace` — keep the workspace, hand over the report | no: the same chain |
| [`doctor_json.sh`](cli/doctor_json.sh) | `d2w --json fhir doctor` — the typed report on stdout, for jq and CI | no: the same chain |

## [`client/`](client/README.md) — the Python library path

Fifty-four examples with [their own README](client/README.md), grouped into nine readings:

| Group | What it answers |
| --- | --- |
| Build a response | I have a paper form's numbers, a visit, a new patient — what do I send? |
| Read a form | What does a published `Questionnaire` tell me before I fill anything? |
| Convert to DHIS2 | What does my response become on the DHIS2 wire, and why would that be refused? |
| Send and verify | How do I post it, and what comes back? |
| Say who a person is | Which attribute is somebody's name, and what does the record say when nobody nominated one? |
| Summarise a record | How do I read one person's record back out and assemble it into a FHIR document? |
| Evaluate over a served guide | How do I ask a running facade a question in FHIRPath, CQL, or ELM — and what may that question reach? |
| Drive the toolchain | Generating, serving, and draining from Python rather than the command line |
| Embed the facade | How do I run the facade inside my own process — no server, no port, no UI? |

**Every one runs in `make verify-examples`**, because [`client/_fixture.py`](client/_fixture.py) stands up what each needs: a scaffolded project, a translation context built live off the instance, and a `d2w fhir serve --live` facade on a port the operating system picks, stopped at exit. `D2W_FHIR_EXAMPLE_PROJECT` and `D2W_FHIR_EXAMPLE_FACADE` point the fixture at your own instead - and the verify suite sets exactly those two itself: it stands the project and the facade up once before its loop and stops the facade after the last example, so a batch pass boots one server rather than a dozen. Set either variable yourself and the suite leaves your fixture alone. The two examples about authentication are the exception in either direction: [`client/authenticate_with_the_client.py`](client/authenticate_with_the_client.py) asks for the `token` posture and [`client/read_register_as_yourself.py`](client/read_register_as_yourself.py) for `dhis2`, and the facade seam answers the default posture only - a facade somebody else started has whatever posture they gave it, so each of these starts a guarded one of its own whether or not a facade is already named.

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
