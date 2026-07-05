# `d2w` CLI

`dhis2w-cli` is a Typer console script (`d2w …`) that bundles every `dhis2w-core` plugin into one entry point. Every command has a matching MCP tool and a matching client accessor — they share the same typed service functions, so the three surfaces stay aligned.

## When to reach for it

- Quick one-shot operations from a terminal (`d2w metadata list dataElements`, `d2w data tracker push fixture.json`, etc.).
- Shell pipelines that pipe DHIS2 responses through `jq` / `awk` / standard tooling.
- CI / cron jobs (every command exits non-zero on failure).
- Day-to-day admin (the [walkthrough](../walkthrough.md) is a good end-to-end taste).

For embedding DHIS2 calls inside a Python service use the [Python client](../client/index.md). For agent-driven workflows use the [MCP server](../mcp/index.md).

## Install

Two install paths depending on whether you want `d2w` on your global `PATH` or pinned inside a project.

### Global user install — recommended for day-to-day terminal use

`uv tool install` puts the `d2w` binary into uv's tool bin directory (which lives on `PATH` after `uv tool update-shell`). Run `d2w …` from anywhere on your laptop.

```bash
uv tool install dhis2w-cli
d2w --version
```

For the `[browser]` extra (Playwright-driven PAT mint, screenshots, OIDC login automation):

```bash
uv tool install 'dhis2w-cli[browser]'
uv run playwright install chromium     # one-time, downloads ~150 MB of Chromium
```

Update / pin / uninstall:

```bash
uv tool upgrade dhis2w-cli                       # latest
uv tool install --reinstall dhis2w-cli==<version>   # pin a specific version
uv tool uninstall dhis2w-cli                     # remove
```

If `d2w` isn't on `PATH` after install, run `uv tool update-shell` once and restart your terminal.

### One-shot via `uvx` (no install)

For a single command without persisting the tool on disk. The package is `dhis2w-cli` but the binary is `d2w`, so `uvx --from` is required:

```bash
uvx --from dhis2w-cli d2w profile verify
```

Each `uvx` invocation re-creates a temporary environment, so it's slower than `uv tool install`. Good for trying the CLI before installing it permanently; not recommended for daily use.

### Local-to-a-project (pinning a specific version)

When you want the CLI pinned in a project's `uv.lock` (e.g. a sync project that calls `d2w …` from its own scripts):

```bash
uv add --dev dhis2w-cli
uv run d2w --version
```

Inside that project shell, `uv run d2w …` uses the pinned version.

### From the workspace checkout (developing dhis2w-cli itself)

If you cloned `dhis2-utils` to hack on the CLI:

```bash
git clone git@github.com:winterop-com/dhis2w-utils.git
cd dhis2w-utils
make install                          # uv sync --all-packages
uv run d2w --version
```

`make install` runs `uv sync --all-packages --all-extras` at the workspace root, so all ten workspace members (including `dhis2w-cli`) install in editable mode.

## First steps

Add a profile (interactive secret prompt — PAT, password, or OAuth2 client secret never go on the command line), then verify the connection:

```bash
# Save user-wide to ~/.config/dhis2/profiles.toml (default):
d2w profile add local --url http://localhost:8080 --auth pat --default

# Or scope to a single project directory (.dhis2/profiles.toml):
d2w profile add local --url http://localhost:8080 --auth pat --local --default

d2w profile verify
d2w system whoami
d2w system info
```

`d2w profile add` supports `--auth pat | basic | oauth2`; the OAuth2 path also has `--from-env` to pull `DHIS2_OAUTH_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` / `_SCOPES` from a `.env.auth` (handy with `make dhis2-run`). The [Connecting to DHIS2 guide](../guides/connecting-to-dhis2.md) covers each auth path in detail.

The `d2w --version` (or `-V`) flag prints the bound `dhis2w-cli` / `dhis2w-core` versions plus the active plugin tree — useful when debugging mismatch between the CLI and the DHIS2 server's reported version.

### Exporting a profile into the shell

`d2w profile env [NAME]` prints `export DHIS2_*` lines for a profile so you can load its connection settings into the current shell (or a CI job) without a TOML file. It is an offline read — the wire client still auto-detects the DHIS2 version on connect; the emitted `DHIS2_VERSION` is the profile's version pin (which major's plugin tree the CLI/MCP binds).

```bash
d2w profile env local_basic              # print the export lines
eval "$(d2w profile env local_basic)"    # load them into the current shell
```

The command only writes to stdout — it cannot mutate your shell, so wrap it in `eval "$(...)"` (or copy-paste). Values are printed as-is, including the password / token (already plaintext in `.dhis2/profiles.toml`), so the output is directly usable. For a redacted view (e.g. screen-sharing) use `d2w profile show` instead.

## Verifying the install

```bash
d2w --version
d2w --help                    # lists every plugin sub-app
d2w metadata --help           # lists metadata commands
d2w system info               # round-trip a real DHIS2 call
```

If `d2w --help` lists every plugin sub-app but `d2w system info` fails, the binary is fine — re-check your profile (`d2w profile show`, `d2w profile verify`).

## Where next

- [Tutorial](../guides/cli-tutorial.md) — step-by-step from `d2w profile add` through the operator workflow set (profile, metadata, analytics, users, maintenance, files, messaging, apps, route, browser, tracker authoring, doctor). The full surface lives in the auto-generated reference below.
- [CLI reference](../cli-reference.md) — auto-generated catalog of every command + option (regenerated by `make docs-cli`).
- [Architecture](../architecture/cli.md) — how the CLI mounts plugin sub-apps, where the service functions live.
- [PAT helper](../pat-helper.md) — `d2w profile pat create` as admin for provisioning PATs at scale.
- [Examples index](../examples.md) — shell scripts grouped by plugin.
