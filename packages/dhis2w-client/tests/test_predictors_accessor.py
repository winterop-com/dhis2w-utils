"""Unit tests for `PredictorsAccessor` (CRUD) + `PredictorGroupsAccessor` — respx-mocked.

The existing `run_all` / `run_one` / `run_group` run-path tests still live
in `test_validation_accessor.py`-adjacent coverage; this file focuses on
the new authoring verbs.
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import Any

import httpx
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


# ---- PredictorsAccessor CRUD --------------------------------------------


@respx.mock
async def test_list_all_filters_by_period_type(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """List all filters by period type."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/predictors").mock(
        return_value=httpx.Response(
            200,
            json={"predictors": [{"id": "PRD00000001", "name": "BCG avg", "periodType": "Monthly"}]},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.predictors.list_all(period_type="Monthly")
    finally:
        await client.close()
    assert route.calls.last.request.url.params["filter"] == "periodType:eq:Monthly"
    assert [p.id for p in rows] == ["PRD00000001"]


@respx.mock
async def test_create_wraps_generator_and_output_refs(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Create wraps generator and output refs."""
    mock_system_info(server_version)
    post = respx.post("https://dhis2.example/api/predictors").mock(
        return_value=httpx.Response(201, json={"response": {"uid": "PRD_NEW0001"}}),
    )
    respx.get("https://dhis2.example/api/predictors/PRD_NEW0001").mock(
        return_value=httpx.Response(
            200,
            json={"id": "PRD_NEW0001", "name": "BCG 3m avg", "periodType": "Monthly"},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        predictor = await client.predictors.create(
            name="BCG 3m avg",
            short_name="BCG3m",
            expression="#{deBCG000001}",
            output_data_element_uid="deOutput0001",
            sequential_sample_count=3,
            organisation_unit_level_uids=["ouLvlFac001"],
        )
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(post.calls.last.request.read())
    assert body["output"] == {"id": "deOutput0001"}
    assert body["generator"]["expression"] == "#{deBCG000001}"
    assert body["generator"]["missingValueStrategy"] == "SKIP_IF_ALL_VALUES_MISSING"
    assert body["sequentialSampleCount"] == 3
    assert body["organisationUnitLevels"] == [{"id": "ouLvlFac001"}]
    assert predictor.id == "PRD_NEW0001"


@respx.mock
async def test_delete_routes_to_predictors_uid(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Delete routes to predictors uid."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/predictors/PRD_X").mock(return_value=httpx.Response(204))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.predictors.delete("PRD_X")
    finally:
        await client.close()
    assert route.called


# ---- PredictorGroupsAccessor --------------------------------------------


@respx.mock
async def test_group_list_all_disables_paging(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Group list all disables paging."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/predictorGroups").mock(
        return_value=httpx.Response(200, json={"predictorGroups": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.predictor_groups.list_all()
    finally:
        await client.close()
    assert route.calls.last.request.url.params["paging"] == "false"


@respx.mock
async def test_group_add_members_posts_per_item_shortcut(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Group add members posts per item shortcut."""
    mock_system_info(server_version)
    a = respx.post("https://dhis2.example/api/predictorGroups/GRP_X/predictors/PRD_A").mock(
        return_value=httpx.Response(204),
    )
    b = respx.post("https://dhis2.example/api/predictorGroups/GRP_X/predictors/PRD_B").mock(
        return_value=httpx.Response(204),
    )
    respx.get("https://dhis2.example/api/predictorGroups/GRP_X").mock(
        return_value=httpx.Response(200, json={"id": "GRP_X", "name": "BCG predictors"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.predictor_groups.add_members("GRP_X", predictor_uids=["PRD_A", "PRD_B"])
    finally:
        await client.close()
    assert a.called and b.called


@respx.mock
async def test_group_remove_members_deletes_per_item_shortcut(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Group remove members deletes per item shortcut."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/predictorGroups/GRP_X/predictors/PRD_A").mock(
        return_value=httpx.Response(204),
    )
    respx.get("https://dhis2.example/api/predictorGroups/GRP_X").mock(
        return_value=httpx.Response(200, json={"id": "GRP_X", "name": "BCG predictors"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.predictor_groups.remove_members("GRP_X", predictor_uids=["PRD_A"])
    finally:
        await client.close()
    assert route.called


async def test_accessors_bound_on_client() -> None:
    """Accessors bound on client."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        assert client.predictors is not None
        assert client.predictor_groups is not None
    finally:
        await client.close()
