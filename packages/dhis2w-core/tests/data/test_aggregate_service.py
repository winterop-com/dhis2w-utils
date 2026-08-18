"""Unit tests for the `aggregate` plugin service layer.

Mocks DHIS2's `/api/dataValueSets` + `/api/dataValues` endpoints via
respx and asserts the service-layer wrapper produces the expected
typed envelopes. Covers the four public functions:
`get_data_values`, `push_data_values`, `set_data_value`, `delete_data_value`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest
import respx
from dhis2w_client.v42 import DataValue
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.aggregate import service


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip DHIS2_* env so `open_client` resolves the explicit profile arg, not env state."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DHIS2_URL", "https://dhis2.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")
    yield


@pytest.fixture
def profile() -> Profile:
    """A simple PAT-auth profile pointed at the respx mock host."""
    return Profile(base_url="https://dhis2.example", auth="pat", token="test-token")


def _mock_preamble() -> None:
    """Mock the endpoints `Dhis2Client.connect()` probes before service calls hit."""
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )


@respx.mock
async def test_get_data_values_returns_typed_envelope(profile: Profile) -> None:
    """`get_data_values` parses /api/dataValueSets into a typed `DataValueSet`."""
    _mock_preamble()
    payload = {
        "dataSet": "lyLU2wR22tC",
        "period": "202403",
        "orgUnit": "ImspTQPwCqd",
        "dataValues": [
            {"dataElement": "fbfJHSPpUQD", "period": "202403", "orgUnit": "ImspTQPwCqd", "value": "12"},
            {"dataElement": "cYeuwXTCPkU", "period": "202403", "orgUnit": "ImspTQPwCqd", "value": "7"},
        ],
    }
    route = respx.get("https://dhis2.example/api/dataValueSets").mock(return_value=httpx.Response(200, json=payload))

    envelope = await service.get_data_values(
        profile,
        data_set="lyLU2wR22tC",
        period="202403",
        org_unit="ImspTQPwCqd",
    )

    assert envelope.dataSet == "lyLU2wR22tC"
    assert envelope.dataValues is not None
    assert len(envelope.dataValues) == 2
    params = route.calls.last.request.url.params
    assert params["dataSet"] == "lyLU2wR22tC"
    assert params["period"] == "202403"
    assert params["orgUnit"] == "ImspTQPwCqd"


@respx.mock
async def test_get_data_values_threads_filters(profile: Profile) -> None:
    """`get_data_values` forwards orgUnitGroup / includeDeleted / lastUpdated as query params."""
    _mock_preamble()
    route = respx.get("https://dhis2.example/api/dataValueSets").mock(
        return_value=httpx.Response(200, json={"dataValues": []})
    )

    await service.get_data_values(
        profile,
        data_set="lyLU2wR22tC",
        org_unit_group="OU_GRP",
        include_deleted=True,
        last_updated="2024-01-01",
    )

    params = route.calls.last.request.url.params
    assert params["orgUnitGroup"] == "OU_GRP"
    assert params["includeDeleted"] == "true"
    assert params["lastUpdated"] == "2024-01-01"


@respx.mock
async def test_get_data_values_sends_a_duration_on_its_own_parameter(profile: Profile) -> None:
    """A `7d`-shaped `last_updated` goes to `lastUpdatedDuration` - the date parameter refuses it with a 400."""
    _mock_preamble()
    route = respx.get("https://dhis2.example/api/dataValueSets").mock(
        return_value=httpx.Response(200, json={"dataValues": []})
    )

    await service.get_data_values(profile, data_set="lyLU2wR22tC", org_unit="ou1", last_updated="7d")

    params = route.calls.last.request.url.params
    assert params["lastUpdatedDuration"] == "7d"
    assert "lastUpdated" not in params


@respx.mock
async def test_get_data_values_truncates_with_limit(profile: Profile) -> None:
    """`limit=N` truncates the parsed `dataValues` list client-side."""
    _mock_preamble()
    payload = {
        "dataValues": [
            {"dataElement": "de1", "period": "202403", "orgUnit": "ou1", "value": "1"},
            {"dataElement": "de2", "period": "202403", "orgUnit": "ou1", "value": "2"},
            {"dataElement": "de3", "period": "202403", "orgUnit": "ou1", "value": "3"},
        ],
    }
    respx.get("https://dhis2.example/api/dataValueSets").mock(return_value=httpx.Response(200, json=payload))

    envelope = await service.get_data_values(profile, limit=2)

    assert envelope.dataValues is not None
    assert len(envelope.dataValues) == 2


@respx.mock
async def test_push_data_values_sends_payload_and_params(profile: Profile) -> None:
    """`push_data_values` POSTs the right body + applies dryRun / importStrategy params."""
    _mock_preamble()
    route = respx.post("https://dhis2.example/api/dataValueSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "httpStatusCode": 200,
                "response": {"status": "OK", "imported": 2, "updated": 0, "ignored": 0, "deleted": 0},
            },
        ),
    )

    response = await service.push_data_values(
        profile,
        data_values=[
            DataValue.model_validate({"dataElement": "de1", "period": "202403", "orgUnit": "ou1", "value": "1"}),
            DataValue.model_validate({"dataElement": "de2", "period": "202403", "orgUnit": "ou1", "value": "2"}),
        ],
        data_set="lyLU2wR22tC",
        dry_run=True,
        import_strategy="CREATE",
    )

    assert response.status == "OK"
    request = route.calls.last.request
    assert request.url.params["dryRun"] == "true"
    assert request.url.params["importStrategy"] == "CREATE"
    body = json.loads(request.read())
    assert body["dataSet"] == "lyLU2wR22tC"
    assert body["dataValues"] == [
        {"dataElement": "de1", "period": "202403", "orgUnit": "ou1", "value": "1"},
        {"dataElement": "de2", "period": "202403", "orgUnit": "ou1", "value": "2"},
    ]


@respx.mock
async def test_set_data_value_uses_query_params(profile: Profile) -> None:
    """`set_data_value` posts to /api/dataValues with the value carried as query params (DHIS2 quirk)."""
    _mock_preamble()
    route = respx.post("https://dhis2.example/api/dataValues").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.set_data_value(
        profile,
        data_element="fbfJHSPpUQD",
        period="202403",
        org_unit="ImspTQPwCqd",
        value="42",
        comment="entered manually",
    )

    assert response.status == "OK"
    request = route.calls.last.request
    assert request.url.params["de"] == "fbfJHSPpUQD"
    assert request.url.params["pe"] == "202403"
    assert request.url.params["ou"] == "ImspTQPwCqd"
    assert request.url.params["value"] == "42"
    assert request.url.params["comment"] == "entered manually"


@respx.mock
async def test_delete_data_value_threads_optional_combos(profile: Profile) -> None:
    """`delete_data_value` issues DELETE /api/dataValues, forwarding co plus the cc + cp attribute pair."""
    _mock_preamble()
    route = respx.delete("https://dhis2.example/api/dataValues").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.delete_data_value(
        profile,
        data_element="fbfJHSPpUQD",
        period="202403",
        org_unit="ImspTQPwCqd",
        category_option_combo="HllvX50cXC0",
        attribute_combo="bRowv6yZOF2",
        attribute_options=["optA0000001", "optB0000002"],
    )

    assert response.status == "OK"
    request = route.calls.last.request
    assert request.url.params["de"] == "fbfJHSPpUQD"
    assert request.url.params["co"] == "HllvX50cXC0"
    # DHIS2's /api/dataValues addresses the attribute option combo via cc (its
    # CategoryCombo UID) + cp (its option UIDs, ;-joined) — there is no
    # attributeOptionCombo query param (BUGS.md #50).
    assert request.url.params["cc"] == "bRowv6yZOF2"
    assert request.url.params["cp"] == "optA0000001;optB0000002"
    assert "aoc" not in request.url.params
    assert "attributeOptionCombo" not in request.url.params


@respx.mock
async def test_set_data_value_forwards_cc_and_cp_attribute_pair(profile: Profile) -> None:
    """`set_data_value` forwards the attribute option combo as cc + cp, never a bare AOC param."""
    _mock_preamble()
    route = respx.post("https://dhis2.example/api/dataValues").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    await service.set_data_value(
        profile,
        data_element="fbfJHSPpUQD",
        period="202403",
        org_unit="ImspTQPwCqd",
        value="42",
        attribute_combo="bRowv6yZOF2",
        attribute_options=["optA0000001"],
    )

    params = route.calls.last.request.url.params
    assert params["cc"] == "bRowv6yZOF2"
    assert params["cp"] == "optA0000001"


async def test_set_data_value_rejects_half_of_the_attribute_pair(profile: Profile) -> None:
    """A cc without cp (or vice versa) is a caller error — DHIS2 needs both together (BUGS.md #50)."""
    with pytest.raises(ValueError, match="must be provided together"):
        await service.set_data_value(
            profile,
            data_element="fbfJHSPpUQD",
            period="202403",
            org_unit="ImspTQPwCqd",
            value="42",
            attribute_combo="bRowv6yZOF2",
        )
    with pytest.raises(ValueError, match="must be provided together"):
        await service.delete_data_value(
            profile,
            data_element="fbfJHSPpUQD",
            period="202403",
            org_unit="ImspTQPwCqd",
            attribute_options=["optA0000001"],
        )


@respx.mock
async def test_set_data_value_followup_puts_typed_body(profile: Profile) -> None:
    """`set_data_value_followup` PUTs the follow-up flag (empty 200) and returns a typed summary."""
    _mock_preamble()
    route = respx.put("https://dhis2.example/api/dataValues/followup").mock(return_value=httpx.Response(200))

    result = await service.set_data_value_followup(
        profile,
        data_element="fbfJHSPpUQD",
        period="202403",
        org_unit="ImspTQPwCqd",
        followup=True,
        category_option_combo="HllvX50cXC0",
    )

    assert result.count == 1
    assert result.followup is True
    body = json.loads(route.calls.last.request.read())
    assert body["dataElement"] == "fbfJHSPpUQD"
    assert body["period"] == "202403"
    assert body["orgUnit"] == "ImspTQPwCqd"
    assert body["followup"] is True
    assert body["categoryOptionCombo"] == "HllvX50cXC0"
