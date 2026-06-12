"""Workspace drift-detection probes — verify BUGS.md workarounds still apply.

These probes exist to catch when DHIS2 fixes an upstream bug — our `pass`
turns to `warn` and we know to clean up the corresponding workaround.
They're not the operator-facing default (run via `d2w doctor bugs`).
"""

from __future__ import annotations

from dhis2w_client.v43 import Dhis2ApiError, Dhis2Client

from dhis2w_core.v43.plugins.doctor._models import ProbeResult

_MIN_DHIS2_VERSION: tuple[int, int] = (2, 42)


async def probe_version(client: Dhis2Client) -> ProbeResult:
    """Check `/api/system/info` → version >= 2.42."""
    try:
        info = await client.get_raw("/api/system/info")
    except Exception as exc:  # noqa: BLE001 — probe must report, not raise
        return ProbeResult(
            name="dhis2-version", category="bugs", status="fail", message=f"/api/system/info failed: {exc}"
        )
    raw = str(info.get("version", ""))
    parts = raw.split(".")
    try:
        major, minor = int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return ProbeResult(
            name="dhis2-version",
            category="bugs",
            status="fail",
            message=f"could not parse DHIS2 version {raw!r} from /api/system/info",
        )
    if (major, minor) < _MIN_DHIS2_VERSION:
        return ProbeResult(
            name="dhis2-version",
            category="bugs",
            status="fail",
            message=f"DHIS2 {raw} < 2.42 — workspace requires 2.42+",
        )
    return ProbeResult(
        name="dhis2-version",
        category="bugs",
        status="pass",
        message=f"{raw} (workspace requires 2.42+)",
    )


async def probe_auth(client: Dhis2Client) -> ProbeResult:
    """Check `/api/me` — authentication works, user has a username."""
    try:
        me = await client.get_raw("/api/me", params={"fields": "id,username,displayName"})
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(name="auth", category="bugs", status="fail", message=f"/api/me failed: {exc}")
    username = str(me.get("username", ""))
    if not username:
        return ProbeResult(name="auth", category="bugs", status="fail", message="/api/me returned no username")
    return ProbeResult(name="auth", category="bugs", status="pass", message=f"authenticated as {username}")


async def probe_analytics_rawdata_json_suffix(client: Dhis2Client) -> ProbeResult:
    """Check BUGS.md #1 — `/api/analytics/rawData` requires `.json` suffix."""
    without_suffix_404 = False
    try:
        await client.get_raw(
            "/api/analytics/rawData",
            params={"dimension": ["dx:nonexistent", "pe:LAST_12_MONTHS"]},
        )
    except Dhis2ApiError as exc:
        without_suffix_404 = exc.status_code == 404
    except Exception:  # noqa: BLE001
        pass
    if not without_suffix_404:
        return ProbeResult(
            name="analytics-rawdata-json-suffix",
            category="bugs",
            status="warn",
            message="GET /api/analytics/rawData (no suffix) didn't 404 — upstream may have fixed content negotiation",
            bugs_ref="BUGS.md #1",
        )
    return ProbeResult(
        name="analytics-rawdata-json-suffix",
        category="bugs",
        status="pass",
        message="404 without .json as expected (workaround still needed)",
        bugs_ref="BUGS.md #1",
    )


async def probe_oauth2_discovery(client: Dhis2Client) -> ProbeResult:
    """Check `/.well-known/openid-configuration` — OAuth2 discovery endpoint."""
    try:
        discovery = await client.get_raw("/.well-known/openid-configuration")
    except Dhis2ApiError as exc:
        if exc.status_code == 404:
            return ProbeResult(
                name="oauth2-discovery",
                category="bugs",
                status="skip",
                message="OAuth2 not enabled (no /.well-known/openid-configuration)",
                bugs_ref="BUGS.md #4",
            )
        return ProbeResult(
            name="oauth2-discovery",
            category="bugs",
            status="fail",
            message=f"discovery returned {exc.status_code}",
        )
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(name="oauth2-discovery", category="bugs", status="fail", message=f"discovery failed: {exc}")
    required = {"authorization_endpoint", "token_endpoint", "jwks_uri"}
    missing = sorted(required - set(discovery))
    if missing:
        return ProbeResult(
            name="oauth2-discovery",
            category="bugs",
            status="fail",
            message=f"discovery missing fields: {missing}",
            bugs_ref="BUGS.md #4",
        )
    issuer = discovery.get("issuer", "?")
    return ProbeResult(
        name="oauth2-discovery",
        category="bugs",
        status="pass",
        message=f"issuer={issuer}, all required fields present",
    )


async def probe_login_config(client: Dhis2Client) -> ProbeResult:
    """Check `/api/loginConfig` — informational summary DHIS2's login app renders."""
    try:
        config = await client.get_raw("/api/loginConfig")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            name="login-config",
            category="bugs",
            status="fail",
            message=f"/api/loginConfig failed: {exc}",
        )
    providers = config.get("oidcProviders") or []
    provider_ids = [p.get("id", "?") for p in providers]
    return ProbeResult(
        name="login-config",
        category="bugs",
        status="pass",
        message=(
            f"title={config.get('applicationTitle', '?')!r} "
            f"oidc-providers={provider_ids} "
            f"useCustomLogoFront={config.get('useCustomLogoFront')}"
        ),
    )


async def probe_userrole_schema_naming(client: Dhis2Client) -> ProbeResult:
    """Check BUGS.md #8 — `/api/schemas/userRole` still mis-pluralizes `authorities` as `authoritys`."""
    try:
        schema = await client.get_raw("/api/schemas/userRole")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            name="userrole-authorities-naming",
            category="bugs",
            status="fail",
            message=f"/api/schemas/userRole failed: {exc}",
            bugs_ref="BUGS.md #8",
        )
    properties = schema.get("properties") or []
    candidate = next(
        (p for p in properties if p.get("name") == "authority" or p.get("fieldName") == "authorities"),
        None,
    )
    if candidate is None:
        return ProbeResult(
            name="userrole-authorities-naming",
            category="bugs",
            status="warn",
            message="UserRole authorities/authority field not found in schema",
            bugs_ref="BUGS.md #8",
        )
    name = candidate.get("name")
    field_name = candidate.get("fieldName")
    if name == "authority" and field_name == "authorities":
        return ProbeResult(
            name="userrole-authorities-naming",
            category="bugs",
            status="pass",
            message=f"schema still reports name={name!r} fieldName={field_name!r} (workaround still needed)",
            bugs_ref="BUGS.md #8",
        )
    return ProbeResult(
        name="userrole-authorities-naming",
        category="bugs",
        status="warn",
        message=f"schema reports name={name!r} fieldName={field_name!r} — shape may have changed upstream",
        bugs_ref="BUGS.md #8",
    )


async def probe_outlier_algorithm_enum(client: Dhis2Client) -> ProbeResult:
    """Check BUGS.md #13 — DHIS2 server still rejects `MOD_Z_SCORE` even though OAS declares it."""
    try:
        await client.get_raw(
            "/api/analytics/outlierDetection",
            params={
                "ds": "nonexistent",
                "ou": "nonexistent",
                "pe": "LAST_12_MONTHS",
                "algorithm": "MOD_Z_SCORE",
            },
        )
    except Dhis2ApiError as exc:
        body = exc.body if isinstance(exc.body, dict) else {}
        message = str(body.get("message", ""))
        if exc.status_code == 400 and "MOD_Z_SCORE" in message and "MODIFIED_Z_SCORE" in message:
            return ProbeResult(
                name="outlier-algorithm-enum",
                category="bugs",
                status="pass",
                message="server still rejects MOD_Z_SCORE (use MODIFIED_Z_SCORE)",
                bugs_ref="BUGS.md #13",
            )
        if exc.status_code == 400:
            return ProbeResult(
                name="outlier-algorithm-enum",
                category="bugs",
                status="skip",
                message=f"unclear response: {exc.status_code} {message[:80]!r}",
                bugs_ref="BUGS.md #13",
            )
        return ProbeResult(
            name="outlier-algorithm-enum",
            category="bugs",
            status="warn",
            message=f"unexpected status {exc.status_code}",
            bugs_ref="BUGS.md #13",
        )
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            name="outlier-algorithm-enum", category="bugs", status="fail", message=f"probe failed: {exc}"
        )
    return ProbeResult(
        name="outlier-algorithm-enum",
        category="bugs",
        status="warn",
        message="MOD_Z_SCORE accepted — upstream may have fixed the enum name",
        bugs_ref="BUGS.md #13",
    )


async def probe_custom_logo_flag_consistency(client: Dhis2Client) -> ProbeResult:
    """Check BUGS.md #11 — `keyUseCustomLogoFront` system setting mirrors `/api/loginConfig.useCustomLogoFront`."""
    try:
        config = await client.get_raw("/api/loginConfig")
        setting = await client.get_raw("/api/systemSettings/keyUseCustomLogoFront")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            name="custom-logo-flag",
            category="bugs",
            status="fail",
            message=f"probe failed: {exc}",
            bugs_ref="BUGS.md #11",
        )
    login_flag = config.get("useCustomLogoFront")
    raw_setting = setting.get("keyUseCustomLogoFront")

    def _truthy(value: object) -> bool:
        return str(value).lower() == "true"

    if _truthy(login_flag) == _truthy(raw_setting):
        return ProbeResult(
            name="custom-logo-flag",
            category="bugs",
            status="pass",
            message=f"consistent: loginConfig={login_flag} keySetting={raw_setting}",
            bugs_ref="BUGS.md #11",
        )
    return ProbeResult(
        name="custom-logo-flag",
        category="bugs",
        status="warn",
        message=(
            f"mismatch — loginConfig.useCustomLogoFront={login_flag} "
            f"vs keyUseCustomLogoFront={raw_setting}. "
            "Upload won't be visible until both agree."
        ),
        bugs_ref="BUGS.md #11",
    )


BUGS_PROBES = (
    probe_version,
    probe_auth,
    probe_login_config,
    probe_oauth2_discovery,
    probe_analytics_rawdata_json_suffix,
    probe_userrole_schema_naming,
    probe_outlier_algorithm_enum,
    probe_custom_logo_flag_consistency,
)
