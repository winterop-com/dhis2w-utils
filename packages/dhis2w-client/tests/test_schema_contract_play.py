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

Adding more resources: append a `(accessor_name, model_name)` pair to
RESOURCES. The accessor_name is the attribute on `client.resources`;
the model_name is informational (used in the parametrize id).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from dhis2w_client import BasicAuth, Dhis2Client

# Each (accessor, model_name) pair represents one schema we want to keep
# in sync with the live DHIS2 wire shape. Picking ~25 covers the most-used
# corners of /api/* without spamming play.
RESOURCES: list[tuple[str, str]] = [
    ("attributes", "Attribute"),
    ("categories", "Category"),
    ("category_combos", "CategoryCombo"),
    ("category_option_combos", "CategoryOptionCombo"),
    ("category_options", "CategoryOption"),
    ("dashboards", "Dashboard"),
    ("data_element_groups", "DataElementGroup"),
    ("data_elements", "DataElement"),
    ("data_sets", "DataSet"),
    ("indicator_groups", "IndicatorGroup"),
    ("indicators", "Indicator"),
    ("legend_sets", "LegendSet"),
    ("maps", "Map"),
    ("option_sets", "OptionSet"),
    ("organisation_unit_groups", "OrganisationUnitGroup"),
    ("organisation_unit_levels", "OrganisationUnitLevel"),
    ("organisation_units", "OrganisationUnit"),
    ("predictors", "Predictor"),
    ("program_indicators", "ProgramIndicator"),
    ("program_rules", "ProgramRule"),
    ("program_stages", "ProgramStage"),
    ("programs", "Program"),
    ("sql_views", "SqlView"),
    ("tracked_entity_attributes", "TrackedEntityAttribute"),
    ("user_groups", "UserGroup"),
    ("user_roles", "UserRole"),
    ("users", "User"),
    ("validation_rules", "ValidationRule"),
    ("visualizations", "Visualization"),
]

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


async def _assert_resource_validates(client: Dhis2Client, accessor_name: str) -> None:
    """Pull one row of `accessor_name` and assert the typed model parses it.

    Skipping rather than failing when the accessor doesn't exist on the
    live version (e.g. v43 drops something we still test for v42) keeps
    the test honest about what's been verified vs not.
    """
    accessor: Any = getattr(client.resources, accessor_name, None)
    if accessor is None:
        pytest.skip(f"client.resources has no `{accessor_name}` attribute on this DHIS2 version")

    rows = await accessor.list(page_size=1, fields="*")
    if not rows:
        pytest.skip(f"play instance has zero `{accessor_name}` rows")

    # `list(fields="*")` returned a typed model already — if it parsed cleanly
    # the contract holds. Hit `get()` too to exercise the single-instance path
    # since it can have different fields than the listing path.
    sample_id = rows[0].id
    if not sample_id:
        pytest.skip(f"first `{accessor_name}` row had no id")
    fetched = await accessor.get(sample_id, fields="*")
    assert fetched is not None, f"GET /api/.../{sample_id} returned None"


@pytest.mark.contract
@pytest.mark.parametrize(("accessor_name", "model_name"), RESOURCES, ids=[m for _, m in RESOURCES])
async def test_v42_schema_contract(
    play_v42_client: Dhis2Client,
    accessor_name: str,
    model_name: str,  # noqa: ARG001 — used as parametrize id
) -> None:
    """Generated v42 model still validates one live row from play."""
    await _assert_resource_validates(play_v42_client, accessor_name)


@pytest.mark.contract
@pytest.mark.parametrize(("accessor_name", "model_name"), RESOURCES, ids=[m for _, m in RESOURCES])
async def test_v43_schema_contract(
    play_v43_client: Dhis2Client,
    accessor_name: str,
    model_name: str,  # noqa: ARG001 — used as parametrize id
) -> None:
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
        pytest.skip(
            f"play instance has zero `/api/tracker/{endpoint}` rows (program {_TRACKER_PROGRAM_UID} + unscoped)"
        )
    model_cls = _import_tracker_model(client.version_key, model_name)
    # `model_validate` raises on shape drift — that's the contract check.
    instance = model_cls.model_validate(row)
    assert instance is not None


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
