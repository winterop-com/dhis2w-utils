# dhis2-utils examples

```
examples/
  fhir/    cli/  client/  mcp/      # d2w fhir - DHIS2 metadata as a FHIR Implementation Guide
  cli/                              # d2w ... Typer CLI, one script per topic
  client/                           # dhis2w-client Python library
  mcp/                              # dhis2w-mcp FastMCP tools, called in-process
  d2ql/                             # d2ql query files
  plugin-external/                  # a third-party plugin registered via entry points
```

## FHIR ([`fhir/`](fhir/README.md))

**`d2w fhir` turns a DHIS2 instance's metadata into a FHIR Implementation Guide**, serves the
compiled guide as a read-and-capture endpoint, and posts what that endpoint captured back into
DHIS2. It has its own group because it is its own product surface, with all three shapes of caller
in it. Start at [`fhir/cli/generate.sh`](fhir/cli/generate.sh) to see the whole loop as commands, or
[`fhir/client/consume_facade.py`](fhir/client/consume_facade.py) if you are integrating against a
guide someone else published.

| File | Shows |
| --- | --- |
| [`fhir/cli/generate.sh`](fhir/cli/generate.sh) | `d2w fhir init` + `generate` + `validate` - scaffold a SUSHI project and write the IG source from DHIS2 metadata |
| [`fhir/cli/serve.sh`](fhir/cli/serve.sh) | `d2w fhir serve` - compile the guide, serve it, post a load set, read the receipts back |
| [`fhir/cli/forward.sh`](fhir/cli/forward.sh) | `d2w fhir forward` - drain the capture spool into DHIS2, dry run first |
| [`fhir/cli/doctor.sh`](fhir/cli/doctor.sh) | `d2w fhir doctor` - the whole chain against one instance, one verdict |
| [`fhir/cli/spool.sh`](fhir/cli/spool.sh) | `d2w fhir spool` + `requeue` - read the capture queue and put a refused receipt back in it |
| [`fhir/client/generate_ig.py`](fhir/client/generate_ig.py) | Generate a whole IG from Python and read the `GenerateFullReport` back as a model |
| [`fhir/client/consume_facade.py`](fhir/client/consume_facade.py) | Plain httpx against a running facade - discover, fill, submit, read the receipt |
| [`fhir/client/forward_spool.py`](fhir/client/forward_spool.py) | Dry-run a drain from Python and read the `ForwardReport` back as a model |
| [`fhir/mcp/validate.py`](fhir/mcp/validate.py) | The `fhir_validate` tool - FHIR-safety of an instance's codes |
| [`fhir/mcp/forward.py`](fhir/mcp/forward.py) | The `fhir_forward` tool - drain a spool from an agent |

`dhis2w-fhir` and `dhis2w-fhir-serve` are not per-version packages - the client detects the DHIS2
major from `/api/system/info` - so this group is one copy that runs against v41, v42, and v43 alike.

Serving needs the extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
The [`d2w fhir` guide series](../docs/guides/fhir/index.md) is the narrative these scripts sit under.

## The three surfaces

| Surface | Best for | Auth handling |
| --- | --- | --- |
| [`client/`](client/) - `dhis2w-client` library | Your own Python tooling; scripts in-process | You pass `AuthProvider` explicitly (Basic, PAT, OAuth2) - no profile layer |
| [`cli/`](cli/) - `d2w <cmd>` | Day-to-day dev, pipelines, human use | Reads `~/.config/dhis2/profiles.toml` + env; `d2w profile add/login` manages creds |
| [`mcp/`](mcp/) - `dhis2w-mcp` | Agents, automation over the MCP protocol | Same profile layer as the CLI; every CLI command has a matching MCP tool |

All three hit DHIS2 through `Dhis2Client`. Pick the shape that fits your caller. See
[Workspace layout](../docs/architecture/workspace.md) for the dependency arrows.

## What every example must be

Two rules, and a new example meets both or it does not land:

1. **Small, self-contained, and about one feature.** A reader opens a file to learn one thing.
   A script that sets up a fixture, exercises four commands, and tears the fixture down teaches
   nobody the second thing it does.
2. **Verified by `make verify-examples`.** An example nobody runs is an example nobody knows still
   works. `infra/scripts/verify_examples.py` executes the whole tree against a seeded stack; an
   entry that genuinely cannot run in a batch pass goes in that script's `SKIP_BY_DEFAULT` with the
   reason stated beside it - "needs a human", "blocks forever", "writes to the instance" - and that
   reason is a gap to close, not a resting place.

`make check-examples` is the static half: every `d2w` command an example invokes resolves in the
Typer tree, every `call_tool("...")` names a registered tool, and every example path an example
mentions exists.

## DHIS2 majors

**One copy of each example, and it runs on v41, v42, and v43.** The wire is the same for almost
everything the examples touch, so a version-neutral file is the honest default.

- CLI and MCP examples name no major at all.
- Client examples that need a version-pinned import are written against **v42, the canonical
  baseline**, and carry one comment saying to swap `.v42` for `.v41` / `.v43` to pin another major.
  Most examples do not need the pin: `dhis2w_core.client_context.open_client(profile)` detects the
  major from `/api/system/info` and dispatches accessors at runtime.
- An example that exists **only** for one major lives under that major's subdirectory -
  [`client/v41/`](client/v41/) for v41 wire quirks, [`client/v43/`](client/v43/) for v43 schema
  changes and their workarounds. `make verify-examples` runs the active major's variants and
  ignores the others.

The per-resource schema differences are at
[`docs/architecture/schema-diff-v41-v42-v43.md`](../docs/architecture/schema-diff-v41-v42-v43.md).

## Running

```bash
make dhis2-run DHIS2_VERSION=v42        # foreground DHIS2 + seeded auth (Ctrl+C stops)
# second terminal:
set -a; source infra/home/credentials/.env.auth; set +a

uv run python examples/client/whoami.py
bash examples/cli/whoami.sh
uv run python examples/mcp/whoami.py
```

Swap `v42` for `v41` or `v43` to boot another stack; the same example files run against all three.
`make refresh-and-verify DHIS2_VERSION=v43` reseeds a v43 instance and runs the whole suite over it.

> **Canonical catalogue**: [`docs/examples.md`](../docs/examples.md) is the curated index - the
> headline examples per topic with links to the concept docs that explain each one. It is not
> exhaustive; `ls examples/{cli,client,mcp,fhir/*}/` is the source of truth for what is on disk.

## Environment

- `DHIS2_URL` - default `http://localhost:8080`
- `DHIS2_PAT` - a Personal Access Token
- `DHIS2_USERNAME`, `DHIS2_PASSWORD` - Basic auth fallback
- `DHIS2_OAUTH_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` / `_SCOPES` - for the OIDC examples
- `DHIS2_PROFILE` - pick a named profile from `profiles.toml` without hardcoding credentials
- `DHIS2_VERSION` - `v41`, `v42`, or `v43` - which stack `make dhis2-run` boots, and which major's
  variant directory `verify_examples` adds to the common set
