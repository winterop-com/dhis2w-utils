"""Verify `d2w security audit` end-to-end via the Typer CLI runner.

Parametrised over the three version trees: `DHIS2_VERSION` selects the
plugin tree `build_app()` mounts, and the matching tree's `open_client`
is patched, so each tree's CLI path is exercised end-to-end in-process.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.v42.plugins.security.models import SecuritySettings
from typer.testing import CliRunner

TREES = ("v41", "v42", "v43")

# A SecuritySettings instance with minPasswordLength below the recommended 8
# so the settings check is guaranteed to produce at least one finding.
_WEAK_SETTINGS = SecuritySettings(
    minPasswordLength=4,
    maxPasswordLength=72,
    credentialsExpires=0,
    credentialsExpiresReminderInDays=28,
    credentialsExpiryAlert=False,
    keyAccountRecovery=True,
    keySelfRegistrationNoRecaptcha=False,
    keyLockMultipleFailedLogins=False,
    enforceVerifiedEmail=False,
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a raw-env profile so the CLI resolves without touching TOML."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


@pytest.fixture
def runner() -> CliRunner:
    """Return a Typer CliRunner for invoking the CLI under test."""
    return CliRunner()


def _make_fake_ctx() -> AsyncMock:
    """Build a fake async-context-manager wrapping a mock DHIS2 client."""
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_WEAK_SETTINGS)
    fake_client.get_raw = AsyncMock(return_value={"data": ["ALL", "F_USER_ADD"]})
    fake_client.base_url = "https://mock.example"
    fake_client.raw_version = "2.42.0"

    ctx = AsyncMock()
    ctx.__aenter__.return_value = fake_client
    ctx.__aexit__.return_value = None
    return ctx


# ---------------------------------------------------------------------------
# Test A: basic run, output folder created, expected report files present
# ---------------------------------------------------------------------------


def test_audit_creates_run_folder_and_report_files(runner: CliRunner, tmp_path: Path) -> None:
    """security audit writes md, jsonl, and html into a dhis2-security-* folder."""
    ctx = _make_fake_ctx()
    with patch("dhis2w_core.v42.plugins.security.audit.open_client", lambda *args, **kwargs: ctx):
        result = runner.invoke(
            build_app(),
            [
                "security",
                "audit",
                "--output-dir",
                str(tmp_path),
                "--no-progress",
                "--no-credential-probe",
                "--skip",
                "version",
            ],
        )

    assert result.exit_code == 0, result.output

    run_folders = list(tmp_path.glob("dhis2-security-*"))
    assert len(run_folders) == 1, f"expected one run folder, got: {run_folders}"
    folder = run_folders[0]

    assert (folder / "report.md").exists()
    assert (folder / "report.jsonl").exists()
    assert (folder / "report.html").exists()


def test_audit_report_md_contains_a_finding(runner: CliRunner, tmp_path: Path) -> None:
    """report.md produced by security audit contains the weak-password finding title."""
    ctx = _make_fake_ctx()
    with patch("dhis2w_core.v42.plugins.security.audit.open_client", lambda *args, **kwargs: ctx):
        result = runner.invoke(
            build_app(),
            [
                "security",
                "audit",
                "--output-dir",
                str(tmp_path),
                "--no-progress",
                "--no-credential-probe",
                "--skip",
                "version",
            ],
        )

    assert result.exit_code == 0, result.output

    folder = next(tmp_path.glob("dhis2-security-*"))
    md_text = (folder / "report.md").read_text(encoding="utf-8")
    assert "Weak minimum password length" in md_text


# ---------------------------------------------------------------------------
# Test B: --json flag emits a report with a summary key
# ---------------------------------------------------------------------------


def test_audit_json_output_has_summary_with_total_findings(runner: CliRunner, tmp_path: Path) -> None:
    """`--json security audit` emits JSON with a summary.total_findings integer."""
    ctx = _make_fake_ctx()
    with patch("dhis2w_core.v42.plugins.security.audit.open_client", lambda *args, **kwargs: ctx):
        result = runner.invoke(
            build_app(),
            [
                "--json",
                "security",
                "audit",
                "--output-dir",
                str(tmp_path),
                "--no-progress",
                "--no-credential-probe",
                "--skip",
                "version",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert "summary" in payload
    assert isinstance(payload["summary"]["total_findings"], int)


# ---------------------------------------------------------------------------
# Test C: parametrised over all three version trees
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tree", TREES)
def test_audit_succeeds_on_every_version_tree(
    runner: CliRunner, tmp_path: Path, tree: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """security audit exits 0 and creates a run folder against every supported version tree."""
    monkeypatch.setenv("DHIS2_VERSION", tree.removeprefix("v"))

    ctx = _make_fake_ctx()
    with patch(f"dhis2w_core.{tree}.plugins.security.audit.open_client", lambda *args, **kwargs: ctx):
        result = runner.invoke(
            build_app(),
            [
                "security",
                "audit",
                "--output-dir",
                str(tmp_path),
                "--no-progress",
                "--no-credential-probe",
                "--skip",
                "version",
            ],
        )

    assert result.exit_code == 0, result.output

    run_folders = list(tmp_path.glob("dhis2-security-*"))
    assert len(run_folders) == 1, f"tree={tree}: expected one run folder, got: {run_folders}"
