# Client examples (v42 — canonical baseline)

Python library usage — `dhis2w-client` + `dhis2w-core.client_context.open_client()` — for callers embedding the DHIS2 client inside a larger application. Every example reads the active DHIS2 profile (via env or TOML) and runs against a v42 DHIS2 stack. v42 is the canonical baseline; v41 and v43 mirror most examples in their own trees.

> **Canonical catalogue**: [`docs/examples.md`](../../../docs/examples.md) — curated v42 example index — headline examples per topic with links to the concept docs that explain each one.

## Prerequisites

```bash
make dhis2-run                                       # DHIS2 v42 + seeded auth
set -a; source infra/home/credentials/.env.auth; set +a

# Create a profile once — examples resolve it automatically via DHIS2_PROFILE / TOML discovery.
d2w profile add local --url http://localhost:8080 --auth pat --default --verify
```

## Running one

```bash
uv run python examples/v42/client/whoami.py
```

Examples that need `DHIS2_OAUTH_*` env (the OIDC flow) say so in their docstring.

## Entry points

- `dhis2w_client.Dhis2Client(url, auth)` — the top-level async client (v42-typed). Runtime dispatch swaps accessors to v41 / v43 when connected to those servers; static typing sees the v42 shape.
- `dhis2w_core.client_context.open_client(profile)` — profile-aware context manager. Most examples use this.
- `dhis2w_core.v42.plugins.<name>.service.*` — service-layer functions for operations that have a typed CLI/MCP surface (metadata import/diff/patch, user admin, …). See `metadata_export_import.py` / `metadata_diff.py` / `metadata_patch.py` for the pattern.

See the [client library tutorial](../../../docs/guides/client-tutorial.md) for a narrative walkthrough of the main entry points.

## v43 schema deltas

DHIS2 v43 differs from v42 in a handful of resource shapes — `DashboardItem.user` becomes `users`, `TrackedEntityAttribute.favorite` becomes `favorites`, `Section.user` and `Program.favorite` are removed, three top-level resources are dropped, and ~20 new fields appear across Program / EventVisualization / Map / TrackedEntityAttribute. The full per-resource diff is at [`docs/architecture/schema-diff-v41-v42-v43.md`](../../../docs/architecture/schema-diff-v41-v42-v43.md); the narrative + access patterns are at [`docs/architecture/versioning.md`](../../../docs/architecture/versioning.md).

Schema-divergence examples (read-side parsing of v43 wire data + write-side setters for v43-only fields) live under [`examples/v43/client/`](../../v43/client/), not here — they need the v43-pinned client class so static type-checkers see the v43-only attributes / methods. Look there for `dashboard_item_users.py`, `tracked_entity_attribute_favorites.py`, `event_visualization_fix_headers.py`, `map_basemaps.py`, `section_user_removed.py`, `removed_resources.py`, and the `program_set_*` setters.
