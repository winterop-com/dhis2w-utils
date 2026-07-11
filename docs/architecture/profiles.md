# Profiles — multi-instance DHIS2 configuration

A **profile** is a named bundle of "how to reach one DHIS2 instance" — a base URL plus credentials. You can have as many as you want, switch between them from the CLI, and target a specific one per MCP tool call.

## Profile model location

The `Profile` Pydantic model itself lives in `dhis2w-client` so library users on PAT, Basic, or session auth can build profiles and call `dhis2w_client.open_client(profile)` without installing `dhis2w-core` and its heavier dependencies. TOML loading + writing, multi-profile resolution (`resolve()` / `load_catalog()` / the precedence chain), and OAuth2 token persistence stay in `dhis2w-core` — every `from dhis2w_core.profile import Profile` etc. import keeps working via re-export.

## Where profiles live

Two TOML files, both read on every tool invocation:

| Scope | Path | Flag | When to use it |
| --- | --- | --- | --- |
| Global (default) | `~/.config/dhis2/profiles.toml` | `--global` | Instances you use everywhere — laptop-default, your personal play server, production |
| Project | `<cwd or ancestor>/.dhis2/profiles.toml` | `--local` | Instance tied to a specific project — `cd` into the dir, profile auto-applies, overrides global of the same name |

**Global is the default.** `d2w profile add foo ...` with no scope flag writes to `~/.config/dhis2/profiles.toml`. Use `--local` when you want a project-scoped profile. This matches `aws configure` (`~/.aws/credentials` default), kubectl (`~/.kube/config`), and git (`git config --global` / `--local`).

Project file wins over global for any profile name that exists in both — useful when a project ships a `.dhis2/profiles.toml` that overrides a global default without disturbing your other work.

Both files live under a **directory** (`.dhis2/` / `~/.config/dhis2/`), not as loose files, so we can drop other per-scope config next to them later (token store, cache DB, preferences) without moving things around.

## File shape

```toml
default = "prod"

[profiles.local]
base_url = "http://localhost:8080"
auth = "pat"
token = "d2p_..."

[profiles.play]
base_url = "https://play.im.dhis2.org/dev"
auth = "basic"
username = "system"
password = "System123"

[profiles.prod]
base_url = "https://dhis2.example.org"
auth = "pat"
token = "d2p_..."
version = "v43"  # optional — pins the plugin tree (see below)
```

The file is written with `0600` perms when created by `d2w profile add`. Gitignore `.dhis2/profiles.toml` — it contains secrets.

### Optional `version` field

`version = "v41" | "v42" | "v43"` selects which **plugin tree** (`dhis2w_core.v{N}.plugins.*`) the CLI/MCP loads at startup. It's a hint, not a wire-client pin — the wire `Dhis2Client` always auto-detects the server's version on `connect()` and rebinds accessors via `_dispatch.py`. See `docs/architecture/versioning.md` for the full chain.

When the field is omitted, the CLI consults the `DHIS2_VERSION` env var (the vXX key: `v41` / `v42` / `v43`); when that's also unset, it defaults to the canonical v42 tree. A `version` pin wins over `DHIS2_VERSION`. `make verify-examples` follows the same `resolve_startup_version()` chain, so a v41-pinned profile runs the `examples/v41/...` tree automatically; on an unpinned profile, `make verify-examples DHIS2_VERSION=v43` drives the v43 tree without editing the profile.

## Resolution precedence

Every tool call (CLI or MCP) resolves a profile through this chain. Highest wins:

```
1. Explicit argument             ← CLI `--profile NAME`, MCP tool arg `profile="NAME"`
2. DHIS2_PROFILE env var         ← set by MCP server config, shell export, or CLI callback
3. DHIS2_URL + DHIS2_PAT/... env ← raw env mode (no TOML needed — CI-friendly)
4. Project TOML default          ← nearest `.dhis2/profiles.toml` walking up from $PWD
5. User-wide TOML default        ← `~/.config/dhis2/profiles.toml`
6. NoProfileError                ← with a clear message telling you to run `d2w profile add`
```

Project overrides global for any profile name that exists in both (merged in `load_catalog()`).

## Naming rules

Profile names must match `^[A-Za-z][A-Za-z0-9_]*$` with a max length of 64:

- starts with an ASCII letter
- contains only letters, digits, and underscores
- no spaces, hyphens, dots, slashes, or other punctuation

Typical names: `local`, `prod`, `prod_eu`, `test42`, `laohis42`, `dhis2_42`, `sandbox`.

These constraints keep names safe as env var suffixes (`DHIS2_PROFILE=prod_eu`), TOML keys, and unquoted shell arguments. `d2w profile add "he llo"` fails with a clean error pointing at these rules. Validation happens at every mutation (`add`, `rename`, `default`) — you can't commit a bad name via the tooling.

## CLI

```bash
d2w profile list                        # see every profile (project + global) with default marker
d2w profile verify                      # hit /api/system/info + /api/me on every profile
d2w profile verify prod                 # verify just one — exit code 0 if ok, 1 if not
d2w profile show prod                   # pretty-print one profile (secrets redacted)
d2w profile show prod --secrets         # including secrets (for copy-paste debugging)
d2w profile env prod                    # print `export DHIS2_*` lines (values as-is)
eval "$(d2w profile env prod)"          # load them into the current shell

# Add a PAT-based profile (goes to ~/.config/dhis2/profiles.toml by default).
# `d2w profile add` doesn't accept secrets as flags (they'd leak into shell
# history). When DHIS2_PAT is unset, the command prompts interactively:
d2w profile add prod \
  --url https://dhis2.example.org \
  --auth pat \
  --default
# Personal Access Token: ******** (typed silently)

# ...with an immediate /api/system/info + /api/me probe to confirm auth works
d2w profile add prod --verify \
  --url https://dhis2.example.org \
  --auth pat
# profile 'prod' saved to /Users/you/.config/dhis2/profiles.toml
#   verified: version=2.42.4 user=admin (182 ms)

# For non-interactive use (CI, Makefile, scripts), load the secret from an
# env file that you keep out of git + history. `set -a` exports each variable
# the file defines until `set +a`:
set -a; source /path/to/.env.auth; set +a
d2w profile add prod --url https://dhis2.example.org --auth pat --default

# Add a basic-auth profile scoped to the current project. `--username` goes
# on the command line; the password is prompted (or read from DHIS2_PASSWORD):
d2w profile add local \
  --local \
  --url http://localhost:8080 \
  --auth basic --username admin
# Password: ********

d2w profile default prod                 # set default = prod in the global file (no flag needed)
d2w profile default prod --local         # set default = prod in the project file

d2w profile rename prod prodeu          # rename in-place; preserves scope + updates default if needed
d2w profile rename prod prodeu --verify # ...and probe the renamed profile
d2w profile remove prod                 # removes from wherever it lives (--global/--local to force one)
```

### `--verify` on mutations

`add`, `rename`, and `default` accept `--verify` to probe the instance immediately after writing. Default is off — most `add` calls happen before the instance is even running (CI bootstrap, docker-compose bring-up, etc.), so forcing a network probe would be wrong by default. Opt in per invocation when you want the immediate feedback:

```bash
d2w profile add prod --verify --url ... --auth pat
# Personal Access Token: ********
# profile 'prod' saved to /Users/you/.config/dhis2/profiles.toml
#   verified: version=2.42.4 user=admin (182 ms)
```

Failures on `--verify` are informational — the profile stays saved with a yellow warning, and the exit code is still 0. Use `d2w profile verify prod` later to re-check.

## Global `--profile` flag

Every `d2w` command accepts `--profile NAME` at the root:

```bash
d2w --profile prod system whoami
d2w -p staging metadata list dataElements
```

The flag sets `DHIS2_PROFILE` for the rest of the invocation, which flows through to every plugin's service call.

## MCP

**Every tool** accepts an optional `profile: str | None = None` kwarg. Agent flow:

```
1. Agent calls `profile_list` →
   [{"name": "local", "default": false, "source": "global-toml", ...},
    {"name": "prod",  "default": true,  "source": "global-toml", ...}]

2. Agent calls `profile_verify("prod")` →
   {"ok": true, "version": "2.42.4", "username": "admin", "latency_ms": 180}

3. Agent calls any other tool targeting that profile →
   `metadata_list(resource="dataElements", profile="prod")`
   `data_aggregate_get(data_set="X", org_unit="Y", profile="prod")`
   `analytics_query(dimensions=[...], profile="prod")`
```

If the agent omits `profile`, resolution falls through to `DHIS2_PROFILE` env (from the MCP server config), then raw env, then TOML default — same chain as the CLI.

### Why writes are CLI-only

`profile_list`, `profile_verify`, `verify_all_profiles`, `profile_show` are exposed as MCP tools — they're read-only and safe. `add_profile`, `remove_profile`, `set_default_profile` are **deliberately not** MCP tools — letting an autonomous agent rewrite your credential files is the wrong default. Mutations go through the CLI, where a human is on the keyboard.

## Running multiple MCP servers against different profiles

Easiest way to connect one agent to several DHIS2 instances is register multiple MCP servers, each with a different env:

```json
{
  "mcpServers": {
    "dhis2-local": {
      "command": "uv", "args": ["run", "dhis2w-mcp"],
      "env": { "DHIS2_PROFILE": "local" }
    },
    "dhis2-prod": {
      "command": "uv", "args": ["run", "dhis2w-mcp"],
      "env": { "DHIS2_PROFILE": "prod" }
    }
  }
}
```

Each server picks up its named profile from `~/.config/dhis2/profiles.toml` via `DHIS2_PROFILE`. The agent sees two disjoint tool namespaces (`dhis2-local/whoami`, `dhis2-prod/whoami`) and picks whichever it needs.

Alternatively: register **one** MCP server and pass `profile="prod"` per tool call. Same result, different ergonomics.

## Full end-to-end: from zero to "I'm querying prod"

```bash
# 1. Add one profile, user-wide, make it default. The PAT is prompted
# interactively (no flag — secrets never go on the command line) or read
# from DHIS2_PAT if set in the current shell.
d2w profile add prod \
  --global \
  --url https://dhis2.example.org \
  --auth pat \
  --default
# Personal Access Token: ********

# 2. Verify the auth works.
d2w profile verify prod
# OK prod  https://dhis2.example.org  auth=pat  version=2.42.4  user=admin  182 ms

# 3. Use it from the CLI (implicit default).
d2w system whoami
d2w metadata list dataElements --limit 10

# 4. Or target it explicitly.
d2w --profile prod metadata get dataElements fbfJHSPpUQD

# 5. Restart your MCP client. The agent sees `prod` via `profile_list`
#    and calls `metadata_get(resource="dataElements", uid="...", profile="prod")`.
```

## Security

- Profile files are written with `0600` perms.
- Gitignore **`.dhis2/profiles.toml`** if you're storing a project-scoped file in a versioned repo.
- Secrets are redacted in `d2w profile show` unless `--secrets` is passed.
- `profile_show` MCP tool redacts unconditionally.
- No plaintext secrets appear in logs.

Planned: OS-keyring-backed storage for OAuth2 tokens (and optionally PATs) so the TOML only holds a reference, not the raw secret.

## What's not in profiles yet

- **Profile import/export.** `d2w profile export prod > prod.toml` is a trivial add when we want to share profile shapes (without secrets) between machines.

## Already shipped (no longer pending)

- **OAuth2 end-to-end integration.** `d2w profile add NAME --auth oauth2 ...` and `d2w profile login NAME` walk the user through the OAuth 2.1 + PKCE flow against `/oauth2/authorize` and `/oauth2/token`. `client_context.build_auth()` wires the resulting `OAuth2Auth` provider into the standard pipeline. The seeded `.env.auth` from `make dhis2-run` plus `d2w profile add ... --auth oauth2 --from-env` provisions a working profile in one command.
- **Per-profile token caches.** `dhis2w-core/token_store.py` is an active `sqlalchemy[asyncio]` + `aiosqlite` store at `.dhis2/tokens.sqlite` (or the user-global equivalent next to the active profiles file). OAuth2 access + refresh tokens land in it; the client refreshes silently near expiry.

## Design decisions

- **Name-as-ID, not UUID.** You pick the name at creation time. Short, readable, stable. No separate identifier to remember.
- **Directories, not loose files.** `.dhis2/` at project root, `~/.config/dhis2/` user-wide. We'll drop cache DBs and token stores in there later without moving anything.
- **Project > global.** A profile named `prod` in the project wins over a global `prod`. Lets a single project override defaults without affecting other work.
- **Writes are CLI-only in MCP.** `profile_list` / `profile_verify` / `profile_show` are read-only and safe; `add` / `remove` / `default` stay CLI-only because agents shouldn't rewrite credential files autonomously.
- **Raw env mode without TOML.** `DHIS2_URL + DHIS2_PAT` alone (no profiles.toml) resolves as a synthetic profile with source `env-raw`. CI-friendly for one-off shell invocations.
