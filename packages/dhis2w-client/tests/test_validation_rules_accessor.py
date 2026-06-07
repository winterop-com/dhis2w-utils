"""Unit tests for `ValidationRulesAccessor` + `ValidationRuleGroupsAccessor` — respx-mocked."""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import Any

import httpx
import respx
from dhis2w_client import BasicAuth, Dhis2Client
from dhis2w_client.generated.v42.enums import Importance, Operator


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


# ---- ValidationRulesAccessor --------------------------------------------


@respx.mock
async def test_list_all_filters_by_period_type(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """List all filters by period type."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/validationRules").mock(
        return_value=httpx.Response(
            200,
            json={
                "validationRules": [
                    {"id": "VR_MONTH01", "name": "BCG gt zero", "periodType": "Monthly", "operator": "greater_than"},
                ],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.validation_rules.list_all(period_type="Monthly", page=2, page_size=25)
    finally:
        await client.close()
    params = route.calls.last.request.url.params
    assert params["filter"] == "periodType:eq:Monthly"
    assert params["page"] == "2"
    assert params["pageSize"] == "25"
    assert [r.id for r in rows] == ["VR_MONTH01"]


@respx.mock
async def test_create_wraps_expression_sides_and_posts(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Create wraps expression sides and posts."""
    mock_system_info(server_version)
    post = respx.post("https://dhis2.example/api/validationRules").mock(
        return_value=httpx.Response(201, json={"response": {"uid": "VR_NEW00001"}}),
    )
    respx.get("https://dhis2.example/api/validationRules/VR_NEW00001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "VR_NEW00001",
                "name": "BCG gt zero",
                "operator": "greater_than",
                "importance": "HIGH",
                "periodType": "Monthly",
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rule = await client.validation_rules.create(
            name="BCG gt zero",
            short_name="BCGgt0",
            left_expression="#{deBCG000001}",
            operator=Operator.GREATER_THAN,
            right_expression="0",
            importance=Importance.HIGH,
            organisation_unit_levels=[4],
        )
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(post.calls.last.request.read())
    assert body["operator"] == "greater_than"
    assert body["importance"] == "HIGH"
    assert body["leftSide"]["expression"] == "#{deBCG000001}"
    assert body["leftSide"]["missingValueStrategy"] == "SKIP_IF_ALL_VALUES_MISSING"
    assert body["leftSide"]["slidingWindow"] is False
    assert body["rightSide"]["expression"] == "0"
    assert body["organisationUnitLevels"] == [4]
    assert rule.id == "VR_NEW00001"


@respx.mock
async def test_delete_routes_to_validation_rules_uid(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Delete routes to validation rules uid."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/validationRules/VR_X").mock(return_value=httpx.Response(204))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.validation_rules.delete("VR_X")
    finally:
        await client.close()
    assert route.called


# ---- ValidationRuleGroupsAccessor --------------------------------------


@respx.mock
async def test_group_list_all_disables_paging(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Group list all disables paging."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/validationRuleGroups").mock(
        return_value=httpx.Response(200, json={"validationRuleGroups": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.validation_rule_groups.list_all()
    finally:
        await client.close()
    assert route.calls.last.request.url.params["paging"] == "false"


@respx.mock
async def test_group_members_filters_by_parent_group(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Group members filters by parent group."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/validationRules").mock(
        return_value=httpx.Response(200, json={"validationRules": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.validation_rule_groups.list_members("GRP_X")
    finally:
        await client.close()
    assert route.calls.last.request.url.params["filter"] == "validationRuleGroups.id:eq:GRP_X"


@respx.mock
async def test_group_add_members_posts_per_item_shortcut(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Group add members posts per item shortcut."""
    mock_system_info(server_version)
    a = respx.post("https://dhis2.example/api/validationRuleGroups/GRP_X/validationRules/VR_A").mock(
        return_value=httpx.Response(204),
    )
    b = respx.post("https://dhis2.example/api/validationRuleGroups/GRP_X/validationRules/VR_B").mock(
        return_value=httpx.Response(204),
    )
    respx.get("https://dhis2.example/api/validationRuleGroups/GRP_X").mock(
        return_value=httpx.Response(200, json={"id": "GRP_X", "name": "BCG rules"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.validation_rule_groups.add_members("GRP_X", validation_rule_uids=["VR_A", "VR_B"])
    finally:
        await client.close()
    assert a.called and b.called


@respx.mock
async def test_group_remove_members_deletes_per_item_shortcut(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Group remove members deletes per item shortcut."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/validationRuleGroups/GRP_X/validationRules/VR_A").mock(
        return_value=httpx.Response(204),
    )
    respx.get("https://dhis2.example/api/validationRuleGroups/GRP_X").mock(
        return_value=httpx.Response(200, json={"id": "GRP_X", "name": "BCG rules"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.validation_rule_groups.remove_members("GRP_X", validation_rule_uids=["VR_A"])
    finally:
        await client.close()
    assert route.called


async def test_accessors_bound_on_client() -> None:
    """Accessors bound on client."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        assert client.validation_rules is not None
        assert client.validation_rule_groups is not None
    finally:
        await client.close()
