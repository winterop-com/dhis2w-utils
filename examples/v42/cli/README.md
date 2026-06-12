# CLI examples

Shell invocations of the `d2w` Typer CLI (installed with `uv sync`). Every CLI command resolves a DHIS2 profile first (from `.dhis2/profiles.toml`, `~/.config/dhis2/profiles.toml`, or `DHIS2_URL`+`DHIS2_PAT` env) and calls into the matching `dhis2w-core` plugin.

> **Canonical catalogue**: [`docs/examples.md`](../../../docs/examples.md) is a curated v42 example index — headline examples per topic, with links to the concept docs that explain each one (not exhaustive; the per-version `examples/v{41,42,43}/` trees are the source of truth). [`docs/cli-reference.md`](../../../docs/cli-reference.md) is the auto-generated reference for every command + flag.

## Prerequisites

```bash
make dhis2-run                               # starts DHIS2 + seeds auth in .env.auth
set -a; source infra/home/credentials/.env.auth; set +a

# create a local profile so `d2w ...` commands resolve it — secrets via env, never argv
d2w profile add local --url http://localhost:8080 --auth pat --default --verify
```

## Shell scripts

Each script is small and self-contained. Run with `bash examples/v42/cli/<name>.sh`.

## Global flags

| Flag | What it does |
| --- | --- |
| `--profile, -p <name>` | Override the active profile for this invocation (beats `DHIS2_PROFILE` env and the TOML default). |
| `--debug, -d` | Verbose output on stderr — logs every HTTP request with method, URL, status, bytes, elapsed ms. Useful when reporting issues or tracing why a command talked to an unexpected endpoint. |

```bash
d2w -d system whoami
# 10:54:05  dhis2w_client.http         GET http://localhost:8080/api/system/info -> 200 (2165 bytes, 9ms)
# 10:54:05  dhis2w_client.http         GET http://localhost:8080/api/me -> 200 (2760 bytes, 17ms)
# admin (admin admin)
```

Debug output lands on stderr so stdout stays pipeable:

```bash
d2w -d route list > routes.json        # routes.json is clean; trace shows in terminal
d2w -d maintenance task types 2> trace.log   # the other way around
```
