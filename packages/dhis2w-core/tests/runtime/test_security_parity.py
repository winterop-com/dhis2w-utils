"""Per-version parity for the `security` plugin service — exercise every public function on all trees.

Mirrors the v42-only CLI tests `tests/security/test_security_settings_cli.py` +
`test_security_authorities_cli.py` at the service layer, but resolves the service per `core_version`
(v41/v42/v43) so the v41/v43 service code is actually executed and counted, not just smoke-imported.
The three service trees are byte-identical copies (only the import version differs), and both endpoints
(`/api/systemSettings`, `/api/me/authorization`) carry the same wire shape across versions, so the
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
async def test_get_security_settings_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_security_settings` parses the security slice of /api/systemSettings, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("security")
    route = respx.get(f"{_HOST}/api/systemSettings").mock(
        return_value=httpx.Response(
            200,
            json={
                "minPasswordLength": 8,
                "maxPasswordLength": 72,
                "credentialsExpires": 0,
                "credentialsExpiresReminderInDays": 28,
                "credentialsExpiryAlert": False,
                "keyAccountRecovery": True,
                "keySelfRegistrationNoRecaptcha": False,
                "keyLockMultipleFailedLogins": False,
                "enforceVerifiedEmail": False,
                "keyAnalysisDisplayProperty": "name",
            },
        ),
    )

    settings = await service.get_security_settings(resolve_profile("probe"))

    assert settings.minPasswordLength == 8
    assert settings.maxPasswordLength == 72
    assert settings.keyAccountRecovery is True
    assert settings.keyLockMultipleFailedLogins is False
    assert route.called


@respx.mock
async def test_get_account_authorities_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_account_authorities` categorises the /api/me/authorization list, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("security")
    route = respx.get(f"{_HOST}/api/me/authorization").mock(
        return_value=httpx.Response(200, json=["F_USER_ADD", "F_SQLVIEW_PUBLIC_ADD", "F_DATAVALUE_ADD"]),
    )

    result = await service.get_account_authorities(resolve_profile("probe"))

    assert result.authorities == sorted(["F_USER_ADD", "F_SQLVIEW_PUBLIC_ADD", "F_DATAVALUE_ADD"])
    assert result.is_superuser is False
    assert [match.key for match in result.categories] == ["user_management", "sql_views"]
    assert result.categories[0].matched == ["F_USER_ADD"]
    assert route.called
