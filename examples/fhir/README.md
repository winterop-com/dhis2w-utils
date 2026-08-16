# FHIR examples

`d2w fhir` turns a DHIS2 instance's metadata into a [FHIR](https://hl7.org/fhir/R4/) Implementation Guide, serves the compiled guide as a read-and-capture endpoint, and posts what that endpoint captured back into DHIS2. It has its own example group because it is its own product surface, in two shapes of caller: the commands, and the Python library.

`dhis2w-fhir` and `dhis2w-fhir-serve` are not per-version packages — the client detects the DHIS2 major from `/api/system/info` — so this is one copy that runs against v41, v42, and v43 alike.

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
| [`generate.sh`](cli/generate.sh) | `d2w fhir init`, `generate` (each target and the whole run), `validate` | yes |
| [`spool.sh`](cli/spool.sh) | `d2w fhir spool`, `requeue` — the capture queue, read and rewound offline | yes |
| [`serve.sh`](cli/serve.sh) | `d2w fhir serve` — compile, serve, post a load set, read the receipts | no: docker compile, binds a port |
| [`forward.sh`](cli/forward.sh) | `d2w fhir forward` — drain the spool into DHIS2, dry run then `--import` | no: docker compile, binds a port, `--import` writes to the instance |
| [`doctor.sh`](cli/doctor.sh) | `d2w fhir doctor` — the whole chain against one instance, one verdict | no: the chain includes the docker compile |

## [`client/`](client/README.md) — the Python library path

Twenty-five examples with [their own README](client/README.md), grouped into five readings:

| Group | What it answers |
| --- | --- |
| Build a response | I have a paper form's numbers, a visit, a new patient — what do I send? |
| Read a form | What does a published `Questionnaire` tell me before I fill anything? |
| Convert to DHIS2 | What does my response become on the DHIS2 wire, and why would that be refused? |
| Send and verify | How do I post it, and what comes back? |
| Drive the toolchain | Generating, serving, and draining from Python rather than the command line |

**Every one runs in `make verify-examples`**, because [`client/_fixture.py`](client/_fixture.py) stands up what each needs: a scaffolded project, a translation context built live off the instance, and a `d2w fhir serve --live` facade on a port the operating system picks, stopped at exit. `D2W_FHIR_EXAMPLE_PROJECT` and `D2W_FHIR_EXAMPLE_FACADE` point the fixture at your own instead.

There are no MCP examples because there are no MCP tools: this surface is driven from the command line and from Python, and what an agent drives is the served facade itself, over HTTP.
