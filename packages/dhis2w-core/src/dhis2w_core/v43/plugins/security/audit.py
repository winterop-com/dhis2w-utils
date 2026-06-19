"""Audit orchestration for the v43 security plugin: open one client, run checks, stream a report."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_client.v43 import Dhis2Client
from dhis2w_client.v43.auth.basic import BasicAuth
from rich.console import Console

from dhis2w_core.profile import Profile
from dhis2w_core.security_core import (
    ANONYMOUS_PROBE_TARGETS,
    DEFAULT_PROBE_PASSWORD,
    DEFAULT_PROBE_USERNAME,
    AnonymousResult,
    AuditReport,
    AuditSummary,
    BoundCheck,
    CheckResult,
    CheckStatus,
    CredentialProbeResult,
    CsvRenderer,
    HtmlRenderer,
    HubApp,
    InstalledApp,
    MarkdownRenderer,
    ReleaseFeed,
    ReportRenderer,
    ReportWriter,
    RoleAudit,
    RunManifest,
    TextRenderer,
    TwoFactorSource,
    TwoFactorSummary,
    UserHygiene,
    build_account_authorities,
    build_role_audit,
    build_user_hygiene,
    classify_probe_status,
    evaluate_account_authorities,
    evaluate_apps,
    evaluate_credential_probe,
    evaluate_guest,
    evaluate_hygiene,
    evaluate_roles,
    evaluate_settings,
    evaluate_two_factor_from_endpoint,
    evaluate_two_factor_from_user_field,
    evaluate_version,
    fetch_release_feed,
    label_for,
    make_reporter,
    parse_dhis2_version,
    resolve_check_keys,
    run_audit,
)
from dhis2w_core.v43.client_context import open_client
from dhis2w_core.v43.plugins.security import _wire
from dhis2w_core.v43.plugins.security.models import SecuritySettings

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


async def _run_version(client: Dhis2Client) -> CheckResult:
    """Classify the running DHIS2 version against EOL/outdated lines and the advisory patch floor."""
    label = label_for("version")
    parsed = parse_dhis2_version(_safe_raw_version(client))
    note: str | None = None
    feed: ReleaseFeed | None
    try:
        feed = await fetch_release_feed()
    except httpx.HTTPError as exc:
        feed = None
        note = f"release feed unavailable ({exc}); EOL and upgrade checks limited to the static advisory floor"
    return CheckResult(
        check="version", label=label, status=CheckStatus.OK, findings=evaluate_version(parsed, feed), note=note
    )


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


async def _run_roles(client: Dhis2Client) -> CheckResult:
    """Fetch the instance's user roles with member counts and classify their authority reach."""
    label = label_for("roles")
    try:
        raw = await client.get_raw(
            "/api/userRoles", params={"fields": "id,name,authorities,users~size", "paging": "false"}
        )
    except Dhis2ApiError as exc:
        return CheckResult(check="roles", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    items = raw.get("userRoles")
    if not isinstance(items, list):
        return CheckResult(
            check="roles", label=label, status=CheckStatus.DEGRADED, note="unexpected /api/userRoles payload shape"
        )
    roles: list[RoleAudit] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        members = item.get("users")
        roles.append(
            build_role_audit(
                role_id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                authorities=[str(authority) for authority in (item.get("authorities") or [])],
                member_count=members if isinstance(members, int) else 0,
            )
        )
    return CheckResult(check="roles", label=label, status=CheckStatus.OK, findings=evaluate_roles(roles))


def _coerce_int(value: Any) -> int:
    """Coerce a JSON value to int, defaulting to 0 for anything non-integer."""
    return value if isinstance(value, int) else 0


def _coerce_float(value: Any) -> float:
    """Coerce a JSON value to float, defaulting to 0.0 for anything non-numeric."""
    return float(value) if isinstance(value, int | float) else 0.0


def _role_id_sets(roles_raw: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Build (ALL-role ids, dangerous-role ids) from a /api/userRoles payload."""
    all_ids: set[str] = set()
    dangerous_ids: set[str] = set()
    items = roles_raw.get("userRoles")
    if not isinstance(items, list):
        return all_ids, dangerous_ids
    for item in items:
        if not isinstance(item, dict):
            continue
        role = build_role_audit(
            role_id=str(item.get("id", "")),
            name=str(item.get("name", "")),
            authorities=[str(authority) for authority in (item.get("authorities") or [])],
            member_count=0,
        )
        if role.is_all:
            all_ids.add(role.id)
        if role.is_all or role.categories:
            dangerous_ids.add(role.id)
    return all_ids, dangerous_ids


def _build_users(items: list[Any], all_role_ids: set[str], dangerous_role_ids: set[str]) -> list[UserHygiene]:
    """Wrap raw /api/users records into typed hygiene views via the per-tree wire extractors."""
    users: list[UserHygiene] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        role_ids = [str(role.get("id", "")) for role in (item.get("userRoles") or []) if isinstance(role, dict)]
        email = item.get("email")
        users.append(
            build_user_hygiene(
                user_id=str(item.get("id", "")),
                username=str(item.get("username", "")),
                disabled=bool(item.get("disabled", False)),
                email=email if isinstance(email, str) else None,
                last_login=_wire.last_login(item),
                two_factor=_wire.two_factor_enabled(item),
                role_ids=role_ids,
                all_role_ids=all_role_ids,
                dangerous_role_ids=dangerous_role_ids,
            )
        )
    return users


async def _fetch_two_factor_summary(client: Dhis2Client) -> tuple[TwoFactorSummary | None, str | None]:
    """Read the superuser-only 2FA summary; degrade with a note when absent (404) or forbidden (403)."""
    try:
        raw = await client.get_raw("/api/users/twoFactor/summary")
    except Dhis2ApiError as exc:
        return None, f"2FA audit endpoint unavailable ({exc}); superuser-2FA coverage not checked"
    privileged = raw.get("privileged")
    privileged = privileged if isinstance(privileged, dict) else {}
    summary = TwoFactorSummary(
        total_users=_coerce_int(raw.get("totalUsers")),
        enabled=_coerce_int(raw.get("enabled")),
        disabled=_coerce_int(raw.get("disabled")),
        coverage_percent=_coerce_float(raw.get("coveragePercent")),
        privileged_with_all=_coerce_int(privileged.get("withAllAuthority")),
        privileged_missing_2fa=_coerce_int(privileged.get("withAllAuthorityMissing2FA")),
    )
    return summary, None


async def _fetch_disabled_2fa_ids(client: Dhis2Client) -> set[str] | None:
    """Read the per-user list of accounts with 2FA disabled (ids only); None on error."""
    try:
        raw = await client.get_raw("/api/users/twoFactor", params={"status": "DISABLED", "paging": "false"})
    except Dhis2ApiError:
        return None
    items = raw.get("users")
    if not isinstance(items, list):
        return None
    return {str(item.get("id", "")) for item in items if isinstance(item, dict)}


async def _run_hygiene(client: Dhis2Client, *, stale_days: int, now: datetime, two_factor_detail: bool) -> CheckResult:
    """Audit per-user hygiene over privileged accounts, joined to login and 2FA posture."""
    label = label_for("hygiene")
    try:
        roles_raw = await client.get_raw("/api/userRoles", params={"fields": "id,authorities", "paging": "false"})
        users_raw = await client.get_raw("/api/users", params={"fields": _wire.USER_FIELDS, "paging": "false"})
    except Dhis2ApiError as exc:
        return CheckResult(check="hygiene", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    user_items = users_raw.get("users")
    if not isinstance(user_items, list):
        return CheckResult(
            check="hygiene", label=label, status=CheckStatus.DEGRADED, note="unexpected /api/users payload shape"
        )
    all_role_ids, dangerous_role_ids = _role_id_sets(roles_raw)
    users = _build_users(user_items, all_role_ids, dangerous_role_ids)
    findings = evaluate_hygiene(users, stale_days=stale_days, now=now)
    note: str | None = None
    if _wire.TWO_FACTOR_SOURCE == TwoFactorSource.USER_FIELD:
        findings.extend(evaluate_two_factor_from_user_field(users))
    else:
        summary, note = await _fetch_two_factor_summary(client)
        disabled_ids = await _fetch_disabled_2fa_ids(client) if (two_factor_detail and summary is not None) else None
        findings.extend(evaluate_two_factor_from_endpoint(summary=summary, users=users, disabled_2fa_ids=disabled_ids))
    return CheckResult(check="hygiene", label=label, status=CheckStatus.OK, findings=findings, note=note)


async def _custom_code_flags(client: Dhis2Client) -> tuple[bool, bool]:
    """Read keyCustomJs / keyCustomCss; True for each when set to a non-empty value."""
    try:
        raw = await client.get_raw("/api/systemSettings", params={"key": ["keyCustomJs", "keyCustomCss"]})
    except Dhis2ApiError:
        return False, False
    custom_js = raw.get("keyCustomJs")
    custom_css = raw.get("keyCustomCss")
    return (
        isinstance(custom_js, str) and bool(custom_js.strip()),
        isinstance(custom_css, str) and bool(custom_css.strip()),
    )


async def _run_apps(client: Dhis2Client) -> CheckResult:
    """Inventory installed apps for side-loaded code, available hub updates, and custom JS/CSS."""
    label = label_for("apps")
    try:
        installed_apps = await client.apps.list_apps()
    except Dhis2ApiError as exc:
        return CheckResult(check="apps", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    installed = [
        InstalledApp(
            name=app.name or app.key or "unknown",
            version=app.version,
            app_hub_id=app.app_hub_id,
            bundled=bool(app.bundled),
            core_app=bool(app.core_app),
        )
        for app in installed_apps
    ]
    hub: list[HubApp] | None
    note: str | None = None
    try:
        catalog = await client.apps.hub_list()
    except (Dhis2ApiError, httpx.HTTPError) as exc:
        hub = None
        note = f"App Hub unreachable ({exc}); update-available checks skipped"
    else:
        hub = []
        for entry in catalog:
            hub_id = entry.id
            if hub_id is None:
                continue
            hub.append(HubApp(app_hub_id=hub_id, versions=[ver for ver in (v.version for v in entry.versions) if ver]))
    custom_js, custom_css = await _custom_code_flags(client)
    findings = evaluate_apps(installed=installed, hub=hub, custom_js=custom_js, custom_css=custom_css)
    return CheckResult(check="apps", label=label, status=CheckStatus.OK, findings=findings, note=note)


async def _probe_anonymous(base_url: str) -> list[AnonymousResult]:
    """GET each login-required endpoint with no credentials, recording the status (None on transport error)."""
    results: list[AnonymousResult] = []
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=10.0), follow_redirects=False) as http:
        for target in ANONYMOUS_PROBE_TARGETS:
            try:
                response = await http.get(f"{base_url}{target.path}", headers=headers)
            except httpx.HTTPError:
                results.append(AnonymousResult(path=target.path))
            else:
                results.append(
                    AnonymousResult(
                        path=target.path,
                        status_code=response.status_code,
                        content_type=response.headers.get("content-type"),
                    )
                )
    return results


async def _self_registration_role(client: Dhis2Client) -> str | None:
    """Return the self-registration role name when self-registration is enabled, else None."""
    try:
        raw = await client.get_raw("/api/configuration/selfRegistrationRole")
    except Dhis2ApiError:
        return None
    name = raw.get("name") or raw.get("displayName") or raw.get("id")
    return name if isinstance(name, str) else None


async def _run_guest(client: Dhis2Client) -> CheckResult:
    """Probe anonymous read access and report self-registration and account-recovery posture."""
    label = label_for("guest")
    anonymous = await _probe_anonymous(client.base_url)
    role = await _self_registration_role(client)
    account_recovery = False
    note: str | None = None
    try:
        settings = await client.get("/api/systemSettings", SecuritySettings)
    except Dhis2ApiError as exc:
        note = f"system settings unavailable ({exc}); account-recovery state not checked"
    else:
        account_recovery = settings.keyAccountRecovery is True
    findings = evaluate_guest(anonymous=anonymous, self_registration_role=role, account_recovery=account_recovery)
    return CheckResult(check="guest", label=label, status=CheckStatus.OK, findings=findings, note=note)


_RUNNERS: dict[str, Callable[[Dhis2Client], Awaitable[CheckResult]]] = {
    "version": _run_version,
    "settings": _run_settings,
    "authorities": _run_authorities,
    "roles": _run_roles,
    "apps": _run_apps,
    "guest": _run_guest,
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


def _bind_hygiene(
    client: Dhis2Client, *, stale_days: int, now: datetime, two_factor_detail: bool
) -> Callable[[], Awaitable[CheckResult]]:
    """Bind the hygiene check to the open client and its run-time options."""

    async def _run() -> CheckResult:
        return await _run_hygiene(client, stale_days=stale_days, now=now, two_factor_detail=two_factor_detail)

    return _run


def _bound_checks(
    client: Dhis2Client,
    keys: Sequence[str],
    console: Console,
    *,
    stale_days: int,
    now: datetime,
    two_factor_detail: bool,
) -> list[BoundCheck]:
    """Build the ordered bound checks for `keys` against the open client."""
    checks: list[BoundCheck] = []
    for key in keys:
        if key == "credential-probe":
            run = _bind_probe(client, console)
        elif key == "hygiene":
            run = _bind_hygiene(client, stale_days=stale_days, now=now, two_factor_detail=two_factor_detail)
        else:
            run = _bind(_RUNNERS[key], client)
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


def _started_at_to_now(started_at: str) -> datetime:
    """Parse the run's started_at stamp into the reference time for staleness math."""
    try:
        return datetime.fromisoformat(started_at)
    except ValueError:
        return datetime.now()


async def run_security_audit(
    profile: Profile,
    *,
    output_dir: Path,
    profile_name: str,
    started_at: str,
    only: list[str] | None = None,
    skip: list[str] | None = None,
    formats: Sequence[str] = DEFAULT_FORMATS,
    stale_days: int = 90,
    two_factor_detail: bool = False,
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
            checks=_bound_checks(
                client,
                keys,
                con,
                stale_days=stale_days,
                now=_started_at_to_now(started_at),
                two_factor_detail=two_factor_detail,
            ),
            writer=writer,
            reporter=reporter,
        )


async def resume_security_audit(
    profile: Profile,
    *,
    folder: Path,
    profile_name: str,
    formats: Sequence[str] = DEFAULT_FORMATS,
    stale_days: int = 90,
    two_factor_detail: bool = False,
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
            checks=_bound_checks(
                client,
                manifest.check_order,
                con,
                stale_days=stale_days,
                now=_started_at_to_now(manifest.started_at),
                two_factor_detail=two_factor_detail,
            ),
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
            factory().emit(folder, report)
    return report
