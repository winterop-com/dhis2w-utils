"""Unit tests for the `user` plugin — service wiring + CLI integration."""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.user import service
from dhis2w_core.v42.plugins.user.service import UserInvite, UserNotFoundError


@pytest.fixture
def basic_profile() -> Profile:
    return Profile(base_url="https://dhis2.example", auth="basic", username="admin", password="district")


def _stub_connect_routes() -> None:
    """Mock the probes the client runs on first connect."""
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))


@respx.mock
async def test_get_by_uid_skips_resolver(basic_profile: Profile) -> None:
    """An 11-char UID hits /api/users/{uid} directly — no filter lookup."""
    _stub_connect_routes()
    route = respx.get("https://dhis2.example/api/users/abcDEFghiJK").mock(
        return_value=httpx.Response(200, json={"id": "abcDEFghiJK", "username": "alice"}),
    )
    user = await service.get_user(basic_profile, "abcDEFghiJK")
    assert user.id == "abcDEFghiJK"
    assert route.called


@respx.mock
async def test_get_by_username_resolves_via_filter(basic_profile: Profile) -> None:
    """A non-UID input resolves through /api/users?filter=username:eq:... first."""
    _stub_connect_routes()
    respx.get("https://dhis2.example/api/users", params={"filter": "username:eq:alice"}).mock(
        return_value=httpx.Response(200, json={"users": [{"id": "abcDEFghiJK"}]}),
    )
    respx.get("https://dhis2.example/api/users/abcDEFghiJK").mock(
        return_value=httpx.Response(200, json={"id": "abcDEFghiJK", "username": "alice"}),
    )
    user = await service.get_user(basic_profile, "alice")
    assert user.id == "abcDEFghiJK"


@respx.mock
async def test_get_by_username_raises_user_not_found(basic_profile: Profile) -> None:
    """Resolver returns `UserNotFoundError` on empty result; CLI renders that clean."""
    _stub_connect_routes()
    respx.get("https://dhis2.example/api/users").mock(
        return_value=httpx.Response(200, json={"users": []}),
    )
    with pytest.raises(UserNotFoundError):
        await service.get_user(basic_profile, "doesnotexist")


@respx.mock
async def test_invite_posts_to_users_invite(basic_profile: Profile) -> None:
    """invite_user POSTs to /api/users/invite with the typed payload."""
    _stub_connect_routes()
    post_route = respx.post("https://dhis2.example/api/users/invite").mock(
        return_value=httpx.Response(
            200,
            json={
                "httpStatus": "OK",
                "httpStatusCode": 200,
                "status": "OK",
                "response": {"uid": "newUserUID1", "klass": "org.hisp.dhis.user.User"},
            },
        ),
    )
    invite = UserInvite(
        email="alice@example.com",
        firstName="Alice",
        surname="Example",
        username="alice",
        userRoles=[{"id": "roleUID12345"}],
        organisationUnits=[{"id": "ouUID1234567"}],
    )
    envelope = await service.invite_user(basic_profile, invite)
    assert envelope.created_uid == "newUserUID1"
    assert post_route.called
    body = post_route.calls.last.request.content
    assert b'"email":"alice@example.com"' in body
    assert b'"username":"alice"' in body


@respx.mock
async def test_reset_password_posts_to_reset_endpoint(basic_profile: Profile) -> None:
    """reset_password hits POST /api/users/{uid}/reset and returns the envelope."""
    _stub_connect_routes()
    route = respx.post("https://dhis2.example/api/users/abcDEFghiJK/reset").mock(
        return_value=httpx.Response(
            200,
            json={"httpStatus": "OK", "httpStatusCode": 200, "status": "OK"},
        ),
    )
    envelope = await service.reset_password(basic_profile, "abcDEFghiJK")
    assert envelope.status == "OK"
    assert route.called


@respx.mock
async def test_reinvite_posts_to_invite_endpoint(basic_profile: Profile) -> None:
    """reinvite_user hits POST /api/users/{uid}/invite."""
    _stub_connect_routes()
    route = respx.post("https://dhis2.example/api/users/abcDEFghiJK/invite").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    envelope = await service.reinvite_user(basic_profile, "abcDEFghiJK")
    assert envelope.status == "OK"
    assert route.called


def test_plugin_registers_on_root_cli() -> None:
    """Plugin discovery picks up `user` and mounts it under `dhis2 user`."""
    from dhis2w_cli.main import build_app  # imported lazily to avoid circular plugin-import noise
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(build_app(), ["user", "--help"])
    assert result.exit_code == 0
    assert "DHIS2 user administration" in result.output
    # Confirm each verb is listed.
    for verb in ("list", "get", "invite", "reinvite", "reset-password"):
        assert verb in result.output
