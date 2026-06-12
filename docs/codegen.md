# Codegen

`dhis2w-codegen` is a workspace member that emits typed pydantic models + resource classes into `packages/dhis2w-client/src/dhis2w_client/generated/v{NN}/`.

Two source-of-truth paths, both emitting into the same per-version directory:

- **`/api/schemas`** → `generated/v{N}/schemas/` + `generated/v{N}/resources.py` + `generated/v{N}/enums.py`. Covers the 100+ metadata resources and their CONSTANT-property enums. Driven by `d2w dev codegen generate` / `rebuild`.
- **`/api/openapi.json`** → `generated/v{N}/oas/`. Covers the instance-side shapes `/api/schemas` can't describe: `WebMessage` envelopes, tracker read/write models, `DataValue` / `DataValueSet`, auth-scheme leaves, data-integrity checks, `SystemInfo`. Driven by `d2w dev codegen oas-rebuild`.

Generated code is **committed**, reviewable in diffs, and forms the typed surface of the client. PyPI consumers of `dhis2w-client` don't need to run codegen to install the library.

## Why a separate member

- **The client wheel on PyPI must stay lean** — no jinja2, no generator tooling.
- **The generator can import `dhis2w-client`** to reuse `AuthProvider` / `Dhis2Client` for talking to the live instance.
- **Future plugins** (e.g. custom-schema generators for specific deployments) can depend on `dhis2w-codegen` without pulling the rest of the tooling.

## Invocation

Four subcommands — `generate` and `rebuild` for the `/api/schemas` path, `oas-rebuild` for OpenAPI, and `diff` for cross-version analysis:

```bash
# /api/schemas — against a live instance (the canonical sources for codegen
# are the play.im.dhis2.org/dev-2-{42,43} instances; `make dhis2-codegen-play`
# wraps both)
uv run d2w dev codegen generate --url https://play.im.dhis2.org/dev-2-43 \
                                  --username admin --password district

# /api/schemas — regenerate from the committed schemas_manifest.json (no network)
uv run d2w dev codegen rebuild                       # every committed version
uv run d2w dev codegen rebuild --manifest path/to/schemas_manifest.json

# /api/openapi.json — regenerate oas/ from the committed openapi.json (no network)
uv run d2w dev codegen oas-rebuild                   # every committed version
uv run d2w dev codegen oas-rebuild --version v42     # just one

# Cross-version diff — surfaces schemas added / removed and per-property
# changes (type, klass, bounds, owner/required/etc) when bumping majors
uv run d2w dev codegen diff v42 v43
uv run d2w dev codegen diff v42 v43 --json    # machine-readable
```

`d2w dev codegen generate` talks to a live instance because it pulls the `/api/schemas` response fresh; the rebuild variants are offline, reading the committed manifest / openapi.json from each `generated/v{N}/` directory. `diff` is also offline — it reads the two committed manifests and surfaces structural drift. The CLI subcommand is registered via `[project.entry-points."dhis2.plugins"]` in `dhis2w-codegen`'s `pyproject.toml`.

## Pipeline

1. **Authenticate.** Use one of the shipped `AuthProvider` implementations. For the standalone run, `--username/--password` or `--pat` give Basic/PAT auth. For the CLI flavor, `--profile NAME` reads the stored profile.
2. **Discover version.** `GET /api/system/info` → extract `version` (e.g. `"2.42.0"` → `"v42"`).
3. **Fetch schemas.** `GET /api/schemas?fields=name,plural,apiEndpoint,displayName,klass,metadata,properties[*]` — one request gets every metadata type with their full property definitions.
4. **Write the manifest.** `generated/v42/schemas_manifest.json` — raw snapshot of the schemas response. Audit trail, and the input to emission. Re-running the emitter without re-fetching is possible.
5. **Emit models.** One pydantic `BaseModel` file per schema, in `generated/v42/schemas/<resource>.py`. Field names mirror DHIS2 wire format (camelCase) so there's no alias translation at parse/serialise time. Nested references use a common `Reference` model with at minimum an `id` field.
6. **Emit resources.** `generated/v42/resources.py` — one `_<Name>Resource` class per metadata type with `get`, `list`, `create`, `update`, `delete`. A `Resources` container class bundles them all and is instantiated by `Dhis2Client.connect()`.
7. **Stamp and format.** `generated/v42/__init__.py` sets `GENERATED = True` and re-exports `Resources`. The whole output directory is run through `ruff format`.

## Schema → pydantic-type mapping

| DHIS2 property type | Python type |
| --- | --- |
| `TEXT`, `IDENTIFIER`, `EMAIL`, `URL`, `PHONENUMBER`, `COLOR` | `str` |
| `BOOLEAN` | `bool` |
| `INTEGER` | `int` |
| `NUMBER` | `float` |
| `DATE`, `DATETIME` | `datetime` |
| `REFERENCE` | `Reference` (min: `{"id": str}`, local to each schema module) |
| `COLLECTION` of X | `list[X]` |
| `COMPLEX` | `Any` (preserves mixed-shape payloads via `ConfigDict(extra="allow")`) |
| `CONSTANT` with `constants=[...]` | Generated `StrEnum` in `dhis2w_client.generated.v{N}.enums` (e.g. `ValueType.INTEGER_POSITIVE`, `DataElementDomain.AGGREGATE`). Accepts bare strings too — `StrEnum` is a `str` subclass. |

The primary key that DHIS2's `/api/schemas` names `uid` is renamed to `id` on emit so generated models match the wire format (DHIS2's REST API uses `id` on every read/write — see BUGS.md #7). The `uid` spelling stays nowhere in generated code.

For collection properties, the generator uses the singular `name + "s"` as the wire field rather than the `/api/schemas` `fieldName` (which is sometimes a Hibernate column alias like `sources` that doesn't match the JSON DHIS2 actually returns).

All properties are `Optional` (default `None`) — DHIS2 doesn't reliably mark which are required in the schema response, and "nothing known" beats "wrong schema".

## What lives in `dhis2w-codegen`

```
packages/dhis2w-codegen/src/dhis2w_codegen/
├── __init__.py
├── __main__.py           # python -m dhis2w_codegen entry
├── cli.py                # Typer sub-app (generate / rebuild / oas-rebuild / diff)
├── diff.py               # Cross-version manifest diff helper
├── discover.py           # /api/system/info + /api/schemas fetch, returns SchemasManifest
├── emit.py               # SchemasManifest → files on disk (the /api/schemas path)
├── oas_emit.py           # openapi.json → files on disk (the /api/openapi.json path)
├── mapping.py            # DHIS2 schema property → Python type string
├── names.py              # camelCase resource → snake_case module + safe Python identifier
├── _shared.py            # helpers used by both emitters (identifier sanitisation, ruff format)
└── templates/            # jinja2 templates
    ├── model.py.jinja    # /api/schemas models
    ├── resources.py.jinja
    ├── enums.py.jinja
    ├── init.py.jinja
    └── oas/              # /api/openapi.json templates
        ├── oas_model.py.jinja
        ├── oas_enums.py.jinja
        ├── oas_aliases.py.jinja
        └── oas_init.py.jinja
```

## Trade-offs

- **Committed generated code**, not gitignored. Diffs are reviewable; downstream PyPI users of `dhis2w-client` don't need to run codegen to install the library.
- **Minor-version granularity** (`v42`, not `2.42.1`). Patch-level differences aren't worth separate modules.
- **Emission uses jinja2 templates**, not ad-hoc string building. Templates are easier to tweak and diff than escaped f-strings.
- **Tests are on the mapping + naming logic**, not the end-to-end emit. Full emission requires a live instance or a canned manifest fixture; we'll commit a minimal one in `tests/fixtures/` so end-to-end tests don't need network.
- **The generator reuses `dhis2w-client`'s auth/client**, so any auth flow that works at runtime also works for codegen. Including OAuth2 PKCE — the generator is just another client consumer.

## OpenAPI emitter specifics

The OAS path diverges from the `/api/schemas` emitter in three ways worth knowing:

- **Every field optional.** OpenAPI's `required:` list is ignored; DHIS2 over-marks fields relative to real response contents (`WebMessage.errorCode` is flagged required but every 200-OK response omits it).
- **Large enums demote to string aliases.** Enums with more than 64 members become plain `str` aliases. `ErrorCode` lists 488 values and adds new ones every minor release — a strict StrEnum would reject every unknown code between regen passes. Small enums (status / domain / value-type / ...) stay closed StrEnums.
- **Builtin shadows rename.** Schema names that collide with Python builtins rename to `DHIS2<Name>` (only `Warning` → `DHIS2Warning` in v42). Pydantic resolves `list[Warning]` to the builtin class at FieldInfo construction regardless of `defer_build`, so emit-time renaming is the only reliable fix.

The `_types_namespace` injection trick in `generated/v{N}/oas/__init__.py` bypasses pydantic's forward-ref + cycle problem: every generated class gets copied into every submodule's globals before `model_rebuild()` runs. See `oas_emit.py` and the `oas_init.py.jinja` template.

Each OpenAPI regen also writes `generated/v{N}/openapi_manifest.json` summarising the emitted set + a sha256 of the input `openapi.json`, so diffs between runs stay readable.

## Deferred

- **Type-aware field/filter/order DSL.** For now, `resources.X.list(fields="id,displayName,...")` takes a string. A typed DSL (`Q.fields(R.DataElement.id, R.DataElement.displayName)`) giving IDE autocomplete over resource properties would be an obvious next step; f-strings already handle the stringly-typed value side well enough that the work hasn't been urgent.
