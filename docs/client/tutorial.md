# `dhis2w-client`: step-by-step guide

> **Learning path · step 4 of 8** — Python library tutorial. Prev: [CLI tutorial](../cli/tutorial.md). Next: [Examples index](../examples.md). For the typed API surface see [API reference](../api/index.md); for the underlying design see [Client architecture](../architecture/client.md).

End-to-end tutorial for the `dhis2w-client` Python library. Most blocks are runnable scripts you can paste into a file, set your env, and run; a handful — clearly marked — are fragments that show one specific pattern (the OAuth2 direct-client section toward the end is the main one). When in doubt, the matching script under `examples/client/` (linked from each section) is the runnable form.

If you already use the `d2w` CLI or the MCP server, this library is what those layers sit on. Use it directly when you're writing Python scripts or your own tooling.

- [Prerequisites](#prerequisites)
- [Install](#install)
- [Concepts: auth + profiles](#concepts-auth-profiles)
- [Your first call](#your-first-call)
- [Profiles — three ways to build one](#profiles-three-ways-to-build-one)
- [Auth providers in detail](#auth-providers-in-detail)
- [Typed resource CRUD](#typed-resource-crud)
- [Bulk operations](#bulk-operations)
- [Error handling](#error-handling)
- [Analytics queries](#analytics-queries)
- [Tracker reads](#tracker-reads)
- [Task polling](#task-polling)
- [UID generation](#uid-generation)
- [Versions + fallback](#versions-fallback)
- [Concurrency](#concurrency)
- [Raw escape hatches](#raw-escape-hatches)
- [When to skip profiles (direct-client path)](#when-to-skip-profiles-direct-client-path)
- [Where next?](#where-next)

## Prerequisites

- Python 3.13+
- A reachable DHIS2 instance (v41, v42, or v43). Local: `make dhis2-run`; remote: your own install or one of the `https://play.im.dhis2.org/dev-2-{41,42,43}` instances.
- Credentials; PAT, username+password, or OAuth2 client config.

## Install

The client is a workspace member. If you're inside this repo:

```bash
uv sync --all-packages        # installs every member
```

Standalone (outside the repo, from PyPI):

```bash
uv add dhis2w-client             # PAT + Basic auth: build Profile + call open_client directly
uv add dhis2w-client dhis2w-core  # adds TOML profile resolution + OAuth2 token persistence
```

PAT, Basic, and session library users get the `Profile` model + `open_client(profile)` from `dhis2w-client` alone. Multi-profile TOML resolution (`profiles.toml` discovery, `resolve()`, `profile_from_env()` with its full precedence chain) and the OAuth2 token cache live in `dhis2w-core` — pull it when you want the CLI/MCP profile layer or when your auth is OAuth2. Calling `dhis2w_client.open_client(oauth2_profile)` raises `NotImplementedError` with the install hint.

The split exists for transitive-dependency weight on PyPI, not for cycle avoidance. `dhis2w-client` keeps a minimal install (`httpx`, `pydantic`, `geojson-pydantic`) so third-party Python apps — FastAPI services, scripts, notebooks — can embed it without pulling in a CLI framework, an MCP server, SQLAlchemy for the OAuth2 token store, or bcrypt. `dhis2w-core` adds all of those because the CLI and MCP server need them. The dependency arrow is one-way: `dhis2w-core` imports from `dhis2w-client`, never the reverse. See [Decisions log](../decisions.md) for the original decision.

## Concepts: auth + profiles

Two concepts to internalise before any code:

**Auth provider.** An `AuthProvider` is "how to prove who you are to DHIS2 on every request." Four shipped variants — `BasicAuth`, `PatAuth`, `OAuth2Auth`, `SessionCookieAuth` — each implementing the same Protocol. The rest of the client doesn't care which one you pick.

**Profile.** A `Profile` is "a named bundle of how to reach one DHIS2 instance" — a base URL plus the parameters needed to build the right `AuthProvider`. A profile can be:

- **Resolved from a TOML file** (`~/.config/dhis2/profiles.toml` or `./.dhis2/profiles.toml`) — the same files the `d2w` CLI manages.
- **Built from raw env variables** (`DHIS2_URL` + `DHIS2_PAT`, or `DHIS2_URL` + `DHIS2_USERNAME` + `DHIS2_PASSWORD`). The raw-env fallback handles PAT and Basic only; OAuth2 needs a saved profile (`d2w profile add ... --auth oauth2 --from-env` reads `DHIS2_OAUTH_*` once and persists the result).
- **Constructed in-memory** from any Python code — no disk, no env, just a Pydantic model.

Profiles are the **preferred entry point** for every Python script. They're what the CLI uses, what the MCP server uses, and what every plugin `service.py` uses. Use them unless you have a specific reason to skip them (see [the direct-client section](#when-to-skip-profiles-direct-client-path) at the end).

**The split:**

- [`dhis2w-client`](../api/index.md) — HTTP client + `AuthProvider` implementations + `Profile` model + `open_client(profile)` for PAT/Basic/session. Standalone PyPI package.
- [`dhis2w-core`](../architecture/overview.md) — TOML profile resolution + `open_client` overload that adds OAuth2 token persistence. Depends on `dhis2w-client`.

Every code block in this guide uses `dhis2w-core.open_client(profile)` (with `profile_from_env()`'s full TOML+env precedence) as the happy path. Library users on PAT, Basic, or session can use `dhis2w_client.open_client(profile)` directly without installing `dhis2w-core` — see [`examples/client/profile_pat_pure_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/profile_pat_pure_client.py). The "direct-client" form (`Dhis2Client(base_url, auth=...)`) is covered at the end for the cases that need the lowest level.

## Your first call

Simplest working script. `open_client(profile)` is an async context manager that resolves the profile's auth, opens a `Dhis2Client`, runs the DHIS2-version handshake, and yields the connected client.

```python
import asyncio

from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    async with open_client(profile_from_env()) as client:
        print(f"Connected to DHIS2 {client.raw_version}")
        me = await client.system.me()
        print(f"  logged in as: {me.username} ({me.displayName})")


asyncio.run(main())
```

**Library-only path (no `dhis2w-core` install).** If your auth is PAT, Basic, or session and you don't want the TOML profile system, build a `Profile` in-memory and call `dhis2w_client.open_client` directly:

```python
import asyncio

from dhis2w_client import NoProfileError, open_client, profile_from_env_raw


async def main() -> None:
    profile = profile_from_env_raw()  # DHIS2_URL + DHIS2_PAT (or USER+PASS) — no TOML
    if profile is None:
        raise NoProfileError("set DHIS2_URL + DHIS2_PAT (or DHIS2_USERNAME + DHIS2_PASSWORD)")
    async with open_client(profile) as client:
        print(f"Connected to DHIS2 {client.raw_version}")
        me = await client.system.me()
        print(f"  logged in as: {me.username} ({me.displayName})")


asyncio.run(main())
```

Both paths return the same `Dhis2Client` — only the install footprint and the profile-resolution behaviour differ. OAuth2 needs the `dhis2w-core` path because the token store provides concurrent-refresh safety. See `examples/client/profile_pat_pure_client.py` for a runnable, version-pinned form of the library-only path.

`profile_from_env()` (in the `dhis2w-core` path above) walks the full precedence chain (first match wins):

1. Explicit `name` argument to `resolve(name)` (or `--profile` on the CLI).
2. `DHIS2_PROFILE` env var → resolve that named profile from the merged TOML catalog.
3. Raw `DHIS2_URL` + (`DHIS2_PAT` or `DHIS2_USERNAME` + `DHIS2_PASSWORD`) env → build a PAT or Basic profile on the fly. OAuth2 is not part of the raw fallback; use `d2w profile add ... --auth oauth2 --from-env` to read `DHIS2_OAUTH_*` once and persist a profile.
4. Project-local `.dhis2/profiles.toml` `default` (walking up from `cwd`).
5. User-global `~/.config/dhis2/profiles.toml` `default`.

What happens on `__aenter__`:
1. Resolves the `Profile` into a concrete `AuthProvider`.
2. Opens an `httpx.AsyncClient` connection pool.
3. Calls `/api/system/info` to discover the DHIS2 version.
4. Binds the matching generated resource accessors (`client.resources.*`).

`client.version_key` is `"v42"` afterwards; `client.raw_version` is `"2.42.4"`.

**Canonical URL discovery.** Step 3 is preceded by one unauthenticated request to
the profile's base URL, because some DHIS2 deployments answer on a different host
than the one you configured (`play.dhis2.org/dev` redirects to
`play.im.dhis2.org/dev`, and `httpx` drops the Authorization header across such a
redirect). The client follows that chain once with no credentials and adopts the
destination as the base URL for everything after — but only when the destination
earns it. A same-origin destination is adopted outright. A different origin is
adopted only when it keeps the configured scheme (an `https://` base URL is never
traded for `http://`), sits on the same registrable domain as the configured host
(the last two labels, so `play.dhis2.org` and `play.im.dhis2.org` are siblings
under `dhis2.org`; an IP address or a single-label host such as `localhost` has no
registrable domain and is never a sibling of anything), and answers
`/api/system/info` with a parsed DHIS2 body — system info, or DHIS2's own error
envelope for an anonymous caller. Anything else keeps the URL you configured, so
an open redirect or an SSO identity provider never receives your credentials.

## Profiles — three ways to build one

### A. Named profile from the TOML file

Exactly what the CLI sees — no difference in resolution path:

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import resolve_profile

async with open_client(resolve_profile("staging")) as client:
    me = await client.system.me()
```

If you don't pass a name, `resolve_profile()` / `profile_from_env()` walk the precedence chain documented above (arg → `DHIS2_PROFILE` → raw env → project TOML → global TOML). See [profiles](../architecture/profiles.md) for the file format and scope rules (global vs project).

### B. From env vars (no TOML file needed)

The `profile_from_env()` fallback kicks in when no TOML is found:

```bash
export DHIS2_URL=http://localhost:8080
export DHIS2_PAT=d2p_abc123
```

```python
async with open_client(profile_from_env()) as client:
    ...
```

Useful in CI, Docker, any scenario where you'd rather not mount a config file.

### C. In-memory, never touches disk

`Profile` is a plain Pydantic model — construct it like any other typed config. Nothing gets persisted anywhere.

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile

# PAT
profile = Profile(base_url="http://localhost:8080", auth="pat", token=os.environ["MY_PAT"])

# Basic (dev only — production should use PAT or OAuth2)
profile = Profile(
    base_url="http://localhost:8080",
    auth="basic",
    username="admin",
    password="district",
)

# OAuth2 client-credentials — for service-account style flows
profile = Profile(
    base_url="http://localhost:8080",
    auth="oauth2",
    client_id=os.environ["DHIS2_OAUTH_CLIENT_ID"],
    client_secret=os.environ["DHIS2_OAUTH_CLIENT_SECRET"],
)

async with open_client(profile) as client:
    me = await client.system.me()
```

Use this when:

- A caller passes you connection details at runtime (SaaS multi-tenant, agent workflows)
- You want to spin up a throwaway client against a per-test fixture
- You want strict control over where the credentials come from

The same `open_client` + `client.*` API works regardless of which of the three paths you used. The rest of this guide assumes any of them.

### Managing on-disk profiles from Python

Every `d2w profile ...` CLI command maps 1:1 onto a function in `dhis2w_core.v42.plugins.profile.service`:

| CLI | Python |
| --- | --- |
| `d2w profile add NAME ...` | `service.add_profile(name, profile, *, scope, make_default)` |
| `d2w profile list` | `service.list_profiles(*, include_shadowed)` → `list[ProfileSummary]` |
| `d2w profile show NAME` | `service.show_profile(name, *, include_secrets)` → `ProfileView` |
| `d2w profile rename OLD NEW` | `service.rename_profile(old, new)` |
| `d2w profile set-default NAME` | `service.set_default_profile(name, *, scope)` |
| `d2w profile remove NAME` | `service.remove_profile(name, *, scope)` |
| `d2w profile verify NAME` | `await service.verify_profile(name)` |

Pass a `start: Path` argument to scope the write to a specific project directory — `service.add_profile(..., scope="project", start=tmp_path)` writes to `<tmp_path>/.dhis2/profiles.toml` instead of the user's real `~/.config/dhis2/profiles.toml`. Handy for tests and isolation.

`examples/client/profile_crud.py` walks both paths — in-memory `Profile(...)` and on-disk `add / rename / set-default / remove` — against an isolated temp directory so it's safe to re-run.

## Auth providers in detail

`Profile.auth` is a `Literal["pat", "basic", "oauth2", "session"]` tag; `open_client` builds the right `AuthProvider` internally. When constructing a profile in-memory, fill the fields for the auth type you pick:

| `auth` value | Required fields | Optional |
| --- | --- | --- |
| `"pat"` | `token` | — |
| `"basic"` | `username`, `password` | — |
| `"oauth2"` | `client_id`, `client_secret` | `scope`, `redirect_uri` (for interactive flows) |
| `"session"` | `cookie` (raw `Cookie` header value, name included) | `xsrf_token` (echoed as `X-XSRF-TOKEN` for CSRF-enforcing writes) |

### PAT (recommended for scripts)

PATs are user-scoped, long-lived, revocable. They travel as `Authorization: ApiToken <token>` (DHIS2-flavoured, not `Bearer`).

```python
profile = Profile(base_url="http://localhost:8080", auth="pat", token=os.environ["DHIS2_PAT"])
async with open_client(profile) as client:
    ...
```

Mint a PAT:

- CLI: `d2w profile pat create --url <url> --admin-user admin --description "example"` (needs `DHIS2_ADMIN_PAT` or `DHIS2_ADMIN_PASSWORD` in env)
- Web UI: every user's profile page at `/dhis-web-user-profile`
- Per the seeded e2e fixture: `make dhis2-run` writes one to `infra/home/credentials/.env.auth`

### Basic (dev only)

`BasicAuth` sends `Authorization: Basic base64(user:pw)` on every request. Use against dev/play instances only.

```python
profile = Profile(base_url="http://localhost:8080", auth="basic", username="admin", password="district")
async with open_client(profile) as client:
    ...
```

### OAuth2 / OIDC (short-lived tokens, auto-refresh)

OAuth2 profiles need one extra step for interactive flows: the user runs `d2w profile login <name>` once, which walks the browser flow and persists an access+refresh token in `.dhis2/tokens.sqlite`. `open_client` then picks up the persisted token automatically on later runs.

```python
profile = Profile(
    base_url="http://localhost:8080",
    auth="oauth2",
    client_id=os.environ["DHIS2_OAUTH_CLIENT_ID"],
    client_secret=os.environ["DHIS2_OAUTH_CLIENT_SECRET"],
    scope="openid",
    redirect_uri="http://localhost:8765",
)

async with open_client(profile, profile_name="my-oauth-profile") as client:
    # Access token auto-refreshes when within 30s of expiry;
    # refreshed tokens written back to the store keyed on (scope, profile_name).
    ...
```

For a complete standalone OAuth2 demo including PKCE, FastAPI redirect receiver, and SQLite token store, see `examples/client/oidc_login.py`. Architecture details in [Pluggable auth](../architecture/auth.md).

### Session cookie (ride an existing browser login)

`SessionCookieAuth` sends a stored browser session verbatim as a raw `Cookie` header on every request. The profile's `cookie` field holds the full header value, cookie name included (e.g. `"JSESSIONID=abc123"`), so any cookie name DHIS2 uses works unchanged. This is the fallback for instances where PAT creation is unavailable (pre-2.38, disabled, or 403 for the user) — prefer PAT when you can mint one.

```python
profile = Profile(base_url="http://localhost:8080", auth="session", cookie=os.environ["DHIS2_SESSION_COOKIE"])
async with open_client(profile) as client:
    ...
```

If the instance enforces CSRF on write endpoints, also set `xsrf_token` (the value of the `XSRF-TOKEN` cookie); the client echoes it as an `X-XSRF-TOKEN` header. It's optional and inert when unset, so read-only sessions can omit it:

```python
profile = Profile(
    base_url="http://localhost:8080",
    auth="session",
    cookie=os.environ["DHIS2_SESSION_COOKIE"],
    xsrf_token=os.environ.get("DHIS2_SESSION_XSRF"),
)
```

Session cookies expire server-side and there is nothing to refresh client-side (`refresh_if_needed` is a no-op). When calls start failing with 401, capture a fresh cookie from the browser and re-run `d2w profile add <name> --auth session` — the upsert replaces the stored value. `d2w profile verify <name>` is the cheap way to detect an expired binding. See `examples/cli/profile_session.sh` for the end-to-end flow.

### Route API auth (for `/api/routes` objects, not for client auth)

DHIS2's Route API proxies requests to upstream services; its `auth` field is a separate discriminated union unrelated to the client-to-DHIS2 auth described above. The typed union lives in `dhis2w_client.AuthScheme`:

```python
from dhis2w_client import AuthSchemeAdapter, HttpBasicAuthScheme

scheme = HttpBasicAuthScheme(type="http-basic", username="svc", password="secret")
parsed = AuthSchemeAdapter.validate_python({"type": "api-token", "token": "..."})
```

## Typed resource CRUD

After `__aenter__`, `client.resources` exposes a typed accessor for every metadata resource DHIS2 publishes at `/api/<plural>`. Attribute names are snake-cased plurals: `data_elements`, `organisation_units`, `category_combos`, etc.

```python
from dhis2w_client import generate_uid
from dhis2w_client.generated.v42.common import Reference
from dhis2w_client.generated.v42.enums import AggregationType, DataElementDomain, ValueType
from dhis2w_client.generated.v42.schemas.data_element import DataElement
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async with open_client(profile_from_env()) as client:
    uid = generate_uid()  # 11-char, client-side, matches dhis2w-core/CodeGenerator.java

    # CREATE
    new_de = DataElement(
        id=uid,
        code=f"EX_DE_{uid}",
        name=f"Example DE {uid}",
        shortName=f"Ex {uid[:4]}",
        domainType=DataElementDomain.AGGREGATE,
        valueType=ValueType.NUMBER,
        aggregationType=AggregationType.SUM,
        categoryCombo=Reference(id="bjDvmb4bfuf"),  # default CC from the seed
    )
    await client.resources.data_elements.create(new_de)

    # READ
    fetched = await client.resources.data_elements.get(uid, fields="id,name,valueType")
    print(f"fetched: {fetched.name} ({fetched.valueType})")

    # UPDATE; PUT the whole model back
    fetched.name = "Renamed"
    await client.resources.data_elements.update(fetched)

    # PATCH; partial update via RFC 6902 JSON Patch
    from dhis2w_client import ReplaceOp

    await client.resources.data_elements.patch(uid, [ReplaceOp(path="/shortName", value="Px")])

    # DELETE
    await client.resources.data_elements.delete(uid)
```

Enum fields are `StrEnum`s; `DataElementDomain.AGGREGATE == "AGGREGATE"` is true, so you can pass bare strings too. `Reference` has both `id` and `code` fields; pick whichever your calling import strategy uses.

### Filters, order, paging

```python
async with open_client(profile_from_env()) as client:
    # Single filter
    recent = await client.resources.data_elements.list(
        filters=["name:like:Penta"],
        fields="id,name",
    )

    # Multi-filter OR
    matches = await client.resources.data_elements.list(
        filters=["name:like:Penta", "code:eq:DE_PENTA1"],
        root_junction="OR",
    )

    # Server-side paging + ordering
    page = await client.resources.organisation_units.list(
        order=["level:asc", "name:asc"],
        page_size=20,
        page=2,
    )

    # Dump everything in one request (paging=False)
    everything = await client.resources.indicators.list(paging=False, fields=":identifiable")

    # Or walk pages to get the `pager` block
    envelope = await client.resources.data_elements.list_raw(page_size=50, page=1)
    pager = envelope.get("pager", {})  # {"page", "pageSize", "total", "pageCount"}
```

Filter syntax is DHIS2's native `property:operator:value` form. Operators: `eq`, `ieq`, `ne`, `like`, `!like`, `ilike`, `in`, `!in`, `null`, `!null`, `gt`, `ge`, `lt`, `le`, `token`. Use Python f-strings for interpolation; `f"valueType:eq:{ValueType.NUMBER}"`.

## Bulk operations

Every write endpoint returns a `WebMessageResponse` envelope. It's the same shape across DHIS2 so we model it once and reuse.

```python
from dhis2w_client import DataValue, DataValueSet, WebMessageResponse
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async with open_client(profile_from_env()) as client:
    payload = DataValueSet(
        dataValues=[
            DataValue(
                dataElement="fClA2Erf6IO",
                period="202603",
                orgUnit="PMa2VCrupOd",
                value="42",
            ),
        ],
    )
    raw = await client.post_raw("/api/dataValueSets", payload.model_dump(exclude_none=True))
    response = WebMessageResponse.model_validate(raw)

    print(f"status={response.status}")
    counts = response.import_count()
    if counts is not None:
        print(
            f"  imported={counts.imported} updated={counts.updated} ignored={counts.ignored} deleted={counts.deleted}"
        )
    for conflict in response.conflicts():
        print(f"  conflict: {conflict.property} = {conflict.value} [{conflict.errorCode}]")
```

Values and *completeness* are two different writes. DHIS2 records whether a data set is finished for a period at `/api/completeDataSetRegistrations`, under the same `(dataSet, period, organisationUnit, attributeOptionCombo)` key — so register it after the values are in, never before:

```python
from dhis2w_client import CompleteDataSetRegistration, CompleteDataSetRegistrations

registrations = CompleteDataSetRegistrations(
    completeDataSetRegistrations=[
        CompleteDataSetRegistration(
            dataSet="BfMAe6Itzgt",
            period="202603",
            organisationUnit="PMa2VCrupOd",
            date="2026-04-02",
            completed=True,
        )
    ]
)
answer = await client.post_raw(
    "/api/completeDataSetRegistrations",
    registrations.model_dump(by_alias=True, exclude_none=True, mode="json"),
)
```

Registering a tuple DHIS2 already holds counts `updated`, not a conflict, so the call is safe to repeat. Leave `attributeOptionCombo` unset on a data set riding the default category combo — DHIS2 fills it. See [Aggregate data values](../api/aggregate.md) for the read-back.

Helpers on `WebMessageResponse`:

- `.status`, `.httpStatus`, `.httpStatusCode`, `.message` — envelope scalar fields
- `.created_uid` — UID from an object-report envelope (handles DHIS2's `response.uid` vs `id` inconsistency, see BUGS.md #4f)
- `.import_count()` → typed `ImportCount` (flat OR nested `response.importCount` forms)
- `.conflicts()` → `list[Conflict]` — per-row rejections with `property`, `value`, `errorCode`
- `.rejected_indexes()` → `list[int]` — payload-array indexes DHIS2 refused
- `.import_report()` → typed `ImportReport` for `/api/metadata` bulk responses
- `.task_ref()` → `(job_type, task_uid)` tuple when DHIS2 returned a job-kickoff envelope

## Error handling

DHIS2 returns 4xx with a JSON body describing what went wrong. The client always raises for ≥400; and always captures the body, even when it's a `WebMessageResponse`.

```python
from dhis2w_client import AuthenticationError, Dhis2ApiError
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile

bogus = Profile(base_url="http://localhost:8080", auth="pat", token="not-a-real-pat")

async with open_client(bogus) as client:
    try:
        await client.system.me()
    except AuthenticationError as exc:
        print(f"401: {exc}")
    except Dhis2ApiError as exc:
        # Any non-401 4xx/5xx
        print(f"{exc.status_code}: {exc.message}")
        envelope = exc.web_message  # typed WebMessageResponse, or None
        if envelope is not None:
            for conflict in envelope.conflicts():
                print(f"  {conflict.property}: {conflict.value}")
```

Exception hierarchy:

- `Dhis2ClientError` — base
- `Dhis2ApiError` — any non-success response; `.body` carries the parsed JSON / text, `.web_message` lazily parses it as `WebMessageResponse`
- `AuthenticationError` — 401 specifically
- `OAuth2FlowError` — state mismatch, missing code, refresh failure
- `UnsupportedVersionError` — no generated client for the DHIS2 version the server reports

## Analytics queries

The `/api/analytics` endpoint has three response shapes. Pass `shape="table"` (default), `"raw"`, or `"dvs"` (DataValueSet).

```python
from dhis2w_client import AnalyticsMetaData, DataValueSet, Grid
from dhis2w_core.v42.plugins.analytics import service

response = await service.query_analytics(
    profile_from_env(),
    dimensions=["dx:fClA2Erf6IO", "pe:LAST_12_MONTHS", "ou:ImspTQPwCqd"],
)
match response:
    case Grid(rows=rows, headers=headers, metaData=meta):
        # `rows` / `headers` / `metaData` are all `| None` per the OAS spec —
        # guard with `or []` / `or {}` or narrow explicitly.
        for row in rows or []:
            print(row)
        # `metaData` is `dict[str, Any]` on the wire; lift to typed when needed.
        if meta:
            typed = AnalyticsMetaData.model_validate(meta)
            print(typed.dimensions["dx"])
    case DataValueSet(dataValues=values):
        for dv in values or []:
            print(f"{dv.dataElement} {dv.period} {dv.orgUnit} = {dv.value}")
```

`Grid` / `GridHeader` are the OAS-emitted canonical types. `AnalyticsMetaData`
is a typed parser helper over `Grid.metaData` — use it when you want the
structured `{items, dimensions}` view; skip it when you're iterating rows.

For streaming large exports to disk, reach for `client.analytics.stream_to(path, params=..., endpoint=...)` — that feeds httpx's chunked transfer straight to a file without buffering the full body.

For resource-table regeneration after a data push, the typed service wrappers avoid the raw-call boilerplate:

```python
envelope = await service.refresh_analytics(profile, last_years=1)
ref = envelope.task_ref()
assert ref is not None
async with open_client(profile) as client:
    completion = await client.tasks.await_completion(ref, timeout=300.0)
print(f"refresh done — {len(completion.notifications)} notifications")
```

`service.refresh_resource_tables(profile)` and `service.refresh_monitoring(profile)` cover the two sibling endpoints (`/api/resourceTables` without a suffix, `/api/resourceTables/monitoring`) for OU-hierarchy or validation-monitoring rebuilds.

## Tracker reads

`client.tracker.tracked_entities`, `.enrollments`, and `.events` read the three `/api/tracker/*` resources with the standard query surface. Each returns the page envelope; rows live under `instances` (or the resource's own name on older minors). The generated models in `dhis2w_client.generated.v42.tracker` are version-scoped, because tracker shapes drift across DHIS2 majors.

```python
from dhis2w_client.generated.v42.tracker import TrackerTrackedEntity

async with open_client(profile_from_env()) as client:
    page = await client.tracker.tracked_entities(
        program="<PROG_UID>",
        org_unit="<OU_UID>",
        ou_mode="DESCENDANTS",
        page_size=10,
    )
    for row in page.get("instances") or page.get("trackedEntities") or []:
        te = TrackerTrackedEntity.model_validate(row)
        print(f"{te.trackedEntity}  type={te.trackedEntityType}  orgUnit={te.orgUnit}")
```

`status` filters by enrollment status on tracked entities and enrollments, by event status on events. `updated_after` and `occurred_after` take an ISO string, a `date`, or a `datetime`. `EventStatus` and `EnrollmentStatus` are `StrEnum`s; `EventStatus.COMPLETED == "COMPLETED"`.

## Aggregate values: export and stream

`client.data_values.export` reads a form's values back as a typed `DataValueSet`; `data_set` / `period` / `org_unit` each take one id or a sequence, and a `start_date` / `end_date` range stands in for a period list. `client.complete_data_set_registrations.export` reads which forms are reported complete with the same selectors.

```python
async with open_client(profile_from_env()) as client:
    values = await client.data_values.export(
        data_set="<DS_UID>", org_unit="<OU_UID>", start_date="2026-01-01", end_date="2026-06-30"
    )
    for value in values.dataValues or []:
        print(f"{value.dataElement} {value.period} = {value.value}")

    complete = await client.complete_data_set_registrations.export(
        data_set="<DS_UID>", org_unit="<OU_UID>", children=True, start_date="2026-01-01", end_date="2026-06-30"
    )
    print(f"{len(complete.completeDataSetRegistrations)} forms reported complete")
```

`export` buffers the whole response. For a national year, stream it instead: `client.stream` writes any endpoint's body chunk by chunk to a `Path`, to anything with `.write(bytes)`, or to a callable, and returns the byte count.

```python
from pathlib import Path

written = await client.stream(
    "GET",
    "/api/dataValueSets.json",
    Path("./exports/2025.json"),
    params={
        "dataSet": ["<DS_UID>"],
        "orgUnit": ["<OU_UID>"],
        "children": "true",
        "startDate": "2025-01-01",
        "endDate": "2025-12-31",
    },
)
```

## Task polling

Every async DHIS2 op (analytics refresh, metadata import, data-integrity run, tracker async push) returns a `JobConfigurationWebMessageResponse` carrying `jobType` + task UID. Use `.task_ref()` to pull the polling tuple, then `client.tasks.await_completion(...)` to block until the job finishes:

```python
from dhis2w_client.v42.tasks import TaskTimeoutError

async with open_client(profile_from_env()) as client:
    envelope = await client.maintenance.run_analytics_tables(last_years=1)
    ref = envelope.task_ref()
    if ref is None:
        raise RuntimeError("response had no jobType/id; nothing to watch")

    try:
        completion = await client.tasks.await_completion(
            ref,
            timeout=300.0,  # seconds; pass None to wait forever
            poll_interval=1.0,  # seconds between polls
        )
    except TaskTimeoutError as exc:
        print(f"task didn't finish in time: {exc}")
        return

    print(f"{completion.level}  {completion.message}")
    # completion.notifications is the full chronological list
    # completion.final is the terminal row (completed=True)
```

`await_completion` handles the polling loop, de-duplicates notifications across polls (so the same progress message isn't yielded twice), and reuses the client's open HTTP connection (no new TCP handshake per poll). Pass a `(job_type, uid)` tuple or a `"JOB_TYPE/uid"` string interchangeably.

For custom rendering (Rich progress bars, server-sent-event bridges), iterate the raw stream instead:

```python
async for notification in client.tasks.iter_notifications(ref, poll_interval=1.0):
    level = (notification.level or "INFO").upper()
    marker = "[x]" if notification.completed else "[ ]"
    print(f"  {level:<5} {marker} {notification.message}")
```

When the caller has its own clock, such as a workflow engine that polls once per tick, `poll_once` reads the feed once and returns instead of looping. Carry its `cursor` into the next call so rows are not reported twice:

```python
poll = await client.tasks.poll_once(ref)
for notification in poll.new:
    print(f"  [{notification.level}] {notification.message}")
if not poll.completed:
    poll = await client.tasks.poll_once(ref, cursor=poll.cursor)
```

See `examples/client/task_await.py` and `examples/client/analytics_tables_poll_once.py` for runnable demos. The CLI `--watch` flag (`d2w maintenance refresh analytics --watch`, `d2w maintenance dataintegrity run --watch`) uses a Rich-progress wrapper on top of the same primitive.

### Streaming data-integrity issues

`client.maintenance.iter_integrity_issues(...)` gives a flat stream over the `{check_name: {issues: [...]}}` map DHIS2 returns from `/api/dataIntegrity/details`. Each yielded `IntegrityIssueRow` carries the owning check's name, display name, and severity:

```python
async with open_client(profile_from_env()) as client:
    async for row in client.maintenance.iter_integrity_issues():
        if (row.severity or "").upper() == "WARNING":
            print(f"{row.check_name:40}  {row.issue.id}  {row.issue.name}")
```

Use `client.maintenance.get_integrity_report(details=True)` (or `details=False` for the cheaper summary endpoint) when you want the full typed report instead. See `examples/client/integrity_issues_stream.py` for a runnable demo.

### System cache

Every client ships a TTL-bounded in-memory cache for the high-repetition system-level reads. `client.system.info()` is **primed on `connect()`** (no second round-trip); `client.system.default_category_combo_uid()` + `client.system.setting(key)` cache per call-site. Default TTL is 300 s:

```python
async with open_client(profile_from_env()) as client:
    info = await client.system.info()  # primed; free
    default_cc = await client.system.default_category_combo_uid()  # fetched once; cached
    title = await client.system.setting("applicationTitle")  # per-key cache

    client.system.invalidate_cache()  # drop everything
    # or: client.system.invalidate_cache(key="setting:applicationTitle")
```

Tune via `open_client(profile, system_cache_ttl=600.0)` or pass `None` to disable. See `examples/client/system_cache.py` for a timed demo.

## UID generation

DHIS2 UIDs are 11-char strings matching `^[A-Za-z][A-Za-z0-9]{10}$`. Instead of `/api/system/id` round-trips, generate them client-side; same algorithm as `dhis2w-core/CodeGenerator.java`:

```python
from dhis2w_client import UID_RE, generate_uid, generate_uids, is_valid_uid

generate_uid()  # "aB3dEf5gH7i"
generate_uids(100)  # list of 100 unique UIDs
is_valid_uid("fClA2Erf6IO")  # True
UID_RE.pattern  # '^[A-Za-z][A-Za-z0-9]{10}$'
```

Uses `secrets.choice` (CSPRNG), matches the `SecureRandom` path upstream. No client connection needed.

## Versions + fallback

On connect, the client pulls `/api/system/info`, extracts the minor version, and binds the matching generated module. Versions shipped: v41, v42, v43. If the reported version has no generated module, construction fails with `UnsupportedVersionError` unless you opt into fallback.

Pass the knob through `open_client`:

```python
async with open_client(profile_from_env(), allow_version_fallback=True) as client:
    # Falls back to the highest generated version <= the server's reported version.
    ...
```

To pin a specific version regardless of what the server reports, you need the direct-client path — see [below](#when-to-skip-profiles-direct-client-path). Regenerate codegen for a new version with `d2w dev codegen rebuild` or point at a live instance with `d2w dev codegen generate --url <url>`.

## Retry on transient failures

Batch workflows hitting a live DHIS2 instance sometimes see transient 5xxs (503 during an analytics refresh) or connection resets (TCP keepalive drops on long idle periods). Opt in to retries via `RetryPolicy`:

```python
from dhis2w_client import RetryPolicy

policy = RetryPolicy(
    max_attempts=5,
    base_delay=0.2,
    backoff_factor=2.0,
    max_delay=5.0,
    jitter=0.15,
    retry_statuses=frozenset({429, 502, 503, 504}),  # default set
)

# Profile-based (preferred):
async with open_client(profile_from_env(), retry_policy=policy) as client:
    ...

# Direct-client path (no dhis2w-core):
async with Dhis2Client(base_url, auth=auth, retry_policy=policy) as client:
    ...
```

Retry scope:

- **Connection-level errors** (`httpx.ConnectError`, `ReadTimeout`, `PoolTimeout`, `RemoteProtocolError`) always retry.
- **Status codes** listed in `policy.retry_statuses` (default: 429, 502, 503, 504) retry.
- **Non-idempotent methods** (POST, PATCH) are exempt by default — double-writes risk DHIS2-side duplicates. Opt in for specific endpoints where you know it's safe (analytics-refresh kick-offs, for instance):

  ```python
  RetryPolicy(retry_non_idempotent=True)
  ```

- **`Retry-After` header** from the server (sent on 429 / 503) overrides the computed backoff for that attempt.

Backoff: `delay = min(max_delay, base_delay * backoff_factor ** (attempt - 1))` with a fractional jitter applied before sleeping.

See `examples/client/retry_policy.py` for a runnable demo across default / aggressive / non-idempotent-opt-in policies.

## Concurrency

The client's `httpx.AsyncClient` is shared across concurrent calls on the same `Dhis2Client` instance; safe to use with `asyncio.gather`.

```python
import asyncio

async with open_client(profile_from_env()) as client:
    # Parallel GETs
    uids = ["fClA2Erf6IO", "UOlfIjgN8X6", "I78gJm4KBo7"]
    elements = await asyncio.gather(
        *(client.resources.data_elements.get(uid) for uid in uids),
    )

    # Parallel writes — DHIS2 is generally fine with moderate concurrency
    # on independent records. Tune to your instance's capacity.
    await asyncio.gather(*(client.resources.data_elements.update(de) for de in elements))
```

Connection pool defaults are httpx's defaults (100 max connections, 20 keepalive).

## Raw escape hatches

Every endpoint DHIS2 has ever built is reachable through five raw methods. Prefer the typed accessors when they exist; these never lose.

```python
async with open_client(profile_from_env()) as client:
    raw = await client.get_raw("/api/some/unusual/path", params={"key": "val"})
    raw = await client.post_raw("/api/metadata", {"dataElements": [...]})
    raw = await client.put_raw("/api/dataElements/abc", {"name": "..."})
    raw = await client.delete_raw("/api/dataElements/abc")
    raw = await client.patch_raw("/api/dataElements/abc", [{"op": "replace", "path": "/name", "value": "..."}])

    # Typed GET against your own model:
    from pydantic import BaseModel

    class MyModel(BaseModel):
        id: str
        name: str

    item = await client.get("/api/something", model=MyModel)
```

`get_raw` always returns `dict[str, Any]`. When DHIS2 returns a bare JSON array (e.g. `/api/system/id`), it's wrapped under `{"data": [...]}` so the return type stays consistent.

`client.stream(method, path, sink, params=...)` is the sixth raw method: it never parses the body and never holds it, writing each chunk to the sink as it arrives. Reach for it when the response is a file, not a document.

## When to skip profiles (direct-client path)

`dhis2w-core` depends on `dhis2w-client`, not the other way around. If you're writing library code that should live without the `dhis2w-core` dependency — a downstream SDK, a minimal Lambda handler, a test fixture — you can drive `Dhis2Client` directly:

```python
from dhis2w_client import BasicAuth, Dhis2Client, PatAuth

# PAT
async with Dhis2Client(
    base_url="http://localhost:8080",
    auth=PatAuth(token=os.environ["DHIS2_PAT"]),
) as client:
    me = await client.system.me()

# Basic (dev only)
async with Dhis2Client(
    base_url="http://localhost:8080",
    auth=BasicAuth(username="admin", password="district"),
) as client:
    ...
```

OAuth2 at the direct-client layer skips the profile's token-store key plumbing — see the `OAuth2Auth` direct-construction block further down.

**When to use which path:**

| You're writing | Use |
| --- | --- |
| A script / CLI tool / internal app (picks up CLI profiles) | `open_client(profile_from_env())` |
| A service that takes connection details at runtime | `open_client(Profile(...))` (in-memory) |
| A plugin / service-layer function inside this workspace | `open_client(profile)` (plugin layer already resolved it) |
| A library that imports `dhis2w-client` from PyPI without `dhis2w-core` | `Dhis2Client(base_url, auth=...)` directly |
| Pinning a specific DHIS2 version regardless of server-reported version | `Dhis2Client(..., version=Dhis2.V42)` directly |

### Direct-client OAuth2 (reference only)

For the rare case where you need `OAuth2Auth` without going through a profile — e.g. you have your own `TokenStore` implementation and want to wire token persistence yourself:

```python
from dhis2w_client import Dhis2Client
from dhis2w_client.v42.auth.oauth2 import OAuth2Auth
from dhis2w_core.token_store import token_store_for_scope

store = token_store_for_scope("global")
token = await store.get("my-oauth-profile")

auth = OAuth2Auth(
    token=token,
    token_store=store,
    token_key="my-oauth-profile",
    token_url="http://localhost:8080/oauth2/token",
    client_id=os.environ["DHIS2_OAUTH_CLIENT_ID"],
    client_secret=os.environ["DHIS2_OAUTH_CLIENT_SECRET"],
)

async with Dhis2Client(base_url="http://localhost:8080", auth=auth) as client:
    ...
```

Under `open_client(profile)`, all the above wiring happens automatically from the `Profile` fields — there's a reason it's the default.

---

## Known gaps + workarounds

A few normal DHIS2 workflows don't have dedicated accessor helpers yet. The pattern is the same in each: mutate the typed model + call `update()` / `import_bundle()`, or drop to `client.post_raw` / `put_raw` / `patch_raw` against the underlying endpoint.

- **DataSet ↔ OrganisationUnit assignment** — `DataSet.organisationUnits[]` has no `add_to_ou` / `remove_from_ou` helper. Pull the DataSet, mutate the list, call `client.data_sets.update(ds)`. Or send a `/api/metadata` bundle with just the OU mutation. See [Data sets API](../api/data-sets.md#per-ou-assignment).
- **Analytics CSV / XML / XLSX output** — `client.analytics.stream_to(Path, ...)` supports `output_format="csv" | "xml" | "xlsx"` but the CLI's `analytics query` only emits JSON. Write a small Python script when you need a non-JSON format; see [Analytics streaming](../api/analytics-stream.md).

These are tracked as future-iteration items on `docs/roadmap.md`; the workaround in each case round-trips through the typed model, so the lack of a helper doesn't block the workflow.

---

## Where next?

- [Connecting to DHIS2](../guides/connecting-to-dhis2.md) — end-to-end setup for PAT / OAuth2 including registering an OAuth2 client
- [Architecture: Pluggable auth](../architecture/auth.md) — how `AuthProvider` works under the hood
- [Architecture: Profiles](../architecture/profiles.md) — file format, scope rules, precedence order
- [Architecture: Typed schemas](../architecture/typed-schemas.md) — full model + enum inventory
- [Architecture: Metadata CRUD](../architecture/metadata-crud.md) — deeper dive on the generated resource accessors
- [Examples index](../examples.md) — the canonical v42 client set (~73 scripts) covering every pattern in this guide; v41 and v43 mirror most of them
