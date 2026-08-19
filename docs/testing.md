# Testing strategy

Tests fall into two tiers (fast unit + slow integration) plus a focused **upstream-bug regression** suite. All run through `make test` / `make test-slow` / `make test-upstream-bugs`.

## Tier 1: fast unit tests (`make test`)

Use **respx** to mock httpx responses. Cover:

- Every auth provider returns the right headers.
- OAuth2 token caching and refresh paths.
- Dhis2Client parses typed pydantic responses, surfaces error hierarchy correctly.
- `available_versions()` discovers generated modules from the filesystem.
- `Dhis2Client.connect()` version-dispatch logic: strict refusal vs nearest-lower fallback.
- Codegen name/type mapping (pure functions).
- Generated resources' CRUD verbs (GET/POST/PUT/DELETE) hit the right paths with the right HTTP verbs.

Fast — currently runs in <0.5s.

## Tier 2: slow integration tests (`make test-slow`)

Hit the live DHIS2 **play/dev** instance. Read-only by default (no destructive writes against a shared demo server). Cover:

- Raw HTTP auth/discovery round trips with Basic auth.
- Full codegen pipeline: discover → emit → import generated module → inspect.
- Connected client: `client.system.info()`, `client.system.me()`, and `client.resources.data_elements.list()` / `get()` against real data.

Marked with `@pytest.mark.slow` so the default `make test` skips them. They run in ~3s and confirm the full chain works against real DHIS2.

## Tier 3: upstream-bug regression suite (`make test-upstream-bugs`)

Every entry in `BUGS.md` (top-level) describing a real DHIS2-side bug we've worked around in this repo gets a paired test in `packages/dhis2w-client/tests/test_upstream_bugs.py`. Each pair has two flavours:

**Mocked (fast, default)**

1. **Bug-still-present (mocked)** — respx-mocked test that models DHIS2's buggy wire response and verifies our client handles it.
2. **Workaround-works (mocked)** — same mocked response, asserts the workaround code produces the correct end state.

**Live (slow, opt-in)**

3. **Bug-still-present (live)** — `@pytest.mark.slow` test that hits the local docker DHIS2 stack via `make dhis2-run DHIS2_VERSION=vN`. POSTs / GETs the actual wire and asserts the bug is observable. When DHIS2 ships an upstream fix and the wire shape changes, this test fails — the loud signal to drop the workaround. Skips when the stack isn't reachable or when the server version doesn't match the bug's target major (so the v43 bug tests only run against a v43 stack).

All flavours carry `@pytest.mark.upstream_bug`. `make test-upstream-bugs` filters to just this marker (`pytest -m upstream_bug`), useful for "show me every workaround we depend on". The respx-mocked halves are fast and run as part of the default `make test` too. The live halves run via `make test-slow` when a stack is up.

### Adding a new pair

1. Append a `### N. <summary>` entry to `BUGS.md` with the curl repro + workaround pointer.
2. Add three tests to `packages/dhis2w-client/tests/test_upstream_bugs.py`:
   - `test_bug_N_<short>_<bug-pattern>` — mocked bug-still-present (respx).
   - `test_bug_N_workaround_<does_the_right_thing>` — mocked workaround-works (respx).
   - `test_bug_N_v<X>_live_<bug-pattern>` — `@pytest.mark.slow` live verifier. Calls `_skip_if_stack_unreachable(local_url)` + `_skip_unless_version(client, "v<X>")` at the top, then POSTs / GETs against the real wire. Cleans up any mutations.
3. Reference BUGS.md #N in every docstring so the link is bidirectional.

The pattern is illustrated in the file with BUGS.md #34 (v43 dropping the `categorys` wire alias) covered end-to-end across all three flavours.

## Test connection details

The `@pytest.mark.slow` E2E suite targets the local docker stack — `make -C infra up-seeded DHIS2_VERSION=vN` brings up the matching DHIS2 major and writes `infra/home/credentials/.env.auth` with `DHIS2_URL` and `DHIS2_PAT`. Each member's `tests/conftest.py` auto-sources that file and exposes the fixtures below.

Defaults:

```
DHIS2_LOCAL_URL=http://localhost:8080
DHIS2_LOCAL_USER=admin
DHIS2_LOCAL_PASS=district
```

Overridable via environment variables. Session-scoped fixtures in each member's `tests/conftest.py`:

```python
@pytest.fixture(scope="session")
def local_url() -> str: ...


@pytest.fixture(scope="session")
def local_username() -> str: ...


@pytest.fixture(scope="session")
def local_password() -> str: ...


@pytest.fixture(scope="session")
def local_available(local_url: str) -> bool: ...  # probes /dhis-web-login/, gate for skips
```

Simple strings, not dataclasses — this sidesteps mypy's "duplicate conftest module" problem across workspace members.

Live-against-play coverage lives in a separate workflow — `@pytest.mark.contract` (`.github/workflows/contract.yml`) hits `play.im.dhis2.org/dev-2-{42,43}` to catch upstream API drift. Nightly E2E never touches play.

## Destructive writes

Currently none. Any test that creates or deletes real resources needs to:

- Use a unique, obviously-test name prefix (e.g. `dhis2w-utils-test-<uuid>`).
- Clean up in a try/finally.
- Be clearly marked in its docstring.

Until that policy is formalised, CRUD write tests live in the unit tier (respx-mocked) only.

## What we don't test (yet)

- OAuth2 end-to-end against a real DHIS2 instance with the interactive browser flow — covered by unit tests (cached token + refresh paths) and by the Playwright-driven e2e in `examples/client/oidc_playwright_login.py`, but not yet wired into `make test`.
- Per-version `tests/v{41,43}/` accessor + plugin trees — v42 has full coverage; v41 + v43 have divergence + smoke tests only (`@upstream_bug` regressions, `test_v41_divergence.py`, `test_v43_divergence.py`). The hand-written client + plugin code in `dhis2w_client.v{41,43}` and `dhis2w_core.v{41,43}` is currently excluded from coverage (`tool.coverage.run.omit` in `pyproject.toml`) until those tests fill in.
