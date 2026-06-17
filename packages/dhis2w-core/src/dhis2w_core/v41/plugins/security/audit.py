"""Audit orchestration for the v41 security plugin: open one client, run checks, stream a report."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from dhis2w_client.errors import Dhis2ApiError
from dhis2w_client.v41 import Dhis2Client
from rich.console import Console

from dhis2w_core.profile import Profile
from dhis2w_core.security_core import (
    AuditReport,
    AuditSummary,
    BoundCheck,
    CheckResult,
    CheckStatus,
    CsvRenderer,
    HtmlRenderer,
    MarkdownRenderer,
    ReportRenderer,
    ReportWriter,
    RunManifest,
    TextRenderer,
    build_account_authorities,
    evaluate_account_authorities,
    evaluate_settings,
    label_for,
    make_reporter,
    resolve_check_keys,
    run_audit,
)
from dhis2w_core.v41.client_context import open_client
from dhis2w_core.v41.plugins.security.models import SecuritySettings

DEFAULT_FORMATS: tuple[str, ...] = ("md", "txt", "csv", "html")

_FINALIZE_RENDERERS: dict[str, Callable[[], ReportRenderer]] = {
    "txt": TextRenderer,
    "csv": CsvRenderer,
    "html": HtmlRenderer,
}
_ALL_RENDERERS: dict[str, Callable[[], ReportRenderer]] = {"md": MarkdownRenderer, **_FINALIZE_RENDERERS}


def scanner_version() -> str:
    """Return the installed dhis2w-core version, or 'unknown' when run off-tree."""
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _version

    try:
        return _version("dhis2w-core")
    except PackageNotFoundError:
        return "unknown"


async def _run_settings(client: Dhis2Client) -> CheckResult:
    """Fetch the security settings slice and evaluate it into findings."""
    label = label_for("settings")
    try:
        settings = await client.get("/api/systemSettings", SecuritySettings)
    except Dhis2ApiError as exc:
        return CheckResult(check="settings", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    return CheckResult(check="settings", label=label, status=CheckStatus.OK, findings=evaluate_settings(settings))


async def _run_authorities(client: Dhis2Client) -> CheckResult:
    """Fetch the audited account's authorities and categorise them into findings."""
    label = label_for("authorities")
    try:
        raw = await client.get_raw("/api/me/authorization")
    except Dhis2ApiError as exc:
        return CheckResult(check="authorities", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    payload = raw.get("data")
    if not isinstance(payload, list):
        return CheckResult(
            check="authorities",
            label=label,
            status=CheckStatus.DEGRADED,
            note="unexpected /api/me/authorization payload shape",
        )
    account = build_account_authorities([str(item) for item in payload])
    return CheckResult(
        check="authorities",
        label=label,
        status=CheckStatus.OK,
        findings=evaluate_account_authorities(account),
    )


_RUNNERS: dict[str, Callable[[Dhis2Client], Awaitable[CheckResult]]] = {
    "settings": _run_settings,
    "authorities": _run_authorities,
}


def _bind(
    runner: Callable[[Dhis2Client], Awaitable[CheckResult]], client: Dhis2Client
) -> Callable[[], Awaitable[CheckResult]]:
    """Bind a check runner to an open client, yielding a zero-argument coroutine."""

    async def _run() -> CheckResult:
        return await runner(client)

    return _run


def _bound_checks(client: Dhis2Client, keys: Sequence[str]) -> list[BoundCheck]:
    """Build the ordered bound checks for `keys` against the open client."""
    return [BoundCheck(key=key, label=label_for(key), run=_bind(_RUNNERS[key], client)) for key in keys]


def _validate_formats(formats: Sequence[str]) -> None:
    """Raise ValueError if any requested report format is not a known format."""
    unknown = sorted({fmt for fmt in formats if fmt not in _ALL_RENDERERS})
    if unknown:
        raise ValueError(f"unknown report format(s): {', '.join(unknown)}; valid formats: {', '.join(_ALL_RENDERERS)}")


def _finalize_renderers(formats: Sequence[str]) -> list[ReportRenderer]:
    """Instantiate the non-streaming renderers selected by `formats` (Markdown streams live)."""
    chosen = set(formats)
    return [factory() for fmt, factory in _FINALIZE_RENDERERS.items() if fmt in chosen]


def _safe_raw_version(client: Dhis2Client) -> str | None:
    """Best-effort raw DHIS2 version string; None when connect has not primed it."""
    try:
        return client.raw_version
    except RuntimeError:
        return None


async def run_security_audit(
    profile: Profile,
    *,
    output_dir: Path,
    profile_name: str,
    started_at: str,
    only: list[str] | None = None,
    skip: list[str] | None = None,
    formats: Sequence[str] = DEFAULT_FORMATS,
    animated: bool = True,
    console: Console | None = None,
) -> AuditReport:
    """Open one client, run the selected checks in order, and stream the report to `output_dir`."""
    _validate_formats(formats)
    keys = resolve_check_keys(only, skip)
    reporter = make_reporter(console or Console(stderr=True), animated=animated)
    async with open_client(profile, profile_name=profile_name) as client:
        manifest = RunManifest(
            target=client.base_url,
            profile=profile_name,
            scanner_version=scanner_version(),
            started_at=started_at,
            dhis2_version=_safe_raw_version(client),
            check_order=keys,
        )
        writer = ReportWriter(
            output_dir,
            manifest,
            streaming_renderer=MarkdownRenderer(),
            finalize_renderers=_finalize_renderers(formats),
        )
        return await run_audit(
            manifest=manifest,
            checks=_bound_checks(client, keys),
            writer=writer,
            reporter=reporter,
        )


async def resume_security_audit(
    profile: Profile,
    *,
    folder: Path,
    profile_name: str,
    formats: Sequence[str] = DEFAULT_FORMATS,
    animated: bool = True,
    console: Console | None = None,
) -> AuditReport:
    """Resume an interrupted run in `folder`, skipping checks already in the JSONL spine."""
    manifest, prior = ReportWriter.load_prior(folder)
    if manifest is None:
        raise FileNotFoundError(f"no audit manifest found in {folder}")
    if manifest.profile != profile_name:
        raise ValueError(f"resume folder was scanned under profile '{manifest.profile}', not '{profile_name}'")
    _validate_formats(formats)
    if manifest.completed:
        # Nothing left to scan; just re-render so we never append a second footer.
        return rerender_report(folder, formats=formats)
    reporter = make_reporter(console or Console(stderr=True), animated=animated)
    async with open_client(profile, profile_name=profile_name) as client:
        if client.base_url != manifest.target:
            raise ValueError(
                f"resume folder targets {manifest.target}, but profile '{profile_name}' "
                f"now connects to {client.base_url}"
            )
        writer = ReportWriter(
            folder,
            manifest,
            streaming_renderer=MarkdownRenderer(),
            finalize_renderers=_finalize_renderers(formats),
            resume=True,
        )
        return await run_audit(
            manifest=manifest,
            checks=_bound_checks(client, manifest.check_order),
            writer=writer,
            reporter=reporter,
            prior=prior,
        )


def rerender_report(folder: Path, *, formats: Sequence[str] = DEFAULT_FORMATS) -> AuditReport:
    """Re-render an existing run's report files from its JSONL spine, without re-scanning."""
    _validate_formats(formats)
    manifest, results = ReportWriter.load_prior(folder)
    if manifest is None:
        raise FileNotFoundError(f"no audit manifest found in {folder}")
    report = AuditReport(manifest=manifest, results=results, summary=AuditSummary.from_results(results))
    chosen = set(formats)
    for fmt, factory in _ALL_RENDERERS.items():
        if fmt in chosen:
            renderer = factory()
            (folder / f"report.{renderer.suffix}").write_text(renderer.render(report), encoding="utf-8")
    return report
