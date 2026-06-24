"""Settings-check tests: version-invariant evaluate_settings verdicts and per-tree CORS wiring.

`evaluate_settings` is version-invariant and tested directly through a typed test double that
satisfies `SettingsLike`; the `_run_settings` wiring (which reads `/api/systemSettings` plus the
separate `/api/configuration/corsWhitelist` array) is exercised against a mock client on all three
version trees.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_core.security_core import (
    CheckStatus,
    CorsWhitelist,
    Severity,
    evaluate_settings,
)
from pydantic import BaseModel, ConfigDict

TREES = ("v41", "v42", "v43")


class _Settings(BaseModel):
    """Frozen test double satisfying SettingsLike with safe non-flagging defaults."""

    model_config = ConfigDict(frozen=True)

    minPasswordLength: int | None = 12
    credentialsExpires: int | None = 90
    keyLockMultipleFailedLogins: bool | None = True
    keySelfRegistrationNoRecaptcha: bool | None = False
    keyCanGrantOwnUserAuthorityGroups: bool | None = False
    keyAccountRecovery: bool | None = False
    enforceVerifiedEmail: bool | None = None
    keyEmailHostName: str | None = "smtp.example.org"
    keyEmailUsername: str | None = "mailer"


def _titles(findings: list[Any]) -> set[str]:
    """Collect finding titles for membership assertions."""
    return {finding.title for finding in findings}


def _by_title(findings: list[Any], title: str) -> Any:
    """Return the single finding with the given title."""
    matches = [finding for finding in findings if finding.title == title]
    assert len(matches) == 1, f"expected exactly one {title!r} finding, got {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# evaluate_settings (version-invariant)
# ---------------------------------------------------------------------------


def test_clean_settings_emit_only_the_static_2fa_note() -> None:
    """A hardened settings slice with no CORS still emits the static no-global-2FA finding only."""
    findings = evaluate_settings(_Settings())
    assert _titles(findings) == {"Two-factor authentication is not globally enforced"}
    assert _by_title(findings, "Two-factor authentication is not globally enforced").severity is Severity.INFO


def test_weak_minimum_password_length_is_medium() -> None:
    """A minPasswordLength below the recommended floor is MEDIUM with the value as evidence."""
    finding = _by_title(evaluate_settings(_Settings(minPasswordLength=6)), "Weak minimum password length")
    assert finding.severity is Severity.MEDIUM
    assert (finding.evidence or {}).get("minPasswordLength") == "6"


def test_failed_login_lockout_disabled_is_medium() -> None:
    """keyLockMultipleFailedLogins False raises a MEDIUM lockout finding."""
    finding = _by_title(
        evaluate_settings(_Settings(keyLockMultipleFailedLogins=False)), "Failed-login lockout disabled"
    )
    assert finding.severity is Severity.MEDIUM


def test_passwords_never_expire_is_warn() -> None:
    """credentialsExpires of 0 raises a WARN never-expire finding."""
    finding = _by_title(evaluate_settings(_Settings(credentialsExpires=0)), "Passwords never expire")
    assert finding.severity is Severity.WARN


def test_self_registration_captcha_disabled_is_medium() -> None:
    """keySelfRegistrationNoRecaptcha True raises a MEDIUM captcha finding."""
    finding = _by_title(
        evaluate_settings(_Settings(keySelfRegistrationNoRecaptcha=True)), "Self-registration captcha disabled"
    )
    assert finding.severity is Severity.MEDIUM


def test_self_grant_authorities_is_high() -> None:
    """keyCanGrantOwnUserAuthorityGroups True is a HIGH privilege-escalation finding."""
    finding = _by_title(
        evaluate_settings(_Settings(keyCanGrantOwnUserAuthorityGroups=True)),
        "Users can grant themselves their own authorities",
    )
    assert finding.severity is Severity.HIGH


def test_cors_wildcard_is_medium() -> None:
    """A `*` origin in the CORS whitelist raises a MEDIUM permissive-CORS finding."""
    findings = evaluate_settings(_Settings(), cors=CorsWhitelist(origins=("https://app.example.org", "*")))
    finding = _by_title(findings, "Permissive CORS wildcard origin")
    assert finding.severity is Severity.MEDIUM


def test_cors_without_wildcard_emits_no_cors_finding() -> None:
    """A concrete-origin CORS whitelist with no `*` raises no permissive-CORS finding."""
    findings = evaluate_settings(_Settings(), cors=CorsWhitelist(origins=("https://app.example.org",)))
    assert "Permissive CORS wildcard origin" not in _titles(findings)


def test_email_verification_off_is_warn() -> None:
    """enforceVerifiedEmail explicitly False raises a standalone WARN email-verification finding."""
    finding = _by_title(evaluate_settings(_Settings(enforceVerifiedEmail=False)), "Email verification is not enforced")
    assert finding.severity is Severity.WARN


def test_email_verification_none_emits_no_finding() -> None:
    """enforceVerifiedEmail None (absent on v41) emits no finding; flagging it would be a false positive."""
    findings = evaluate_settings(_Settings(enforceVerifiedEmail=None))
    assert "Email verification is not enforced" not in _titles(findings)


def test_email_verification_on_emits_no_finding() -> None:
    """enforceVerifiedEmail True raises no email-verification finding."""
    findings = evaluate_settings(_Settings(enforceVerifiedEmail=True))
    assert "Email verification is not enforced" not in _titles(findings)


def test_non_empty_cors_without_wildcard_is_info_with_origins() -> None:
    """A non-empty no-wildcard CORS whitelist raises an INFO with the origins enumerated in evidence."""
    origins = ("https://app.example.org", "https://admin.example.org")
    finding = _by_title(
        evaluate_settings(_Settings(), cors=CorsWhitelist(origins=origins)),
        "CORS origin allowlist configured",
    )
    assert finding.severity is Severity.INFO
    evidence = finding.evidence or {}
    for origin in origins:
        assert origin in evidence.get("origins", "")


def test_wildcard_cors_is_medium_only_not_info() -> None:
    """A wildcard CORS whitelist raises the MEDIUM permissive finding only, never the INFO allowlist one."""
    findings = evaluate_settings(_Settings(), cors=CorsWhitelist(origins=("*", "https://app.example.org")))
    titles = _titles(findings)
    assert "Permissive CORS wildcard origin" in titles
    assert "CORS origin allowlist configured" not in titles


def test_empty_cors_emits_neither_cors_finding() -> None:
    """An empty CORS whitelist raises neither the wildcard MEDIUM nor the allowlist INFO."""
    findings = evaluate_settings(_Settings(), cors=CorsWhitelist(origins=()))
    titles = _titles(findings)
    assert "Permissive CORS wildcard origin" not in titles
    assert "CORS origin allowlist configured" not in titles


def test_cors_none_skips_only_the_cors_verdict() -> None:
    """cors=None (unreadable) skips the CORS verdict while the other verdicts still fire."""
    findings = evaluate_settings(
        _Settings(minPasswordLength=4, keyCanGrantOwnUserAuthorityGroups=True),
        cors=None,
    )
    titles = _titles(findings)
    assert "Permissive CORS wildcard origin" not in titles
    assert "Weak minimum password length" in titles
    assert "Users can grant themselves their own authorities" in titles


def test_global_2fa_note_is_always_emitted() -> None:
    """The no-global-2FA finding is unconditional, even with a wildcard CORS present."""
    findings = evaluate_settings(_Settings(), cors=CorsWhitelist(origins=("*",)))
    finding = _by_title(findings, "Two-factor authentication is not globally enforced")
    assert finding.severity is Severity.INFO


def test_email_unconfigured_with_recovery_on_is_warn() -> None:
    """Account recovery on with blank SMTP host/username raises a WARN email-misconfig finding."""
    finding = _by_title(
        evaluate_settings(_Settings(keyAccountRecovery=True, keyEmailHostName="", keyEmailUsername="")),
        "Email-dependent feature on while SMTP is unconfigured",
    )
    assert finding.severity is Severity.WARN


def test_email_unconfigured_with_verification_on_is_warn() -> None:
    """Email verification on with a blank username raises the WARN email-misconfig finding."""
    findings = evaluate_settings(
        _Settings(enforceVerifiedEmail=True, keyEmailHostName="smtp.example.org", keyEmailUsername="   ")
    )
    assert "Email-dependent feature on while SMTP is unconfigured" in _titles(findings)


def test_email_configured_suppresses_the_email_finding() -> None:
    """A configured SMTP host and username suppress the email finding even with recovery on."""
    findings = evaluate_settings(
        _Settings(keyAccountRecovery=True, keyEmailHostName="smtp.example.org", keyEmailUsername="mailer")
    )
    assert "Email-dependent feature on while SMTP is unconfigured" not in _titles(findings)


def test_email_finding_skipped_when_recovery_and_verification_off() -> None:
    """Blank SMTP is fine when neither recovery nor verification is on; no email finding fires."""
    findings = evaluate_settings(_Settings(keyEmailHostName="", keyEmailUsername=""))
    assert "Email-dependent feature on while SMTP is unconfigured" not in _titles(findings)


def test_cors_whitelist_has_wildcard_property() -> None:
    """CorsWhitelist.has_wildcard is True only when a `*` origin is present."""
    assert CorsWhitelist(origins=("*",)).has_wildcard is True
    assert CorsWhitelist(origins=("https://app.example.org",)).has_wildcard is False
    assert CorsWhitelist(origins=()).has_wildcard is False


# ---------------------------------------------------------------------------
# Per-tree wiring: _run_settings reads systemSettings + corsWhitelist
# ---------------------------------------------------------------------------


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _settings_type(tree: str) -> Any:
    """Return the per-tree SecuritySettings projection."""
    models = import_module(f"dhis2w_core.{tree}.plugins.security.models")
    return models.SecuritySettings


def _mock_client(*, settings: Any, cors_raw: dict[str, Any] | Exception) -> MagicMock:
    """A client whose typed settings read and CORS get_raw return the given fixtures."""
    client = MagicMock()
    client.get = AsyncMock(return_value=settings)
    if isinstance(cors_raw, Exception):
        client.get_raw = AsyncMock(side_effect=cors_raw)
    else:
        client.get_raw = AsyncMock(return_value=cors_raw)
    return client


@pytest.mark.parametrize("tree", TREES)
async def test_run_settings_flags_self_grant_and_cors_wildcard(tree: str) -> None:
    """_run_settings surfaces the self-grant HIGH and the CORS wildcard MEDIUM across trees."""
    audit = _audit_module(tree)
    settings_type = _settings_type(tree)
    settings = settings_type(minPasswordLength=12, keyCanGrantOwnUserAuthorityGroups=True)
    client = _mock_client(settings=settings, cors_raw={"data": ["*", "https://app.example.org"]})

    result = await audit._run_settings(client)

    assert result.status is CheckStatus.OK
    assert result.note is None
    titles = _titles(result.findings)
    assert "Users can grant themselves their own authorities" in titles
    assert "Permissive CORS wildcard origin" in titles


@pytest.mark.parametrize("tree", TREES)
async def test_run_settings_degrades_cors_only_when_unreadable(tree: str) -> None:
    """A CORS read error skips only the CORS verdict, keeps the other verdicts, and adds a note."""
    audit = _audit_module(tree)
    settings_type = _settings_type(tree)
    settings = settings_type(minPasswordLength=4)
    client = _mock_client(settings=settings, cors_raw=Dhis2ApiError(403, "forbidden"))

    result = await audit._run_settings(client)

    assert result.status is CheckStatus.OK
    assert result.note is not None and "CORS" in result.note
    titles = _titles(result.findings)
    assert "Permissive CORS wildcard origin" not in titles
    assert "Weak minimum password length" in titles


@pytest.mark.parametrize("tree", TREES)
async def test_run_settings_degrades_when_settings_endpoint_errors(tree: str) -> None:
    """An error reading /api/systemSettings degrades the whole check rather than a false all-clear."""
    audit = _audit_module(tree)
    client = MagicMock()
    client.get = AsyncMock(side_effect=Dhis2ApiError(500, "boom"))

    result = await audit._run_settings(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []


@pytest.mark.parametrize("tree", TREES)
async def test_run_settings_skips_cors_on_unexpected_payload_shape(tree: str) -> None:
    """A CORS payload dict with no `data` array skips the verdict with a note."""
    audit = _audit_module(tree)
    settings_type = _settings_type(tree)
    client = _mock_client(settings=settings_type(minPasswordLength=12), cors_raw={"unexpected": "shape"})

    result = await audit._run_settings(client)

    assert result.note is not None and "CORS" in result.note
    assert "Permissive CORS wildcard origin" not in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_settings_degrades_cors_on_network_timeout(tree: str) -> None:
    """A network timeout on the CORS fetch degrades only the CORS verdict; status stays OK and other verdicts fire."""
    audit = _audit_module(tree)
    settings_type = _settings_type(tree)
    settings = settings_type(minPasswordLength=4)
    client = _mock_client(settings=settings, cors_raw=httpx.ConnectError("timeout"))

    result = await audit._run_settings(client)

    assert result.status is CheckStatus.OK
    assert result.note is not None and "CORS" in result.note
    assert "Permissive CORS wildcard origin" not in _titles(result.findings)
    assert "Weak minimum password length" in _titles(result.findings)
