"""Read-only mode for the full dhis2-mcp server (env DHIS2_MCP_READONLY)."""

from __future__ import annotations

import pytest
from dhis2w_mcp.readonly import is_read_tool, readonly_enabled
from dhis2w_mcp.server import build_server
from fastmcp import Client

# Tools that must classify as WRITE even though their trailing token looks read-ish: the mutation verb
# (`add`/`remove`/`set`) sits in verb position and the name trails in a noun-like `members`/`status`.
# These are the exact names the old trailing-verb heuristic misfiled as reads.
_WRITE_WITH_READ_LOOKING_TAIL = (
    "messaging_set_status",
    "metadata_category_option_group_add_members",
    "metadata_category_option_group_remove_members",
    "metadata_data_element_group_add_members",
    "metadata_data_element_group_remove_members",
    "metadata_indicator_group_add_members",
    "metadata_indicator_group_remove_members",
    "metadata_organisation_unit_group_add_members",
    "metadata_organisation_unit_group_remove_members",
    "metadata_predictor_group_add_members",
    "metadata_predictor_group_remove_members",
    "metadata_program_indicator_group_add_members",
    "metadata_program_indicator_group_remove_members",
    "metadata_validation_rule_group_add_members",
    "metadata_validation_rule_group_remove_members",
)

# Genuine reads whose name contains a `...Set` resource noun (`dataSet`, `optionSet`, `legendSet`,
# `...GroupSet`): the `set` here is a noun, not the mutation verb, so they must stay allowed.
_READ_WITH_SET_NOUN = (
    "metadata_data_set_get",
    "metadata_option_set_get",
    "metadata_option_set_find",
    "metadata_option_set_attribute_get",
    "metadata_option_set_attribute_find",
    "metadata_legend_set_get",
    "metadata_category_option_group_set_get",
    "metadata_data_element_group_set_get",
    "metadata_indicator_group_set_get",
    "metadata_organisation_unit_group_set_get",
)

# List-members reads: trailing `members` with NO write verb — the counterpart the write-verb check
# must NOT steal (unlike `add_members`/`remove_members`).
_READ_GROUP_MEMBERS = (
    "metadata_category_option_group_members",
    "metadata_data_element_group_members",
    "metadata_indicator_group_members",
    "metadata_organisation_unit_group_members",
    "metadata_predictor_group_members",
    "metadata_program_indicator_group_members",
    "metadata_validation_rule_group_members",
)

# A spread of plain reads that the trailing-verb fallback should allow.
_PLAIN_READS = (
    "metadata_count",
    "metadata_list",
    "metadata_search",
    "metadata_data_element_get",
    "system_whoami",
    "system_info",
    "maintenance_task_status",
    "maintenance_dataintegrity_result",
    "data_tracker_outstanding",
)

# A spread of plain writes the trailing-verb check already caught (regression guard on the fallback).
_PLAIN_WRITES = (
    "metadata_data_element_create",
    "metadata_data_set_create",
    "metadata_data_set_delete",
    "metadata_data_set_rename",
    "system_settings_set",
    "system_settings_set_many",
    "data_tracker_push",
    "metadata_import",
    "metadata_merge",
    "metadata_option_set_sync",
    "metadata_organisation_unit_move",
    "user_reset_password",
    "user_invite",
    "maintenance_predictors_run",
)


@pytest.mark.parametrize("name", _WRITE_WITH_READ_LOOKING_TAIL)
def test_write_verb_beats_read_looking_tail(name: str) -> None:
    """add_members / remove_members / set_status are writes despite a read-looking trailing token."""
    assert is_read_tool(name) is False


@pytest.mark.parametrize("name", _READ_WITH_SET_NOUN)
def test_set_noun_stays_read(name: str) -> None:
    """A `...Set` resource noun is not the mutation verb `set`, so these reads stay allowed."""
    assert is_read_tool(name) is True


@pytest.mark.parametrize("name", _READ_GROUP_MEMBERS)
def test_list_members_is_read(name: str) -> None:
    """Listing group members is a genuine read (no write verb, trailing `members`)."""
    assert is_read_tool(name) is True


@pytest.mark.parametrize("name", _PLAIN_READS)
def test_plain_reads_allowed(name: str) -> None:
    """Ordinary get/list/count/search/status/result reads classify read."""
    assert is_read_tool(name) is True


@pytest.mark.parametrize("name", _PLAIN_WRITES)
def test_plain_writes_refused(name: str) -> None:
    """Ordinary create/delete/set/push/import/... writes classify write."""
    assert is_read_tool(name) is False


@pytest.mark.parametrize(
    ("value", "enabled"),
    [("1", True), ("true", True), ("YES", True), ("on", True), ("", False), ("0", False), ("off", False)],
)
def test_readonly_enabled_reads_env(monkeypatch: pytest.MonkeyPatch, value: str, enabled: bool) -> None:
    """readonly_enabled honours the truthy env conventions."""
    monkeypatch.setenv("DHIS2_MCP_READONLY", value)
    assert readonly_enabled() is enabled


# The authoritative read surface: every tool the read-only server may expose, hand-verified against the
# assembled registry. Pinning the exact allowlist makes the "no write leaks" assertion non-circular —
# it does not re-derive expected from actual via the same heuristic under test. A new read tool exposed
# here should be reviewed and added deliberately; a write leaking in fails the subset check below.
_VERIFIED_READ_TOOLS: frozenset[str] = frozenset(
    {
        "analytics_enrollments_query",
        "analytics_events_query",
        "analytics_query",
        "analytics_tracked_entities_query",
        "apps_get",
        "apps_hub_list",
        "apps_hub_url_get",
        "apps_list",
        "customize_show",
        "data_aggregate_get",
        "data_tracker_enrollment_list",
        "data_tracker_event_list",
        "data_tracker_get",
        "data_tracker_list",
        "data_tracker_outstanding",
        "data_tracker_relationship_list",
        "data_tracker_type_list",
        "datastore_get",
        "datastore_list_keys",
        "datastore_list_namespaces",
        "files_documents_get",
        "files_documents_list",
        "files_resources_get",
        "maintenance_dataintegrity_result",
        "maintenance_task_list",
        "maintenance_task_status",
        "maintenance_task_type_list",
        "maintenance_validation_result_list",
        "messaging_get",
        "messaging_list",
        "metadata_attribute_find",
        "metadata_attribute_get",
        "metadata_category_combo_get",
        "metadata_category_get",
        "metadata_category_option_combo_get",
        "metadata_category_option_get",
        "metadata_category_option_group_get",
        "metadata_category_option_group_members",
        "metadata_category_option_group_set_get",
        "metadata_count",
        "metadata_dashboard_get",
        "metadata_data_element_get",
        "metadata_data_element_group_get",
        "metadata_data_element_group_members",
        "metadata_data_element_group_set_get",
        "metadata_data_set_get",
        "metadata_diff",
        "metadata_get",
        "metadata_indicator_get",
        "metadata_indicator_group_get",
        "metadata_indicator_group_members",
        "metadata_indicator_group_set_get",
        "metadata_legend_set_get",
        "metadata_list",
        "metadata_map_get",
        "metadata_option_set_attribute_find",
        "metadata_option_set_attribute_get",
        "metadata_option_set_find",
        "metadata_option_set_get",
        "metadata_organisation_unit_get",
        "metadata_organisation_unit_group_get",
        "metadata_organisation_unit_group_members",
        "metadata_organisation_unit_group_set_get",
        "metadata_organisation_unit_level_get",
        "metadata_organisation_unit_tree",
        "metadata_predictor_get",
        "metadata_predictor_group_get",
        "metadata_predictor_group_members",
        "metadata_program_get",
        "metadata_program_indicator_get",
        "metadata_program_indicator_group_get",
        "metadata_program_indicator_group_members",
        "metadata_program_rule_get",
        "metadata_program_stage_get",
        "metadata_search",
        "metadata_section_get",
        "metadata_sql_view_get",
        "metadata_tracked_entity_attribute_get",
        "metadata_tracked_entity_type_get",
        "metadata_type_list",
        "metadata_usage",
        "metadata_validation_rule_get",
        "metadata_validation_rule_group_get",
        "metadata_validation_rule_group_members",
        "metadata_visualization_get",
        "profile_list",
        "profile_show",
        "profile_verify",
        "route_get",
        "route_list",
        "system_calendar_get",
        "system_info",
        "system_server_info",
        "system_settings_get",
        "system_settings_list",
        "system_whoami",
        "user_get",
        "user_group_get",
        "user_group_list",
        "user_group_sharing_get",
        "user_list",
        "user_role_authority_list",
        "user_role_get",
        "user_role_list",
    }
)


async def test_no_mutating_tool_is_classified_read() -> None:
    """Across the whole assembled registry, every tool is_read_tool allows is a hand-verified read.

    Subset (exposed <= verified reads) is the safety property: no write can slip through, and a newly
    exposed tool that is not on the verified list trips this test for review.
    """
    server = build_server()
    all_tools = await server.list_tools(run_middleware=False)  # every registered tool, guard bypassed
    exposed = {tool.name for tool in all_tools if is_read_tool(tool.name)}
    leaked = exposed - _VERIFIED_READ_TOOLS
    assert not leaked, f"tools classified read but not on the verified read allowlist: {sorted(leaked)}"


async def test_readonly_server_hides_write_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """With DHIS2_MCP_READONLY set, list_tools exposes only verified reads; without it, writes appear."""
    monkeypatch.setenv("DHIS2_MCP_READONLY", "1")
    async with Client(build_server()) as client:
        names = [tool.name for tool in await client.list_tools()]
    assert names, "expected some read tools"
    unexpected = set(names) - _VERIFIED_READ_TOOLS
    assert not unexpected, f"unexpected non-read exposed: {sorted(unexpected)}"
    # The specific bug: mutating group-membership and status tools must never be listed.
    for blocked in _WRITE_WITH_READ_LOOKING_TAIL:
        assert blocked not in names
    # ...while their read siblings stay visible.
    for allowed in _READ_GROUP_MEMBERS:
        assert allowed in names

    monkeypatch.delenv("DHIS2_MCP_READONLY", raising=False)
    async with Client(build_server()) as client:
        open_names = [tool.name for tool in await client.list_tools()]
    assert any(name.endswith("_create") for name in open_names), "writes should be present without read-only mode"


async def test_readonly_call_refuses_write_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hidden write tool is also refused at call time under read-only mode."""
    from fastmcp.exceptions import ToolError

    monkeypatch.setenv("DHIS2_MCP_READONLY", "1")
    async with Client(build_server()) as client:
        with pytest.raises(ToolError, match="read-only mode"):
            await client.call_tool("messaging_set_status", {"uid": "x", "status": "SOLVED"})
