"""Unit tests for `Dhis2Client.category_combos` + `category_option_combos` — respx-mocked."""

from __future__ import annotations

import json as _json
from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import (
    BasicAuth,
    Dhis2Client,
)


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


@respx.mock
async def test_combo_list_all_returns_typed_combos(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Combo list all returns typed combos."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/categoryCombos").mock(
        return_value=httpx.Response(
            200,
            json={
                "categoryCombos": [
                    {
                        "id": "CC_DEFAULT",
                        "name": "default",
                        "isDefault": True,
                        "dataDimensionType": "DISAGGREGATION",
                        "categories": [{"id": "CAT_DEFAULT"}],
                        "categoryOptionCombos": [{"id": "COC_DEFAULT"}],
                    },
                ],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.category_combos.list_all()
    finally:
        await client.close()
    assert len(rows) == 1
    assert type(rows[0]).__name__ == "CategoryCombo"
    assert rows[0].isDefault is True


@respx.mock
async def test_combo_create_wires_categories_in_payload(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Combo create wires categories in payload."""
    mock_system_info(server_version)
    create_route = respx.post("https://dhis2.example/api/categoryCombos").mock(
        return_value=httpx.Response(
            201,
            json={"status": "OK", "httpStatusCode": 201, "response": {"uid": "CC_NEW"}},
        ),
    )
    respx.get("https://dhis2.example/api/categoryCombos/CC_NEW").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "CC_NEW",
                "name": "Sex x AgeGroup",
                "dataDimensionType": "DISAGGREGATION",
                "skipTotal": False,
                "categories": [{"id": "CAT_SEX"}, {"id": "CAT_AGE"}],
                "categoryOptionCombos": [],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        created = await client.category_combos.create(
            name="Sex x AgeGroup",
            categories=["CAT_SEX", "CAT_AGE"],
        )
    finally:
        await client.close()
    body = _json.loads(create_route.calls.last.request.read())
    assert body["name"] == "Sex x AgeGroup"
    assert body["dataDimensionType"] == "DISAGGREGATION"
    assert body["categories"] == [{"id": "CAT_SEX"}, {"id": "CAT_AGE"}]
    assert body["skipTotal"] is False
    assert created.id == "CC_NEW"


async def test_combo_create_rejects_empty_categories() -> None:
    """A CategoryCombo with no Categories is invalid — service surfaces ValueError."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    with pytest.raises(ValueError, match="at least one category"):
        await client.category_combos.create(name="Empty", categories=[])


@respx.mock
async def test_combo_create_against_v43_uses_categories_not_categorys() -> None:
    """v43 dropped the `categorys` alias (BUGS.md #34); writes must use `categories`."""
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.43.0"}),
    )
    create_route = respx.post("https://dhis2.example/api/categoryCombos").mock(
        return_value=httpx.Response(201, json={"status": "OK", "httpStatusCode": 201, "response": {"uid": "CC_NEW"}}),
    )
    respx.get("https://dhis2.example/api/categoryCombos/CC_NEW").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "CC_NEW",
                "name": "Sex",
                "dataDimensionType": "DISAGGREGATION",
                "skipTotal": False,
                "categories": [{"id": "CAT_SEX"}],
                "categoryOptionCombos": [],
            },
        ),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        assert client.version_key == "v43"
        await client.category_combos.create(name="Sex", categories=["CAT_SEX"])
    body = _json.loads(create_route.calls.last.request.read())
    assert "categorys" not in body
    assert body["categories"] == [{"id": "CAT_SEX"}]


@respx.mock
async def test_combo_wait_for_coc_generation_returns_when_count_lands(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Helper triggers the v43 maintenance task, then polls until COC count reaches `expected_count`."""
    mock_system_info(server_version)
    respx.post("https://dhis2.example/api/maintenance/categoryOptionComboUpdate").mock(
        return_value=httpx.Response(200, json={"httpStatus": "OK"}),
    )
    response_sequence = [
        httpx.Response(200, json={"categoryOptionCombos": [{"id": "COC_1"}]}),
        httpx.Response(200, json={"categoryOptionCombos": [{"id": "COC_1"}, {"id": "COC_2"}]}),
        httpx.Response(
            200,
            json={"categoryOptionCombos": [{"id": "COC_1"}, {"id": "COC_2"}, {"id": "COC_3"}, {"id": "COC_4"}]},
        ),
    ]
    respx.get("https://dhis2.example/api/categoryOptionCombos").mock(side_effect=response_sequence)
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        landed = await client.category_combos.wait_for_coc_generation(
            "CC_BIG", expected_count=4, timeout_seconds=5.0, poll_interval_seconds=0.01
        )
    finally:
        await client.close()
    assert landed == 4


@respx.mock
async def test_combo_wait_for_coc_generation_times_out(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Combo wait for coc generation times out."""
    mock_system_info(server_version)
    respx.post("https://dhis2.example/api/maintenance/categoryOptionComboUpdate").mock(
        return_value=httpx.Response(200, json={"httpStatus": "OK"}),
    )
    respx.get("https://dhis2.example/api/categoryOptionCombos").mock(
        return_value=httpx.Response(200, json={"categoryOptionCombos": [{"id": "COC_1"}]}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(TimeoutError, match="expected 4"):
            await client.category_combos.wait_for_coc_generation(
                "CC_STALE", expected_count=4, timeout_seconds=0.05, poll_interval_seconds=0.01
            )
    finally:
        await client.close()


@respx.mock
async def test_coc_list_for_combo_filters_by_category_combo_id(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Coc list for combo filters by category combo id."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/categoryOptionCombos").mock(
        return_value=httpx.Response(
            200,
            json={
                "categoryOptionCombos": [
                    {"id": "COC_M", "name": "Male", "categoryCombo": {"id": "CC_SEX"}},
                    {"id": "COC_F", "name": "Female", "categoryCombo": {"id": "CC_SEX"}},
                ]
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.category_option_combos.list_for_combo("CC_SEX")
    finally:
        await client.close()
    assert route.call_count == 1
    assert route.calls.last.request.url.params["filter"] == "categoryCombo.id:eq:CC_SEX"
    assert all(type(row).__name__ == "CategoryOptionCombo" for row in rows)
    assert {row.id for row in rows} == {"COC_M", "COC_F"}
