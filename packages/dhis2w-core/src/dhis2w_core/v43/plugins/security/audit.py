"""Audit orchestration for the v43 security plugin: open one client, run checks, stream a report."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_client.generated.v43.oas import LoginConfigResponse, Route
from dhis2w_client.v43 import Dhis2Client
from dhis2w_client.v43.auth.basic import BasicAuth
from pydantic import ValidationError
from rich.console import Console

from dhis2w_core.profile import Profile
from dhis2w_core.security_core import (
    ANONYMOUS_PROBE_TARGETS,
    DEFAULT_PROBE_PASSWORD,
    DEFAULT_PROBE_USERNAME,
    AnonymousResult,
    AuditPosture,
    AuditReport,
    AuditSummary,
    BoundCheck,
    CheckResult,
    CheckStatus,
    CorsWhitelist,
    CredentialProbeResult,
    CsvRenderer,
    ExplorerRenderer,
    FetchedGroup,
    FetchedObject,
    FetchedRole,
    FetchedShare,
    FetchedUser,
    HtmlRenderer,
    HubApp,
    InstalledApp,
    LoginProviderView,
    MarkdownRenderer,
    OAuth2ClientView,
    ReleaseFeed,
    ReportRenderer,
    ReportWriter,
    ResolvedFocusType,
    RoleAudit,
    RouteTarget,
    RunManifest,
    SchemaShareability,
    SharingGraph,
    TextRenderer,
    TokensInventory,
    TransportHeaders,
    TwoFactorSource,
    TwoFactorSummary,
    TypeInventory,
    UserHygiene,
    build_account_authorities,
    build_role_audit,
    build_sharing_graph,
    build_sharing_view,
    build_user_hygiene,
    classify_probe_status,
    compute_effective_access,
    evaluate_account_authorities,
    evaluate_apps,
    evaluate_audit_config,
    evaluate_auth_methods,
    evaluate_credential_probe,
    evaluate_guest,
    evaluate_hygiene,
    evaluate_roles,
    evaluate_routes,
    evaluate_settings,
    evaluate_sharing,
    evaluate_tokens,
    evaluate_transport,
    evaluate_two_factor_from_endpoint,
    evaluate_two_factor_from_user_field,
    evaluate_version,
    fetch_release_feed,
    label_for,
    make_reporter,
    parse_dhis2_version,
    parse_dhis_conf,
    resolve_check_keys,
    resolve_focus_types,
    run_audit,
)
from dhis2w_core.security_core.routes import host_from_url
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


async def _run_transport(client: Dhis2Client) -> CheckResult:
    """Read the TLS scheme and security headers off one /api/system/info response and evaluate them."""
    label = label_for("transport")
    scheme = urlsplit(client.base_url).scheme or "http"
    try:
        response = await client.get_response("/api/system/info")
    except (Dhis2ApiError, httpx.HTTPError) as exc:
        return CheckResult(check="transport", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    headers = TransportHeaders(
        base_url=client.base_url,
        scheme=scheme,
        strict_transport_security=response.headers.get("strict-transport-security"),
        content_security_policy=response.headers.get("content-security-policy"),
        x_frame_options=response.headers.get("x-frame-options"),
        x_content_type_options=response.headers.get("x-content-type-options"),
        server=response.headers.get("server"),
    )
    return CheckResult(check="transport", label=label, status=CheckStatus.OK, findings=evaluate_transport(headers))


async def _run_settings(client: Dhis2Client) -> CheckResult:
    """Fetch the security settings slice plus the CORS whitelist and evaluate them into findings."""
    label = label_for("settings")
    try:
        settings = await client.get("/api/systemSettings", SecuritySettings)
    except (Dhis2ApiError, httpx.HTTPError) as exc:
        return CheckResult(check="settings", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    cors = await _fetch_cors_whitelist(client)
    note = None if cors is not None else "CORS whitelist unreadable; wildcard-origin verdict skipped"
    return CheckResult(
        check="settings",
        label=label,
        status=CheckStatus.OK,
        findings=evaluate_settings(settings, cors=cors),
        note=note,
    )


async def _fetch_cors_whitelist(client: Dhis2Client) -> CorsWhitelist | None:
    """Read `/api/configuration/corsWhitelist` into a CorsWhitelist, or None when unreadable."""
    try:
        raw = await client.get_raw("/api/configuration/corsWhitelist")
    except (Dhis2ApiError, httpx.HTTPError):
        return None
    payload = raw.get("data", raw)
    if not isinstance(payload, list):
        return None
    return CorsWhitelist(origins=tuple(str(origin) for origin in payload))


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


# Route fields the check reads: identity, destination, run gating, and the discriminated auth block.
_ROUTE_FIELDS = "id,code,name,url,disabled,authorities,auth,headers,responseTimeoutSeconds"


def _route_target(route: Route) -> RouteTarget:
    """Wrap one typed oas.Route into a RouteTarget, pulling non-secret auth identity via the wire extractor."""
    url = route.url or ""
    auth_type, auth_identity = _wire.route_auth(route)
    return RouteTarget(
        uid=route.id,
        code=route.code,
        name=route.name or route.id or "unknown",
        url=url,
        host=host_from_url(url),
        disabled=bool(route.disabled),
        allows_subpaths=url.endswith("/**"),
        auth_type=auth_type,
        auth_identity=auth_identity,
        required_authorities=tuple(route.authorities or ()),
    )


async def _run_routes(client: Dhis2Client) -> CheckResult:
    """Inventory /api/routes and flag destinations on private/internal or cloud-metadata hosts (never runs a route).

    Each route is validated individually so a malformed auth block on one route (e.g. an unknown `type`
    that triggers a pydantic ValidationError) skips that route with a counted note rather than aborting
    the entire check and losing all other routes' findings.
    """
    label = label_for("routes")
    try:
        raw = await client.get_raw("/api/routes", params={"fields": _ROUTE_FIELDS, "paging": "false"})
    except (Dhis2ApiError, httpx.HTTPError) as exc:
        return CheckResult(check="routes", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    raw_routes = raw.get("routes")
    if not isinstance(raw_routes, list):
        raw_routes = []
    targets: list[RouteTarget] = []
    skipped = 0
    for raw_route in raw_routes:
        if not isinstance(raw_route, dict):
            skipped += 1
            continue
        try:
            route = Route.model_validate(raw_route)
            targets.append(_route_target(route))
        except (ValidationError, ValueError, TypeError):
            # Full validation failed -- try again without the auth block. An unrecognized or
            # missing auth `type` causes pydantic's discriminated union to reject the whole route.
            # Stripping auth and re-validating lets us include the route with auth_type="unknown"
            # so the carries-auth finding still fires when credentials are present on the wire.
            if not isinstance(raw_route.get("auth"), dict):
                skipped += 1
                continue
            try:
                route_no_auth = Route.model_validate({k: v for k, v in raw_route.items() if k != "auth"})
                url = route_no_auth.url or ""
                targets.append(
                    RouteTarget(
                        uid=route_no_auth.id,
                        code=route_no_auth.code,
                        name=route_no_auth.name or route_no_auth.id or "unknown",
                        url=url,
                        host=host_from_url(url),
                        disabled=bool(route_no_auth.disabled),
                        allows_subpaths=url.endswith("/**"),
                        auth_type="unknown",
                        auth_identity=None,
                        required_authorities=tuple(route_no_auth.authorities or ()),
                    )
                )
            except (ValidationError, ValueError, TypeError):
                skipped += 1
    note = f"{skipped} route(s) could not be parsed and were skipped" if skipped else None
    return CheckResult(check="routes", label=label, status=CheckStatus.OK, findings=evaluate_routes(targets), note=note)


# Token fields the check reads: identity, type, expiry, created timestamp, owner id, and the polymorphic
# allowlist attributes. An explicit fields= projection guarantees attributes and expire are returned. The
# secret `key` is @JsonIgnore upstream and never on the wire, so it is never requested or read.
# paging=false is required so the full inventory is returned on instances with >50 tokens; without it
# the response silently truncates to the first page and the inventory is incomplete.
_TOKEN_FIELDS = "id,name,type,expire,created,createdBy[id],attributes[type,allowedIps,allowedMethods,allowedReferrers]"


async def _account_is_superuser(client: Dhis2Client) -> bool:
    """Read /api/me/authorization and report whether the audited account holds the ALL authority.

    Reuses the same identity read the authorities check uses. The ALL authority bypasses the ACL, so an
    account with it sees the system-wide token inventory; without it the /api/apiToken list is filtered to
    the account's own tokens. A read error is treated as not-superuser so the scope caveat still fires.
    """
    try:
        raw = await client.get_raw("/api/me/authorization")
    except (Dhis2ApiError, httpx.HTTPError):
        return False
    payload = raw.get("data")
    if not isinstance(payload, list):
        return False
    return "ALL" in {str(item) for item in payload}


async def _run_tokens(client: Dhis2Client) -> CheckResult:
    """Inventory the PATs readable by the audited account and flag non-expiring / no-IP-allowlist posture.

    `now` is captured here at the I/O edge (epoch millis, UTC) and threaded into the deterministic
    `evaluate_tokens` reducer as `now_epoch_millis`, which uses it to detect expired-but-not-deleted tokens;
    the reducer itself never reads the clock. A non-superuser account sees only its own tokens, so the
    reducer adds an INFO scope caveat when `account_is_superuser` is False.
    """
    label = label_for("tokens")
    superuser = await _account_is_superuser(client)
    try:
        raw = await client.get_raw("/api/apiToken", params={"fields": _TOKEN_FIELDS, "paging": "false"})
    except (Dhis2ApiError, httpx.HTTPError) as exc:
        return CheckResult(check="tokens", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    records = raw.get("apiToken")
    if not isinstance(records, list):
        records = []
    inventory = TokensInventory(tokens=tuple(_wire.tokens_from_raw(records)), account_is_superuser=superuser)
    now_epoch_millis = int(datetime.now(tz=UTC).timestamp() * 1000)
    findings = evaluate_tokens(inventory, now_epoch_millis=now_epoch_millis)
    return CheckResult(check="tokens", label=label, status=CheckStatus.OK, findings=findings)


async def _run_auth_methods(client: Dhis2Client) -> CheckResult:
    """Inventory the external login surface: pre-auth OIDC providers and registered OAuth2 clients.

    The OIDC half (GET /api/loginConfig, pre-auth by design) is mandatory; if it fails the whole check
    degrades. The OAuth2-client half (GET /api/oAuth2Clients) requires F_OAUTH2_CLIENT_MANAGE on v42/v43, so
    a 401/403/404 (or transport error) does not fail the check: the loginConfig OIDC findings still run and
    the check degrades with a note. The client secret is never read or carried into a finding.
    """
    label = label_for("auth-methods")
    try:
        login_raw = await client.get_raw("/api/loginConfig")
    except (Dhis2ApiError, httpx.HTTPError) as exc:
        return CheckResult(check="auth-methods", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    try:
        login_config = LoginConfigResponse.model_validate(login_raw)
    except ValidationError:
        return CheckResult(
            check="auth-methods",
            label=label,
            status=CheckStatus.DEGRADED,
            note="unexpected /api/loginConfig payload shape",
        )
    oidc_providers = [
        LoginProviderView(provider_id=provider.id or "", login_text=provider.loginText)
        for provider in login_config.oidcProviders or []
    ]
    clients: list[OAuth2ClientView] | None
    note: str | None = None
    status = CheckStatus.OK
    try:
        clients_raw = await client.get_raw("/api/oAuth2Clients", params={"fields": _wire.OAUTH2_CLIENT_FIELDS})
    except (Dhis2ApiError, httpx.HTTPError) as exc:
        clients = None
        status = CheckStatus.DEGRADED
        if getattr(exc, "status_code", None) in (401, 403):
            note = f"OAuth2 clients unreadable (requires F_OAUTH2_CLIENT_MANAGE): {exc}"
        else:
            note = f"OAuth2 clients unreadable: {exc}"
    else:
        clients = _wire.oauth2_clients(clients_raw)
    findings = evaluate_auth_methods(oidc_providers=oidc_providers, oauth2_clients=clients)
    return CheckResult(check="auth-methods", label=label, status=status, findings=findings, note=note)


async def _run_audit_config(client: Dhis2Client, dhis_conf_path: Path | None) -> CheckResult:
    """Report the auditing posture: the API-only INFO when no dhis.conf is given, else the parsed verdicts.

    DHIS2 does not expose its audit configuration over the API, so this check reads nothing per-run from the
    client. With no `--dhis-conf` the posture is the unparsed (`parsed=False`) placeholder and the reducer
    emits the not-API-readable INFO. With a path, `parse_dhis_conf` reads a local copy of dhis.conf; a
    missing/unreadable/unparseable file degrades the check with a note rather than a finding about the instance.
    """
    label = label_for("audit-config")
    if dhis_conf_path is None:
        return CheckResult(
            check="audit-config",
            label=label,
            status=CheckStatus.OK,
            findings=evaluate_audit_config(AuditPosture(parsed=False)),
        )
    try:
        posture = parse_dhis_conf(dhis_conf_path)
    except (ValidationError, ValueError, TypeError, OSError) as exc:
        return CheckResult(
            check="audit-config",
            label=label,
            status=CheckStatus.DEGRADED,
            note=f"dhis.conf unreadable ({exc}); audit posture not evaluated",
        )
    return CheckResult(
        check="audit-config", label=label, status=CheckStatus.OK, findings=evaluate_audit_config(posture)
    )


_RUNNERS: dict[str, Callable[[Dhis2Client], Awaitable[CheckResult]]] = {
    "version": _run_version,
    "transport": _run_transport,
    "settings": _run_settings,
    "authorities": _run_authorities,
    "roles": _run_roles,
    "apps": _run_apps,
    "guest": _run_guest,
    "auth-methods": _run_auth_methods,
    "tokens": _run_tokens,
    "routes": _run_routes,
}

# How many objects the sharing scan pages at a time, and the default scan budget (max objects
# inspected across all focus types) when the CLI does not override --max-objects.
SHARING_PAGE_SIZE = 200
DEFAULT_SHARING_MAX_OBJECTS = 5000

# Object fields and principal fields the sharing scan reads. Objects carry only their identity plus
# the sharing block; principals carry the membership/role edges and the counts the graph needs.
_SHARING_OBJECT_FIELDS = "id,name,code,sharing"
_SHARING_USER_FIELDS = "id,username,displayName,disabled,lastLogin,userRoles[id],userGroups[id]"


def _id_list(value: Any) -> list[str]:
    """Extract the non-empty `id` values from a list of `{id: ...}` records."""
    if not isinstance(value, list):
        return []
    return [str(entry["id"]) for entry in value if isinstance(entry, dict) and entry.get("id")]


def _shares_from_block(block: Any) -> list[FetchedShare]:
    """Map a sharing `users` / `userGroups` block (uid -> {access}) into typed share records."""
    shares: list[FetchedShare] = []
    if isinstance(block, dict):
        for uid, value in block.items():
            access = value.get("access") if isinstance(value, dict) else None
            shares.append(FetchedShare(principal_uid=str(uid), access=access if isinstance(access, str) else ""))
    return shares


def _fetched_object(item: dict[str, Any], focus: ResolvedFocusType) -> FetchedObject:
    """Map one raw object record and its sharing block into a typed FetchedObject."""
    sharing = item.get("sharing")
    sharing = sharing if isinstance(sharing, dict) else {}
    owner = sharing.get("owner")
    public = sharing.get("public")
    code = item.get("code")
    return FetchedObject(
        uid=str(item.get("id", "")),
        type=focus.name,
        name=str(item.get("name") or item.get("id") or ""),
        code=code if isinstance(code, str) else None,
        data_bearing=focus.data_bearing,
        owner=owner if isinstance(owner, str) else None,
        public_access=public if isinstance(public, str) else None,
        external=bool(sharing.get("external", False)),
        user_shares=_shares_from_block(sharing.get("users")),
        group_shares=_shares_from_block(sharing.get("userGroups")),
    )


async def _fetch_shareable_focus(client: Dhis2Client) -> list[ResolvedFocusType]:
    """Read /api/schemas and resolve the curated focus set to the types this server reports shareable."""
    raw = await client.get_raw("/api/schemas", params={"fields": "name,plural,shareable,dataShareable"})
    items = raw.get("schemas")
    schemas: list[SchemaShareability] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            schemas.append(
                SchemaShareability(
                    name=str(item.get("name", "")),
                    plural=str(item.get("plural", "")),
                    shareable=bool(item.get("shareable", False)),
                    data_shareable=bool(item.get("dataShareable", False)),
                )
            )
    return resolve_focus_types(schemas)


async def _scan_focus_type(
    client: Dhis2Client, focus: ResolvedFocusType, *, budget: int
) -> tuple[int, list[FetchedObject], int, bool]:
    """Page one focus type, returning (server total, retained objects, scanned count, capped flag).

    Pages `/api/<plural>` keeping only objects with non-default sharing. Stops once `budget` objects
    have been scanned for this type, flagging that this type's scan was capped before exhausting it.
    """
    page = 1
    server_total = 0
    scanned = 0
    kept: list[FetchedObject] = []
    while True:
        raw = await client.get_raw(
            f"/api/{focus.plural}",
            params={
                "fields": _SHARING_OBJECT_FIELDS,
                "paging": "true",
                "pageSize": str(SHARING_PAGE_SIZE),
                "page": str(page),
            },
        )
        pager = raw.get("pager")
        pager = pager if isinstance(pager, dict) else {}
        if page == 1:
            total = pager.get("total")
            server_total = total if isinstance(total, int) else 0
        items = raw.get(focus.plural)
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            obj = _fetched_object(item, focus)
            scanned += 1
            if obj.has_non_default_sharing:
                kept.append(obj)
            if scanned >= budget:
                return server_total, kept, scanned, True
        page_count = pager.get("pageCount")
        if not isinstance(page_count, int) or page >= page_count:
            break
        page += 1
    return server_total, kept, scanned, False


def _parse_sharing_users(raw: dict[str, Any]) -> list[FetchedUser]:
    """Map a /api/users payload into typed user records with their role and group memberships."""
    items = raw.get("users")
    users: list[FetchedUser] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            display = item.get("displayName")
            last_login = item.get("lastLogin")
            users.append(
                FetchedUser(
                    uid=str(item.get("id", "")),
                    username=str(item.get("username", "")),
                    display_name=display if isinstance(display, str) else None,
                    disabled=bool(item.get("disabled", False)),
                    last_login=last_login if isinstance(last_login, str) else None,
                    role_uids=_id_list(item.get("userRoles")),
                    group_uids=_id_list(item.get("userGroups")),
                )
            )
    return users


def _parse_sharing_roles(raw: dict[str, Any]) -> list[FetchedRole]:
    """Map a /api/userRoles payload (with users~size) into typed role records."""
    items = raw.get("userRoles")
    roles: list[FetchedRole] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            members = item.get("users")
            roles.append(
                FetchedRole(
                    uid=str(item.get("id", "")),
                    name=str(item.get("name", "")),
                    authorities=[str(authority) for authority in (item.get("authorities") or [])],
                    member_count=members if isinstance(members, int) else 0,
                )
            )
    return roles


def _parse_sharing_groups(raw: dict[str, Any]) -> list[FetchedGroup]:
    """Map a /api/userGroups payload (with users~size and managedGroups) into typed group records."""
    items = raw.get("userGroups")
    groups: list[FetchedGroup] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            members = item.get("users")
            groups.append(
                FetchedGroup(
                    uid=str(item.get("id", "")),
                    name=str(item.get("name", "")),
                    member_count=members if isinstance(members, int) else 0,
                    managed_group_uids=_id_list(item.get("managedGroups")),
                )
            )
    return groups


async def _fetch_sharing_principals(
    client: Dhis2Client,
) -> tuple[list[FetchedUser], list[FetchedRole], list[FetchedGroup]]:
    """Read the bounded principal subgraph: users, roles, and groups in full (paging disabled)."""
    users_raw = await client.get_raw("/api/users", params={"fields": _SHARING_USER_FIELDS, "paging": "false"})
    roles_raw = await client.get_raw(
        "/api/userRoles", params={"fields": "id,name,authorities,users~size", "paging": "false"}
    )
    groups_raw = await client.get_raw(
        "/api/userGroups", params={"fields": "id,name,users~size,managedGroups[id]", "paging": "false"}
    )
    return _parse_sharing_users(users_raw), _parse_sharing_roles(roles_raw), _parse_sharing_groups(groups_raw)


async def _run_sharing(
    client: Dhis2Client, *, max_objects: int, generated_at: str, graph_sink: list[SharingGraph] | None = None
) -> CheckResult:
    """Build the sharing access graph once (focus types, capped) and reduce it into exposure findings.

    When `graph_sink` is provided (the `--sharing-graph` explorer is requested) the effective-access
    closure is computed and the graph is stashed for the explorer emitter; otherwise only the findings
    are derived. The graph is built once either way -- the findings and the explorer are projections.
    """
    label = label_for("sharing")
    objects: list[FetchedObject] = []
    inventory: list[TypeInventory] = []
    remaining = max_objects
    truncated = False
    capped_at: str | None = None
    try:
        focus_types = await _fetch_shareable_focus(client)
        for focus in focus_types:
            if remaining <= 0:
                truncated = True
                capped_at = focus.name
                break
            total, kept, scanned, capped = await _scan_focus_type(client, focus, budget=remaining)
            inventory.append(TypeInventory(type=focus.name, data_bearing=focus.data_bearing, total=total))
            objects.extend(kept)
            remaining -= scanned
            if capped:
                truncated = True
                capped_at = focus.name
                break
        users, roles, groups = await _fetch_sharing_principals(client)
    except Dhis2ApiError as exc:
        return CheckResult(check="sharing", label=label, status=CheckStatus.DEGRADED, note=f"HTTP error: {exc}")
    truncation_note = (
        f"Scanning stopped at the --max-objects budget ({max_objects}); objects from '{capped_at}' "
        "onward were not inspected, so the findings below are a lower bound."
        if truncated
        else None
    )
    graph = build_sharing_graph(
        target=client.base_url,
        generated_at=generated_at,
        objects=objects,
        users=users,
        roles=roles,
        groups=groups,
        type_inventory=inventory,
        truncated=truncated,
        truncation_note=truncation_note,
    )
    findings = evaluate_sharing(graph)
    note = truncation_note
    if graph_sink is not None:
        graph = graph.model_copy(update={"effective": compute_effective_access(graph)})
        graph_sink.append(graph)
        explorer_note = "Interactive explorer generated: open sharing-explorer.html for the effective-access graph."
        note = f"{truncation_note} {explorer_note}" if truncation_note else explorer_note
    return CheckResult(check="sharing", label=label, status=CheckStatus.OK, findings=findings, note=note)


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


def _bind_sharing(
    client: Dhis2Client, *, max_objects: int, generated_at: str, graph_sink: list[SharingGraph] | None
) -> Callable[[], Awaitable[CheckResult]]:
    """Bind the sharing check to the open client, its scan budget, the run's timestamp, and the sink."""

    async def _run() -> CheckResult:
        return await _run_sharing(client, max_objects=max_objects, generated_at=generated_at, graph_sink=graph_sink)

    return _run


def _bind_audit_config(client: Dhis2Client, *, dhis_conf_path: Path | None) -> Callable[[], Awaitable[CheckResult]]:
    """Bind the audit-config check to the open client and the optional local dhis.conf path."""

    async def _run() -> CheckResult:
        return await _run_audit_config(client, dhis_conf_path)

    return _run


def _bound_checks(
    client: Dhis2Client,
    keys: Sequence[str],
    console: Console,
    *,
    stale_days: int,
    now: datetime,
    two_factor_detail: bool,
    max_objects: int,
    generated_at: str,
    dhis_conf_path: Path | None = None,
    graph_sink: list[SharingGraph] | None = None,
) -> list[BoundCheck]:
    """Build the ordered bound checks for `keys` against the open client."""
    checks: list[BoundCheck] = []
    for key in keys:
        if key == "credential-probe":
            run = _bind_probe(client, console)
        elif key == "hygiene":
            run = _bind_hygiene(client, stale_days=stale_days, now=now, two_factor_detail=two_factor_detail)
        elif key == "sharing":
            run = _bind_sharing(client, max_objects=max_objects, generated_at=generated_at, graph_sink=graph_sink)
        elif key == "audit-config":
            run = _bind_audit_config(client, dhis_conf_path=dhis_conf_path)
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


def _emit_explorer_if_requested(
    folder: Path, graph_sink: list[SharingGraph], manifest: RunManifest, *, visualize: bool
) -> None:
    """Write the interactive explorer bundle into the run folder when the graph was captured for it."""
    if not (visualize and graph_sink):
        return
    view = build_sharing_view(
        graph_sink[0],
        profile=manifest.profile,
        version=manifest.dhis2_version or "unknown",
        scanner=manifest.scanner_version,
    )
    ExplorerRenderer().emit(folder, view)


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
    max_objects: int = DEFAULT_SHARING_MAX_OBJECTS,
    dhis_conf_path: Path | None = None,
    visualize: bool = False,
    animated: bool = True,
    console: Console | None = None,
) -> AuditReport:
    """Open one client, run the selected checks in order, and stream the report to `output_dir`."""
    _validate_formats(formats)
    keys = resolve_check_keys(only, skip)
    con = console or Console(stderr=True)
    reporter = make_reporter(con, animated=animated)
    graph_sink: list[SharingGraph] = []
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
        report = await run_audit(
            manifest=manifest,
            checks=_bound_checks(
                client,
                keys,
                con,
                stale_days=stale_days,
                now=_started_at_to_now(started_at),
                two_factor_detail=two_factor_detail,
                max_objects=max_objects,
                generated_at=started_at,
                dhis_conf_path=dhis_conf_path,
                graph_sink=graph_sink if visualize else None,
            ),
            writer=writer,
            reporter=reporter,
        )
        _emit_explorer_if_requested(output_dir, graph_sink, manifest, visualize=visualize)
        return report


async def resume_security_audit(
    profile: Profile,
    *,
    folder: Path,
    profile_name: str,
    formats: Sequence[str] = DEFAULT_FORMATS,
    stale_days: int = 90,
    two_factor_detail: bool = False,
    max_objects: int = DEFAULT_SHARING_MAX_OBJECTS,
    dhis_conf_path: Path | None = None,
    visualize: bool = False,
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
    graph_sink: list[SharingGraph] = []
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
        report = await run_audit(
            manifest=manifest,
            checks=_bound_checks(
                client,
                manifest.check_order,
                con,
                stale_days=stale_days,
                now=_started_at_to_now(manifest.started_at),
                two_factor_detail=two_factor_detail,
                max_objects=max_objects,
                generated_at=manifest.started_at,
                dhis_conf_path=dhis_conf_path,
                graph_sink=graph_sink if visualize else None,
            ),
            writer=writer,
            reporter=reporter,
            prior=prior,
        )
        _emit_explorer_if_requested(folder, graph_sink, manifest, visualize=visualize)
        return report


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
