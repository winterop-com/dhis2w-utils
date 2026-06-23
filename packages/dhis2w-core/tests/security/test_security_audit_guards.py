"""Safety guards for the audit framework: selection/format validation, no-clobber, resume."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.security_core import (
    CheckResult,
    CheckStatus,
    MarkdownRenderer,
    ReportWriter,
    RunManifest,
    resolve_check_keys,
)
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "http://mock.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")


def _manifest() -> RunManifest:
    return RunManifest(
        target="https://play.example",
        profile="demo",
        scanner_version="0.0.0",
        started_at="2026-06-13T00:00:00+00:00",
        check_order=["settings"],
    )


def _ok(check: str) -> CheckResult:
    return CheckResult(check=check, label=check.title(), status=CheckStatus.OK)


def test_resolve_check_keys_defaults_to_all_implemented() -> None:
    assert resolve_check_keys() == [
        "version",
        "transport",
        "settings",
        "authorities",
        "roles",
        "hygiene",
        "credential-probe",
        "guest",
        "apps",
        "sharing",
        "auth-methods",
        "tokens",
        "routes",
    ]


def test_resolve_check_keys_only_filters_to_named_checks() -> None:
    assert resolve_check_keys(only=["settings"]) == ["settings"]


def test_resolve_check_keys_rejects_unknown_key() -> None:
    with pytest.raises(ValueError, match="unknown check key"):
        resolve_check_keys(only=["bogus"])


def test_resolve_check_keys_rejects_not_yet_implemented_key() -> None:
    with pytest.raises(ValueError, match="not implemented"):
        resolve_check_keys(only=["audit-config"])


def test_resolve_check_keys_rejects_empty_selection() -> None:
    with pytest.raises(ValueError, match="no checks selected"):
        resolve_check_keys(
            skip=[
                "version",
                "transport",
                "settings",
                "authorities",
                "credential-probe",
                "roles",
                "hygiene",
                "apps",
                "guest",
                "sharing",
                "auth-methods",
                "tokens",
                "routes",
            ]
        )


def test_report_writer_refuses_to_clobber_existing_run(tmp_path: Path) -> None:
    folder = tmp_path / "run"
    writer = ReportWriter(folder, _manifest(), streaming_renderer=MarkdownRenderer())
    writer.write_result(_ok("settings"))
    writer.close()
    with pytest.raises(FileExistsError):
        ReportWriter(folder, _manifest(), streaming_renderer=MarkdownRenderer())


def test_report_writer_resume_appends_without_clobber(tmp_path: Path) -> None:
    folder = tmp_path / "run"
    writer = ReportWriter(folder, _manifest(), streaming_renderer=MarkdownRenderer())
    writer.write_result(_ok("settings"))
    writer.close()
    resumed = ReportWriter(folder, _manifest(), streaming_renderer=MarkdownRenderer(), resume=True)
    resumed.write_result(_ok("authorities"))
    resumed.close()
    spine = [line for line in (folder / "report.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(spine) == 2


def test_report_writer_context_manager_closes_handles(tmp_path: Path) -> None:
    folder = tmp_path / "run"
    with ReportWriter(folder, _manifest(), streaming_renderer=MarkdownRenderer()) as writer:
        writer.write_result(_ok("settings"))
    assert writer._spine.closed
    assert writer._markdown.closed


def test_audit_cli_rejects_unknown_check_key(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        build_app(), ["security", "audit", "--checks", "bogus", "--output-dir", str(tmp_path), "--no-progress"]
    )
    assert result.exit_code == 2


def test_audit_cli_rejects_unknown_format(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        build_app(), ["security", "audit", "--format", "pdf", "--output-dir", str(tmp_path), "--no-progress"]
    )
    assert result.exit_code == 2
