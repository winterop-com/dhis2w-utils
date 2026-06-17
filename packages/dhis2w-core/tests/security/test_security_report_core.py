"""Unit and integration tests for the version-invariant security audit core.

Covers AuditSummary rollups, every renderer, ReportWriter end-to-end via
run_audit, resume behaviour, and error-isolation inside the audit loop.
All tests are pure in-process with no network calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from dhis2w_core.security_core import (
    AuditFinding,
    AuditReport,
    AuditSummary,
    BoundCheck,
    CheckResult,
    CheckStatus,
    CsvRenderer,
    HtmlRenderer,
    MarkdownRenderer,
    ProgressReporter,
    ReportWriter,
    RunManifest,
    Severity,
    TextRenderer,
    make_reporter,
    run_audit,
)
from rich.console import Console

# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

_MANIFEST = RunManifest(
    target="https://test.example",
    profile="default",
    scanner_version="0.0.1-test",
    started_at="2026-01-01T00:00:00+00:00",
    dhis2_version="2.42.0",
    check_order=["settings", "authorities"],
)


def _finding(severity: Severity, title: str = "Test finding", check: str = "settings") -> AuditFinding:
    """Build a minimal AuditFinding for use in tests."""
    return AuditFinding(
        check=check,
        severity=severity,
        title=title,
        detail=f"Detail for {title}.",
    )


def _ok_result(check: str = "settings", findings: list[AuditFinding] | None = None) -> CheckResult:
    """Build a CheckResult with status OK and an optional findings list."""
    return CheckResult(
        check=check,
        label=f"Label for {check}",
        status=CheckStatus.OK,
        findings=findings or [],
    )


def _plain_reporter(console: Console | None = None) -> ProgressReporter:
    """Return a non-animated PlainLogReporter that keeps tests quiet."""
    return make_reporter(console or Console(stderr=True), animated=False)


# ---------------------------------------------------------------------------
# 1. AuditSummary.from_results / .worst
# ---------------------------------------------------------------------------


def test_audit_summary_counts_mixed_severities() -> None:
    """from_results accumulates one count per severity tier correctly."""
    results = [
        _ok_result("settings", [_finding(Severity.CRITICAL), _finding(Severity.HIGH)]),
        _ok_result("authorities", [_finding(Severity.MEDIUM), _finding(Severity.WARN), _finding(Severity.INFO)]),
    ]
    summary = AuditSummary.from_results(results)
    assert summary.critical == 1
    assert summary.high == 1
    assert summary.medium == 1
    assert summary.warn == 1
    assert summary.info == 1
    assert summary.total_findings == 5


def test_audit_summary_check_status_counts() -> None:
    """from_results splits check statuses into the matching counter fields."""
    results = [
        CheckResult(check="a", label="A", status=CheckStatus.OK),
        CheckResult(check="b", label="B", status=CheckStatus.DEGRADED),
        CheckResult(check="c", label="C", status=CheckStatus.ERROR),
        CheckResult(check="d", label="D", status=CheckStatus.SKIPPED),
        CheckResult(check="e", label="E", status=CheckStatus.OK),
    ]
    summary = AuditSummary.from_results(results)
    assert summary.checks_run == 5
    assert summary.checks_ok == 2
    assert summary.checks_degraded == 1
    assert summary.checks_error == 1
    assert summary.checks_skipped == 1


def test_audit_summary_worst_returns_most_urgent_severity() -> None:
    """worst returns the highest-rank severity present across all findings."""
    results = [
        _ok_result("settings", [_finding(Severity.WARN), _finding(Severity.INFO)]),
        _ok_result("authorities", [_finding(Severity.HIGH)]),
    ]
    summary = AuditSummary.from_results(results)
    assert summary.worst is Severity.HIGH


def test_audit_summary_worst_is_none_when_no_findings() -> None:
    """worst is None when the run produced no findings at all."""
    summary = AuditSummary.from_results([_ok_result("settings"), _ok_result("authorities")])
    assert summary.worst is None


def test_audit_summary_worst_is_none_for_empty_results() -> None:
    """worst is None when from_results receives an empty list."""
    summary = AuditSummary.from_results([])
    assert summary.worst is None


def test_audit_summary_worst_critical_beats_all() -> None:
    """CRITICAL is returned as worst even when every other tier also has findings."""
    findings = [_finding(s) for s in Severity]
    results = [_ok_result("settings", findings)]
    summary = AuditSummary.from_results(results)
    assert summary.worst is Severity.CRITICAL


# ---------------------------------------------------------------------------
# 2. Renderer tests
# ---------------------------------------------------------------------------

_FINDING_WITH_ANGLE = AuditFinding(
    check="settings",
    severity=Severity.MEDIUM,
    title="Weak minimum password length",
    detail="minPasswordLength is 4; at least 8 is recommended.",
    evidence={"minPasswordLength": "4"},
)

_FINDING_INFO = AuditFinding(
    check="authorities",
    severity=Severity.INFO,
    title="Account holds ALL (superuser)",
    detail="This account has unrestricted access.",
)


def _sample_report() -> AuditReport:
    """Build a two-result AuditReport for renderer tests."""
    results = [
        CheckResult(
            check="settings",
            label="System security settings",
            status=CheckStatus.OK,
            findings=[_FINDING_WITH_ANGLE],
        ),
        CheckResult(
            check="authorities",
            label="Audited account authorities",
            status=CheckStatus.OK,
            findings=[_FINDING_INFO],
        ),
    ]
    return AuditReport(
        manifest=_MANIFEST,
        results=results,
        summary=AuditSummary.from_results(results),
    )


def test_markdown_renderer_contains_severity_labels() -> None:
    """MarkdownRenderer output includes the severity value strings for each finding."""
    output = MarkdownRenderer().render(_sample_report())
    assert "MEDIUM" in output
    assert "INFO" in output


def test_markdown_renderer_contains_finding_title() -> None:
    """MarkdownRenderer output includes the finding title text."""
    output = MarkdownRenderer().render(_sample_report())
    assert "Weak minimum password length" in output


def test_markdown_renderer_contains_guardrail_note() -> None:
    """MarkdownRenderer footer contains the read-only guardrail statement."""
    output = MarkdownRenderer().render(_sample_report())
    assert "read-only GET requests" in output


def test_text_renderer_contains_severity_labels() -> None:
    """TextRenderer output includes the severity strings."""
    output = TextRenderer().render(_sample_report())
    assert "MEDIUM" in output
    assert "INFO" in output


def test_text_renderer_contains_finding_title() -> None:
    """TextRenderer output includes the finding title text."""
    output = TextRenderer().render(_sample_report())
    assert "Weak minimum password length" in output


def test_csv_renderer_has_one_header_row() -> None:
    """CsvRenderer emits exactly one header row with the expected column names."""
    output = CsvRenderer().render(_sample_report())
    lines = [line for line in output.splitlines() if line.strip()]
    assert lines[0].startswith("check,severity,title")


def test_csv_renderer_has_one_data_row_per_finding() -> None:
    """CsvRenderer emits one data row for every finding in the report."""
    report = _sample_report()
    total_findings = sum(len(r.findings) for r in report.results)
    output = CsvRenderer().render(report)
    data_lines = [line for line in output.splitlines() if line.strip()][1:]
    assert len(data_lines) == total_findings


def test_html_renderer_contains_severity_labels() -> None:
    """HtmlRenderer output includes the severity strings."""
    output = HtmlRenderer().render(_sample_report())
    assert "MEDIUM" in output
    assert "INFO" in output


def test_html_renderer_contains_finding_title() -> None:
    """HtmlRenderer output includes the finding title."""
    output = HtmlRenderer().render(_sample_report())
    assert "Weak minimum password length" in output


def test_html_renderer_contains_guardrail_note() -> None:
    """HtmlRenderer footer contains the read-only guardrail statement."""
    output = HtmlRenderer().render(_sample_report())
    assert "read-only GET requests" in output


def test_html_renderer_escapes_angle_bracket_in_title() -> None:
    """HtmlRenderer HTML-escapes a < character that appears in a finding title."""
    finding = AuditFinding(
        check="settings",
        severity=Severity.WARN,
        title="Value <8 is too low",
        detail="Some detail.",
    )
    result = CheckResult(check="settings", label="Settings", status=CheckStatus.OK, findings=[finding])
    report = AuditReport(
        manifest=_MANIFEST,
        results=[result],
        summary=AuditSummary.from_results([result]),
    )
    output = HtmlRenderer().render(report)
    assert "<8" not in output
    assert "&lt;8" in output


# ---------------------------------------------------------------------------
# 3. ReportWriter end-to-end via run_audit
# ---------------------------------------------------------------------------


async def _settings_result() -> CheckResult:
    """Return a canned settings CheckResult."""
    return CheckResult(
        check="settings",
        label="System security settings",
        status=CheckStatus.OK,
        findings=[_FINDING_WITH_ANGLE],
    )


async def _authorities_result() -> CheckResult:
    """Return a canned authorities CheckResult."""
    return CheckResult(
        check="authorities",
        label="Audited account authorities",
        status=CheckStatus.OK,
        findings=[_FINDING_INFO],
    )


def _two_bound_checks() -> list[BoundCheck]:
    """Build two BoundChecks with canned async runners."""
    return [
        BoundCheck(key="settings", label="System security settings", run=_settings_result),
        BoundCheck(key="authorities", label="Audited account authorities", run=_authorities_result),
    ]


async def test_run_audit_creates_all_output_files(tmp_path: Path) -> None:
    """run_audit writes manifest.json, report.jsonl, report.md, report.txt, report.csv, report.html."""
    folder = tmp_path / "run"
    writer = ReportWriter(
        folder,
        _MANIFEST,
        streaming_renderer=MarkdownRenderer(),
        finalize_renderers=[TextRenderer(), CsvRenderer(), HtmlRenderer()],
    )
    reporter = _plain_reporter()
    report = await run_audit(
        manifest=_MANIFEST,
        checks=_two_bound_checks(),
        writer=writer,
        reporter=reporter,
    )

    assert (folder / "manifest.json").exists()
    assert (folder / "report.jsonl").exists()
    assert (folder / "report.md").exists()
    assert (folder / "report.txt").exists()
    assert (folder / "report.csv").exists()
    assert (folder / "report.html").exists()

    spine_lines = [line for line in (folder / "report.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(spine_lines) == 2

    manifest_data = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["completed"] is True

    assert report.summary.total_findings == 2


# ---------------------------------------------------------------------------
# 4. Resume: load_prior + ReportWriter(resume=True)
# ---------------------------------------------------------------------------


async def test_resume_skips_already_completed_checks(tmp_path: Path) -> None:
    """Resuming a partial run replays the prior result and runs only the missing check."""
    folder = tmp_path / "resume-run"

    # First pass: write only the settings result, do not finalize.
    writer1 = ReportWriter(
        folder,
        _MANIFEST,
        streaming_renderer=MarkdownRenderer(),
        finalize_renderers=[TextRenderer(), CsvRenderer(), HtmlRenderer()],
    )
    settings_result = await _settings_result()
    writer1.write_result(settings_result)
    # Intentionally do not call writer1.finalize: simulates an interrupted run.
    writer1._spine.close()
    writer1._markdown.close()

    # load_prior returns the single completed result.
    loaded_manifest, prior = ReportWriter.load_prior(folder)
    assert loaded_manifest is not None
    assert len(prior) == 1
    assert prior[0].check == "settings"

    # Second pass: resume=True, run both checks; settings must not be duplicated.
    writer2 = ReportWriter(
        folder,
        _MANIFEST,
        streaming_renderer=MarkdownRenderer(),
        finalize_renderers=[TextRenderer(), CsvRenderer(), HtmlRenderer()],
        resume=True,
    )
    reporter = _plain_reporter()
    report = await run_audit(
        manifest=_MANIFEST,
        checks=_two_bound_checks(),
        writer=writer2,
        reporter=reporter,
        prior=prior,
    )

    spine_text = (folder / "report.jsonl").read_text(encoding="utf-8")
    spine_lines = [line for line in spine_text.splitlines() if line.strip()]
    assert len(spine_lines) == 2, "spine must have exactly 2 lines (no duplicate)"
    assert report.summary.checks_run == 2


# ---------------------------------------------------------------------------
# 5. Error isolation: one failing check does not abort the audit
# ---------------------------------------------------------------------------


async def _exploding_check() -> CheckResult:
    """Raise unconditionally to simulate a broken check implementation."""
    raise RuntimeError("simulated check failure")


async def test_failing_check_becomes_error_result_and_audit_continues(tmp_path: Path) -> None:
    """A check that raises produces an ERROR CheckResult; the remaining check still completes."""
    folder = tmp_path / "error-run"

    checks = [
        BoundCheck(key="settings", label="System security settings", run=_exploding_check),
        BoundCheck(key="authorities", label="Audited account authorities", run=_authorities_result),
    ]
    writer = ReportWriter(
        folder,
        _MANIFEST,
        streaming_renderer=MarkdownRenderer(),
        finalize_renderers=[TextRenderer(), CsvRenderer(), HtmlRenderer()],
    )
    reporter = _plain_reporter()
    report = await run_audit(
        manifest=_MANIFEST,
        checks=checks,
        writer=writer,
        reporter=reporter,
    )

    assert report.summary.checks_run == 2
    error_results = [r for r in report.results if r.status is CheckStatus.ERROR]
    assert len(error_results) == 1
    assert "RuntimeError" in (error_results[0].note or "")

    ok_results = [r for r in report.results if r.status is CheckStatus.OK]
    assert len(ok_results) == 1
    assert ok_results[0].check == "authorities"
