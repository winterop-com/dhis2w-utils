"""Per-version parity for the `user` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/user/test_user_plugin.py` routes + assertions, but resolves the service
per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted, not
just smoke-imported. The three service trees are byte-identical copies (only the import version
differs), so the assertions are the same on every tree. Mocked (respx); no live stack.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_list_users_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_users` unwraps the `{users: [...]}` envelope into typed User models, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("user")
    route = respx.get(f"{_HOST}/api/users").mock(
        return_value=httpx.Response(
            200,
            json={"users": [{"id": "abcDEFghiJK", "username": "alice"}, {"id": "zzzYYYwwwVV", "username": "bob"}]},
        ),
    )

    users = await service.list_users(resolve_profile("probe"), filters=["disabled:eq:false"])

    assert [user.id for user in users] == ["abcDEFghiJK", "zzzYYYwwwVV"]
    assert route.calls.last.request.url.params["filter"] == "disabled:eq:false"


@respx.mock
async def test_get_user_by_uid_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_user` fetches /api/users/{uid} directly when given an 11-char UID, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("user")
    route = respx.get(f"{_HOST}/api/users/abcDEFghiJK").mock(
        return_value=httpx.Response(200, json={"id": "abcDEFghiJK", "username": "alice"}),
    )

    user = await service.get_user(resolve_profile("probe"), "abcDEFghiJK")

    assert user.id == "abcDEFghiJK"
    assert route.called


@respx.mock
async def test_invite_user_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`invite_user` POSTs the typed payload to /api/users/invite and surfaces the new UID, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("user")
    route = respx.post(f"{_HOST}/api/users/invite").mock(
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

    invite = service.UserInvite(
        email="alice@example.com",
        firstName="Alice",
        surname="Example",
        username="alice",
        userRoles=[{"id": "roleUID12345"}],
        organisationUnits=[{"id": "ouUID1234567"}],
    )
    envelope = await service.invite_user(resolve_profile("probe"), invite)

    assert envelope.created_uid == "newUserUID1"
    body = route.calls.last.request.content
    assert b'"email":"alice@example.com"' in body
    assert b'"username":"alice"' in body


@respx.mock
async def test_reinvite_user_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`reinvite_user` hits POST /api/users/{uid}/invite, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("user")
    route = respx.post(f"{_HOST}/api/users/abcDEFghiJK/invite").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    envelope = await service.reinvite_user(resolve_profile("probe"), "abcDEFghiJK")

    assert envelope.status == "OK"
    assert route.called


@respx.mock
async def test_reset_password_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`reset_password` hits POST /api/users/{uid}/reset and returns the envelope, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("user")
    route = respx.post(f"{_HOST}/api/users/abcDEFghiJK/reset").mock(
        return_value=httpx.Response(200, json={"httpStatus": "OK", "httpStatusCode": 200, "status": "OK"}),
    )

    envelope = await service.reset_password(resolve_profile("probe"), "abcDEFghiJK")

    assert envelope.status == "OK"
    assert route.called


@respx.mock
async def test_current_user_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`current_user` parses /api/me and resolves UID-only programs to refs, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("user")
    me_route = respx.get(f"{_HOST}/api/me").mock(
        return_value=httpx.Response(
            200,
            json={"id": "abcDEFghiJK", "username": "admin", "programs": ["prg01234567"]},
        ),
    )
    programs_route = respx.get(f"{_HOST}/api/programs").mock(
        return_value=httpx.Response(200, json={"programs": [{"id": "prg01234567", "displayName": "Antenatal care"}]}),
    )

    me = await service.current_user(resolve_profile("probe"))

    assert me.id == "abcDEFghiJK"
    assert me_route.called
    assert programs_route.called
    assert me.programs is not None
    assert me.programs[0].id == "prg01234567"
