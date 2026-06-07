"""Unit tests for the `user-role` plugin."""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.user_role import service


@pytest.fixture
def basic_profile() -> Profile:
    return Profile(base_url="https://dhis2.example", auth="basic", username="admin", password="district")


def _stub_connect_routes() -> None:
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))


@respx.mock
async def test_add_user_hits_role_users_endpoint(basic_profile: Profile) -> None:
    """Add user hits role users endpoint."""
    _stub_connect_routes()
    route = respx.post("https://dhis2.example/api/userRoles/rolUID_12345/users/userUID_567").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    await service.add_user(basic_profile, "rolUID_12345", "userUID_567")
    assert route.called


@respx.mock
async def test_remove_user_uses_delete(basic_profile: Profile) -> None:
    """Remove user uses delete."""
    _stub_connect_routes()
    route = respx.delete("https://dhis2.example/api/userRoles/rolUID_12345/users/userUID_567").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    await service.remove_user(basic_profile, "rolUID_12345", "userUID_567")
    assert route.called


@respx.mock
async def test_list_authorities_returns_sorted(basic_profile: Profile) -> None:
    """List authorities returns sorted."""
    _stub_connect_routes()
    respx.get("https://dhis2.example/api/userRoles/rolUID_12345").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "rolUID_12345",
                "name": "Superuser",
                "authorities": ["F_METADATA_EXPORT", "ALL", "F_USER_VIEW"],
            },
        ),
    )
    auths = await service.list_authorities(basic_profile, "rolUID_12345")
    assert auths == ["ALL", "F_METADATA_EXPORT", "F_USER_VIEW"]


def test_cli_mounted_under_user() -> None:
    """CLI is mounted under the user domain (`dhis2 user role`)."""
    from dhis2w_cli.main import build_app
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(build_app(), ["user", "role", "--help"])
    assert result.exit_code == 0
    assert "Manage DHIS2 user roles" in result.output
