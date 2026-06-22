"""Per-version parity for the `system` plugin service — exercise every public function on all trees.

One happy-path test per public (non-underscore) function in `plugins/system/service.py`, resolved per
`core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted, not just
smoke-imported. The three service trees are byte-identical copies (only the import version differs), so
the assertions are the same on every tree. Mocked (respx); no live stack.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_client.v42 import DhisCalendar
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_server_info_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`server_info` introspects the running process without opening a DHIS2 client, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("system")

    info = await service.server_info()

    assert info.active_plugin_tree in {"v41", "v42", "v43"}
    assert info.active_plugin_tree_source
    assert info.dhis2w_core_version


@respx.mock
async def test_whoami_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`whoami` merges /api/me authorities into the full /api/users/{id} object, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("system")
    respx.get(f"{_HOST}/api/me").mock(
        return_value=httpx.Response(200, json={"id": "usr01234567", "authorities": ["ALL", "F_EXPORT_DATA"]}),
    )
    user_route = respx.get(f"{_HOST}/api/users/usr01234567").mock(
        return_value=httpx.Response(200, json={"id": "usr01234567", "username": "admin"}),
    )

    me = await service.whoami(resolve_profile("probe"))

    assert me.id == "usr01234567"
    assert me.username == "admin"
    assert me.authorities == ["ALL", "F_EXPORT_DATA"]
    assert user_route.calls.last.request.url.params["fields"]


@respx.mock
async def test_system_info_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`system_info` returns the typed /api/system/info envelope, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("system")

    info = await service.system_info(resolve_profile("probe"))

    assert info.version


@respx.mock
async def test_get_calendar_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_calendar` reads `keyCalendar` from /api/systemSettings/{key}, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("system")
    route = respx.get(f"{_HOST}/api/systemSettings/keyCalendar").mock(
        return_value=httpx.Response(200, json={"keyCalendar": "ethiopian"}),
    )

    calendar = await service.get_calendar(resolve_profile("probe"))

    assert calendar == "ethiopian"
    assert route.called


@respx.mock
async def test_set_calendar_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_calendar` POSTs the calendar name to /api/systemSettings/keyCalendar, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("system")
    route = respx.post(f"{_HOST}/api/systemSettings/keyCalendar").mock(return_value=httpx.Response(200))

    await service.set_calendar(resolve_profile("probe"), DhisCalendar.NEPALI)

    assert route.calls.last.request.read() == b"nepali"


@respx.mock
async def test_generate_uids_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`generate_uids` returns the `codes` list from /api/system/id with the `limit` param, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("system")
    route = respx.get(f"{_HOST}/api/system/id").mock(
        return_value=httpx.Response(200, json={"codes": ["abcDEFghiJK", "zzzYYYwwwVV"]}),
    )

    codes = await service.generate_uids(resolve_profile("probe"), limit=2)

    assert codes == ["abcDEFghiJK", "zzzYYYwwwVV"]
    assert route.calls.last.request.url.params["limit"] == "2"


@respx.mock
async def test_set_system_setting_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_system_setting` POSTs the value to /api/systemSettings/{key}, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("system")
    route = respx.post(f"{_HOST}/api/systemSettings/keyAnalysisDisplayProperty").mock(
        return_value=httpx.Response(200),
    )

    await service.set_system_setting(resolve_profile("probe"), "keyAnalysisDisplayProperty", "shortName")

    assert route.calls.last.request.read() == b"shortName"


@respx.mock
async def test_set_system_settings_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`set_system_settings` POSTs each key/value and returns the applied keys, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("system")
    respx.post(f"{_HOST}/api/systemSettings/keyA").mock(return_value=httpx.Response(200))
    respx.post(f"{_HOST}/api/systemSettings/keyB").mock(return_value=httpx.Response(200))

    applied = await service.set_system_settings(resolve_profile("probe"), {"keyA": "1", "keyB": "2"})

    assert applied == ["keyA", "keyB"]


@respx.mock
async def test_get_setting_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_setting` reads one setting from /api/systemSettings/{key}, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("system")
    route = respx.get(f"{_HOST}/api/systemSettings/keyFlag").mock(
        return_value=httpx.Response(200, json={"keyFlag": "sierra_leone"}),
    )

    value = await service.get_setting(resolve_profile("probe"), "keyFlag")

    assert value == "sierra_leone"
    assert route.called


@respx.mock
async def test_list_settings_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_settings` parses /api/systemSettings into a raw `{key: value}` snapshot, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("system")
    respx.get(f"{_HOST}/api/systemSettings").mock(
        return_value=httpx.Response(200, json={"keyCalendar": "iso8601", "keyFlag": "sierra_leone"}),
    )

    snapshot = await service.list_settings(resolve_profile("probe"))

    assert snapshot.pairs() == [("keyCalendar", "iso8601"), ("keyFlag", "sierra_leone")]
