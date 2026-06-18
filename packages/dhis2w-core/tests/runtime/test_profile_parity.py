"""Per-version parity for the `profile` plugin service — exercise the HTTP-touching functions on all trees.

The `profile` service is mostly local profile management (read/write profiles.toml, redact secrets,
OIDC discovery) and most of its public functions never open a DHIS2 client. The two that do are
`verify_profile` and `verify_all_profiles`, which build a client from the profile and probe
`/api/system/info` + `/api/me`. Those are resolved per `core_version` (v41/v42/v43) so the v41/v43
service code is actually executed and counted, not just smoke-imported. A purely-local call
(`discover_oidc_profile`, mocked OIDC discovery) is included so the local branch is also walked on
every tree. The three service trees are byte-identical copies (only the import version differs), so the
assertions are the same on every tree. Mocked (respx); no live stack.

Covered (HTTP):     verify_profile, verify_all_profiles
Covered (local):    discover_oidc_profile (mocked /.well-known discovery)
Purely-local/skipped (covered by tests/profile/* and non-HTTP):
    list_profiles, show_profile, add_profile, remove_profile, rename_profile, set_default_profile
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import respx

_HOST = "https://dhis2.example"


@respx.mock
async def test_verify_profile_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`verify_profile` probes /api/system/info + /api/me and reports ok=True, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("profile")
    me_route = respx.get(f"{_HOST}/api/me").mock(
        return_value=httpx.Response(200, json={"id": "usr01234567", "username": "admin"}),
    )

    result = await service.verify_profile("probe")

    assert result.ok
    assert result.name == "probe"
    assert result.base_url == _HOST
    assert result.auth == "basic"
    assert result.username == "admin"
    assert me_route.called


@respx.mock
async def test_verify_all_profiles_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`verify_all_profiles` returns one ok=True result per known profile, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("profile")
    respx.get(f"{_HOST}/api/me").mock(
        return_value=httpx.Response(200, json={"id": "usr01234567", "username": "admin"}),
    )

    results = await service.verify_all_profiles()

    assert [r.name for r in results] == ["probe"]
    assert results[0].ok
    assert results[0].username == "admin"


@respx.mock
async def test_discover_oidc_profile_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`discover_oidc_profile` builds an oauth2 Profile from /.well-known discovery, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("profile")
    respx.get(f"{_HOST}/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": _HOST,
                "authorization_endpoint": f"{_HOST}/oauth2/authorize",
                "token_endpoint": f"{_HOST}/oauth2/token",
                "jwks_uri": f"{_HOST}/oauth2/jwks",
                "scopes_supported": ["openid", "profile"],
            },
        ),
    )

    discovered = await service.discover_oidc_profile(_HOST, client_id="my-client", client_secret="my-secret")

    assert discovered.issuer == _HOST
    assert discovered.profile.auth == "oauth2"
    assert discovered.profile.base_url == _HOST
    assert discovered.profile.client_id == "my-client"
    assert discovered.profile.client_secret == "my-secret"
