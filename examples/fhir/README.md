# FHIR examples

`d2w fhir` turns a DHIS2 instance's metadata into a [FHIR](https://hl7.org/fhir/R4/) Implementation Guide, serves the compiled guide as a read-and-capture endpoint, and posts what that endpoint captured back into DHIS2. It has its own example group because it is its own product surface, with all three shapes of caller in it.

`dhis2w-fhir` and `dhis2w-fhir-serve` are not per-version packages — the client detects the DHIS2 major from `/api/system/info` — so this is one copy that runs against v41, v42, and v43 alike.

The narrative these scripts sit under is the [`d2w fhir` guide series](../../docs/guides/fhir/index.md); [`docs/examples.md`](../../docs/examples.md) is the curated catalogue.

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

## [`client/`](client/) — the Python library path

| File | Shows | Runs in `make verify-examples` |
| --- | --- | --- |
| [`generate_ig.py`](client/generate_ig.py) | `load_project` + `resolve_generation_profile` + `generate_full`, and the `GenerateFullReport` consumed as a model rather than parsed as text | yes |
| [`consume_facade.py`](client/consume_facade.py) | Plain httpx against a running facade: `/metadata`, search, `$generate`, POST a capture, read the receipt, read `/spool`. No DHIS2 and no dhis2w package needed | no: needs a facade already listening |
| [`forward_spool.py`](client/forward_spool.py) | `forward_responses` dry run, and the `ForwardReport` counts, per-receipt outcomes, and rejection reasons rolled up by cause | no: needs a project whose spool holds receipts |

Give either of the last two what it needs and it runs green:

```bash
d2w fhir serve --live --port 8123 &                       # from inside a scaffolded project
uv run python examples/fhir/client/consume_facade.py http://127.0.0.1:8123
uv run python examples/fhir/client/forward_spool.py /path/to/project
```

