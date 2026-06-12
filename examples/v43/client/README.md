# Client examples (v43)

Python library usage — `dhis2w-client` + `dhis2w-core.client_context.open_client()` — for callers embedding the DHIS2 client inside a larger application. Every example reads the active DHIS2 profile (via env or TOML) and runs against a v43 DHIS2 stack.

> **Canonical catalogue**: [`docs/examples.md`](../../../docs/examples.md) — curated v42 example index — headline examples per topic with links to the concept docs that explain each one. v41 and v43 mirror most of those, plus carry version-specific additions for their schema deltas.

## Prerequisites

```bash
make dhis2-run                                       # DHIS2 + seeded auth (v42 by default — for v43 launch with `DHIS2_VERSION=43 make dhis2-run`)
set -a; source infra/home/credentials/.env.auth; set +a

# Create a profile once — examples resolve it automatically via DHIS2_PROFILE / TOML discovery.
d2w profile add local --url http://localhost:8080 --auth pat --default --verify
```

## Running one

```bash
uv run python examples/v43/client/whoami.py
```

Examples that need `DHIS2_OAUTH_*` env (the OIDC flow) say so in their docstring.

## Entry points

- `dhis2w_client.v43.Dhis2Client(url, auth)` — the raw async client, version-pinned. Use when you want static typing through v43-only typed accessors (e.g. `client.programs.set_labels`).
- `dhis2w_core.v43.client_context.open_client(profile)` — profile-aware context manager that yields a v43-pinned client. Most examples use this.
- The top-level `dhis2w_core.client_context.open_client(profile)` yields the v42-typed top-level `Dhis2Client`; runtime dispatch still swaps accessors to v43 when connected to a v43 server, but static type-checkers see the v42 shape.

See the [client library tutorial](../../../docs/guides/client-tutorial.md) for a narrative walkthrough of the main entry points and the version-pinning trade-offs.

## v43-specific examples

DHIS2 v43 differs from v42 in a handful of resource shapes — `DashboardItem.user` becomes `users`, `TrackedEntityAttribute.favorite` becomes `favorites`, `Section.user` and `Program.favorite` are removed, three top-level resources are dropped, and ~20 new fields appear across Program / EventVisualization / Map / TrackedEntityAttribute. The full per-resource diff is at [`docs/architecture/schema-diff-v41-v42-v43.md`](../../../docs/architecture/schema-diff-v41-v42-v43.md); the narrative + access patterns are at [`docs/architecture/versioning.md`](../../../docs/architecture/versioning.md).

Examples that exercise v43-only fields or workarounds (v42 + v41 don't ship these):

| Example | Schema / change kind |
| --- | --- |
| `dashboard_item_users.py` | `DashboardItem.user` -> `users` (rename + reshape: `Reference` -> `list[User]`) |
| `tracked_entity_attribute_favorites.py` | `TrackedEntityAttribute.favorite` -> `favorites` (rename + reshape) + 6 new search fields |
| `program_set_labels.py` / `program_set_change_log.py` / `program_set_enrollment_category_combo.py` | v43-only `Program` setters for the new UI label / change-log / alt-enrollment-CC fields |
| `event_visualization_fix_headers.py` | `EventChart` / `EventReport` / `EventVisualization` add `fixColumnHeaders`, `fixRowHeaders`, `hideEmptyColumns` |
| `map_basemaps.py` | `Map.basemaps` v43-only addition (collection of `Basemap`) |
| `section_user_removed.py` | `Section.user` removed in v43 (also `Section.favorite`) |
| `removed_resources.py` | `pushAnalysis`, `externalFileResource`, `dataInputPeriods` removed in v43 |
| `category_combo_coc_regen.py` | v43 BUGS #33: CategoryCombo saves no longer auto-regen the COC matrix — `client.category_combos.wait_for_coc_generation(...)` workaround |
