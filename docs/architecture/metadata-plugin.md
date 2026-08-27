# Metadata plugin

`dhis2w-core/v42/plugins/metadata/` is the workspace's largest plugin — the `metadata_*` group registers roughly 230 MCP tools (the auto-regenerated [MCP reference](../mcp-reference.md) is the source of truth), spanning bundle workflows, cross-resource search, RFC 6902 patching, and dedicated authoring sub-apps for the highest-traffic DHIS2 resources. The generic CRUD still ships on `client.resources.<name>` (see [Metadata CRUD](metadata-crud.md)) and remains the right escape hatch when a specific resource type doesn't have a hand-written sub-app yet.

## What it exposes

### Core surface — CRUD, bundle ops, cross-resource workflows

| Operation | CLI | MCP tool |
| --- | --- | --- |
| List available resource types | `d2w metadata type list` | `metadata_type_list` |
| List instances of one type | `d2w metadata list <resource>` | `metadata_list` |
| Fetch one by UID | `d2w metadata get <resource> <uid>` | `metadata_get` |
| Search across every resource | `d2w metadata search <query>` | `metadata_search` |
| Reverse-lookup "what references this UID?" | `d2w metadata usage <uid>` | `metadata_usage` |
| Patch an object (RFC 6902) | `d2w metadata patch <resource> <uid>` | `metadata_patch` |
| Export a bundle | `d2w metadata export` | `metadata_export` |
| Import a bundle | `d2w metadata import FILE` | `metadata_import` |
| Diff two bundles (or bundle vs live) | `d2w metadata diff A B [--live]` | `metadata_diff` |
| Diff two profiles (staging vs prod drift) | `d2w metadata diff-profiles A B -r <resource>` | `metadata_diff_profiles` |
| Merge one profile's metadata into another | `d2w metadata merge SOURCE TARGET -r <resource> [--dry-run]` | `metadata_merge` |

The `<resource>` argument is DHIS2's camelCase plural — `dataElements`, `indicators`, `organisationUnits`, `dashboards`, `dataSets`. The plugin maps it to the Resources attribute (`data_elements`, etc.) via a tiny camel-to-snake helper.

### Authoring sub-apps — hand-written surfaces for the high-traffic resources

| Sub-app | Purpose | API doc |
| --- | --- | --- |
| `d2w metadata organisation-units` + `organisation-unit-groups` + `organisation-unit-group-sets` + `organisation-unit-levels` | Hierarchy tree walk, per-level rename, group + group-set authoring | [organisation units](../api/organisation-units.md) |
| `d2w metadata data-elements` + `data-element-groups` + `data-element-group-sets` | Aggregate + tracker DE authoring, thematic groups, analytics dimensions | [data elements](../api/data-elements.md) |
| `d2w metadata indicators` + `indicator-groups` + `indicator-group-sets` | Computed-ratio authoring with numerator/denominator expression pre-flight | [indicators](../api/indicators.md) |
| `d2w metadata program-indicators` + `program-indicator-groups` | Tracker-analytics authoring (pair, not triple — DHIS2 has no PIGroupSet) | [program indicators](../api/program-indicators.md) |
| `d2w metadata category-options` + `category-option-groups` + `category-option-group-sets` | Disaggregation values + validity windows + analytics dimensions | [category options](../api/category-options.md) |
| `d2w metadata legend-sets` | Colour-range authoring attached to visualisations + maps | [legend sets](../api/legend-sets.md) |
| `d2w metadata option-sets` | `OptionSet` / `Option` workflows — get / find / idempotent `sync` | — |
| `d2w metadata attributes` | Cross-resource `AttributeValue` workflows (get / set / delete / find) | — |
| `d2w metadata program-rules` | Program-rule introspection + expression validation + DE-usage lookup | — |
| `d2w metadata sql-views` | SQL-view list / get / execute / refresh / adhoc | [SQL views](../api/sql-views.md) |
| `d2w metadata visualizations` + `d2w metadata dashboards` | Spec-driven visualization authoring + dashboard composition | [visualizations](../api/visualizations.md) |
| `d2w metadata maps` | Thematic-choropleth + boundary map authoring | [maps](../api/maps.md) |

The five analytics triples follow a single canonical-naming rule — lowercase + hyphenate the DHIS2 `/api/<resource>` path — so the CLI / MCP tool / Python attribute names all derive mechanically from the wire resource name (`/api/organisationUnitGroupSets` → `d2w metadata organisation-unit-group-sets` → `metadata_organisation_unit_group_set_*` → `client.organisation_unit_group_sets`).

## `metadata list` — full flag surface

Every DHIS2 `/api/<resource>` query parameter is exposed:

| Flag | DHIS2 param | Example | Notes |
| --- | --- | --- | --- |
| `--fields` | `fields=` | `--fields ":identifiable"` | See [Field selector](#field-selector). |
| `--filter` | `filter=` | `--filter "name:like:Penta"` | Repeatable. See [Filter syntax](#filter-syntax). |
| `--root-junction` | `rootJunction=` | `--root-junction OR` | Combine multiple `--filter`s. Default `AND`. |
| `--order` | `order=` | `--order "name:asc"` | Repeatable, later clauses tie-break. |
| `--page` | `page=` | `--page 2` | 1-based. Server-side. |
| `--page-size` | `pageSize=` | `--page-size 100` | Default 50 on DHIS2's side. |
| `--all` | `paging=false` + walk | `--all` | Stream every server-side page via `iter_metadata`. |
| `--translate` / `--no-translate` | `translate=` | `--translate` | Return localised `displayName`, etc. |
| `--locale` | `locale=` | `--locale fr` | Pair with `--translate`. |
| `--json` | — | `--json` | Emit JSON instead of a rich table. |

## Filter syntax

DHIS2 filters follow `property:operator:value`:

| Operator | Meaning | Example |
| --- | --- | --- |
| `eq` | equals | `code:eq:DE_PENTA1` |
| `!eq` / `ne` | not equal | `code:!eq:REFERENCE` |
| `gt`, `ge`, `lt`, `le` | numeric/date compare | `created:ge:2024-01-01` |
| `like` / `!like` | SQL LIKE (case-sensitive) | `name:like:Penta` |
| `ilike` / `!ilike` | case-insensitive LIKE | `name:ilike:malaria` |
| `in:[a,b,c]` | property in set | `id:in:[abc,def]` |
| `!in:[a,b]` | property NOT in set | `code:!in:[X,Y]` |
| `null` / `!null` | null / non-null | `description:null` |
| `empty` / `!empty` | empty string | `code:empty` |
| `token` / `!token` | token-match (whitespace-split) | `name:token:malaria cases` |

Combine via repeated `--filter`:

```bash
d2w metadata list dataElements \
  --filter "valueType:eq:INTEGER_POSITIVE" \
  --filter "domainType:eq:AGGREGATE"
# AND by default — both must match
```

Or OR:

```bash
d2w metadata list dataElements \
  --filter "name:like:Penta" \
  --filter "code:eq:DE_PENTA1" \
  --root-junction OR
# either match is enough
```

Nested-property filters work too: `children.name:like:x`.

## Field selector

Plain, preset, nested, and transformed:

| Shape | Example | Resolves to |
| --- | --- | --- |
| Plain | `id,name,code` | those three fields |
| Preset | `:identifiable` | `id,name,code,created,lastUpdated,displayName` |
| Preset | `:nameable` | `:identifiable` + `shortName`, `description` |
| Preset | `:owner` | every "owner"-category field for the resource |
| Preset | `:all` | every field on the object |
| Exclusion | `:all,!lastUpdated` | `:all` minus `lastUpdated` |
| Nested | `children[id,name,level]` | those fields inside each `children` entry |
| Rename | `displayName~rename(label)` | DHIS2 returns the field as `label` |

```bash
# Presets save typing for the common shapes
d2w metadata list dataElements --fields ":identifiable"

# Nested selector pulls a sub-tree
d2w metadata list organisationUnits --fields "id,name,children[id,name]"

# `:all,!<field>` excludes expensive fields
d2w metadata list dashboards --fields ":all,!dashboardItems"
```

## Pagination

| Mode | How | When to use |
| --- | --- | --- |
| Single page | `--page 1 --page-size 50` | Interactive use, top-N browsing. |
| Walk pages | `--page N` repeatedly | You control the iteration. |
| Stream all | `--all` | Full catalog dump; the service walks page=1,2,... internally. |

`--all` uses the service's `iter_metadata` async generator with `page_size=500` by default — large enough to keep request count low, small enough not to blow memory on heavy `:all` selectors.

## Localisation

```bash
d2w metadata list dataElements --translate --locale fr --fields ":identifiable"
# displayName returns the French translation when DHIS2 has one
```

## `metadata search` — cross-resource UID / code / name lookup

`d2w metadata search <query>` takes one verb and finds every matching object across every enabled DHIS2 metadata resource. The query matches with `ilike` on three axes, OR-merged by the client:

- `id:ilike:<q>` — full or partial UID.
- `code:ilike:<q>` — business code fragment.
- `name:ilike:<q>` — case-insensitive substring on the name.

Same verb for every use case: paste a UID from a log line, a prefix you remember, a code from an interop mapping, or an English fragment — the call returns a table grouped by resource type with name, UID, and code per hit.

```bash
# Name fragment — broadest hit set.
d2w metadata search measles

# Full UID — resolves to the owning resource type (dataElements, dashboards, ...)
d2w metadata search s46m5MS0hxu

# Partial UID prefix — ilike:<prefix> matches everything starting with it.
d2w metadata search s46m

# JSON output for scripting.
d2w --json metadata search measles | jq '.hits.dataElements | length'
```

`--page-size N` narrows the per-resource cap (default 50). `--json` emits the typed `SearchResults` payload for downstream pipelines.

### Narrowing the search

Three flags polish the default broadcast-search behaviour when you know more about what you're looking for:

- `--resource <plural>` — narrow to one DHIS2 resource kind (e.g. `dataElements`, `dashboards`). Skips the cross-resource broadcast and hits `/api/<resource>` directly, so you get the same three `id`/`code`/`name` fanout but only against the one type you care about.
- `--fields id,name,code,valueType,domainType,...` — ask DHIS2 for extra attributes per hit. Anything beyond the core four (`id` / `name` / `code` / `href`) lands on `SearchHit.extras` and renders as trailing columns in the Rich table.
- `--exact` — switch every filter from `:ilike:` (substring) to `:eq:` (strict). Useful when a partial UID like `s46m` would match too many siblings.

```bash
# Strict UID match, narrowed to DEs, with the value-type column:
d2w metadata search s46m5MS0hxu --exact --resource dataElements \
    --fields id,name,code,valueType,domainType,aggregationType
```

MCP side:

```python
result = await mcp.call_tool(
    "metadata_search",
    {
        "query": "measles",
        "resource": "dataElements",
        "fields": "id,name,code,valueType",
        "exact": False,
        "page_size": 20,
    },
)
# -> {"query": "measles", "hits": {"dataElements": [...]}, "total": 7}
```

**Why three HTTP calls instead of one?** DHIS2's `/api/metadata` endpoint silently ignores `rootJunction` and ANDs multiple filters (see BUGS.md #29). The accessor fans out three concurrent single-filter calls (one per field) and merges them with UID dedup. Three round-trips for cross-field OR — when DHIS2 fixes the endpoint's filter semantics, this collapses back to one call.

## `metadata usage` — reverse lookup "what references this UID?"

`d2w metadata usage <uid>` is the complement of `search`: instead of finding the UID, you paste the UID and get back every object that references it. Useful as a deletion-safety probe — any dashboard / visualization / map / dataset / program / program stage / program rule / user / org-unit group that would break if you deleted the UID shows up in the result.

How it works:

1. Resolve the UID's owning resource via `/api/identifiableObjects/{uid}` — DHIS2's canonical "what type is this UID" endpoint.
2. Look up the known reference paths for that owning type in the client's `_USAGE_PATTERNS` map.
3. Fan out concurrent `/api/<target>?filter=<path>:eq:<uid>` calls — e.g. for a data element, hit `dataSets?filter=dataSetElements.dataElement.id:eq:<uid>`, `visualizations?filter=dataDimensionItems.dataElement.id:eq:<uid>`, and so on across ~8 reference paths.
4. Merge the per-target results into the same `SearchResults` shape `metadata search` returns, grouped by owning target resource.

```bash
# Before removing a data element, see what uses it:
d2w metadata usage s46m5MS0hxu
# -> 1 dataset, 10 visualizations, 3 maps (in the Sierra Leone seed)

# A viz is only on dashboards:
d2w metadata usage Qyuliufvfjl
# -> 2 dashboards

# Root org unit surfaces users, OU groups, datasets, programs:
d2w metadata usage ImspTQPwCqd
```

Coverage is best-effort — the reference map encodes the shapes most likely to block a delete in practice. Unknown owning types (e.g. `userRoles` outside the usual pattern) return an empty result; that's a signal to extend the map, not a proof the UID is unreferenced.

MCP side:

```python
result = await mcp.call_tool("metadata_usage", {"uid": "s46m5MS0hxu"})
# -> same `SearchResults` shape as metadata_search
```

## MCP example

```python
await mcp.call_tool(
    "metadata_list",
    {
        "resource": "dataElements",
        "fields": ":identifiable",
        "filters": ["valueType:eq:INTEGER_POSITIVE", "domainType:eq:AGGREGATE"],
        "root_junction": "AND",
        "order": ["name:asc"],
        "page_size": 25,
        "translate": True,
        "locale": "fr",
    },
)
# -> [{"id": "...", "name": "...", "code": "...", ...}, ...]
```

Agents pass `paging=False` (the default when `--all` is on at the CLI) to receive every row in one response.

## Typed surface all the way through

The plugin returns typed pydantic models at every service boundary; the
JSON-shaped `dict` only appears at the two edges that actually need it —
the HTTP wire (going in and out of DHIS2) and the MCP/CLI serialisation
edge (where the output format is text). Every other layer is typed.

| Service function | Return type |
| --- | --- |
| `list_metadata(...)` | `list[<GeneratedModel>]` (e.g. `list[DataElement]`) |
| `get_metadata(...)` | `<GeneratedModel>` |
| `iter_metadata(...)` | `AsyncIterator[<GeneratedModel>]` |
| `export_metadata(...)` | `MetadataBundle` |
| `diff_bundles(left, right)` | `MetadataDiff` (takes `MetadataBundle` on both sides) |
| `bundle_dangling_references(bundle)` | `DanglingReferences` |
| `import_metadata(profile, bundle)` | `WebMessageResponse` (takes `MetadataBundle`) |

### `MetadataBundle`

`dhis2w_core.v42.plugins.metadata.models.MetadataBundle` wraps a DHIS2
`GET /api/metadata` response. DHIS2's top-level keys come in two shapes —
meta (`system`, `date`) and dynamic resource collections (`dataElements`,
`indicators`, ...). `MetadataBundle` exposes the meta keys as typed
nullable slots and the resource collections via typed accessor methods:

```python
from dhis2w_core.v42.plugins.metadata.models import MetadataBundle

# Build from a raw /api/metadata response (or JSON on disk):
bundle = MetadataBundle.from_raw(json.loads(path.read_text()))

# Iterate resource collections:
for resource_name, items in bundle.resources():
    for item in items:
        print(item.id, item.name)  # typed id + name

# Helpers:
bundle.all_uids()  # set[str] — every top-level UID
bundle.summary()  # {dataElements: 12, indicators: 3, ...}
bundle.total()  # total object count
bundle.get_resource("dataElements")  # list[MetadataItem] or []
bundle.has_resource("options")  # bool
```

Each item is a `MetadataItem` — `extra="allow"` pydantic model with typed
`id` + `name` plus every other DHIS2 field preserved. Nested references
inside an item (e.g. `categoryCombo: {id: ...}`) stay as bounded dicts in
`model_extra`; the rule carveout lets those bottom-layer refs exist
because they're only ever reached through typed accessors, never a
function's return type.

### Where dicts still appear (by design)

`list_metadata` / `get_metadata` return typed generated models; dumping
to JSON happens at the MCP tool edge (`_dump_model(...)`) and the CLI
JSON-output edge (`_dump_for_cli(...)`). Library callers get typed
models all the way through; agents get dicts.

The `POST /api/metadata` wire serialisation uses `bundle.to_wire()` which
returns a `dict[str, Any]` — consumed on the very next line by
`client.post_raw`. Same carveout as any `model_dump` call at an HTTP
boundary.

## Error handling

- Unknown resource → `UnknownResourceError` with a helpful message suggesting `list_resource_types`. Both CLI and MCP surface this as an actionable error.
- Server-side errors (403, 409, 500) propagate as `Dhis2ApiError` — FastMCP wraps them as tool-error results with the DHIS2 message body attached.

## Patch — partial updates via RFC 6902 JSON Patch

`d2w metadata patch <resource> <uid>` applies an RFC 6902 JSON Patch to a
single metadata object. DHIS2 accepts `PATCH /api/<resource>/{uid}` on every
metadata type — much lighter than round-tripping the full object via PUT
when you only need to change a handful of fields.

### Two input modes

**Inline:** `--set path=value` and `--remove path` are both repeatable and
combine into a single patch array on the wire. Values are JSON-decoded when
they parse as JSON, so booleans and numbers type through correctly:

```bash
d2w metadata patch dataElements fClA2Erf6IO \
  --set '/description=Renamed via CLI' \
  --set '/zeroIsSignificant=false' \
  --remove '/legacyField'
```

**File:** `--file patch.json` reads a full patch array on disk — every RFC
6902 op is accepted (`add`, `remove`, `replace`, `test`, `move`, `copy`):

```bash
cat > patch.json <<'JSON'
[
  {"op": "replace", "path": "/name", "value": "New name"},
  {"op": "copy", "path": "/shortName", "from": "/name"},
  {"op": "test", "path": "/valueType", "value": "INTEGER"}
]
JSON
d2w metadata patch dataElements fClA2Erf6IO --file patch.json
```

`--file` and `--set`/`--remove` are mutually exclusive (the CLI refuses
both in one call and refuses neither).

### Typed ops in Python code

Library callers skip the CLI and work with the discriminated `JsonPatchOp`
Union directly — every op is its own pydantic class with `extra="forbid"`
so wrong-shape payloads fail at construction time (a `RemoveOp` with a
`value` field is rejected before hitting DHIS2):

```python
from dhis2w_client import AddOp, ReplaceOp, RemoveOp, MoveOp
from dhis2w_core.v42.plugins.metadata import service

# Typed ops — IDE autocomplete on every field, no stringly-typed `op` tag.
await service.patch_metadata(
    profile,
    "dataElements",
    "fClA2Erf6IO",
    [
        ReplaceOp(path="/description", value="Updated"),
        AddOp(path="/code", value="DE_PENTA_1"),
        RemoveOp(path="/legacyField"),
    ],
)

# Or go straight through the generated accessor (no service layer):
await client.resources.data_elements.patch(
    "fClA2Erf6IO",
    [ReplaceOp(path="/name", value="Renamed")],
)
```

Typed + dict ops mix freely — dicts route through `JsonPatchOpAdapter` on
the wire:

```python
await service.patch_metadata(
    profile,
    "dataElements",
    uid,
    [
        ReplaceOp(path="/description", value="Typed"),
        {"op": "add", "path": "/code", "value": "DICT_OP"},  # also accepted
    ],
)
```

### MCP

The `metadata_patch(resource, uid, ops)` tool accepts any list of
`{op, path, value?, from?}` dicts. The tool signature routes each op
through the adapter server-side, so agents get clear validation errors
instead of silent DHIS2 400s when they pass wrong-shape ops.

## Export / import

Round-trip metadata across instances with `d2w metadata export` and
`d2w metadata import` — two commands that together cover the
cross-environment dev workflow (copy a slice from a live instance to a
fresh stack, diff against upstream, or ship a reviewed bundle through CI).

### Export

`GET /api/metadata` with optional per-resource narrowing + DHIS2's standard
skip flags.

```bash
# Everything DHIS2 exports by default, lossless round-trip fields:
d2w metadata export --output full.json

# Narrow slice: dataElements + indicators, identifiable fields only:
d2w metadata export \
  --resource dataElements --resource indicators \
  --fields ":identifiable" --output slice.json

# Trim sharing blocks (useful when the target has different users/groups):
d2w metadata export --skip-sharing --output clean.json
```

The bundle summary (resource → count) prints to **stderr** so stdout stays
pipe-friendly (`d2w metadata export | jq ...` works). `--output FILE`
also prints the summary table + the total written.

### Per-resource filters (narrow the export)

DHIS2's `/api/metadata` accepts per-resource filters and field selectors
via the `<resource>:filter=<expr>` / `<resource>:fields=<selector>` query
param form. Both are exposed:

```bash
# All dataElements whose name contains "Penta" AND valueType is INTEGER_POSITIVE,
# plus every indicator whose code starts with "HIV_":
d2w metadata export \
  --resource dataElements --resource indicators \
  --filter "dataElements:name:like:Penta" \
  --filter "dataElements:valueType:eq:INTEGER_POSITIVE" \
  --filter "indicators:code:like:HIV_" \
  --output slice.json

# Per-resource fields override: keep heavy `:owner` for dataElements, but only
# grab `:identifiable` for the large categoryCombos collection:
d2w metadata export \
  --resource dataElements --resource categoryCombos \
  --fields ":owner" \
  --resource-fields "dataElements::owner" \
  --resource-fields "categoryCombos::identifiable" \
  --output filtered.json
```

The filter DSL is identical to `d2w metadata list --filter`
([filter syntax](#filter-syntax)) — just prefixed with the resource name
and a colon. Repeated `--filter` values for the same resource are AND'd
server-side.

### Reference integrity (dangling-reference warning)

Narrowing an export by filter or resource type means your bundle can end
up with nested `{"id": "abc"}` references pointing at objects you didn't
include. `d2w metadata export` walks the downloaded bundle by default
and warns when this happens:

```
WARNING: 7 dangling reference(s) — UIDs referenced by objects in the bundle
but not present in the bundle itself.
  field             missing  sample UIDs
  categoryCombo     4        bjDvmb4bfuf, pA2tGE9o2o5, ... (+2 more)
  optionSet         2        PiZhoVG4Epg, XkQjnXmbpRG
  legendSets        1        PWpD1lcuIWn
Re-run with the referenced resource types added (e.g.
`--resource categoryCombos --resource optionSets`) or silence with
`--no-check-references`.
```

The walker groups by **reference field name** (the JSON key that held the
`{"id": "..."}`) so the user knows which resource type to add. It skips a
curated noise list by default — `createdBy`, `lastUpdatedBy`, `user`,
`userAccesses`, `userGroupAccesses`, `sharing` — because a metadata export
rarely includes the users DHIS2 refers to from those slots; including
them in the warning would drown the signal.

The programmatic API (`service.bundle_dangling_references(bundle)`) returns
a typed `DanglingReferences` model with `items` (per-field), `total_missing`,
`bundle_uid_count`, and an `is_clean` convenience flag — the same shape the
MCP `metadata_export` tool returns under `dangling_references` when
`check_references=True` (default).

Turn the check off with `--no-check-references` for scripted pipelines that
don't want the extra walk.

**Default `fields=":owner"`.** This is the field preset DHIS2 itself uses
internally for cross-instance imports — every property required to
faithfully recreate the object on the target. Narrowing to `":identifiable"`
/ `"id,name"` is fine for inspection but fails on import because key fields
(category-combo references, sharing, etc.) are missing.

### Import

`POST /api/metadata` with typed flag surface for every DHIS2 import
parameter.

```bash
# Real import (upsert, atomic rollback on any failure):
d2w metadata import bundle.json

# Pre-check with DHIS2's validate mode — runs preheat + validation, commits nothing:
d2w metadata import bundle.json --dry-run

# Tighter strategy: CREATE only (fails if any object already exists):
d2w metadata import bundle.json --strategy CREATE --atomic-mode ALL

# Loose: keep going on individual failures, continue-on-error semantics:
d2w metadata import bundle.json --atomic-mode NONE

# Resolve references by CODE instead of UID (useful for bundles from a
# different instance where UIDs won't match):
d2w metadata import bundle.json --identifier CODE
```

`--dry-run` maps to DHIS2's `importMode=VALIDATE` — the server runs the full
validation + preheat pass but doesn't commit. The resulting report (via
`WebMessageResponse.import_count()` / `.conflicts()`) shows what *would*
happen.

Full flag surface mirrors DHIS2 1:1: `--strategy`, `--atomic-mode`,
`--identifier`, `--skip-sharing`, `--skip-translation`, `--skip-validation`,
`--merge-mode`, `--preheat-mode`, `--flush-mode`. Every option is a direct
pass-through; no workspace-invented defaults except `CREATE_AND_UPDATE` +
`ALL` (which match DHIS2's own defaults).

### Service / MCP

The same surface is reachable from the library:

```python
from dhis2w_client import Dhis2Client
from dhis2w_core.v42.plugins.metadata import service

async with Dhis2Client(url, auth) as client:
    bundle = await service.export_metadata(
        profile,
        resources=["dataElements"],
        fields=":owner",
    )
    report = await service.import_metadata(
        profile,
        bundle,
        import_strategy="CREATE_AND_UPDATE",
        dry_run=True,
    )
    print(report.import_count())
```

MCP tools: `metadata_export` + `metadata_import`. Both accept a
`bundle_path` on disk so multi-megabyte bundles don't flow through the MCP
channel. See `examples/mcp/metadata_export.py` and
`examples/mcp/metadata_import.py` for the tool-call form.

## Diff — preview before importing

`d2w metadata diff` compares two bundles structurally (or one bundle
against the live instance) and reports per-resource create / update / delete
counts. Use it as a safety gate before a real `metadata import` so you can
see exactly which objects get touched.

```bash
# File vs file — structural comparison of two exports:
d2w metadata diff baseline.json candidate.json

# File vs live instance — "what would change if I imported baseline.json?":
d2w metadata diff baseline.json --live

# Show up to 5 offending UIDs per resource row:
d2w metadata diff baseline.json candidate.json --show-uids

# JSON envelope, for piping into CI:
d2w --json metadata diff baseline.json candidate.json | jq '.total_updated'

# Custom ignore list: treat `code` changes as noise too:
d2w metadata diff a.json b.json --ignore code --ignore description
```

### What counts as a change

Objects are matched by `id` across the two bundles. Each pair goes into
exactly one bucket:

- **created** — UID present in `right` but not `left`.
- **deleted** — UID present in `left` but not `right`.
- **updated** — UID present in both, at least one non-ignored top-level field
  differs.
- **unchanged** — UID present in both, every comparable field matches.

### Default ignored fields

DHIS2 rewrites `lastUpdated`, `lastUpdatedBy`, `created`, `createdBy`,
`translations`, `access`, `favorites`, and `href` on every import — they
would otherwise dominate diff output with noise. They're skipped by default.
Add more via repeated `--ignore FIELD` (the defaults stay; your additions
extend the set).

### `--live` narrows the export

Passing `--live` exports only the resource types present in `left` — so a
bundle that contains just `dataElements` triggers a fetch of just
`/api/metadata?dataElements=true`, not the full catalog. That keeps the
diff fast enough for interactive use.

### Service / MCP

```python
from dhis2w_core.v42.plugins.metadata import service

diff = service.diff_bundles(left_bundle, right_bundle)
print(diff.total_created, diff.total_updated, diff.total_deleted)
for resource in diff.resources:
    for change in resource.updated:
        print(resource.resource, change.id, change.changed_fields)

# Or: file-on-disk vs live instance.
live_diff = await service.diff_bundle_against_instance(
    profile,
    bundle,
    bundle_label="baseline.json",
)
```

MCP tool: `metadata_diff` (pass `left_path` + `right_path`, or `left_path` +
`live=True`). See `examples/mcp/metadata_diff.py` and
`examples/client/metadata_diff.py` for worked calls.

## `diff-profiles` — staging-vs-prod drift

`d2w metadata diff-profiles <a> <b>` exports the same resource slice from
two registered profiles concurrently and diffs them. Built for drift
monitoring between environments — staging and prod diverge by design on
user accounts, org-unit assignments, and incidental settings, so the
command REQUIRES a resource list and layers filters on top.

```bash
# Minimum: narrow to specific resource types (required).
d2w metadata diff-profiles stage prod -r dataElements -r indicators

# Per-resource filter — same `property:operator:value` DSL as
# `d2w metadata list --filter`, prefixed with the resource name:
d2w metadata diff-profiles stage prod \
  -r dataElements -r indicators \
  --filter 'dataElements:name:like:Penta' \
  --filter 'indicators:name:like:Penta'

# Extend the ignore list for cross-environment noise
# (sharing blocks and translations often differ without being "drift"):
d2w metadata diff-profiles stage prod -r dataElements \
  --ignore sharing --ignore translations

# CI shape: non-zero exit on any drift, JSON output for the alerting script.
d2w metadata diff-profiles stage prod -r dataElements \
  --exit-on-drift --json
```

The underlying engine (`service.diff_profiles`) fans out two
`export_metadata` calls via `asyncio.gather` so a slow staging instance
doesn't serialise with prod. Same filters are applied on both sides — what
you compare is always apples-to-apples.

MCP tool: `metadata_diff_profiles` (same shape; filters come in as
`per_resource_filters: {"resource": ["filter_expr", ...]}`).

The `examples/client/profile_drift_check.py` cookbook shows the Python
library path for the same pattern (useful when you want to post-process the
typed `MetadataDiff` before deciding what counts as real drift).
