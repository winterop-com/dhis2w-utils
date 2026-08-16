# Version-aware generated clients

## URLs do not carry the version

DHIS2's API is always mounted at `/api/...`. Earlier DHIS2 releases exposed a versioned path variant (`/api/30/dataElements`); that's being phased out. Every URL this client constructs uses the plain `/api/{plural}` form.

Version-awareness therefore lives in the **payload shapes**, not the URLs. DHIS2 2.42 returns slightly different fields for (say) a `DataElement` than 2.44. Our generated pydantic models capture those differences per-version, and `Dhis2Client.connect()` picks the right module for whatever instance you're connected to.

## Why version-scoped models at all

DHIS2 schemas evolve across versions. New metadata types appear, existing types get new properties, enums pick up new constants. A single hand-curated client either gets out of date or lags behind the latest release.

Instead of fighting that, we lean in: each supported DHIS2 version gets its **own generated module** under `dhis2w_client.generated.v{NN}`, produced by `d2w codegen` from that instance's `/api/schemas` endpoint.

## Layout

```
packages/dhis2w-client/src/dhis2w_client/
├── __init__.py          # version-agnostic re-exports (Dhis2 enum, Dhis2Client, ...)
├── generated/           # auto-generated wire types per version
│   ├── __init__.py      # version registry + loader + Dhis2 enum
│   ├── v41/             # DHIS2 2.41.x
│   ├── v42/             # DHIS2 2.42.x (119 schemas)
│   └── v43/             # DHIS2 2.43.x (116 schemas)
├── v41/                 # hand-written client surface for v41
├── v42/                 # hand-written client surface for v42 (canonical)
├── v43/                 # hand-written client surface for v43
└── <submodule>.py       # top-level shims re-exporting from v42 for backwards-compat

packages/dhis2w-core/src/dhis2w_core/
├── plugin.py            # discovery walks dhis2w_core.v{N}.plugins.*
├── v42/plugins/<name>/  # canonical plugin tree (cli.py, mcp.py, service.py, ...)
├── v41/plugins/<name>/  # mirror of v42, diverges per-file as v41 quirks land
└── v43/plugins/<name>/  # mirror of v42, diverges per-file as v43 quirks land
```

Three supported majors — v41, v42, v43. Other DHIS2 majors are out of scope; the codegen tooling can still target them via `d2w dev codegen generate --url ...` against an arbitrary stack, but no manifests or generated trees are committed.

The hand-written `v{N}/` subpackages start as byte-equivalent copies of v42 and diverge per-file as version-specific behaviour lands (the `categorys` -> `categories` field rename on v43's CategoryCombo, the missing `OAuth2ClientCredentialsAuthScheme` on v41's generated tree, etc.). Until a file diverges, all three trees import from `dhis2w_client.generated.v42.*` to keep the symbol set consistent. Divergence is per-method and called out in BUGS.md.

Each populated `v{NN}/` carries:

- `__init__.py` — sets `GENERATED = True` and re-exports every resource schema (`from dhis2w_client.generated.v42 import DataElement`).
- `schemas/` — one pydantic `BaseModel` per DHIS2 metadata type, with `Field(description=...)` hints for owner/writable/bounds.
- `resources.py` — typed CRUD accessors (`client.resources.dataElements.get/list/create/update/delete`).
- `schemas_manifest.json` — snapshot of the `/api/schemas` response used at generation time. Committed so `d2w dev codegen rebuild` can regenerate offline.

The generated code is **committed**, not gitignored. Diffs are reviewable in PRs — you can see when a new field appears on a resource, when an enum gains a constant, when an endpoint is removed. The per-version `infra/v{N}/dump.sql.gz` dumps (Flyway-bootstrapped, no user data) sit alongside as cheap restore points.

## The `Dhis2` enum

`dhis2w_client.Dhis2` is a `StrEnum` listing the three supported majors — `Dhis2.V41`, `Dhis2.V42`, `Dhis2.V43`. Two uses:

```python
from dhis2w_client import Dhis2, Dhis2Client

# 1. Pin the version, skip auto-detection via /api/system/info.
async with Dhis2Client(url, auth=auth, version=Dhis2.V42) as client:
    ...

# 2. Direct schema import without the full path.
from dhis2w_client.generated.v42 import DataElement, OrganisationUnit
```

## Plugin-tree selection at CLI / MCP startup

The CLI (`d2w ...`) and MCP server (`dhis2w-mcp`) pick a single plugin tree at bootstrap from `dhis2w_core.v{41,42,43}.plugins.*`. The selection chain (`dhis2w_core.plugin.resolve_startup_version`):

1. **`profile.version`** — if the active profile carries `version = "v41" | "v42" | "v43"` in `profiles.toml`, that tree is loaded.
2. **`DHIS2_VERSION` env var** — the vXX key (`v41` / `v42` / `v43`). Lets `make verify-examples DHIS2_VERSION=v43` exercise the v43 plugin tree against a v43 stack without hand-editing every profile. A bare digit (`43`) is not accepted.
3. **Default `v42`** — the canonical baseline.

This selection is independent of the wire client's actual version detection (`Dhis2Client.connect()` — see below). A profile pinned to v43 plugin tree against a v42 stack would load v43-specific plugin overrides + the v42 wire client; runtime dispatch swaps accessors after `connect()` so the wire chain remains correct regardless.

```bash
# Force the v43 plugin tree for a one-off run (overrides profile.version)
DHIS2_VERSION=v43 d2w metadata list dataElements
```

Library callers using `from dhis2w_client.v43 import Dhis2Client` skip the resolution chain entirely — the import path pins the version.

## Runtime dispatch

On `Dhis2Client.connect()`:

1. `GET /api/system/info` → raw version string (e.g. `"2.42.0"`).
2. The minor component is extracted (e.g. `42`) and mapped to `"v42"`.
3. `dhis2w_client.generated.available_versions()` is consulted — only populated versions (`GENERATED = True`) are candidates.
4. If `"v42"` is populated, that module is loaded and bound to `client.resources`, `client.models`, etc.
5. If `"v42"` is not populated and `allow_version_fallback=False` (default), `UnsupportedVersionError` is raised, pointing the user at `d2w codegen`.
6. If fallback is enabled and the live version isn't populated, the nearest-lower populated version is chosen — never higher. With v41 + v42 + v43 populated, the practical case is "any DHIS2 above v43 falls back to v43".

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    # client.version_key == "v42"  (or "v43", depending on the active profile)
    # client.raw_version == "2.42.0"
    ...
```

## Working with version-specific types

Hand-written client helpers (`client.system.info()`, `client.dashboards.list()`, `client.tracked_entity_attributes.get()`, etc.) currently parse responses against the **v42** generated models. That's fine for the ~95% of fields that are stable across DHIS2 v42 and v43, but it means:

- v43-only fields (e.g. `Program.enableChangeLog`, `TrackedEntityAttribute.trigramIndexed`) are not visible at typed-access time. They survive on the parsed model under `model_extra` because every generated class uses `ConfigDict(extra="allow")`.
- A handful of **breaking-shape** schemas — fields where the v43 wire shape isn't structurally compatible with the v42 model — fail to parse against v43 wire data. The full list is in [Schema diff: v41 -> v42 -> v43](schema-diff-v41-v42-v43.md). The headline cases:

    | Schema | v42 | v43 |
    | --- | --- | --- |
    | `DashboardItem.user` | `Reference \| None` | `list[User]` (renamed `users` on the wire) |
    | `TrackedEntityAttribute.favorite` | `bool` | `list[str]` (renamed `favorites` on the wire) |
    | `Section.user` | `Reference \| None` | removed |
    | `Program.favorite` | `list[str]` | removed |
    | `Legend` | full identifiable-object surface | almost everything stripped (~20 fields removed) |

If you need typed access to v43-only fields, or you want to defensively branch on the live version, here are the patterns.

### Pattern 1 — branch on `client.version_key`

`Dhis2Client.version_key` returns the loaded module key (`"v42"`, `"v43"`, ...) after `connect()`. Use it to decide which path to take when the wire shape differs:

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    if client.version_key == "v43":
        # v43-only field, accessed via model_extra (the v42-typed model has it under .model_extra).
        info = await client.system.info()
        capability = (info.model_extra or {}).get("systemCapabilities")
    else:
        capability = None
```

### Pattern 2 — direct `dhis2w_client.generated.v43.*` imports

For typed access to a v43-only model, import it directly. This bypasses the v42-pinned helper and works against any v43 instance:

```python
from dhis2w_client.generated.v43.schemas.tracked_entity_attribute import (
    TrackedEntityAttribute as TrackedEntityAttributeV43,
)
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    raw = await client.get_raw("/api/trackedEntityAttributes/foo")
    # On v43, this gets you the typed `favorites: list[str]` plus the new search fields.
    attribute = TrackedEntityAttributeV43.model_validate(raw)
    print(attribute.favorites, attribute.trigramIndexed)
```

The `dhis2w_client.generated.v43.*` paths are first-class — every v43 schema is importable. The `examples/client/v43_*.py` files are runnable end-to-end demos, one per changed schema (DashboardItem, TrackedEntityAttribute, Program, EventVisualization, Map, Section, removed resources). Pick the file matching the schema you care about; each shows both the `model_extra` path and the direct-v43-import path.

### Pattern 3 — pin the client to a known version

If you control the deployment and want to skip the `/api/system/info` round-trip on `connect()`, pass `version=Dhis2.V43` explicitly. The client will assert the server matches and bind the v43 generated module up-front:

```python
from dhis2w_client import Dhis2, Dhis2Client

async with Dhis2Client(url, auth=auth, version=Dhis2.V43) as client:
    ...
```

### What this does NOT solve

Hand-written helper return types are still annotated as v42-shape at static-type-check time. mypy / pyright will flag `program.enableChangeLog` as unknown even though the parsed object has it in `model_extra`. The honest options are: cast, `getattr(model, "enableChangeLog", None)`, or use Pattern 2 above. We may revisit this with a generic-over-version client in a future release; the current contract is "runtime is correct, static is v42-flavored."

## Why strict by default

When `Dhis2Client.connect()` finds the live version doesn't have a populated module — e.g. someone runs against a DHIS2 above v43 — there are three reasonable choices:

- **Refuse** — force the user to run codegen against the live instance. Guarantees typing matches reality.
- **Fall back to the nearest-lower populated version** — newer fields silently disappear; typed access to known fields still works.
- **Runtime-generate** — build pydantic models on the fly from `/api/schemas`. Dynamic types, no static analysis, no IDE autocomplete. Rejected.

We default to "refuse" because a strict codebase that loudly fails when things are stale beats one that silently diverges. Opt-in soft fallback (`allow_version_fallback=True`) is there for CLIs and agents that want to keep working against unknown versions with a warning.

## Regenerating

`make dhis2-codegen-all` (or the underlying `infra/scripts/codegen_all_versions.sh`) orchestrates the whole pipeline. Default set is v41 + v42 + v43:

```bash
infra/scripts/codegen_all_versions.sh            # default — v41 + v42 + v43
infra/scripts/codegen_all_versions.sh 43         # subset
```

For each version N, the script:

1. Brings up a fresh `dhis2/core:N` stack with an empty-gzip placeholder where `infra/v{N}/dump.sql.gz` sits (so Flyway bootstraps a clean schema instead of loading the seeded e2e dump into a fresh stack).
2. Waits for `/api/system/info` to respond.
3. Runs `d2w dev codegen generate` against `http://localhost:8080` with admin/district, which writes `generated/v{N}/schemas/`, `resources.py`, `__init__.py`, and `schemas_manifest.json`.
4. `pg_dump`s the post-Flyway schema into `infra/v{N}/dump.sql.gz` (excluding derived analytics_*, aggregated_*, completeness_*, and `_*` tables — those are regenerated by `analytics-trigger`).
5. Tears down, restores the committed dump.

Rebuilding from a committed manifest (no network) is cheap:

```bash
uv run d2w dev codegen rebuild                              # every v{N}/schemas_manifest.json
uv run d2w dev codegen rebuild --manifest path/to/foo.json  # just one
```

Useful after touching `emit.py` or the Jinja templates when you want all three trees refreshed without booting each server.

## Trade-offs

- **More code to review.** Every DHIS2 release produces a committed diff. That's the point — it's auditable — but it means the `generated/` folder grows with each version.
- **Committed generated code.** Some teams prefer gitignored generators. We don't — we want diffs reviewable, and we want `dhis2w-client` to work on PyPI without users having to run codegen themselves.
- **One codegen per version, not per instance.** If two v42 instances have wildly different custom metadata, one of them will have models its code doesn't describe. We cover the standard schema; per-instance customization is not a goal of `dhis2w-client` and probably belongs in a plugin.
- **Minor version only.** We key on `"v42"`, not `"2.42.1"`. Patch-level differences are not worth separate modules. If DHIS2 changes the schema mid-minor (which they shouldn't), we'd need to revisit.
