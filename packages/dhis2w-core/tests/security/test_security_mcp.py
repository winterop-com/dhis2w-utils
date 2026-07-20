"""MCP read surface for the `security` plugin: the three cheap read tools, no audit tool.

Builds a FastMCP server from each version tree's `security` plugin and drives it through
FastMCP's in-process Client (CLAUDE.md's mandated MCP test shape), with respx mocking the
DHIS2 endpoints. Asserts the three `security_*` read tools register (and nothing audit /
probe / sharing related does), and that each returns the correct typed model; including
the version tool's EOL / below-floor findings and its single-request, no-external-feed
guarantee.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module

import httpx
import pytest
import respx
from dhis2w_core.plugin import discover_plugins
from dhis2w_core.security_core import releases
from fastmcp import Client, FastMCP

_HOST = "https://dhis2.example"

# `core_version` is the shared conftest fixture that parametrizes a test body across v41/v42/v43.


def _server_for(tree: str) -> FastMCP:
    """Register one version tree's plugins onto a fresh FastMCP server."""
    server: FastMCP = FastMCP("security-mcp-test")
    for plugin in discover_plugins(tree):
        plugin.register_mcp(server)
    return server


@pytest.fixture(autouse=True)
def _clear_release_cache() -> None:
    """Drop the module-level release-feed cache so a leaked feed fetch can't be served from cache."""
    releases._CACHE.clear()


def _structured(result: object) -> dict[str, object]:
    """Normalize a FastMCP tool-call result to its structured-content dict."""
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    data = getattr(result, "data", None)
    if data is not None and hasattr(data, "model_dump"):
        dumped = data.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if isinstance(data, dict):
        return data
    raise AssertionError(f"unexpected FastMCP result shape: {result!r}")


async def test_registers_exactly_three_read_tools_no_audit(core_version: str) -> None:
    """Each tree exposes the three `security_*` read tools and no audit / probe / sharing tool."""
    async with Client(_server_for(core_version)) as client:
        names = {tool.name for tool in await client.list_tools()}
    security = {name for name in names if name.startswith("security_")}
    assert security == {"security_settings", "security_authorities", "security_version"}
    # The long-running surface (audit / report / credential probe / guest / sharing) stays CLI-only:
    # no security_* tool may expose any of it.
    forbidden = {
        name
        for name in security
        if any(token in name for token in ("audit", "report", "probe", "credential", "guest", "sharing"))
    }
    assert not forbidden, f"audit/probe/sharing tools must stay CLI-only, found: {forbidden}"


async def test_read_tools_have_basemodel_returns_and_docstrings(core_version: str) -> None:
    """Every `security_*` tool has a non-empty description and a typed (object) output schema."""
    async with Client(_server_for(core_version)) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    for name in ("security_settings", "security_authorities", "security_version"):
        tool = tools[name]
        assert tool.description and tool.description.strip(), f"{name} has an empty docstring"
        # A BaseModel return surfaces as a typed object output schema on the MCP wire.
        assert tool.outputSchema is not None, f"{name} must declare a typed output schema"
        assert tool.outputSchema.get("type") == "object", f"{name} must return a typed BaseModel (object schema)"


@respx.mock
async def test_security_settings_returns_typed_settings(
    core_version: str, core_profile: None, mock_system_info: Callable[..., None]
) -> None:
    """`security_settings` returns the typed SecuritySettings slice on every tree."""
    mock_system_info(core_version)
    respx.get(f"{_HOST}/api/systemSettings").mock(
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
            },
        )
    )
    settings_module = import_module(f"dhis2w_core.{core_version}.plugins.security.models")
    async with Client(_server_for(core_version)) as client:
        result = await client.call_tool("security_settings", {"profile": "probe"})
    payload = _structured(result)
    assert payload["minPasswordLength"] == 8
    assert payload["keyAccountRecovery"] is True
    assert payload["keyLockMultipleFailedLogins"] is False
    # The structured payload validates against the tree's typed SecuritySettings model.
    settings_module.SecuritySettings.model_validate(payload)


@respx.mock
async def test_security_authorities_returns_categorised_account(
    core_version: str, core_profile: None, mock_system_info: Callable[..., None]
) -> None:
    """`security_authorities` returns the categorised AccountAuthorities on every tree."""
    from dhis2w_core.security_core import AccountAuthorities

    mock_system_info(core_version)
    respx.get(f"{_HOST}/api/me/authorization").mock(
        return_value=httpx.Response(200, json=["F_USER_ADD", "F_SQLVIEW_PUBLIC_ADD", "F_DATAVALUE_ADD"])
    )
    async with Client(_server_for(core_version)) as client:
        result = await client.call_tool("security_authorities", {"profile": "probe"})
    account = AccountAuthorities.model_validate(_structured(result))
    assert account.authorities == sorted(["F_USER_ADD", "F_SQLVIEW_PUBLIC_ADD", "F_DATAVALUE_ADD"])
    assert account.is_superuser is False
    assert [match.key for match in account.categories] == ["user_management", "sql_views"]


# Per-tree versions below that line's advisory patch floor (v41 floor 8.2, v42 5.1, v43 0.1). The client
# only connects to a server on its own major line, so the below-floor case is tested per tree on its line.
_BELOW_FLOOR_VERSION = {"v41": "2.41.5.0", "v42": "2.42.4.0", "v43": "2.43.0.0"}
# Per-tree versions above that line's floor and on a supported line -> no findings with feed=None.
_CLEAN_VERSION = {"v41": "2.41.9", "v42": "2.42.6", "v43": "2.43.1"}


@respx.mock
async def test_security_version_flags_below_advisory_floor(core_version: str, core_profile: None) -> None:
    """`security_version` flags a below-advisory-floor patch HIGH, with no external-feed call."""
    from dhis2w_core.security_core import VersionPosture

    feed_route = respx.get(url__startswith=releases.RELEASES_FEED_URL).mock(
        return_value=httpx.Response(200, json={"versions": []})
    )
    version = _BELOW_FLOOR_VERSION[core_version]
    respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json={"version": version}))
    async with Client(_server_for(core_version)) as client:
        result = await client.call_tool("security_version", {"profile": "probe"})
    posture = VersionPosture.model_validate(_structured(result))
    assert posture.version == version
    assert posture.parsed is not None and posture.parsed.line == int(core_version[1:])
    titles = {finding.title for finding in posture.findings}
    assert "Running below the security-advisory patch floor" in titles
    assert all(finding.severity.value == "HIGH" for finding in posture.findings)
    assert not feed_route.called, "security_version must not fetch the external release feed"


@respx.mock
async def test_security_version_clean_version_has_no_findings(core_version: str, core_profile: None) -> None:
    """A supported, above-floor version yields no findings (feed=None skips patch-currency noise)."""
    from dhis2w_core.security_core import VersionPosture

    feed_route = respx.get(url__startswith=releases.RELEASES_FEED_URL).mock(
        return_value=httpx.Response(200, json={"versions": []})
    )
    version = _CLEAN_VERSION[core_version]
    respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json={"version": version}))
    async with Client(_server_for(core_version)) as client:
        result = await client.call_tool("security_version", {"profile": "probe"})
    posture = VersionPosture.model_validate(_structured(result))
    assert posture.version == version
    assert posture.findings == ()
    assert not feed_route.called, "security_version must not fetch the external release feed"
