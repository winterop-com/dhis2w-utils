"""Unit tests for the `user-group` plugin."""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.user_group import service


@pytest.fixture
def basic_profile() -> Profile:
    return Profile(base_url="https://dhis2.example", auth="basic", username="admin", password="district")


def _stub_connect_routes() -> None:
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))


@respx.mock
async def test_add_member_hits_dedicated_endpoint(basic_profile: Profile) -> None:
    """DHIS2 v42 names the userGroup member collection `users`, not `members`."""
    _stub_connect_routes()
    route = respx.post("https://dhis2.example/api/userGroups/grpUID_12345/users/userUID_567").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    envelope = await service.add_member(basic_profile, "grpUID_12345", "userUID_567")
    assert envelope.status == "OK"
    assert route.called


@respx.mock
async def test_remove_member_uses_delete(basic_profile: Profile) -> None:
    """Remove member uses delete."""
    _stub_connect_routes()
    route = respx.delete("https://dhis2.example/api/userGroups/grpUID_12345/users/userUID_567").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    await service.remove_member(basic_profile, "grpUID_12345", "userUID_567")
    assert route.called


@respx.mock
async def test_apply_group_sharing_routes_to_sharing_endpoint(basic_profile: Profile) -> None:
    """Confirm the user-group sharing call lands on /api/sharing?type=userGroup."""
    _stub_connect_routes()
    route = respx.post(
        "https://dhis2.example/api/sharing",
        params={"type": "userGroup", "id": "grpUID_12345"},
    ).mock(return_value=httpx.Response(200, json={"status": "OK"}))
    from dhis2w_client import SharingBuilder

    envelope = await service.apply_group_sharing(
        basic_profile,
        "grpUID_12345",
        SharingBuilder(owner_user_id="adminUID_12"),
    )
    assert envelope.status == "OK"
    assert route.called


def test_cli_mounted_under_user() -> None:
    """CLI is mounted under the user domain (`dhis2 user group`)."""
    from dhis2w_cli.main import build_app
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(build_app(), ["user", "group", "--help"])
    assert result.exit_code == 0
    assert "Manage DHIS2 user groups" in result.output
