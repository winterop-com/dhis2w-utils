"""Unit tests for `ProgramStagesAccessor` — respx-mocked."""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import Any

import httpx
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


@respx.mock
async def test_list_for_filters_by_program_and_disables_paging(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """List for filters by program and disables paging."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/programStages").mock(
        return_value=httpx.Response(
            200,
            json={"programStages": [{"id": "PSx1", "name": "Visit 1", "sortOrder": 1}]},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.program_stages.list_for("PRG1")
    finally:
        await client.close()
    params = route.calls.last.request.url.params
    assert params["filter"] == "program.id:eq:PRG1"
    assert params["paging"] == "false"
    assert params["order"] == "sortOrder:asc"


@respx.mock
async def test_create_posts_payload_with_program_ref(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Create posts payload with program ref."""
    mock_system_info(server_version)
    post = respx.post("https://dhis2.example/api/programStages").mock(
        return_value=httpx.Response(201, json={"response": {"uid": "PS_NEW00001"}}),
    )
    respx.get("https://dhis2.example/api/programStages/PS_NEW00001").mock(
        return_value=httpx.Response(200, json={"id": "PS_NEW00001", "name": "ANC 1st"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        stage = await client.program_stages.create(
            name="ANC 1st",
            program_uid="PRG1",
            repeatable=True,
            min_days_from_start=0,
            sort_order=1,
        )
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(post.calls.last.request.read())
    assert body["name"] == "ANC 1st"
    assert body["program"] == {"id": "PRG1"}
    assert body["repeatable"] is True
    assert body["sortOrder"] == 1
    assert stage.id == "PS_NEW00001"


@respx.mock
async def test_add_element_round_trips_and_strips_self_ref(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Add element round trips and strips self ref."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programStages/PS1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "PS1",
                "name": "Visit 1",
                "programStageDataElements": [
                    {
                        "dataElement": {"id": "DE_A"},
                        "compulsory": True,
                        "programStage": {"id": "PS1"},
                    },
                ],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/programStages/PS1").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.program_stages.add_element("PS1", "DE_B", compulsory=False, sort_order=2)
    finally:
        await client.close()
    assert put.calls.last.request.url.params["mergeMode"] == "REPLACE"
    body: dict[str, Any] = _json.loads(put.calls.last.request.read())
    ids = [entry["dataElement"]["id"] for entry in body["programStageDataElements"]]
    assert ids == ["DE_A", "DE_B"]
    assert all("programStage" not in entry for entry in body["programStageDataElements"])
    added = body["programStageDataElements"][1]
    assert added["compulsory"] is False
    assert added["sortOrder"] == 2


@respx.mock
async def test_add_element_idempotent_when_already_linked(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Add element idempotent when already linked."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programStages/PS1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "PS1",
                "name": "Visit 1",
                "programStageDataElements": [{"dataElement": {"id": "DE_A"}}],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/programStages/PS1").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.program_stages.add_element("PS1", "DE_A")
    finally:
        await client.close()
    assert put.called is False


@respx.mock
async def test_remove_element_filters_the_psde_list(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Remove element filters the psde list."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programStages/PS1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "PS1",
                "name": "Visit 1",
                "programStageDataElements": [
                    {"dataElement": {"id": "DE_A"}},
                    {"dataElement": {"id": "DE_B"}},
                ],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/programStages/PS1").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.program_stages.remove_element("PS1", "DE_A")
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(put.calls.last.request.read())
    ids = [entry["dataElement"]["id"] for entry in body["programStageDataElements"]]
    assert ids == ["DE_B"]


@respx.mock
async def test_reorder_preserves_flags_and_writes_sort_order(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Reorder preserves flags and writes sort order."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programStages/PS1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "PS1",
                "name": "Visit 1",
                "programStageDataElements": [
                    {"dataElement": {"id": "DE_A"}, "compulsory": True, "sortOrder": 0},
                    {"dataElement": {"id": "DE_B"}, "compulsory": False, "sortOrder": 1},
                    {"dataElement": {"id": "DE_C"}, "compulsory": False, "sortOrder": 2},
                ],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/programStages/PS1").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.program_stages.reorder("PS1", ["DE_C", "DE_A", "DE_B"])
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(put.calls.last.request.read())
    entries = body["programStageDataElements"]
    assert [e["dataElement"]["id"] for e in entries] == ["DE_C", "DE_A", "DE_B"]
    assert [e["sortOrder"] for e in entries] == [0, 1, 2]
    # DE_A's compulsory flag preserved from the previous entry
    assert entries[1]["compulsory"] is True
    # DE_B's compulsory flag preserved
    assert entries[2]["compulsory"] is False


@respx.mock
async def test_delete_routes_through_generated_resource(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Delete routes through generated resource."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/programStages/PS_X").mock(return_value=httpx.Response(204))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.program_stages.delete("PS_X")
    finally:
        await client.close()
    assert route.called


async def test_accessor_is_bound_on_client() -> None:
    """Accessor is bound on client."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        assert client.program_stages is not None
    finally:
        await client.close()
