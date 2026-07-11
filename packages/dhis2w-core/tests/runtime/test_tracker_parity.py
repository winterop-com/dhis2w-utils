"""Per-version parity for the `tracker` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/data/test_tracker_*.py` routes + assertions, but resolves the service per
`core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted, not just
smoke-imported. The three service trees are byte-identical copies (only the import version differs), so
the assertions are the same on every tree. Mocked (respx); no live stack.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib import import_module
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile
from pydantic import BaseModel

_HOST = "https://dhis2.example"


def _tracker_bundle_class(core_version: str) -> type[BaseModel]:
    """Return the version tree's `TrackerBundle` class."""
    bundle_cls: type[BaseModel] = import_module(f"dhis2w_client.generated.{core_version}.tracker").TrackerBundle
    return bundle_cls


@respx.mock
async def test_resolve_tracked_entity_type_uid_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`resolve_tracked_entity_type` returns a UID-shaped value as-is, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")

    uid = await service.resolve_tracked_entity_type(resolve_profile("probe"), "tet01234567")

    assert uid == "tet01234567"


@respx.mock
async def test_resolve_tracked_entity_type_name_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`resolve_tracked_entity_type` resolves a name via /api/trackedEntityTypes, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.get(f"{_HOST}/api/trackedEntityTypes").mock(
        return_value=httpx.Response(200, json={"trackedEntityTypes": [{"id": "abcDEFghiJK", "name": "Person"}]}),
    )

    uid = await service.resolve_tracked_entity_type(resolve_profile("probe"), "Person")

    assert uid == "abcDEFghiJK"
    assert route.calls.last.request.url.params["filter"] == "name:ilike:Person"


@respx.mock
async def test_list_tracked_entities_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_tracked_entities` unwraps the `{pager, trackedEntities: [...]}` envelope, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.get(f"{_HOST}/api/tracker/trackedEntities").mock(
        return_value=httpx.Response(
            200,
            json={
                "pager": {"page": 1, "pageSize": 50},
                "trackedEntities": [
                    {"trackedEntity": "abcDEFghiJK", "trackedEntityType": "tet01234567"},
                    {"trackedEntity": "zzzYYYwwwVV", "trackedEntityType": "tet01234567"},
                ],
            },
        ),
    )

    result = await service.list_tracked_entities(resolve_profile("probe"), tracked_entity_type="tet01234567")

    assert [te.trackedEntity for te in result] == ["abcDEFghiJK", "zzzYYYwwwVV"]
    assert route.calls.last.request.url.params["trackedEntityType"] == "tet01234567"


@respx.mock
async def test_get_tracked_entity_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_tracked_entity` fetches one entity by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.get(f"{_HOST}/api/tracker/trackedEntities/abcDEFghiJK").mock(
        return_value=httpx.Response(200, json={"trackedEntity": "abcDEFghiJK", "trackedEntityType": "tet01234567"}),
    )

    result = await service.get_tracked_entity(resolve_profile("probe"), "abcDEFghiJK")

    assert result.trackedEntity == "abcDEFghiJK"
    assert route.called


@respx.mock
async def test_list_enrollments_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_enrollments` unwraps the `{pager, enrollments: [...]}` envelope, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.get(f"{_HOST}/api/tracker/enrollments").mock(
        return_value=httpx.Response(
            200,
            json={
                "pager": {"page": 1, "pageSize": 50},
                "enrollments": [{"enrollment": "enr01234567", "program": "prg01234567"}],
            },
        ),
    )

    result = await service.list_enrollments(resolve_profile("probe"), program="prg01234567")

    assert [e.enrollment for e in result] == ["enr01234567"]
    assert route.calls.last.request.url.params["program"] == "prg01234567"


@respx.mock
async def test_list_events_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_events` unwraps the `{pager, events: [...]}` envelope, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.get(f"{_HOST}/api/tracker/events").mock(
        return_value=httpx.Response(
            200,
            json={
                "pager": {"page": 1, "pageSize": 50},
                "events": [{"event": "evt01234567", "program": "prg01234567"}],
            },
        ),
    )

    result = await service.list_events(resolve_profile("probe"), program="prg01234567")

    assert [e.event for e in result] == ["evt01234567"]
    assert route.calls.last.request.url.params["program"] == "prg01234567"


@respx.mock
async def test_list_relationships_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_relationships` unwraps the `{pager, relationships: [...]}` envelope, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.get(f"{_HOST}/api/tracker/relationships").mock(
        return_value=httpx.Response(
            200,
            json={
                "pager": {"page": 1, "pageSize": 50},
                "relationships": [{"relationship": "rel01234567", "relationshipType": "rtyp1234567"}],
            },
        ),
    )

    result = await service.list_relationships(resolve_profile("probe"), tracked_entity="abcDEFghiJK")

    assert [r.relationship for r in result] == ["rel01234567"]
    assert route.calls.last.request.url.params["trackedEntity"] == "abcDEFghiJK"


@respx.mock
async def test_push_tracker_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`push_tracker` POSTs the bundle to /api/tracker with the import params, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.post(f"{_HOST}/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.push_tracker(
        resolve_profile("probe"),
        _tracker_bundle_class(core_version).model_validate({"events": [{"event": "evt01234567"}]}),
        import_strategy="CREATE",
        dry_run=True,
    )

    assert response.status == "OK"
    request = route.calls.last.request
    assert request.url.params["importStrategy"] == "CREATE"
    assert request.url.params["importMode"] == "VALIDATE"
    assert "dryRun" not in request.url.params
    assert request.url.params["async"] == "false"
    assert json.loads(request.content) == {"events": [{"event": "evt01234567"}]}


@respx.mock
async def test_delete_tracker_objects_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_tracker_objects` builds the minimal bundle with importStrategy=DELETE, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.post(f"{_HOST}/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    await service.delete_tracker_objects(resolve_profile("probe"), kind="events", uids=["evt01234567", "evt7654321X"])

    request = route.calls.last.request
    assert request.url.params["importStrategy"] == "DELETE"
    assert json.loads(request.content) == {"events": [{"event": "evt01234567"}, {"event": "evt7654321X"}]}


@respx.mock
async def test_register_tracked_entity_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`register_tracked_entity` posts a trackedEntities bundle and returns the new UIDs, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.post(f"{_HOST}/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    result = await service.register_tracked_entity(
        resolve_profile("probe"),
        program="prg01234567",
        org_unit="ou001234567",
        tracked_entity_type="tet01234567",
    )

    assert result.response.status == "OK"
    assert result.tracked_entity
    assert result.enrollment
    body = json.loads(route.calls.last.request.content)
    assert body["trackedEntities"][0]["trackedEntityType"] == "tet01234567"


@respx.mock
async def test_enroll_tracked_entity_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`enroll_tracked_entity` posts an enrollments bundle and returns the new UID, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.post(f"{_HOST}/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    result = await service.enroll_tracked_entity(
        resolve_profile("probe"),
        tracked_entity="abcDEFghiJK",
        program="prg01234567",
        org_unit="ou001234567",
    )

    assert result.response.status == "OK"
    assert result.enrollment
    body = json.loads(route.calls.last.request.content)
    assert body["enrollments"][0]["trackedEntity"] == "abcDEFghiJK"


@respx.mock
async def test_add_tracker_event_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_tracker_event` posts an events bundle and returns the new event UID, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    route = respx.post(f"{_HOST}/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    result = await service.add_tracker_event(
        resolve_profile("probe"),
        program="prg01234567",
        program_stage="stg01234567",
        org_unit="ou001234567",
        enrollment="enr01234567",
    )

    assert result.response.status == "OK"
    assert result.event
    body = json.loads(route.calls.last.request.content)
    assert body["events"][0]["programStage"] == "stg01234567"


@respx.mock
async def test_outstanding_enrollments_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`outstanding_enrollments` flags enrollments missing a non-repeatable stage event, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("tracker")
    respx.get(f"{_HOST}/api/programs/prg01234567").mock(
        return_value=httpx.Response(
            200,
            json={
                "programStages": [
                    {"id": "stg01234567", "repeatable": False},
                    {"id": "stg76543210", "repeatable": False},
                ]
            },
        ),
    )
    respx.get(f"{_HOST}/api/tracker/enrollments").mock(
        return_value=httpx.Response(
            200,
            json={
                "enrollments": [
                    {
                        "enrollment": "enr01234567",
                        "trackedEntity": "abcDEFghiJK",
                        "program": "prg01234567",
                        "orgUnit": "ou001234567",
                        "events": [{"programStage": "stg01234567"}],
                    },
                ],
            },
        ),
    )

    result = await service.outstanding_enrollments(resolve_profile("probe"), "prg01234567")

    assert len(result) == 1
    assert result[0].enrollment == "enr01234567"
    assert result[0].missing_stages == ["stg76543210"]
