"""The version-invariant audit loop: run checks in order, stream, report progress."""

from __future__ import annotations

from collections.abc import Sequence

from dhis2w_core.security_core.registry import BoundCheck
from dhis2w_core.security_core.report.base import ProgressReporter
from dhis2w_core.security_core.report.model import AuditReport, AuditSummary, CheckResult, CheckStatus, RunManifest
from dhis2w_core.security_core.report.progress import AUDIT_ACTIVITY, result_style, result_summary, scorecard
from dhis2w_core.security_core.streaming import ReportWriter


async def run_audit(
    *,
    manifest: RunManifest,
    checks: Sequence[BoundCheck],
    writer: ReportWriter,
    reporter: ProgressReporter,
    prior: Sequence[CheckResult] = (),
) -> AuditReport:
    """Run each check in order, streaming results and driving the progress display.

    `prior` carries already-completed results from a resumed run: those steps
    are surfaced to the progress display but neither re-run nor re-written. Any
    exception raised by a check becomes an ERROR result so one failing check
    never aborts the whole audit.
    """
    total = len(checks)
    results: list[CheckResult] = list(prior)
    done: dict[str, CheckResult] = {result.check: result for result in results}

    reporter.start(total, activity=AUDIT_ACTIVITY)
    try:
        for index, check in enumerate(checks, start=1):
            reporter.step(index, total, check.label)
            cached = done.get(check.key)
            if cached is not None:
                _report_result(reporter, index, total, cached)
                continue
            try:
                result = await check.run()
            except Exception as exc:  # one check must never abort the audit
                result = CheckResult(
                    check=check.key,
                    label=check.label,
                    status=CheckStatus.ERROR,
                    note=f"{type(exc).__name__}: {exc}",
                )
            results.append(result)
            writer.write_result(result)
            _report_result(reporter, index, total, result)

        summary = AuditSummary.from_results(results)
        report = AuditReport(
            manifest=manifest.model_copy(update={"completed": True}),
            results=results,
            summary=summary,
        )
        writer.finalize(report)
    finally:
        writer.close()
        # Tear the live display down on EVERY exit path: an exception from write_result/finalize/close
        # must not leave the Rich Live refresh thread running with the terminal corrupted. On success,
        # finish() below still prints the scorecard; stop() is idempotent.
        reporter.stop()
    reporter.finish(scorecard(summary))
    return report


def _report_result(reporter: ProgressReporter, index: int, total: int, result: CheckResult) -> None:
    """Hand one completed check to the progress display as a label, a summary line, and a style."""
    reporter.complete(index, total, result.label, result_summary(result), style=result_style(result))
