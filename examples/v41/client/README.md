# Client examples (v41)

Python library usage — `dhis2w-client` + `dhis2w-core.client_context.open_client()` — for callers embedding the DHIS2 client inside a larger application. Every example reads the active DHIS2 profile (via env or TOML) and runs against a v41 DHIS2 stack.

> **Canonical catalogue**: [`docs/examples.md`](../../../docs/examples.md) — curated v42 example index — headline examples per topic with links to the concept docs that explain each one. v41 and v43 mirror most of those, plus carry version-specific additions for their schema deltas.

## Prerequisites

```bash
make dhis2-run                                       # DHIS2 + seeded auth (v42 by default — for v41 launch with `DHIS2_VERSION=41 make dhis2-run`)
set -a; source infra/home/credentials/.env.auth; set +a

# Create a profile once — examples resolve it automatically via DHIS2_PROFILE / TOML discovery.
d2w profile add local --url http://localhost:8080 --auth pat --default --verify
```

## Running one

```bash
uv run python examples/v41/client/whoami.py
```

Examples that need `DHIS2_OAUTH_*` env (the OIDC flow) say so in their docstring.

## Entry points

- `dhis2w_client.v41.Dhis2Client(url, auth)` — the raw async client, version-pinned. Use when you want static typing through v41-only typed accessors.
- `dhis2w_core.v41.client_context.open_client(profile)` — profile-aware context manager that yields a v41-pinned client. Most examples use this.
- The top-level `dhis2w_core.client_context.open_client(profile)` yields the v42-typed top-level `Dhis2Client`; runtime dispatch still swaps accessors to v41 when connected to a v41 server, but static type-checkers see the v42 shape.

See the [client library tutorial](../../../docs/guides/client-tutorial.md) for a narrative walkthrough of the main entry points and the version-pinning trade-offs.

## v41-specific examples

DHIS2 v41 has a small set of wire-shape quirks the workspace tracks in `BUGS.md`. The examples below specifically demonstrate them; v42 and v43 don't ship equivalents because the quirks don't exist on those versions:

| Example | Quirk / change kind |
| --- | --- |
| `oauth2_cid_field.py` | v41 OAuth2 client wire shape uses `cid` instead of `clientId` (BUGS.md #39) |
| `apps_display_name.py` | v41 `App.displayName` runtime override (the `App.model_rebuild()` materialisation path) |
| `grid_rows_wire_shape.py` | v41 `Grid.rows` widening — OAS says `list[list[dict]]`, wire is scalars |

For the schema-level v41 ↔ v42 ↔ v43 diff, see [`docs/architecture/schema-diff-v41-v42-v43.md`](../../../docs/architecture/schema-diff-v41-v42-v43.md).
