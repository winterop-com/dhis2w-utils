"""Tests for `Dhis2Client.complete_data_set_registrations.export`."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2ApiError, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


def _registrations_payload() -> dict[str, object]:
    """Canned /api/completeDataSetRegistrations export envelope."""
    return {
        "completeDataSetRegistrations": [
            {
                "dataSet": "BfMAe6Itzgt",
                "period": "202401",
                "organisationUnit": "DiszpKrYNg8",
                "attributeOptionCombo": "HllvX50cXC0",
                "date": "2024-02-01",
                "storedBy": "admin",
                "completed": True,
            },
            {
                "dataSet": "BfMAe6Itzgt",
                "period": "202402",
                "organisationUnit": "DiszpKrYNg8",
                "completed": False,
            },
        ],
    }


@respx.mock
async def test_export_builds_repeated_params_and_parses_envelope(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`export(...)` repeats dataSet/period/orgUnit params and validates the typed envelope."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/completeDataSetRegistrations").mock(
        return_value=httpx.Response(200, json=_registrations_payload()),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.complete_data_set_registrations.export(
            data_set=["BfMAe6Itzgt", "V8MHeZHIrcP"],
            period="202401",
            org_unit="DiszpKrYNg8",
            children=True,
            created="2024-01-01",
            last_updated="2024-02-01",
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params.get_list("dataSet") == ["BfMAe6Itzgt", "V8MHeZHIrcP"]
    assert params.get_list("period") == ["202401"]
    assert params["orgUnit"] == "DiszpKrYNg8"
    assert params["children"] == "true"
    assert params["created"] == "2024-01-01"
    assert params["lastUpdated"] == "2024-02-01"
    assert [r.period for r in result.completeDataSetRegistrations] == ["202401", "202402"]
    assert result.completeDataSetRegistrations[0].storedBy == "admin"
    assert result.completeDataSetRegistrations[0].completed is True


@respx.mock
async def test_export_omits_none_params(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Unset params never reach the wire; a bare export sends no query string."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/completeDataSetRegistrations").mock(
        return_value=httpx.Response(200, json={"completeDataSetRegistrations": []}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.complete_data_set_registrations.export()
    finally:
        await client.close()

    assert str(route.calls.last.request.url.params) == ""
    assert result.completeDataSetRegistrations == []


@respx.mock
async def test_export_selects_by_date_range_and_extra_params(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`start_date`/`end_date` and `extra_params` cover the rest of the surface."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/completeDataSetRegistrations").mock(
        return_value=httpx.Response(200, json={"completeDataSetRegistrations": []}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.complete_data_set_registrations.export(
            data_set="BfMAe6Itzgt",
            org_unit="DiszpKrYNg8",
            start_date="2024-01-01",
            end_date="2024-03-31",
            extra_params={"idScheme": "CODE", "dataSetIdScheme": "UID"},
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["startDate"] == "2024-01-01"
    assert params["endDate"] == "2024-03-31"
    assert params["idScheme"] == "CODE"
    assert params["dataSetIdScheme"] == "UID"


@respx.mock
async def test_export_raises_dhis2_api_error_on_4xx(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """A 4xx surfaces as `Dhis2ApiError` with the status code intact."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/completeDataSetRegistrations").mock(
        return_value=httpx.Response(409, json={"httpStatus": "Conflict", "message": "boom"}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(Dhis2ApiError) as exc_info:
            await client.complete_data_set_registrations.export(data_set="BfMAe6Itzgt")
    finally:
        await client.close()

    assert exc_info.value.status_code == 409
