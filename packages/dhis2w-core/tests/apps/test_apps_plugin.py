"""Tests for the apps plugin — CLI surface, update logic, descriptor."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.apps import plugin, service
from dhis2w_core.v42.plugins.apps.cli import app as apps_app
from dhis2w_core.v42.plugins.apps.models import UpdateSummary
from dhis2w_core.v42.plugins.apps.service import InstallTargetError
from typer.testing import CliRunner

_runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Raw-env profile so `profile_from_env()` resolves without TOML."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DHIS2_URL", "https://dhis2.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")
    yield


@pytest.fixture
def profile() -> Profile:
    """Minimal profile for service-layer tests."""
    return Profile(base_url="https://dhis2.example", auth="pat", token="test-token")


def _mock_preamble() -> None:
    """Connect-time probes (root + /api/system/info)."""
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )


_INSTALLED = [
    {
        "key": "widget",
        "name": "Dashboard Widget",
        "displayName": "Dashboard Widget",
        "version": "1.0.0",
        "bundled": False,
        "app_hub_id": "hub-widget",
    },
    {
        "key": "reports",
        "name": "Reports (bundled, hub-updatable)",
        "version": "100.2.0",
        "bundled": True,
        "app_hub_id": "hub-reports",
    },
    {
        "key": "side-loaded",
        "name": "Side-Loaded",
        "version": "0.1.0",
        "bundled": False,
    },
]

_HUB = [
    {
        "id": "hub-widget",
        "name": "Dashboard Widget",
        "versions": [
            {"id": "ver-100", "version": "1.0.0"},
            {"id": "ver-200", "version": "2.0.0"},
        ],
    },
    {
        "id": "hub-reports",
        "name": "Reports",
        "versions": [
            {"id": "ver-reports-1002", "version": "100.2.0"},
            {"id": "ver-reports-1003", "version": "100.3.0"},
        ],
    },
]


def test_plugin_descriptor() -> None:
    """Plugin registers under `apps` with a meaningful description."""
    assert plugin.name == "apps"
    assert "appHub" in plugin.description or "app hub" in plugin.description.lower()


def test_cli_help_lists_every_verb() -> None:
    """`d2w apps --help` exposes every verb including snapshot + restore."""
    result = _runner.invoke(apps_app, ["--help"])
    assert result.exit_code == 0, result.output
    for verb in ("list", "add", "remove", "update", "reload", "snapshot", "restore", "hub-list", "hub-url"):
        assert verb in result.output


def test_hub_url_rejects_set_plus_clear() -> None:
    """`hub-url --set X --clear` is a user error — pick one direction."""
    result = _runner.invoke(apps_app, ["hub-url", "--set", "https://x", "--clear"])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_update_command_rejects_both_key_and_all() -> None:
    """`update <key> --all` is a user error (pick one or the other)."""
    result = _runner.invoke(apps_app, ["update", "widget", "--all"])
    assert result.exit_code != 0
    assert "not both" in result.output


def test_update_command_requires_key_or_all() -> None:
    """`update` with no key and no --all flag is a user error."""
    result = _runner.invoke(apps_app, ["update"])
    assert result.exit_code != 0
    assert "key" in result.output.lower() or "--all" in result.output.lower()


def test_full_cli_mounts_apps_plugin() -> None:
    """The auto-discovered plugin mounts under `d2w apps` on the root CLI."""
    root = build_app()
    result = _runner.invoke(root, ["apps", "--help"])
    assert result.exit_code == 0, result.output
    assert "list" in result.output


@respx.mock
async def test_update_all_updates_bundled_and_non_bundled_skips_side_loaded(profile: Profile) -> None:
    """update_all: updates widget + reports (both hub-updatable, reports is bundled); skips side-loaded."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/apps").mock(return_value=httpx.Response(200, json=_INSTALLED))
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    widget_route = respx.post("https://dhis2.example/api/appHub/ver-200").mock(return_value=httpx.Response(201))
    reports_route = respx.post("https://dhis2.example/api/appHub/ver-reports-1003").mock(
        return_value=httpx.Response(201),
    )

    summary: UpdateSummary = await service.update_all(profile)

    assert summary.updated == 2
    assert summary.up_to_date == 0
    assert summary.skipped == 1
    assert summary.failed == 0
    assert widget_route.called
    assert reports_route.called

    widget = next(o for o in summary.outcomes if o.key == "widget")
    assert widget.status == "UPDATED"
    assert widget.from_version == "1.0.0"
    assert widget.to_version == "2.0.0"

    reports = next(o for o in summary.outcomes if o.key == "reports")
    assert reports.status == "UPDATED"
    assert reports.from_version == "100.2.0"
    assert reports.to_version == "100.3.0"

    side = next(o for o in summary.outcomes if o.key == "side-loaded")
    assert side.status == "SKIPPED"
    assert side.reason is not None
    assert "app_hub_id" in side.reason


@respx.mock
async def test_update_all_reports_up_to_date_when_versions_match(profile: Profile) -> None:
    """If the installed version equals the latest hub version, outcome is UP_TO_DATE (no POST)."""
    _mock_preamble()
    hub_same_version = [
        {
            "id": "hub-widget",
            "name": "Dashboard Widget",
            "versions": [{"id": "ver-100", "version": "1.0.0"}],
        },
    ]
    respx.get("https://dhis2.example/api/apps").mock(
        return_value=httpx.Response(200, json=[_INSTALLED[0]]),
    )
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=hub_same_version))
    install_route = respx.post("https://dhis2.example/api/appHub/ver-100").mock(
        return_value=httpx.Response(201),
    )

    summary = await service.update_all(profile)

    assert summary.updated == 0
    assert summary.up_to_date == 1
    assert not install_route.called


@respx.mock
async def test_update_all_dry_run_reports_available_without_posting(profile: Profile) -> None:
    """`dry_run=True` tags updates as AVAILABLE (incl. bundled-with-hub-id) and skips every install POST."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/apps").mock(return_value=httpx.Response(200, json=_INSTALLED))
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    widget_route = respx.post("https://dhis2.example/api/appHub/ver-200").mock(return_value=httpx.Response(201))
    reports_route = respx.post("https://dhis2.example/api/appHub/ver-reports-1003").mock(
        return_value=httpx.Response(201),
    )

    summary = await service.update_all(profile, dry_run=True)

    assert summary.updated == 0
    assert summary.available == 2
    assert summary.skipped == 1
    widget = next(o for o in summary.outcomes if o.key == "widget")
    assert widget.status == "AVAILABLE"
    assert widget.to_version == "2.0.0"
    reports = next(o for o in summary.outcomes if o.key == "reports")
    assert reports.status == "AVAILABLE"
    assert reports.to_version == "100.3.0"
    assert not widget_route.called
    assert not reports_route.called


@respx.mock
async def test_update_one_failing_install_reports_failed(profile: Profile) -> None:
    """A 500 on /api/appHub/{id} lands as a FAILED outcome with the reason captured."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/apps").mock(return_value=httpx.Response(200, json=[_INSTALLED[0]]))
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    respx.post("https://dhis2.example/api/appHub/ver-200").mock(return_value=httpx.Response(500))

    outcome = await service.update_one(profile, "widget")

    assert outcome.status == "FAILED"
    assert outcome.reason is not None


@respx.mock
async def test_update_one_unknown_key_fails_cleanly(profile: Profile) -> None:
    """`update_one('missing')` returns a FAILED outcome with the typo hint."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/apps").mock(return_value=httpx.Response(200, json=[]))

    outcome = await service.update_one(profile, "missing")

    assert outcome.status == "FAILED"
    assert outcome.reason is not None
    assert "missing" in outcome.reason


@respx.mock
async def test_install_from_hub_with_version_id_installs_directly(profile: Profile) -> None:
    """A real App Hub version id is POSTed straight to /api/appHub/{versionId}; resolved_from='version-id'."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    install_route = respx.post("https://dhis2.example/api/appHub/ver-200").mock(return_value=httpx.Response(201))

    target = await service.install_from_hub(profile, "ver-200")

    assert install_route.called
    assert target.version_id == "ver-200"
    assert target.version == "2.0.0"
    assert target.app_name == "Dashboard Widget"
    assert target.resolved_from == "version-id"


@respx.mock
async def test_install_from_hub_with_app_id_resolves_latest_version(profile: Profile) -> None:
    """An App Hub *app* id resolves to that app's latest version (BUGS.md #46); resolved_from='app-id'."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    install_route = respx.post("https://dhis2.example/api/appHub/ver-200").mock(return_value=httpx.Response(201))

    target = await service.install_from_hub(profile, "hub-widget")

    assert install_route.called
    assert target.version_id == "ver-200"
    assert target.version == "2.0.0"
    assert target.resolved_from == "app-id"


@respx.mock
async def test_install_from_hub_unknown_id_raises_without_posting(profile: Profile) -> None:
    """An id matching neither a version nor an app id raises InstallTargetError and POSTs nothing."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))
    install_route = respx.post(url__regex=r"https://dhis2\.example/api/appHub/.+").mock(
        return_value=httpx.Response(201),
    )

    with pytest.raises(InstallTargetError, match="neither an App Hub version id nor an app id"):
        await service.install_from_hub(profile, "not-a-real-id")

    assert not install_route.called


@respx.mock
async def test_hub_versions_returns_app_versions_newest_first(profile: Profile) -> None:
    """hub_versions(app_id) returns the app with versions sorted by descending semver."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))

    record = await service.hub_versions(profile, "hub-widget")

    assert record.name == "Dashboard Widget"
    assert [v.version for v in record.versions] == ["2.0.0", "1.0.0"]
    assert [v.id for v in record.versions] == ["ver-200", "ver-100"]


@respx.mock
async def test_hub_versions_unknown_app_id_raises(profile: Profile) -> None:
    """hub_versions on a non-app-id raises InstallTargetError pointing at hub-list."""
    _mock_preamble()
    respx.get("https://dhis2.example/api/appHub").mock(return_value=httpx.Response(200, json=_HUB))

    with pytest.raises(InstallTargetError, match="not an App Hub app id"):
        await service.hub_versions(profile, "ver-200")
