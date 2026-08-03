"""Unit tests for `ProgramRulesAccessor` — respx-mocked, no live stack."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


# ---- list_all --------------------------------------------------------------


@respx.mock
async def test_list_all_orders_by_priority_and_scopes_to_program(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`list_all(program_uid)` scopes to one program + sorts by priority ascending."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/programRules").mock(
        return_value=httpx.Response(
            200,
            json={
                "programRules": [
                    {"id": "pr1", "name": "First", "priority": 1, "condition": "true"},
                    {"id": "pr2", "name": "Second", "priority": 2, "condition": "false"},
                ]
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rules = await client.program_rules.list_all(program_uid="PROGRAM_UID")
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["filter"] == "program.id:eq:PROGRAM_UID"
    assert params["order"] == "priority:asc"
    assert [r.name for r in rules] == ["First", "Second"]


@respx.mock
async def test_list_all_without_program_uid_skips_filter(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """No program_uid → no filter param emitted; list everything."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/programRules").mock(
        return_value=httpx.Response(200, json={"programRules": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.program_rules.list_all()
    finally:
        await client.close()
    assert "filter" not in route.calls.last.request.url.params


# ---- get_rule ----------------------------------------------------------------


@respx.mock
async def test_get_rule_returns_typed_model(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Get rule returns typed model."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programRules/pr1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "pr1",
                "name": "Probe",
                "priority": 1,
                "condition": "#{V_X} > 0",
                "programRuleActions": [
                    {
                        "id": "pra1",
                        "programRuleActionType": "SHOWWARNING",
                        "content": "hello",
                    }
                ],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rule = await client.program_rules.get_rule("pr1")
    finally:
        await client.close()
    assert rule.id == "pr1"
    assert rule.priority == 1
    assert rule.programRuleActions is not None
    assert len(rule.programRuleActions) == 1


# ---- variables_for + the `fields=*` source-type quirk -------------------------


@respx.mock
async def test_variables_for_names_source_type_field_explicitly(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`fields=*` omits `programRuleVariableSourceType`, so the accessor names it."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/programRuleVariables").mock(
        return_value=httpx.Response(
            200,
            json={
                "programRuleVariables": [
                    {
                        "id": "v1",
                        "name": "V_X",
                        "programRuleVariableSourceType": "DATAELEMENT_CURRENT_EVENT",
                        "dataElement": {"id": "de1"},
                    }
                ]
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        vars_ = await client.program_rules.variables_for("PROGRAM_UID")
    finally:
        await client.close()
    assert len(vars_) == 1
    fields = route.calls.last.request.url.params["fields"]
    assert "programRuleVariableSourceType" in fields


# ---- actions_for (uses rule→actions forward ref; BUGS.md #22c) ---------------


@respx.mock
async def test_actions_for_uses_rule_forward_reference(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """BUGS.md #22c — action→rule back-ref is unreliable; fetch rule + unwrap `programRuleActions`."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/programRules/pr1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "pr1",
                "name": "Probe",
                "programRuleActions": [
                    {"id": "pra1", "programRuleActionType": "SHOWWARNING", "content": "warn"},
                    {"id": "pra2", "programRuleActionType": "SHOWERROR", "content": "err"},
                ],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        actions = await client.program_rules.actions_for("pr1")
    finally:
        await client.close()
    # Only one HTTP call — no attempt at the broken `/api/programRuleActions?filter=programRule.id` path.
    assert route.call_count == 1
    assert [a.id for a in actions] == ["pra1", "pra2"]


# ---- where_de_is_used (walks all rules, filters client-side) ----------------


@respx.mock
async def test_where_de_is_used_matches_rules_touching_a_de(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Where de is used matches rules touching a de."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programRules").mock(
        return_value=httpx.Response(
            200,
            json={
                "programRules": [
                    {
                        "id": "pr1",
                        "name": "Touches DEancVisit1",
                        "programRuleActions": [
                            {"id": "a1", "dataElement": {"id": "DEancVisit1"}},
                        ],
                    },
                    {
                        "id": "pr2",
                        "name": "Touches TEA",
                        "programRuleActions": [
                            {"id": "a2", "attribute": {"id": "TEAabc"}},
                        ],
                    },
                    {
                        "id": "pr3",
                        "name": "Also DEancVisit1",
                        "programRuleActions": [
                            {"id": "a3", "dataElement": {"id": "DEancVisit1"}},
                        ],
                    },
                ]
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        matches = await client.program_rules.where_de_is_used("DEancVisit1")
    finally:
        await client.close()
    assert [r.id for r in matches] == ["pr1", "pr3"]


# ---- validate_expression delegates to client.validation ---------------------


@respx.mock
async def test_validate_expression_delegates_to_describe_expression(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`validate_expression` round-trips through `/api/expressions/description` via client.validation."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/expressions/description").mock(
        return_value=httpx.Response(200, json={"status": "OK", "message": "Valid", "description": "#{V_X} > 0"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.program_rules.validate_expression("#{V_X} > 0", context="generic")
    finally:
        await client.close()
    assert result.valid is True
    assert result.status == "OK"


async def test_accessor_is_bound_on_client() -> None:
    """`client.program_rules` exists + exposes the expected methods."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        for attr in (
            "list_all",
            "get_rule",
            "variables_for",
            "actions_for",
            "where_de_is_used",
            "validate_expression",
        ):
            assert hasattr(client.program_rules, attr), f"missing {attr}"
    finally:
        await client.close()


# ---- smoke: list-rules raw-shape tolerance ---------------------------------


@respx.mock
async def test_list_all_tolerates_non_list_payload(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """DHIS2 returns `programRules: null` on edge-cases; handler returns empty list instead of crashing."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programRules").mock(
        return_value=httpx.Response(200, json={"programRules": None}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.program_rules.list_all()
    finally:
        await client.close()
    assert result == []


# pytest-asyncio auto mode takes care of `async def` test discovery.
# No need for explicit @pytest.mark.asyncio decorators.
_ = pytest  # keep the import honest
