"""Audit orchestration for the v42 security plugin: open one client, run checks, stream a report."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

import httpx
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_client.v42 import Dhis2Client
from dhis2w_client.v42.auth.basic import BasicAuth
from rich.console import Console

from dhis2w_core.profile import Profile
from dhis2w_core.security_core import (
    DEFAULT_PROBE_PASSWORD,
    DEFAULT_PROBE_USERNAME,
    AuditReport,
    AuditSummary,
    BoundCheck,
    CheckResult,
    CheckStatus,
    CredentialProbeResult,
    CsvRenderer,
    HtmlRenderer,
    MarkdownRenderer,
    ReportRenderer,
    ReportWriter,
    RunManifest,
    TextRenderer,
    build_account_authorities,
    classify_probe_status,
    evaluate_account_authorities,
    evaluate_credential_probe,
    evaluate_settings,
    label_for,
    make_reporter,
    resolve_check_keys,
    run_audit,
)
from dhis2w_core.v42.client_context import open_client
from dhis2w_core.v42.plugins.security.models import SecuritySettings

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


async def _lockout_active(client: Dhis2Client) -> bool:
    """Read keyLockMultipleFailedLogins so the probe can warn before it tries a wrong password."""
    try:
        settings = await client.get("/api/systemSettings", SecuritySettings)
    except Dhis2ApiError:
        return False
    return settings.keyLockMultipleFailedLogins is True


async def _probe_default_credentials(base_url: str, *, lockout_active: bool) -> CredentialProbeResult:
    """Issue exactly one HTTP Basic GET /api/me as admin/district and classify the status."""
    auth = BasicAuth(username=DEFAULT_PROBE_USERNAME, password=DEFAULT_PROBE_PASSWORD)
    headers = {**await auth.headers(), "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=10.0), follow_redirects=False) as http:
        response = await http.get(f"{base_url}/api/me", headers=headers)
    return CredentialProbeResult(
        outcome=classify_probe_status(response.status_code),
        status_code=response.status_code,
        lockout_active=lockout_active,
    )


async def _run_credential_probe(client: Dhis2Client, console: Console) -> CheckResult:
    """Make one HTTP Basic login attempt for admin/district, warning first when lockout is active."""
    label = label_for("credential-probe")
    lockout_active = await _lockout_active(client)
    if lockout_active:
        console.print(
            f"WARNING: failed-login lockout is enabled; the single default-credential probe attempt "
            f"counts toward locking the real '{DEFAULT_PROBE_USERNAME}' account.",
            style="bold yellow",
            highlight=False,
        )
    try:
        result = await _probe_default_credentials(client.base_url, lockout_active=lockout_active)
    except httpx.HTTPError as exc:
        return CheckResult(
            check="credential-probe",
            label=label,
            status=CheckStatus.DEGRADED,
            note=f"probe transport error: {exc}",
        )
    note = (
        "failed-login lockout is enabled; the single probe attempt counts toward the lockout counter"
        if lockout_active
        else None
    )
    return CheckResult(
        check="credential-probe",
        label=label,
        status=CheckStatus.OK,
        findings=evaluate_credential_probe(result),
        note=note,
    )


def _bind(
    runner: Callable[[Dhis2Client], Awaitable[CheckResult]], client: Dhis2Client
) -> Callable[[], Awaitable[CheckResult]]:
    """Bind a check runner to an open client, yielding a zero-argument coroutine."""

    async def _run() -> CheckResult:
        return await runner(client)

    return _run


def _bind_probe(client: Dhis2Client, console: Console) -> Callable[[], Awaitable[CheckResult]]:
    """Bind the credential probe to the open client plus a console for the lockout warning."""

    async def _run() -> CheckResult:
        return await _run_credential_probe(client, console)

    return _run


def _bound_checks(client: Dhis2Client, keys: Sequence[str], console: Console) -> list[BoundCheck]:
    """Build the ordered bound checks for `keys` against the open client."""
    checks: list[BoundCheck] = []
    for key in keys:
        run = _bind_probe(client, console) if key == "credential-probe" else _bind(_RUNNERS[key], client)
        checks.append(BoundCheck(key=key, label=label_for(key), run=run))
    return checks


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
    con = console or Console(stderr=True)
    reporter = make_reporter(con, animated=animated)
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
            checks=_bound_checks(client, keys, con),
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
    con = console or Console(stderr=True)
    reporter = make_reporter(con, animated=animated)
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
            checks=_bound_checks(client, manifest.check_order, con),
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
