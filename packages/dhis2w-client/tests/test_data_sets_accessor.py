"""Unit tests for `DataSetsAccessor` — respx-mocked."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import respx
from dhis2w_client import BasicAuth, Dhis2Client
from dhis2w_client.v42.periods import PeriodType


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


def _mock_default_combo() -> None:
    respx.get("https://dhis2.example/api/categoryCombos").mock(
        return_value=httpx.Response(200, json={"categoryCombos": [{"id": "ccDefault001", "name": "default"}]}),
    )


@respx.mock
async def test_list_all_filters_by_period_type_and_returns_typed_models(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """List all filters by period type and returns typed models."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/dataSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataSets": [
                    {"id": "DS_MONTHLY1", "name": "ds1", "periodType": "Monthly"},
                    {"id": "DS_MONTHLY2", "name": "ds2", "periodType": "Monthly"},
                ],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.data_sets.list_all(period_type=PeriodType.MONTHLY, page=2, page_size=25)
    finally:
        await client.close()
    params = route.calls.last.request.url.params
    assert params["filter"] == "periodType:eq:Monthly"
    assert params["page"] == "2"
    assert params["pageSize"] == "25"
    assert [ds.id for ds in rows] == ["DS_MONTHLY1", "DS_MONTHLY2"]


@respx.mock
async def test_get_returns_typed_model(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Get returns typed model."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dataSets/DS001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "DS001",
                "name": "demo",
                "periodType": "Monthly",
                "dataSetElements": [{"dataElement": {"id": "DE1"}}],
                "sections": [{"id": "SEC1", "name": "Sec", "sortOrder": 1}],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        ds = await client.data_sets.get("DS001")
    finally:
        await client.close()
    assert ds.id == "DS001"
    assert len(ds.dataSetElements or []) == 1
    assert len(ds.sections or []) == 1


@respx.mock
async def test_create_falls_back_to_system_default_combo_when_omitted(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Create falls back to system default combo when omitted."""
    mock_system_info(server_version)
    _mock_default_combo()
    post = respx.post("https://dhis2.example/api/dataSets").mock(
        return_value=httpx.Response(201, json={"response": {"uid": "DS_NEW00001"}}),
    )
    respx.get("https://dhis2.example/api/dataSets/DS_NEW00001").mock(
        return_value=httpx.Response(200, json={"id": "DS_NEW00001", "name": "ANC", "periodType": "Monthly"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        ds = await client.data_sets.create(
            name="ANC",
            short_name="ANC",
            period_type=PeriodType.MONTHLY,
            open_future_periods=2,
        )
    finally:
        await client.close()
    body = post.calls.last.request.read()
    import json as _json

    payload: dict[str, Any] = _json.loads(body)
    assert payload["periodType"] == "Monthly"
    assert payload["openFuturePeriods"] == 2
    assert payload["categoryCombo"] == {"id": "ccDefault001"}
    assert ds.id == "DS_NEW00001"


@respx.mock
async def test_add_element_round_trips_and_strips_self_ref(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Add element round trips and strips self ref."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dataSets/DS001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "DS001",
                "name": "demo",
                "periodType": "Monthly",
                "dataSetElements": [
                    {
                        "dataElement": {"id": "DE_A"},
                        "dataSet": {"id": "DS001"},
                    },
                ],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/dataSets/DS001").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_sets.add_element("DS001", "DE_B", category_combo_uid="cc_override")
    finally:
        await client.close()
    import json as _json

    body: dict[str, Any] = _json.loads(put.calls.last.request.read())
    dse_ids = [entry["dataElement"]["id"] for entry in body["dataSetElements"]]
    assert dse_ids == ["DE_A", "DE_B"]
    assert body["dataSetElements"][1]["categoryCombo"] == {"id": "cc_override"}
    assert all("dataSet" not in entry for entry in body["dataSetElements"]), "self-ref must be stripped"


@respx.mock
async def test_add_element_is_idempotent_when_de_already_present(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Add element is idempotent when de already present."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dataSets/DS001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "DS001",
                "name": "demo",
                "periodType": "Monthly",
                "dataSetElements": [{"dataElement": {"id": "DE_A"}}],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/dataSets/DS001").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_sets.add_element("DS001", "DE_A")
    finally:
        await client.close()
    assert put.called is False


@respx.mock
async def test_remove_element_filters_the_dse_list(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Remove element filters the dse list."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dataSets/DS001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "DS001",
                "name": "demo",
                "periodType": "Monthly",
                "dataSetElements": [
                    {"dataElement": {"id": "DE_A"}},
                    {"dataElement": {"id": "DE_B"}},
                ],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/dataSets/DS001").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_sets.remove_element("DS001", "DE_A")
    finally:
        await client.close()
    import json as _json

    body: dict[str, Any] = _json.loads(put.calls.last.request.read())
    assert [entry["dataElement"]["id"] for entry in body["dataSetElements"]] == ["DE_B"]


@respx.mock
async def test_delete_routes_to_data_sets_uid(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Delete routes to data sets uid."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/dataSets/DS001").mock(return_value=httpx.Response(204))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_sets.delete("DS001")
    finally:
        await client.close()
    assert route.called


async def test_accessor_is_bound_on_client() -> None:
    """Accessor is bound on client."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        assert client.data_sets is not None
    finally:
        await client.close()
