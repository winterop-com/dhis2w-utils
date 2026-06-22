"""Per-version parity for the `customize` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/customize/test_customize_plugin.py` preset-dir coverage, but resolves the
service per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted,
not just smoke-imported. The three service trees are byte-identical copies (only the import version
differs), so the assertions are the same on every tree. Mocked (respx); no live stack.

The customize service does branding: logo uploads via `/api/staticContent/{logo_front,logo_banner}`
(each followed by a `keyUseCustomLogo*` system-setting POST), CSS via `/api/files/style` (followed by a
`keyStyle` POST), read-only `/api/loginConfig`, and a preset-dir loader that stitches them together.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_upload_logo_front_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`upload_logo_front` POSTs the image to staticContent + flips keyUseCustomLogoFront, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("customize")
    logo = tmp_path / "logo_front.png"
    logo.write_bytes(b"front-png-bytes")
    static_route = respx.post(f"{_HOST}/api/staticContent/logo_front").mock(return_value=httpx.Response(204))
    setting_route = respx.post(f"{_HOST}/api/systemSettings/keyUseCustomLogoFront").mock(
        return_value=httpx.Response(200, json={"status": "OK"})
    )

    await service.upload_logo_front(resolve_profile("probe"), logo)

    assert static_route.called
    assert b"front-png-bytes" in static_route.calls.last.request.read()
    assert setting_route.calls.last.request.read() == b"true"


@respx.mock
async def test_upload_logo_banner_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`upload_logo_banner` POSTs the image to staticContent + flips keyUseCustomLogoBanner, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("customize")
    logo = tmp_path / "logo_banner.png"
    logo.write_bytes(b"banner-png-bytes")
    static_route = respx.post(f"{_HOST}/api/staticContent/logo_banner").mock(return_value=httpx.Response(204))
    setting_route = respx.post(f"{_HOST}/api/systemSettings/keyUseCustomLogoBanner").mock(
        return_value=httpx.Response(200, json={"status": "OK"})
    )

    await service.upload_logo_banner(resolve_profile("probe"), logo)

    assert static_route.called
    assert b"banner-png-bytes" in static_route.calls.last.request.read()
    assert setting_route.calls.last.request.read() == b"true"


@respx.mock
async def test_upload_style_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`upload_style` POSTs CSS to /api/files/style + sets keyStyle=style, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("customize")
    css = tmp_path / "style.css"
    css.write_text("body{color:red}", encoding="utf-8")
    style_route = respx.post(f"{_HOST}/api/files/style").mock(return_value=httpx.Response(204))
    setting_route = respx.post(f"{_HOST}/api/systemSettings/keyStyle").mock(
        return_value=httpx.Response(200, json={"status": "OK"})
    )

    await service.upload_style(resolve_profile("probe"), css)

    assert style_route.calls.last.request.read() == b"body{color:red}"
    assert setting_route.calls.last.request.read() == b"style"


@respx.mock
async def test_get_login_config_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_login_config` parses the read-only /api/loginConfig summary, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("customize")
    route = respx.get(f"{_HOST}/api/loginConfig").mock(
        return_value=httpx.Response(200, json={"applicationTitle": "Demo DHIS2"})
    )

    config = await service.get_login_config(resolve_profile("probe"))

    assert config.applicationTitle == "Demo DHIS2"
    assert route.called


@respx.mock
async def test_apply_preset_dir_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`apply_preset_dir` loads logos + CSS + preset.json and applies each, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("customize")
    (tmp_path / "logo_front.png").write_bytes(b"front-png")
    (tmp_path / "logo_banner.png").write_bytes(b"banner-png")
    (tmp_path / "style.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "preset.json").write_text('{"applicationTitle": "Hello"}', encoding="utf-8")
    respx.post(f"{_HOST}/api/staticContent/logo_front").mock(return_value=httpx.Response(204))
    respx.post(f"{_HOST}/api/staticContent/logo_banner").mock(return_value=httpx.Response(204))
    respx.post(f"{_HOST}/api/files/style").mock(return_value=httpx.Response(204))
    title_route = respx.post(f"{_HOST}/api/systemSettings/applicationTitle").mock(
        return_value=httpx.Response(200, json={"status": "OK"})
    )
    respx.post(url__regex=rf"{_HOST}/api/systemSettings/key.*").mock(
        return_value=httpx.Response(200, json={"status": "OK"})
    )

    result = await service.apply_preset_dir(resolve_profile("probe"), tmp_path)

    assert result.logo_front_uploaded
    assert result.logo_banner_uploaded
    assert result.style_uploaded
    assert result.settings_applied == ["applicationTitle"]
    assert title_route.calls.last.request.read() == b"Hello"
