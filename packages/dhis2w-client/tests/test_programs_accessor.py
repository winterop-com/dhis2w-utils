"""Unit tests for `ProgramsAccessor` — respx-mocked."""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


def _mock_default_combo() -> None:
    respx.get("https://dhis2.example/api/categoryCombos").mock(
        return_value=httpx.Response(200, json={"categoryCombos": [{"id": "ccDefault001", "name": "default"}]}),
    )


@respx.mock
async def test_list_all_filters_by_program_type(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """List all filters by program type."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/programs").mock(
        return_value=httpx.Response(
            200,
            json={"programs": [{"id": "PRG00000001", "name": "ANC", "programType": "WITH_REGISTRATION"}]},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.programs.list_all(program_type="WITH_REGISTRATION")
    finally:
        await client.close()
    assert route.calls.last.request.url.params["filter"] == "programType:eq:WITH_REGISTRATION"
    assert [r.id for r in rows] == ["PRG00000001"]


@respx.mock
async def test_create_with_registration_requires_tet_raises(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Create with registration requires tet raises."""
    mock_system_info(server_version)
    _mock_default_combo()
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(ValueError, match="tracked_entity_type_uid"):
            await client.programs.create(name="ANC", short_name="ANC")
    finally:
        await client.close()


@respx.mock
async def test_create_posts_payload_with_tet_ref_and_default_combo(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Create posts payload with tet ref and default combo."""
    mock_system_info(server_version)
    _mock_default_combo()
    post = respx.post("https://dhis2.example/api/programs").mock(
        return_value=httpx.Response(201, json={"response": {"uid": "PRG_NEW00001"}}),
    )
    respx.get("https://dhis2.example/api/programs/PRG_NEW00001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "PRG_NEW00001",
                "name": "ANC",
                "programType": "WITH_REGISTRATION",
                "trackedEntityType": {"id": "TETperson001"},
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        program = await client.programs.create(
            name="ANC",
            short_name="ANC",
            tracked_entity_type_uid="TETperson001",
            display_incident_date=True,
        )
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(post.calls.last.request.read())
    assert body["programType"] == "WITH_REGISTRATION"
    assert body["trackedEntityType"] == {"id": "TETperson001"}
    assert body["categoryCombo"] == {"id": "ccDefault001"}
    assert body["displayIncidentDate"] is True
    assert program.id == "PRG_NEW00001"


@respx.mock
async def test_create_without_registration_skips_tet_check(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Create without registration skips tet check."""
    mock_system_info(server_version)
    _mock_default_combo()
    respx.post("https://dhis2.example/api/programs").mock(
        return_value=httpx.Response(201, json={"response": {"uid": "EVT_NEW00001"}}),
    )
    respx.get("https://dhis2.example/api/programs/EVT_NEW00001").mock(
        return_value=httpx.Response(
            200,
            json={"id": "EVT_NEW00001", "name": "Supervision", "programType": "WITHOUT_REGISTRATION"},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        program = await client.programs.create(
            name="Supervision visit",
            short_name="Supv",
            program_type="WITHOUT_REGISTRATION",
        )
    finally:
        await client.close()
    assert program.id == "EVT_NEW00001"


@respx.mock
async def test_add_attribute_round_trips_and_strips_self_ref(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Add attribute round trips and strips self ref."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programs/PRG1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "PRG1",
                "name": "ANC",
                "programTrackedEntityAttributes": [
                    {
                        "trackedEntityAttribute": {"id": "TEA_A"},
                        "mandatory": True,
                        "program": {"id": "PRG1"},
                    },
                ],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/programs/PRG1").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.programs.add_attribute(
            "PRG1",
            "TEA_B",
            mandatory=False,
            searchable=True,
            sort_order=2,
        )
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(put.calls.last.request.read())
    ids = [
        entry["trackedEntityAttribute"]["id"]
        for entry in body["programTrackedEntityAttributes"]
        if "trackedEntityAttribute" in entry
    ]
    assert ids == ["TEA_A", "TEA_B"]
    assert all("program" not in entry for entry in body["programTrackedEntityAttributes"]), "self-ref must be stripped"
    added = body["programTrackedEntityAttributes"][1]
    assert added["searchable"] is True
    assert added["sortOrder"] == 2


@respx.mock
async def test_add_attribute_idempotent_when_already_linked(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Add attribute idempotent when already linked."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programs/PRG1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "PRG1",
                "name": "ANC",
                "programTrackedEntityAttributes": [{"trackedEntityAttribute": {"id": "TEA_A"}}],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/programs/PRG1").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.programs.add_attribute("PRG1", "TEA_A")
    finally:
        await client.close()
    assert put.called is False


@respx.mock
async def test_add_organisation_unit_uses_per_item_post_shortcut(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Add organisation unit uses per item post shortcut."""
    mock_system_info(server_version)
    post = respx.post("https://dhis2.example/api/programs/PRG1/organisationUnits/OU_A").mock(
        return_value=httpx.Response(204),
    )
    respx.get("https://dhis2.example/api/programs/PRG1").mock(
        return_value=httpx.Response(200, json={"id": "PRG1", "name": "ANC"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.programs.add_organisation_unit("PRG1", "OU_A")
    finally:
        await client.close()
    assert post.called


@respx.mock
async def test_remove_organisation_unit_uses_per_item_delete_shortcut(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Remove organisation unit uses per item delete shortcut."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/programs/PRG1/organisationUnits/OU_A").mock(
        return_value=httpx.Response(204),
    )
    respx.get("https://dhis2.example/api/programs/PRG1").mock(
        return_value=httpx.Response(200, json={"id": "PRG1", "name": "ANC"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.programs.remove_organisation_unit("PRG1", "OU_A")
    finally:
        await client.close()
    assert route.called


@respx.mock
async def test_delete_routes_to_programs_uid(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Delete routes to programs uid."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/programs/PRG_X").mock(return_value=httpx.Response(204))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.programs.delete("PRG_X")
    finally:
        await client.close()
    assert route.called


async def test_accessor_is_bound_on_client() -> None:
    """Accessor is bound on client."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        assert client.programs is not None
    finally:
        await client.close()
