"""Per-version parity for the `user_role` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/user/test_user_role_plugin.py` routes + assertions, but resolves the service
per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted, not just
smoke-imported. The three service trees are byte-identical copies (only the import version differs), so the
assertions are the same on every tree. Mocked (respx); no live stack.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_list_user_roles_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_user_roles` lists /api/userRoles into typed models, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_role")
    route = respx.get(f"{_HOST}/api/userRoles").mock(
        return_value=httpx.Response(
            200,
            json={
                "userRoles": [
                    {"id": "rolUID_12345", "name": "Superuser"},
                    {"id": "rolUID_67890", "name": "Data entry"},
                ]
            },
        ),
    )

    roles = await service.list_user_roles(resolve_profile("probe"))

    assert [role.id for role in roles] == ["rolUID_12345", "rolUID_67890"]
    assert route.called


@respx.mock
async def test_get_user_role_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_user_role` fetches one role by UID, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_role")
    route = respx.get(f"{_HOST}/api/userRoles/rolUID_12345").mock(
        return_value=httpx.Response(200, json={"id": "rolUID_12345", "name": "Superuser"}),
    )

    role = await service.get_user_role(resolve_profile("probe"), "rolUID_12345")

    assert role.id == "rolUID_12345"
    assert role.name == "Superuser"
    assert route.called


@respx.mock
async def test_list_authorities_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_authorities` unwraps + sorts a role's authorities, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_role")
    route = respx.get(f"{_HOST}/api/userRoles/rolUID_12345").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "rolUID_12345",
                "name": "Superuser",
                "authorities": ["F_METADATA_EXPORT", "ALL", "F_USER_VIEW"],
            },
        ),
    )

    auths = await service.list_authorities(resolve_profile("probe"), "rolUID_12345")

    assert auths == ["ALL", "F_METADATA_EXPORT", "F_USER_VIEW"]
    assert route.calls.last.request.url.params["fields"] == "id,name,authorities"


@respx.mock
async def test_add_user_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`add_user` POSTs to /api/userRoles/{role}/users/{user}, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_role")
    route = respx.post(f"{_HOST}/api/userRoles/rolUID_12345/users/userUID_567").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.add_user(resolve_profile("probe"), "rolUID_12345", "userUID_567")

    assert response.status == "OK"
    assert route.called


@respx.mock
async def test_remove_user_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_user` DELETEs /api/userRoles/{role}/users/{user}, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("user_role")
    route = respx.delete(f"{_HOST}/api/userRoles/rolUID_12345/users/userUID_567").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.remove_user(resolve_profile("probe"), "rolUID_12345", "userUID_567")

    assert response.status == "OK"
    assert route.called
