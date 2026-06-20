# System module

The `system` module on `Dhis2Client` wraps the non-metadata system endpoints — `/api/system/info` and `/api/me`. These don't come from `/api/schemas`, so they're **hand-written** in `dhis2w_client/system.py` rather than generated.

## Usage

```python
async with Dhis2Client(...) as client:
    info = await client.system.info()
    # -> SystemInfo(version="2.44-SNAPSHOT", revision="abc1234", ...)

    me = await client.system.me()
    # -> Me(id="xY123", username="system", authorities=["ALL"], ...)
```

`client.system` is initialised in `Dhis2Client.__init__` — it's available before `connect()` completes. That matters because `connect()` itself calls `system.info()` internally to discover the version.

## Models

Both `SystemInfo` and `Me` carry `model_config = ConfigDict(extra="allow")` so unknown fields from the DHIS2 response are preserved on the model (accessible via `model.__pydantic_extra__` or dict-style). That's deliberate — system endpoints accumulate fields across DHIS2 versions and we don't want to silently drop them.

The common fields are explicitly typed:

- **`SystemInfo`** — `version`, `revision`, `buildTime`, `serverDate`, `contextPath`, `calendar`, `dateFormat`, `systemId`, `systemName`
- **`Me`** — `id`, `username`, `displayName`, `email`, `firstName`, `surname`, `authorities`, `organisationUnits`, `userGroups`, `userRoles`

## Server introspection (`ServerInfo`)

`/api/system/info` describes the DHIS2 server. **`ServerInfo`** describes the *workspace process* talking to it — which plugin tree (`v41` / `v42` / `v43`) was selected at startup, where that selection came from (`profile.version` field / `DHIS2_VERSION` env / default fallback), and which `dhis2w-*` packages are installed.

Surface:

- Service: `dhis2w_core.v{N}.plugins.system.service.server_info() -> ServerInfo`. Process-local — opens no DHIS2 client, so it's safe to call from MCP hosts that haven't (yet) authenticated.
- MCP tool: `system_server_info()` returns the typed model. Useful for agents that want to detect plugin-tree mismatch before issuing version-sensitive calls (e.g. before invoking `metadata_program_set_labels`, which only exists on the v43 tree).

```python
from dhis2w_core.v43.plugins.system.service import server_info

info = await server_info()
# -> ServerInfo(active_plugin_tree="v43",
#               active_plugin_tree_source="DHIS2_VERSION='v43' env",
#               dhis2w_core_version="0.10.0",
#               dhis2w_mcp_version="0.10.0",
#               dhis2w_cli_version=None)
```

Fields: `active_plugin_tree`, `active_plugin_tree_source`, `dhis2w_core_version`, `dhis2w_mcp_version`, `dhis2w_cli_version` — all `model_config = ConfigDict(frozen=True)`. The `*_version` fields are `None` when the matching package isn't pip-installed (e.g. when running as a library out of the workspace checkout).

## Calendar

`SystemModule.calendar()` reads the active DHIS2 calendar (`keyCalendar` system setting); `set_calendar()` writes it. The nine valid values match the `@Component name()` of every implementation under `org.hisp.dhis.calendar.impl` in `dhis2/dhis2w-core` — `coptic`, `ethiopian`, `gregorian`, `islamic`, `iso8601`, `julian`, `nepali`, `persian`, `thai`. `iso8601` is the server default and the value `getCalendar()` returns on `SystemSettings.java` when nothing is set. `DhisCalendar` exposes them as a `StrEnum` so callers get autocomplete + Typer choice validation; `set_calendar` accepts either the enum or a raw string.

The Settings app at `/dhis-web-settings/#/calendar` still surfaces these in v42 — a `Calendar` tab with a dropdown that lists all nine options and a "Change calendar setting" confirmation modal — so the calendar isn't UI-hidden. The UI fires the same `POST /api/42/systemSettings/keyCalendar` the client uses. On a local single-replica `infra/` stack (DHIS2 `2.42.4`) the write round-trips cleanly through both the API and the UI; on the shared `play.im.dhis2.org/dev-2-42` instance neither path persists the value, which looks like a deployment-topology issue rather than a server bug (`BUGS.md` entry 32).

## Why hand-written, not generated

`/api/schemas` lists metadata types. `SystemInfo` and `Me` are not metadata types — they're computed endpoints. They'd be missing from any codegen run. Hand-writing them is the correct call.

Same logic will apply to the next batch of modules: tracker, data values, analytics. Those are computed/derived endpoints with their own API shapes.

## Open question

Should `client.system.info()` cache its result for the lifetime of the client? `Dhis2Client.connect()` already fetches it once (for version discovery); a second call via `client.system.info()` re-fetches. For now the two paths don't share state — simplest. If latency matters, a lazy cache on the client is a small change.
