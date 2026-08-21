# Security plugin

Read-only inspection of a DHIS2 instance's security posture. Starts deliberately
small — one command, `d2w security settings` — and is built to grow one command
at a time.

```
d2w security settings        # password policy, credential expiry, registration, lockout
d2w --json security settings # the same data as a typed JSON object
```

The plugin is **CLI-only** today: the descriptor's `register_mcp` is a no-op and
there is no `mcp.py`. That is a valid plugin shape (see
[plugin runtime](plugins.md)), and the [extension recipe](#adding-the-next-security-command)
below covers adding an MCP surface when a command warrants one.

## Layout

```
packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/security/
├── __init__.py    # plugin descriptor — name "security", register_cli, no-op register_mcp
├── cli.py         # Typer sub-app + register(app); render helpers (_number / _months / _flag)
├── service.py     # async pure functions taking a Profile, returning typed models
└── models.py      # SecuritySettings view-model
```

The three version trees are mechanical copies that differ **only** by import path
(`dhis2w_core.v42` -> `v41` / `v43`). The `/api/systemSettings` keys and endpoint
are identical across v41/v42/v43, so there is no per-version divergence to carry.

## `settings` — security slice of `/api/systemSettings`

`service.get_security_settings(profile)` does one `GET /api/systemSettings` and
validates the response into `SecuritySettings`. The model declares only the
security-relevant fields; Pydantic's default `extra="ignore"` drops the rest of the
~100-key settings object, so the slice stays focused in **both** the table and under
`--json` (no need to filter with `?key=` query params).

`SecuritySettings` is a **deliberate projection** of the generated OAS
`SystemSettings` model (`dhis2w_client.generated.v{41,42,43}.oas`), which already
declares every field here. We don't reuse the full generated model for this read
because it can't validate a live `/api/systemSettings` response: the endpoint returns
`keyAnalysisDisplayProperty` lowercase (`"name"`), which the OAS `DisplayProperty`
enum rejects ([BUGS.md #42](https://github.com/winterop-com/dhis2w-utils/blob/main/BUGS.md)).
The projection omits that one field, so it parses. The clean long-term fix is an OAS
spec-patch widening that enum, then a `client.system.settings() -> SystemSettings`
accessor the plugin can call — at which point this projection can shrink to a render
concern. Per `CLAUDE.md` rule 7, always grep the generated trees before hand-writing a
model; this is the documented exception, not a license to duplicate.

| Field (wire key) | Meaning |
| --- | --- |
| `minPasswordLength` | Minimum password length the server enforces |
| `maxPasswordLength` | Maximum password length |
| `credentialsExpires` | Password-expiry interval in months; `0` renders as `0 (never)` |
| `credentialsExpiresReminderInDays` | Days before expiry the user is reminded |
| `credentialsExpiryAlert` | Whether expiry alerts are sent |
| `keyAccountRecovery` | Self-service account recovery enabled (`accountRecovery` in the table) |
| `keySelfRegistrationNoRecaptcha` | Self-registration without reCAPTCHA |
| `keyLockMultipleFailedLogins` | Lock accounts after repeated failed logins |
| `enforceVerifiedEmail` | Require a verified email address |

### Example output

```
              security settings
┌─────────────────────────────────┬──────────┐
│minPasswordLength                │ 8        │
│maxPasswordLength                │ 72       │
│credentialsExpires               │ 0 (never)│
│credentialsExpiresReminderInDays │ 28       │
│credentialsExpiryAlert           │ no       │
│accountRecovery                  │ enabled  │
│selfRegistrationNoRecaptcha      │ disabled │
│lockMultipleFailedLogins         │ disabled │
│enforceVerifiedEmail             │ disabled │
└─────────────────────────────────┴──────────┘
```

## Library API

```python
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v42.plugins.security import service

settings = await service.get_security_settings(profile_from_env())
if (settings.minPasswordLength or 0) < 12:
    print("weak password floor")
```

## Adding the next security command

The plugin is a teaching-sized template. Adding a command — say
`d2w security whoami` — is the same loop every plugin follows. Do the work in the
**v42 tree first**, verify it against a live server, then sweep the two siblings.

1. **Service function** — add an `async def` to
   `v42/plugins/security/service.py` that takes a `Profile`, opens a client with
   `open_client`, and returns a typed model. Reuse the typed client surface where it
   exists (`client.system.me()`, `client.resources.<x>.list(...)`) and fall back to
   `client.get(path, model=..., params=...)` for raw endpoints.

   ```python
   async def whoami(profile: Profile) -> Me:
       """Return the authenticated user (username, roles, authorities)."""
       async with open_client(profile) as client:
           return await client.system.me()
   ```

2. **Model** — if the command returns a new shape, add a `BaseModel` to
   `models.py` (never a `dict` across module boundaries — see the typed-data rule in
   `CLAUDE.md`). Keep `extra="ignore"` unless you genuinely want to surface unknown
   keys. Reuse an existing client model (like `Me`) when one fits.

3. **CLI command** — add a `@app.command(...)` to `cli.py`. Branch on
   `is_json_output()`: dump the model under `--json`, otherwise build `DetailRow`s and
   call `render_detail` (or `render_list` for collections). Keep formatting in small
   helpers like the existing `_flag` / `_months` / `_number`.

4. **Sweep to v41 + v43** (hard requirement — `CLAUDE.md` rule 15). Every new
   symbol/command lands in all three trees. The trees differ only by import path, so:

   ```bash
   base=packages/dhis2w-core/src/dhis2w_core
   for V in v41 v43; do
     for f in cli.py service.py models.py __init__.py; do
       sed -e "s/dhis2w_core\.v42/dhis2w_core.$V/g" \
           -e "s/dhis2w_client\.v42/dhis2w_client.$V/g" \
           "$base/v42/plugins/security/$f" > "$base/$V/plugins/security/$f"
     done
   done
   grep -rn "v42" $base/v41/plugins/security $base/v43/plugins/security   # must print nothing
   ```

   If a command's wire shape ever diverges across versions, fold that divergence into
   the same PR and add a `BUGS.md` entry — don't ship "v42-only, others later".

5. **Test** — add a case to
   `packages/dhis2w-core/tests/security/test_security_settings_cli.py` (or a sibling). Patch
   `dhis2w_core.v42.plugins.security.service.open_client` with an `AsyncMock` context
   whose fake client returns your model, then drive the command through
   `CliRunner`. Assert both the `--json` payload and one human-output line.

6. **Examples** — add the invocation to `examples/cli/security.sh` (all
   three; they can be identical when the command is version-agnostic).

7. **Docs** — `make docs-cli` regenerates `docs/cli-reference.md` from the Typer app
   (it picks up the new command automatically). Add a row to this page's command list
   and, if the command is example-worthy, to `docs/examples.md`. Run `make docs-build`
   to surface broken links.

8. **Bridge read-only allowlist** — a new **read** command is refused by the
   [CLI bridge](../mcp/bridge.md) under `DHIS2_MCP_READONLY=1` until you register it.
   Add its leaf path to `READ_ONLY_COMMANDS` in
   `packages/dhis2w-mcp-bridge/src/dhis2w_mcp_bridge/cli_bridge.py`. The bridge's drift
   test derives the expected set from a verb heuristic (`get`/`list`/`show`/…), so if your
   command's verb is one of those you only update the committed set; if the verb is novel
   or collides with a write elsewhere in the tree (as `settings` does — a read under
   `security`, a write under `customize`), also add the full path to `READ_ONLY_LEAVES`
   in `packages/dhis2w-mcp-bridge/tests/test_cli_bridge.py`. The bridge is version-agnostic,
   so this is a single edit, not a three-tree sweep.

9. **Gate** — `make lint && make test` must pass before the PR.

### Adding an MCP surface

When a read command is worth exposing to MCP clients:

1. Create `v{41,42,43}/plugins/security/mcp.py` with a `register(mcp)` that wraps the
   same `service.py` function as a FastMCP tool (model the file on
   `user_group/mcp.py`). Tools dump the typed model at the MCP edge — never return a
   `dict` from the service layer.
2. Flip the descriptor's `register_mcp` in `__init__.py` from the no-op to
   `mcp_module.register(mcp)` and import `mcp as mcp_module`.
3. `make docs-mcp` regenerates `docs/mcp-reference.md`; the surface test in
   `packages/dhis2w-mcp/tests/test_mcp_surface.py` will see the new tools.

## Candidate next commands

Read-only first; these all map to endpoints the plugin can reach without mutating
state:

- `d2w security whoami` — authenticated user, roles, and authority count from
  `/api/me` (typed `Me` already exists in `dhis2w-client`).
- `d2w security authorities` — the current user's effective authorities from
  `/api/me/authorization`. That is the endpoint the DHIS2 Web API documentation
  gives for this list, and it is the one the command reads. `/api/me/authorities`
  answers the same list on 2.43.1 — both are declared in the instance's OpenAPI
  document, both return an identical array, and both have a `/{authority}`
  sibling that answers `true` or `false` — but only
  `/api/me/authorization` appears anywhere in the documentation. Reading the
  undocumented spelling buys nothing and takes on a name upstream never promised
  to keep.
- `d2w security password-policy --lint` — turn `settings` into pass/warn checks
  against a baseline (min length, expiry set, lockout on) — a thin sibling of the
  `doctor` probe model.
- `d2w security sharing-defaults` — default public-access settings for new metadata
  (`keyRequireAddToView`, `keyCanGrantOwnUserAuthorityGroups`, …).
- `d2w security sessions` — active sessions / OAuth2 clients, where the API exposes
  them.

Writes (rotating credentials, toggling self-registration, editing security settings)
are intentionally **out of scope** until a concrete caller needs them — keep the
plugin read-only by default, and gate any future write behind an explicit confirm
like the other mutating plugins.
