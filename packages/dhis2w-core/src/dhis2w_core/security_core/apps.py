"""Installed-apps audit: side-loaded frontend code, App Hub update currency, and custom JS/CSS.

Three independent signals. Side-loaded apps (installed outside the App Hub, so carrying no
`app_hub_id`) run untrusted frontend code and are flagged without needing the hub. Update currency
compares each hub-backed app against the App Hub catalog and is skipped entirely when the hub is
unreachable, so an App Hub outage never reads as "every app is untrusted". Custom JavaScript or CSS
configured through the `keyCustomJs` / `keyCustomCss` system settings injects code into every
operator session and is persistent XSS in the hands of anyone who can write those settings.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.controls import CheckOutcome, ControlLog
from dhis2w_core.security_core.findings import AuditFinding, Severity

_CHECK = "apps"


class InstalledApp(BaseModel):
    """One installed DHIS2 app with the fields the apps audit reasons over."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str | None = None
    app_hub_id: str | None = None
    bundled: bool = False
    core_app: bool = False


class HubApp(BaseModel):
    """One App Hub catalog entry: its hub id and the version strings published for it."""

    model_config = ConfigDict(frozen=True)

    app_hub_id: str
    versions: list[str] = []


def evaluate_apps(
    *,
    installed: list[InstalledApp],
    hub: list[HubApp] | None,
    custom_js: bool,
    custom_css: bool,
) -> CheckOutcome:
    """Record the app controls (side-loaded, hub update, custom JS/CSS), flagging each that trips.

    `hub=None` means the App Hub was unreachable, so update currency is skipped this run; the
    side-loaded and custom-code signals do not need the hub.
    """
    log = ControlLog(_CHECK)
    log.mark_passed("apps-side-loaded", "apps-custom-js", "apps-custom-css")
    if hub is None:
        log.mark_skipped("apps-update-available", "App Hub unreachable")
    else:
        log.mark_passed("apps-update-available")
    for finding in _side_loaded_findings(installed):
        log.record(finding)
    if hub is not None:
        for finding in _update_findings(installed, hub):
            log.record(finding)
    for finding in _custom_code_findings(custom_js=custom_js, custom_css=custom_css):
        log.record(finding)
    return log.result()


def _side_loaded_findings(installed: list[InstalledApp]) -> list[AuditFinding]:
    """Flag each non-bundled app installed outside the App Hub as untrusted side-loaded code."""
    findings: list[AuditFinding] = []
    for app in installed:
        if app.bundled or app.core_app or app.app_hub_id:
            continue
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.HIGH,
                title="Side-loaded app installed",
                detail=(
                    f"App '{app.name}' was installed outside the App Hub (no app hub id); side-loaded "
                    "frontend code is untrusted and runs as every operator who opens it."
                ),
                subject=app.name,
                group_key="side-loaded-app",
                evidence={"app": app.name, "version": app.version or "unknown"},
                control="apps-side-loaded",
            )
        )
    return findings


def _update_findings(installed: list[InstalledApp], hub: list[HubApp]) -> list[AuditFinding]:
    """Flag each hub-backed app whose installed version is behind the App Hub's latest."""
    latest_by_id = {entry.app_hub_id: _latest(entry.versions) for entry in hub}
    findings: list[AuditFinding] = []
    for app in installed:
        if not app.app_hub_id:
            continue
        latest = latest_by_id.get(app.app_hub_id)
        if latest is None or not _is_newer(latest, app.version):
            continue
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.MEDIUM,
                title="App update available",
                detail=(
                    f"App '{app.name}' is at {app.version or 'unknown'}; the App Hub has {latest}. "
                    "App updates often carry security fixes."
                ),
                subject=app.name,
                group_key="app-update",
                evidence={"app": app.name, "installed": app.version or "unknown", "latest": latest},
                control="apps-update-available",
            )
        )
    return findings


def _custom_code_findings(*, custom_js: bool, custom_css: bool) -> list[AuditFinding]:
    """Flag configured custom JavaScript and CSS, each injected into every operator session."""
    findings: list[AuditFinding] = []
    if custom_js:
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.HIGH,
                title="Custom JavaScript injected into every app",
                detail=(
                    "keyCustomJs is set; the configured JavaScript runs in every operator's session across "
                    "all apps. Anyone who can write this setting holds persistent XSS over the instance."
                ),
                evidence={"setting": "keyCustomJs"},
                control="apps-custom-js",
            )
        )
    if custom_css:
        findings.append(
            AuditFinding(
                check=_CHECK,
                severity=Severity.HIGH,
                title="Custom CSS injected into every app",
                detail=(
                    "keyCustomCss is set; the configured CSS loads in every operator's session and can "
                    "deface the UI or exfiltrate data through crafted selectors."
                ),
                evidence={"setting": "keyCustomCss"},
                control="apps-custom-css",
            )
        )
    return findings


def _latest(versions: list[str]) -> str | None:
    """Return the highest-versioned string, or None when the list is empty."""
    candidates = [version for version in versions if version]
    if not candidates:
        return None
    return max(candidates, key=_version_key)


def _is_newer(latest: str | None, current: str | None) -> bool:
    """Return True when `latest` is a strictly higher version than `current`, ignoring trailing zeros."""
    latest_key = _version_key(latest)
    current_key = _version_key(current)
    width = max(len(latest_key), len(current_key))
    return _pad(latest_key, width) > _pad(current_key, width)


def _pad(parts: tuple[int, ...], width: int) -> tuple[int, ...]:
    """Right-pad a version tuple with zeros so 1.2 and 1.2.0 compare equal."""
    return parts + (0,) * (width - len(parts))


def _version_key(value: str | None) -> tuple[int, ...]:
    """Parse a version into integer parts, ignoring a leading 'v' and any -prerelease / +build suffix.

    '1.2.3' and 'v1.2.3-rc.1+build' both yield (1, 2, 3), so a hub pre-release like '1.2.4-SNAPSHOT'
    still ranks above an installed '1.2.3'. A token with no leading digits contributes 0; a missing or
    fully non-numeric version yields (0,). This is deliberately more tolerant than the strict-numeric
    helper in the `apps` plugin, because the App Hub catalog carries free-form third-party versions.
    """
    if not value:
        return (0,)
    core = value.strip().lstrip("vV").split("-", 1)[0].split("+", 1)[0]
    parts: list[int] = []
    for token in core.split("."):
        leading = ""
        for char in token:
            if not char.isdigit():
                break
            leading += char
        parts.append(int(leading) if leading else 0)
    return tuple(parts) or (0,)
