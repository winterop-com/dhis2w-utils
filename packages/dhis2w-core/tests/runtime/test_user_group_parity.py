"""Per-version parity for the `user_group` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/user/test_user_group_plugin.py` routes + assertions, but resolves the
service per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted,
not just smoke-imported. The three service trees are byte-identical copies (only the import version
differs), so the assertions are the same on every tree. Mocked (respx); no live stack.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_client.v42 import SharingBuilder
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_list_user_groups_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_user_groups` unwraps the `{userGroups: [...]}` envelope, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_group")
    route = respx.get(f"{_HOST}/api/userGroups").mock(
        return_value=httpx.Response(
            200,
            json={"userGroups": [{"id": "grpUID_12345", "name": "Admins"}, {"id": "grpUID_67890", "name": "Viewers"}]},
        ),
    )

    result = await service.list_user_groups(resolve_profile("probe"))

    assert [group.id for group in result] == ["grpUID_12345", "grpUID_67890"]
    assert route.called


@respx.mock
async def test_get_user_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_user_group` fetches one group by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_group")
    route = respx.get(f"{_HOST}/api/userGroups/grpUID_12345").mock(
        return_value=httpx.Response(200, json={"id": "grpUID_12345", "name": "Admins"}),
    )

    result = await service.get_user_group(resolve_profile("probe"), "grpUID_12345")

    assert result.id == "grpUID_12345"
    assert route.called


@respx.mock
async def test_create_user_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_user_group` POSTs the new group and returns the import-summary, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("user_group")
    route = respx.post(f"{_HOST}/api/userGroups").mock(
        return_value=httpx.Response(
            201,
            json={"status": "OK", "httpStatusCode": 201, "response": {"uid": "grpUID_12345"}},
        ),
    )

    response = await service.create_user_group(resolve_profile("probe"), name="Admins", code="ADM")

    assert response.status == "OK"
    assert b'"name":"Admins"' in route.calls.last.request.read()


@respx.mock
async def test_delete_user_group_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_user_group` DELETEs /api/userGroups/{uid}, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_group")
    route = respx.delete(f"{_HOST}/api/userGroups/grpUID_12345").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    await service.delete_user_group(resolve_profile("probe"), "grpUID_12345")

    assert route.called


@respx.mock
async def test_add_member_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_member` POSTs /api/userGroups/{group}/users/{user}, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_group")
    route = respx.post(f"{_HOST}/api/userGroups/grpUID_12345/users/userUID_567").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    envelope = await service.add_member(resolve_profile("probe"), "grpUID_12345", "userUID_567")

    assert envelope.status == "OK"
    assert route.called


@respx.mock
async def test_remove_member_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_member` DELETEs /api/userGroups/{group}/users/{user}, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_group")
    route = respx.delete(f"{_HOST}/api/userGroups/grpUID_12345/users/userUID_567").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    envelope = await service.remove_member(resolve_profile("probe"), "grpUID_12345", "userUID_567")

    assert envelope.status == "OK"
    assert route.called


@respx.mock
async def test_get_group_sharing_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_group_sharing` fetches the sharing block via /api/sharing, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_group")
    route = respx.get(f"{_HOST}/api/sharing", params={"type": "userGroup", "id": "grpUID_12345"}).mock(
        return_value=httpx.Response(200, json={"object": {"publicAccess": "rw------"}}),
    )

    sharing = await service.get_group_sharing(resolve_profile("probe"), "grpUID_12345")

    assert sharing.publicAccess == "rw------"
    assert route.called


@respx.mock
async def test_apply_group_sharing_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`apply_group_sharing` POSTs to /api/sharing?type=userGroup, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_group")
    route = respx.post(f"{_HOST}/api/sharing", params={"type": "userGroup", "id": "grpUID_12345"}).mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )

    envelope = await service.apply_group_sharing(
        resolve_profile("probe"),
        "grpUID_12345",
        SharingBuilder(owner_user_id="adminUID_12"),
    )

    assert envelope.status == "OK"
    assert route.called
