# Client examples

Python library usage — `dhis2w-client` + `dhis2w-core.client_context.open_client()` — for callers embedding the DHIS2 client inside a larger application. Every example reads the active DHIS2 profile (via env or TOML). The `dhis2w-fhir` library path lives in its own group at [`examples/fhir/client/`](../fhir/client/).

> **Canonical catalogue**: [`docs/examples.md`](../../docs/examples.md) — curated example index — headline examples per topic with links to the concept docs that explain each one.

## Prerequisites

```bash
make dhis2-run                                       # DHIS2 + seeded auth
set -a; source infra/home/credentials/.env.auth; set +a

# Create a profile once — examples resolve it automatically via DHIS2_PROFILE / TOML discovery.
d2w profile add local --url http://localhost:8080 --auth pat --default --verify
```

## Running one

```bash
uv run python examples/client/whoami.py
```

Examples that need `DHIS2_OAUTH_*` env (the OIDC flow) say so in their docstring.

## Entry points

- `dhis2w_client.Dhis2Client(url, auth)` — the top-level async client (v42-typed). Runtime dispatch swaps accessors to v41 / v43 when connected to those servers; static typing sees the v42 shape.
- `dhis2w_core.client_context.open_client(profile)` — profile-aware context manager. Most examples use this, and it needs no version pin at all.
- `dhis2w_core.v42.plugins.<name>.service.*` — service-layer functions for operations that have a typed CLI/MCP surface (metadata import/diff/patch, user admin, …). See `metadata_export.py` / `metadata_diff.py` / `metadata_patch.py` for the pattern.

See the [client library tutorial](../../docs/client/tutorial.md) for a narrative walkthrough of the main entry points.

## Which DHIS2 major an example is written against

Every example here runs on v41, v42, and v43. Where an example needs a version-pinned import — `dhis2w_client.v42`, `dhis2w_core.v42.client_context`, `dhis2w_client.generated.v42.schemas` — it is written against **v42, the canonical baseline**, and carries one comment above that import saying to swap `.v42` for `.v41` / `.v43` to pin another major. The pin buys static typing through a major's own accessors; runtime dispatch is correct either way.

## Version-only examples

An example that exists for one major and has no counterpart on the others lives under that major's subdirectory. `make verify-examples` runs the active major's variants and ignores the rest.

### [`v43/`](v43/) — v43 schema deltas

DHIS2 v43 differs from v42 in a handful of resource shapes — `DashboardItem.user` becomes `users`, `TrackedEntityAttribute.favorite` becomes `favorites`, `Section.user` and `Program.favorite` are removed, three top-level resources are dropped, and ~20 new fields appear across Program / EventVisualization / Map / TrackedEntityAttribute. The full per-resource diff is at [`docs/architecture/schema-diff-v41-v42-v43.md`](../../docs/architecture/schema-diff-v41-v42-v43.md); the narrative + access patterns are at [`docs/architecture/versioning.md`](../../docs/architecture/versioning.md).

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

### [`v41/`](v41/) — v41 wire quirks

DHIS2 v41 has a small set of wire-shape quirks the workspace tracks in `BUGS.md`. v42 and v43 ship no equivalents because the quirks do not exist there.

| Example | Quirk / change kind |
| --- | --- |
| `oauth2_cid_field.py` | v41 OAuth2 client wire shape uses `cid` instead of `clientId` (BUGS.md #39) |
| `apps_display_name.py` | v41 `App.displayName` runtime override (the `App.model_rebuild()` materialisation path) |
| `grid_rows_wire_shape.py` | v41 `Grid.rows` widening — OAS says `list[list[dict]]`, wire is scalars |
