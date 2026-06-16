"""Live-schema contract tests against play.im.dhis2.org.

Pulls one real instance of each major resource from `dev-2-42` and
`dev-2-43` and runs it through the matching generated pydantic model.
Catches DHIS2 ship-day API drift the day it lands — if a field type
changes, a new required field appears, or an enum gains a constant we
don't know about, the model_validate call below raises and this test
fails.

Marked `@pytest.mark.contract` so it runs in a dedicated CI job
(`.github/workflows/contract.yml`) and not as part of `make test`.
The play instances are public; the only failure mode tied to network
is an instance being down — those skip rather than fail.

Coverage is exhaustive, not curated: the parametrize list is generated at
collection time from every `client.resources.<name>` accessor that supports
`.list`, per version (see `_listable_resource_accessors`). New generated
resources are picked up automatically. A resource the live instance has no
data for (or that doesn't exist on a given version) skips individually, so a
run gives a full pass / skip / fail overview across the whole resource surface.
"""

from __future__ import annotations

import warnings
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from dhis2w_client import BasicAuth, Dhis2Client
from dhis2w_client.errors import Dhis2ApiError


class UndeclaredFieldWarning(UserWarning):
    """A live row carried fields the generated model doesn't declare (additive drift)."""


def _listable_resource_accessors(version_key: str) -> list[str]:
    """Every `client.resources.<name>` accessor that supports `.list`, for one version.

    Enumerated statically from the generated `Resources` class (constructed with a
    stub object, so no network round-trip at collection time) — auto-generating
    keeps the contract suite exhaustive instead of hand-curating a subset, and new
    generated resources are covered the moment codegen adds them. The cost is one
    live list+get per resource per version; resources the instance has no data for
    skip individually (see `_assert_resource_validates`).
    """
    import importlib

    module = importlib.import_module(f"dhis2w_client.generated.{version_key}.resources")
    resources = module.Resources(object())  # accessors only stash the client; constructing one hits no network
    return sorted(
        name for name in dir(resources) if not name.startswith("_") and hasattr(getattr(resources, name), "list")
    )


# Built per version at collection time so v42/v43 each cover their own resource
# set (v43 drops `push_analysis`, for instance). Every listable `/api/{resource}`
# is exercised — a full overview, not a curated subset.
_V42_RESOURCES = _listable_resource_accessors("v42")
_V43_RESOURCES = _listable_resource_accessors("v43")

PLAY_URLS = {
    "v42": "https://play.im.dhis2.org/dev-2-42",
    "v43": "https://play.im.dhis2.org/dev-2-43",
}


async def _make_client(url: str) -> AsyncIterator[Dhis2Client]:
    """Connect to a play instance, skipping the test if it's unreachable."""
    client = Dhis2Client(url, auth=BasicAuth(username="admin", password="district"), allow_version_fallback=True)
    try:
        try:
            await client.connect()
        except httpx.HTTPError as exc:
            pytest.skip(f"play instance {url} unreachable: {exc}")
        yield client
    finally:
        await client.close()


@pytest.fixture
async def play_v42_client() -> AsyncIterator[Dhis2Client]:
    """Yield a connected client for `dev-2-42`, skipping if the host is down."""
    async for client in _make_client(PLAY_URLS["v42"]):
        yield client


@pytest.fixture
async def play_v43_client() -> AsyncIterator[Dhis2Client]:
    """Yield a connected client for `dev-2-43`, skipping if the host is down."""
    async for client in _make_client(PLAY_URLS["v43"]):
        yield client


def _report_undeclared_fields(label: str, model: Any) -> None:
    """Warn (never fail) when a parsed row carries fields the model doesn't declare.

    The generated models are `extra="allow"`, so any field DHIS2 returns that the
    model doesn't know about is captured in `.model_extra`. That is additive drift
    — harmless for a forward-compatible client, but worth surfacing so codegen can
    pick the field up deliberately. Emitted as an `UndeclaredFieldWarning` (shows
    in pytest's warnings summary) rather than an assertion, so it never reds the
    contract job; genuine *incompatible* drift still fails via `model_validate`.
    """
    undeclared = sorted((model.model_extra or {}).keys()) if hasattr(model, "model_extra") else []
    if undeclared:
        warnings.warn(
            f"`{label}` returned fields not declared on the generated model: {undeclared}",
            UndeclaredFieldWarning,
            stacklevel=2,
        )


async def _assert_resource_validates(client: Dhis2Client, accessor_name: str) -> None:
    """Pull one row of `accessor_name` and assert the typed model parses it.

    The contract this test guards is "the generated model parses a live row", so
    only a pydantic validation error counts as a failure. Everything that means
    "couldn't fetch a row to check" is a `skip` with a reason, keeping the suite
    a full pass / skip / fail overview rather than a red wall:

    - accessor absent on this version (e.g. v43 dropped it),
    - the instance has zero rows of this resource,
    - the resource isn't listable for this user (`GET` returns 4xx) — e.g. the
      OAuth2 authorization / consent tables 403 for admin; they're Spring
      Authorization Server runtime state, not admin-listable metadata.

    A genuine schema drift surfaces as a `pydantic.ValidationError` raised inside
    `accessor.list()` / `.get()` (which parse into the typed model) and fails.
    """
    accessor: Any = getattr(client.resources, accessor_name, None)
    if accessor is None:
        pytest.skip(f"client.resources has no `{accessor_name}` attribute on this DHIS2 version")

    try:
        rows = await accessor.list(page_size=1, fields="*")
    except Dhis2ApiError as exc:
        pytest.skip(f"`{accessor_name}` not listable on this instance: HTTP {exc.status_code}")
    if not rows:
        pytest.skip(f"play instance has zero `{accessor_name}` rows")

    _report_undeclared_fields(accessor_name, rows[0])

    # `list(fields="*")` returned a typed model already — if it parsed cleanly
    # the contract holds. Hit `get()` too to exercise the single-instance path
    # since it can have different fields than the listing path.
    sample_id = rows[0].id
    if not sample_id:
        pytest.skip(f"first `{accessor_name}` row had no id")
    try:
        fetched = await accessor.get(sample_id, fields="*")
    except Dhis2ApiError as exc:
        pytest.skip(f"GET `{accessor_name}/{sample_id}` returned HTTP {exc.status_code}")
    assert fetched is not None, f"GET /api/.../{sample_id} returned None"


@pytest.mark.contract
@pytest.mark.parametrize("accessor_name", _V42_RESOURCES, ids=_V42_RESOURCES)
async def test_v42_schema_contract(play_v42_client: Dhis2Client, accessor_name: str) -> None:
    """Generated v42 model still validates one live row from play."""
    await _assert_resource_validates(play_v42_client, accessor_name)


@pytest.mark.contract
@pytest.mark.parametrize("accessor_name", _V43_RESOURCES, ids=_V43_RESOURCES)
async def test_v43_schema_contract(play_v43_client: Dhis2Client, accessor_name: str) -> None:
    """Generated v43 model still validates one live row from play."""
    await _assert_resource_validates(play_v43_client, accessor_name)


# ---------------------------------------------------------------------------
# Tracker endpoints don't fit the `client.resources.X` accessor pattern —
# they live under `/api/tracker/*` with envelope `{pager, <resource>: [...]}`.
# We hit them via raw GETs and validate the first row through the matching
# `dhis2w_client.generated.v{N}.oas.tracker_*` pydantic model.
#
# The Sierra Leone play fixture seeds the `IpHINAT79UW` Child Programme
# (tracker, with-registration), so trackedEntities + enrollments always have
# rows there. That program ships with zero events on the dev play instances,
# so the events check discovers a program that currently has events at runtime
# rather than hard-coding one (the dev instances re-seed) — see
# `_fetch_first_tracker_row`.
# ---------------------------------------------------------------------------

_TRACKER_PROGRAM_UID = "IpHINAT79UW"  # Child Programme, with-registration: trackedEntities + enrollments.
_TRACKER_ROOT_OU = "ImspTQPwCqd"  # Sierra Leone root.


# v43 split the v42 `TrackerEvent` schema into `TrackerTrackerEvent`
# (tracker-program events) and `TrackerSingleEvent` (event-program events).
# `/api/tracker/events` maps to the tracker-event shape, so the parametrize id
# stays `TrackerEvent` (stable across versions) while v43 validates the renamed
# class. Keep this map keyed by the v42 name so new renames are one-liners.
_TRACKER_MODEL_RENAMES: dict[str, dict[str, str]] = {
    "v43": {"TrackerEvent": "TrackerTrackerEvent"},
}


def _import_tracker_model(version_key: str, model_name: str) -> Any:
    """Resolve `dhis2w_client.generated.v{N}.oas.<snake>.<ModelName>` dynamically.

    Versioned lookup avoids hard-coding both v42 and v43 import lines for
    each parametrize id. Applies `_TRACKER_MODEL_RENAMES` first so version-renamed
    schemas resolve, then falls back to a `pytest.skip` when the model isn't
    present on the requested version (e.g. v43 dropped a class).
    """
    import importlib

    model_name = _TRACKER_MODEL_RENAMES.get(version_key, {}).get(model_name, model_name)
    snake = "".join("_" + c.lower() if c.isupper() else c for c in model_name).lstrip("_")
    module_path = f"dhis2w_client.generated.{version_key}.oas.{snake}"
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        pytest.skip(f"model {model_name} not present in {module_path}")
    cls = getattr(module, model_name, None)
    if cls is None:
        pytest.skip(f"{module_path} has no class {model_name}")
    return cls


TRACKER_ENDPOINTS: list[tuple[str, str]] = [
    # (api-path segment under /api/tracker/, generated model class name)
    ("trackedEntities", "TrackerTrackedEntity"),
    ("enrollments", "TrackerEnrollment"),
    ("events", "TrackerEvent"),
    # `/api/tracker/relationships` is omitted — it requires `trackedEntity=` /
    # `enrollment=` / `event=` (no listing-by-program shape) and the seeded
    # play TEs ship with zero relationships, so we'd always skip. When play
    # gains relationship data, add it back with a TE-anchored query pattern.
]


async def _query_one_tracker_row(client: Dhis2Client, endpoint: str, program_uid: str) -> Any:
    """GET one `/api/tracker/{endpoint}` row scoped to `program_uid`, or None."""
    params = {"program": program_uid, "orgUnit": _TRACKER_ROOT_OU, "ouMode": "DESCENDANTS", "pageSize": "1"}
    raw = await client.get_raw(f"/api/tracker/{endpoint}", params=params)
    rows = raw.get(endpoint) or []
    return rows[0] if rows else None


async def _fetch_first_tracker_row(client: Dhis2Client, endpoint: str) -> Any:
    """Return one `/api/tracker/{endpoint}` row, or None if the instance has none.

    The `IpHINAT79UW` Child Programme has trackedEntities + enrollments but zero
    events on the dev play instances, so the events case needs a program that
    actually carries events. Rather than hard-code one (the dev instances
    re-seed, so any single program/event can vanish between runs and re-skip),
    discover a program with data at runtime: try the Child Programme, then probe
    every program (event programs first — they carry the seed's events) until one
    returns a row. We must scope to a program because v43 rejects an unscoped
    `/api/tracker/events` query with HTTP 400. trackedEntities / enrollments
    return on the first pass, so only `events` reaches the discovery loop.
    """
    row = await _query_one_tracker_row(client, endpoint, _TRACKER_PROGRAM_UID)
    if row is not None:
        return row
    raw_programs = await client.get_raw("/api/programs", params={"fields": "id,programType", "paging": "false"})
    programs = raw_programs.get("programs") or []
    # Event programs (WITHOUT_REGISTRATION) are likeliest to carry event rows in
    # the seed, so probe them before with-registration programs to minimise calls.
    ordered_ids = [p["id"] for p in programs if p.get("programType") == "WITHOUT_REGISTRATION" and p.get("id")]
    ordered_ids += [p["id"] for p in programs if p.get("programType") != "WITHOUT_REGISTRATION" and p.get("id")]
    for program_uid in ordered_ids:
        row = await _query_one_tracker_row(client, endpoint, program_uid)
        if row is not None:
            return row
    return None


async def _assert_tracker_endpoint_validates(client: Dhis2Client, endpoint: str, model_name: str) -> None:
    """Pull one row of `/api/tracker/{endpoint}` and validate it through the matching pydantic model."""
    row = await _fetch_first_tracker_row(client, endpoint)
    if row is None:
        pytest.skip(f"play instance has zero `/api/tracker/{endpoint}` rows in any program")
    model_cls = _import_tracker_model(client.version_key, model_name)
    # `model_validate` raises on shape drift — that's the contract check.
    instance = model_cls.model_validate(row)
    assert instance is not None
    _report_undeclared_fields(f"/api/tracker/{endpoint}", instance)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("endpoint", "model_name"),
    TRACKER_ENDPOINTS,
    ids=[m for _, m in TRACKER_ENDPOINTS],
)
async def test_v42_tracker_contract(
    play_v42_client: Dhis2Client,
    endpoint: str,
    model_name: str,
) -> None:
    """Generated v42 tracker model still validates one live row from play."""
    await _assert_tracker_endpoint_validates(play_v42_client, endpoint, model_name)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("endpoint", "model_name"),
    TRACKER_ENDPOINTS,
    ids=[m for _, m in TRACKER_ENDPOINTS],
)
async def test_v43_tracker_contract(
    play_v43_client: Dhis2Client,
    endpoint: str,
    model_name: str,
) -> None:
    """Generated v43 tracker model still validates one live row from play."""
    await _assert_tracker_endpoint_validates(play_v43_client, endpoint, model_name)
