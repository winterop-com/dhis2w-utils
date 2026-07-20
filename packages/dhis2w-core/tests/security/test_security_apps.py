"""Apps-check tests: side-loaded detection, hub update currency, custom JS/CSS, and per-tree wiring.

`evaluate_apps` is version-invariant and tested directly; the `_run_apps` wiring (which maps the
client's typed App / AppHubApp accessors into the version-invariant models) is exercised against a
mock client across all three version trees.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_core.security_core import (
    CheckStatus,
    HubApp,
    InstalledApp,
    Severity,
    evaluate_apps,
)

TREES = ("v41", "v42", "v43")


def _titles(findings: list[Any]) -> set[str]:
    """Collect finding titles for membership assertions."""
    return {finding.title for finding in findings}


# ---------------------------------------------------------------------------
# evaluate_apps (version-invariant)
# ---------------------------------------------------------------------------


def test_side_loaded_app_without_hub_id_is_high() -> None:
    """A non-bundled app installed outside the App Hub is flagged HIGH and folds under one key."""
    findings = evaluate_apps(
        installed=[InstalledApp(name="Sideloaded", version="1.0.0")],
        hub=[],
        custom_js=False,
        custom_css=False,
    ).findings
    side = [f for f in findings if f.title == "Side-loaded app installed"]
    assert side and side[0].severity is Severity.HIGH
    assert side[0].subject == "Sideloaded"
    assert side[0].group_key == "side-loaded-app"


def test_bundled_and_core_apps_are_not_side_loaded() -> None:
    """Bundled and core apps with no app_hub_id are trusted and not flagged."""
    findings = evaluate_apps(
        installed=[
            InstalledApp(name="Bundled", version="1.0.0", bundled=True),
            InstalledApp(name="Core", version="1.0.0", core_app=True),
        ],
        hub=[],
        custom_js=False,
        custom_css=False,
    ).findings
    assert "Side-loaded app installed" not in _titles(findings)


def test_hub_backed_app_is_not_side_loaded() -> None:
    """An app carrying an app_hub_id came from the hub and is not side-loaded."""
    findings = evaluate_apps(
        installed=[InstalledApp(name="Reports", version="1.0.0", app_hub_id="hub-1")],
        hub=[],
        custom_js=False,
        custom_css=False,
    ).findings
    assert "Side-loaded app installed" not in _titles(findings)


def test_update_available_is_medium_with_numeric_semver() -> None:
    """A hub-backed app behind the hub's latest semver is MEDIUM (100.10.0 beats 100.3.1 numerically)."""
    findings = evaluate_apps(
        installed=[InstalledApp(name="Reports", version="100.3.1", app_hub_id="hub-reports")],
        hub=[HubApp(app_hub_id="hub-reports", versions=["100.3.1", "100.4.0", "100.10.0"])],
        custom_js=False,
        custom_css=False,
    ).findings
    update = [f for f in findings if f.title == "App update available"]
    assert update and update[0].severity is Severity.MEDIUM
    assert update[0].subject == "Reports"
    assert update[0].group_key == "app-update"
    assert (update[0].evidence or {}).get("latest") == "100.10.0"


def test_app_at_latest_version_has_no_update_finding() -> None:
    """An app already at (or above) the hub's latest version reports no update."""
    findings = evaluate_apps(
        installed=[InstalledApp(name="Cache", version="2.0.0", app_hub_id="hub-cache")],
        hub=[HubApp(app_hub_id="hub-cache", versions=["1.0.0", "2.0.0"])],
        custom_js=False,
        custom_css=False,
    ).findings
    assert "App update available" not in _titles(findings)


def test_app_not_in_hub_catalog_is_not_flagged() -> None:
    """An app whose app_hub_id is absent from the catalog produces no finding (never a false 'untrusted')."""
    findings = evaluate_apps(
        installed=[InstalledApp(name="Orphan", version="1.0.0", app_hub_id="hub-missing")],
        hub=[HubApp(app_hub_id="hub-other", versions=["9.9.9"])],
        custom_js=False,
        custom_css=False,
    ).findings
    assert findings == []


def test_prerelease_versions_do_not_flag_a_downgrade_or_miss_an_update() -> None:
    """Pre-release / build suffixes are tolerated: no false downgrade, and a newer snapshot still flags."""
    no_downgrade = evaluate_apps(
        installed=[InstalledApp(name="Beta", version="2.0.0-beta", app_hub_id="hub-beta")],
        hub=[HubApp(app_hub_id="hub-beta", versions=["1.9.0"])],
        custom_js=False,
        custom_css=False,
    ).findings
    assert "App update available" not in _titles(no_downgrade)

    real_update = evaluate_apps(
        installed=[InstalledApp(name="App", version="1.2.3", app_hub_id="hub-app")],
        hub=[HubApp(app_hub_id="hub-app", versions=["1.2.4-SNAPSHOT"])],
        custom_js=False,
        custom_css=False,
    ).findings
    assert "App update available" in _titles(real_update)


def test_trailing_zero_versions_compare_equal() -> None:
    """An app at '2.0' against a hub '2.0.0' is the same release and is not flagged as an update."""
    findings = evaluate_apps(
        installed=[InstalledApp(name="App", version="2.0", app_hub_id="hub-app")],
        hub=[HubApp(app_hub_id="hub-app", versions=["2.0.0"])],
        custom_js=False,
        custom_css=False,
    ).findings
    assert "App update available" not in _titles(findings)


def test_installed_ahead_of_hub_uses_numeric_not_lexicographic_compare() -> None:
    """An app ahead of the hub's latest reports no update; 100.10.0 beats 100.9.0 numerically, not as strings."""
    findings = evaluate_apps(
        installed=[InstalledApp(name="App", version="100.10.0", app_hub_id="hub-app")],
        hub=[HubApp(app_hub_id="hub-app", versions=["100.9.0"])],
        custom_js=False,
        custom_css=False,
    ).findings
    assert "App update available" not in _titles(findings)


def test_hub_unreachable_skips_updates_but_keeps_other_signals() -> None:
    """hub=None suppresses update findings while side-loaded and custom-code signals still run."""
    findings = evaluate_apps(
        installed=[
            InstalledApp(name="Sideloaded", version="1.0.0"),
            InstalledApp(name="Reports", version="1.0.0", app_hub_id="hub-reports"),
        ],
        hub=None,
        custom_js=False,
        custom_css=True,
    ).findings
    titles = _titles(findings)
    assert "App update available" not in titles
    assert "Side-loaded app installed" in titles
    assert "Custom CSS injected into every app" in titles


def test_custom_js_and_css_are_high() -> None:
    """Configured custom JavaScript and CSS each raise a HIGH injection finding."""
    findings = evaluate_apps(installed=[], hub=[], custom_js=True, custom_css=True).findings
    by_title = {f.title: f for f in findings}
    assert by_title["Custom JavaScript injected into every app"].severity is Severity.HIGH
    assert by_title["Custom CSS injected into every app"].severity is Severity.HIGH


def test_no_custom_code_when_unset() -> None:
    """No custom-code findings when neither keyCustomJs nor keyCustomCss is set."""
    findings = evaluate_apps(installed=[], hub=[], custom_js=False, custom_css=False).findings
    assert findings == []


# ---------------------------------------------------------------------------
# Per-tree wiring: _run_apps maps the client accessors into the audit models
# ---------------------------------------------------------------------------


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _app_types(tree: str) -> tuple[Any, Any]:
    """Return the (App, AppHubApp) types for a version tree."""
    client_module = import_module(f"dhis2w_client.{tree}")
    return client_module.App, client_module.AppHubApp


def _mock_client(*, apps: list[Any], catalog: Any, settings: dict[str, Any]) -> MagicMock:
    """A client whose typed apps accessors and systemSettings read return the given fixtures."""
    client = MagicMock()
    client.apps = MagicMock()
    client.apps.list_apps = AsyncMock(return_value=apps)
    client.apps.hub_list = AsyncMock(return_value=catalog)
    client.get_raw = AsyncMock(return_value=settings)
    return client


@pytest.mark.parametrize("tree", TREES)
async def test_run_apps_flags_side_loaded_update_and_custom_js(tree: str) -> None:
    """_run_apps surfaces a side-loaded app, an available update, and custom JS; bundled apps are ignored."""
    audit = _audit_module(tree)
    app_type, hub_type = _app_types(tree)
    apps = [
        app_type(name="Sideloaded", version="1.0.0"),
        app_type(name="Core", version="1.0.0", bundled=True),
        app_type(name="Reports", version="100.3.1", app_hub_id="hub-reports"),
    ]
    catalog = [hub_type(id="hub-reports", versions=[{"version": "100.10.0", "id": "v1"}])]
    client = _mock_client(apps=apps, catalog=catalog, settings={"keyCustomJs": "alert(1)", "keyCustomCss": ""})

    result = await audit._run_apps(client)

    assert result.status is CheckStatus.OK
    assert result.note is None
    titles = _titles(result.findings)
    assert "Side-loaded app installed" in titles
    assert "App update available" in titles
    assert "Custom JavaScript injected into every app" in titles
    assert not any("CSS" in title for title in titles)


@pytest.mark.parametrize("tree", TREES)
async def test_run_apps_degrades_to_note_when_hub_unreachable(tree: str) -> None:
    """A hub fetch error degrades to a note and skips updates; the check itself still succeeds."""
    audit = _audit_module(tree)
    app_type, _hub_type = _app_types(tree)
    client = _mock_client(
        apps=[app_type(name="Reports", version="1.0.0", app_hub_id="hub-x")],
        catalog=[],
        settings={},
    )
    client.apps.hub_list = AsyncMock(side_effect=Dhis2ApiError(503, "hub down"))

    result = await audit._run_apps(client)

    assert result.status is CheckStatus.OK
    assert result.note is not None and "App Hub unreachable" in result.note
    assert "App update available" not in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_apps_degrades_when_apps_endpoint_errors(tree: str) -> None:
    """An error listing installed apps degrades the whole check rather than reporting a false all-clear."""
    audit = _audit_module(tree)
    client = MagicMock()
    client.apps = MagicMock()
    client.apps.list_apps = AsyncMock(side_effect=Dhis2ApiError(500, "boom"))

    result = await audit._run_apps(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []


@pytest.mark.parametrize(
    ("settings", "expect_js", "expect_css"),
    [
        (
            {"keyCustomJs": "   ", "keyCustomCss": "  body{}  "},
            False,
            True,
        ),  # whitespace-only ignored; trimmed-nonempty flagged
        ({}, False, False),  # keys absent from the response
        ({"keyCustomJs": True, "keyCustomCss": 0}, False, False),  # non-string values ignored
    ],
)
async def test_run_apps_custom_code_flag_handling(settings: dict[str, Any], expect_js: bool, expect_css: bool) -> None:
    """_custom_code_flags treats whitespace-only, missing, and non-string settings as 'not configured'."""
    audit = _audit_module("v42")
    client = _mock_client(apps=[], catalog=[], settings=settings)

    result = await audit._run_apps(client)

    titles = _titles(result.findings)
    assert ("Custom JavaScript injected into every app" in titles) is expect_js
    assert ("Custom CSS injected into every app" in titles) is expect_css
