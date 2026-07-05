"""Per-version parity for the `aggregate` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/data/test_aggregate_service.py` routes + assertions, but resolves the
service per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted,
not just smoke-imported. Mocked (respx); no live stack.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile
from pydantic import BaseModel

_HOST = "https://dhis2.example"


def _data_value_class(core_version: str) -> type[BaseModel]:
    """Return the version tree's generated `DataValue` class."""
    data_value_cls: type[BaseModel] = import_module(f"dhis2w_client.{core_version}").DataValue
    return data_value_cls


@respx.mock
async def test_aggregate_get_data_values_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_data_values` parses /api/dataValueSets into a typed envelope, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("aggregate")
    payload = {
        "dataSet": "lyLU2wR22tC",
        "dataValues": [
            {"dataElement": "fbfJHSPpUQD", "period": "202403", "orgUnit": "ImspTQPwCqd", "value": "12"},
            {"dataElement": "cYeuwXTCPkU", "period": "202403", "orgUnit": "ImspTQPwCqd", "value": "7"},
        ],
    }
    route = respx.get(f"{_HOST}/api/dataValueSets").mock(return_value=httpx.Response(200, json=payload))

    envelope = await service.get_data_values(
        resolve_profile("probe"), data_set="lyLU2wR22tC", period="202403", org_unit="ImspTQPwCqd"
    )

    assert envelope.dataValues is not None
    assert len(envelope.dataValues) == 2
    assert route.calls.last.request.url.params["dataSet"] == "lyLU2wR22tC"


@respx.mock
async def test_aggregate_push_data_values_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`push_data_values` POSTs the body + dryRun/importStrategy params, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("aggregate")
    route = respx.post(f"{_HOST}/api/dataValueSets").mock(
        return_value=httpx.Response(
            200,
            json={"status": "OK", "httpStatusCode": 200, "response": {"status": "OK", "imported": 2}},
        ),
    )

    response = await service.push_data_values(
        resolve_profile("probe"),
        data_values=[
            _data_value_class(core_version).model_validate(
                {"dataElement": "de1", "period": "202403", "orgUnit": "ou1", "value": "1"}
            )
        ],
        data_set="lyLU2wR22tC",
        dry_run=True,
        import_strategy="CREATE",
    )

    assert response.status == "OK"
    request = route.calls.last.request
    assert request.url.params["dryRun"] == "true"
    assert request.url.params["importStrategy"] == "CREATE"
    assert b'"dataSet":"lyLU2wR22tC"' in request.read()


@respx.mock
async def test_aggregate_set_data_value_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_data_value` posts to /api/dataValues with value carried as query params, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("aggregate")
    route = respx.post(f"{_HOST}/api/dataValues").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200})
    )

    await service.set_data_value(
        resolve_profile("probe"),
        data_element="fbfJHSPpUQD",
        period="202403",
        org_unit="ImspTQPwCqd",
        value="42",
    )

    params = route.calls.last.request.url.params
    assert params["de"] == "fbfJHSPpUQD"
    assert params["value"] == "42"


@respx.mock
async def test_aggregate_delete_data_value_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_data_value` DELETEs /api/dataValues with the cell key as params, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("aggregate")
    route = respx.delete(f"{_HOST}/api/dataValues").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200})
    )

    await service.delete_data_value(
        resolve_profile("probe"), data_element="fbfJHSPpUQD", period="202403", org_unit="ImspTQPwCqd"
    )

    params = route.calls.last.request.url.params
    assert params["de"] == "fbfJHSPpUQD"
    assert params["pe"] == "202403"
