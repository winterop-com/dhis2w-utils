"""Unit tests for `Dhis2Client.categories` — respx-mocked, across the v41/v42/v43 trees.

`categories` is identical across versions, so the same wire mocks + assertions run against
all three accessor trees via the `server_version` parametrization (see conftest).
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


@respx.mock
async def test_list_all_returns_typed_categories(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """List all returns typed categories."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/categories").mock(
        return_value=httpx.Response(
            200,
            json={
                "categories": [
                    {
                        "id": "CAT_SEX",
                        "name": "Sex",
                        "shortName": "Sex",
                        "dataDimensionType": "DISAGGREGATION",
                        "categoryOptions": [
                            {"id": "CO_M", "name": "Male"},
                            {"id": "CO_F", "name": "Female"},
                        ],
                    },
                ],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.categories.list_all()
    finally:
        await client.close()
    assert len(rows) == 1
    assert type(rows[0]).__name__ == "Category"
    assert rows[0].id == "CAT_SEX"
    assert rows[0].dataDimensionType == "DISAGGREGATION"


@respx.mock
async def test_create_wires_options_in_payload_and_fetches_back(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Create wires options in payload and fetches back."""
    mock_system_info(server_version)
    create_route = respx.post("https://dhis2.example/api/categories").mock(
        return_value=httpx.Response(
            201,
            json={"status": "OK", "httpStatusCode": 201, "response": {"uid": "CAT_NEW"}},
        ),
    )
    respx.get("https://dhis2.example/api/categories/CAT_NEW").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "CAT_NEW",
                "name": "Modality",
                "shortName": "Mod",
                "dataDimensionType": "DISAGGREGATION",
                "categoryOptions": [{"id": "CO_X"}, {"id": "CO_Y"}],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        created = await client.categories.create(
            name="Modality",
            short_name="Mod",
            options=["CO_X", "CO_Y"],
        )
    finally:
        await client.close()
    body = _json.loads(create_route.calls.last.request.read())
    assert body["name"] == "Modality"
    assert body["dataDimensionType"] == "DISAGGREGATION"
    assert body["categoryOptions"] == [{"id": "CO_X"}, {"id": "CO_Y"}]
    assert created.id == "CAT_NEW"


@respx.mock
async def test_rename_partial_updates_only_the_passed_fields(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Rename partial updates only the passed fields."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/categories/CAT_A").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "CAT_A",
                "name": "Sex",
                "shortName": "Sex",
                "code": "SEX",
                "description": "Original",
                "dataDimensionType": "DISAGGREGATION",
            },
        ),
    )
    put_route = respx.put("https://dhis2.example/api/categories/CAT_A").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.categories.rename("CAT_A", short_name="Gender")
    finally:
        await client.close()
    body = _json.loads(put_route.calls.last.request.read())
    assert body["shortName"] == "Gender"
    assert body["name"] == "Sex"  # untouched
    assert body["description"] == "Original"  # untouched


async def test_rename_rejects_no_op_call() -> None:
    """Service layer surfaces a ValueError when no rename field was passed (version-agnostic)."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    with pytest.raises(ValueError, match="rename requires"):
        await client.categories.rename("CAT_A")
