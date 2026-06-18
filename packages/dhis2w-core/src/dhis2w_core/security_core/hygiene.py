"""Per-user account hygiene: privileged accounts joined to login and 2FA posture."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.findings import AuditFinding, Severity

_CHECK = "hygiene"

# The well-known seed account DHIS2 installs on a fresh database.
SEED_USERNAME = "admin"


class TwoFactorSource(StrEnum):
    """Where a version tree reads per-user 2FA state from."""

    USER_FIELD = "user-field"  # v41: twoFactorEnabled on /api/users
    AUDIT_ENDPOINT = "audit-endpoint"  # v42/v43: /api/users/twoFactor (dhis2-core#23925)


class UserHygiene(BaseModel):
    """One user account with the fields the hygiene check reasons over."""

    model_config = ConfigDict(frozen=True)

    id: str
    username: str
    disabled: bool = False
    email: str | None = None
    last_login: str | None = None
    two_factor: bool | None = None
    is_superuser: bool = False
    is_privileged: bool = False


class TwoFactorSummary(BaseModel):
    """The slice of GET /api/users/twoFactor/summary the audit reports on."""

    model_config = ConfigDict(frozen=True)

    total_users: int = 0
    enabled: int = 0
    disabled: int = 0
    coverage_percent: float = 0.0
    privileged_with_all: int = 0
    privileged_missing_2fa: int = 0


def build_user_hygiene(
    *,
    user_id: str,
    username: str,
    disabled: bool,
    email: str | None,
    last_login: str | None,
    two_factor: bool | None,
    role_ids: list[str],
    all_role_ids: set[str],
    dangerous_role_ids: set[str],
) -> UserHygiene:
    """Build a typed hygiene view, deriving superuser/privileged status from role membership."""
    ids = set(role_ids)
    is_superuser = bool(ids & all_role_ids)
    is_privileged = is_superuser or bool(ids & dangerous_role_ids)
    return UserHygiene(
        id=user_id,
        username=username,
        disabled=disabled,
        email=email,
        last_login=last_login,
        two_factor=two_factor,
        is_superuser=is_superuser,
        is_privileged=is_privileged,
    )


def evaluate_hygiene(users: list[UserHygiene], *, stale_days: int, now: datetime) -> list[AuditFinding]:
    """Per-user hygiene findings over privileged accounts, plus seed-account and inventory signals."""
    findings: list[AuditFinding] = []
    for user in users:
        if not user.is_privileged:
            continue
        if user.disabled:
            findings.append(
                _finding(
                    user,
                    Severity.MEDIUM,
                    "Disabled account holds privileged roles",
                    f"Disabled account '{user.username}' still holds privileged roles; "
                    "re-enabling the account restores that access.",
                    group_key="disabled-privileged",
                )
            )
            continue
        if user.last_login is None:
            findings.append(
                _finding(
                    user,
                    Severity.HIGH,
                    "Privileged account never logged in",
                    f"Privileged account '{user.username}' has never logged in; "
                    "a dormant admin account is a takeover target.",
                    group_key="never-logged-in",
                )
            )
        elif _is_stale(user.last_login, now, stale_days):
            findings.append(
                _finding(
                    user,
                    Severity.MEDIUM,
                    "Stale privileged account",
                    f"Privileged account '{user.username}' has not logged in for over "
                    f"{stale_days} days (last: {user.last_login}).",
                    group_key="stale",
                    last=user.last_login,
                )
            )
        if not user.email:
            findings.append(
                _finding(
                    user,
                    Severity.WARN,
                    "Privileged account has no email",
                    f"Privileged account '{user.username}' has no email; "
                    "password recovery and security alerts cannot reach it.",
                    group_key="no-email",
                )
            )
    findings.extend(_seed_admin_findings(users))
    findings.append(_inventory_finding(users))
    return findings


def evaluate_two_factor_from_user_field(users: list[UserHygiene]) -> list[AuditFinding]:
    """v41 path: flag each enabled superuser whose per-user 2FA flag is off."""
    return [
        _finding(
            user,
            Severity.CRITICAL,
            "Superuser without 2FA",
            f"Superuser '{user.username}' does not have two-factor authentication enabled.",
            group_key="superuser-no-2fa",
        )
        for user in users
        if user.is_superuser and not user.disabled and user.two_factor is False
    ]


def evaluate_two_factor_from_endpoint(
    *,
    summary: TwoFactorSummary | None,
    users: list[UserHygiene],
    disabled_2fa_ids: set[str] | None,
) -> list[AuditFinding]:
    """v42/v43 path: report the privileged-without-2FA count, or name them when detail is fetched."""
    if summary is None:
        return []
    if disabled_2fa_ids is not None:
        return [
            _finding(
                user,
                Severity.CRITICAL,
                "Superuser without 2FA",
                f"Superuser '{user.username}' (ALL authority) does not have two-factor authentication enabled.",
                group_key="superuser-no-2fa",
            )
            for user in users
            if user.is_superuser and not user.disabled and user.id in disabled_2fa_ids
        ]
    if summary.privileged_missing_2fa > 0:
        return [
            AuditFinding(
                check=_CHECK,
                severity=Severity.CRITICAL,
                title="Superusers without 2FA",
                detail=(
                    f"{summary.privileged_missing_2fa} of {summary.privileged_with_all} ALL-authority account(s) "
                    "lack two-factor authentication."
                ),
                evidence={
                    "missing_2fa": str(summary.privileged_missing_2fa),
                    "with_all": str(summary.privileged_with_all),
                },
            )
        ]
    return []


def _finding(
    user: UserHygiene,
    severity: Severity,
    title: str,
    detail: str,
    *,
    group_key: str,
    last: str | None = None,
) -> AuditFinding:
    """Build a per-user hygiene finding keyed to the account and folded by `group_key`."""
    evidence = {"last": last} if last is not None else None
    return AuditFinding(
        check=_CHECK,
        severity=severity,
        title=title,
        detail=detail,
        subject=user.username,
        evidence=evidence,
        group_key=group_key,
    )


def _seed_admin_findings(users: list[UserHygiene]) -> list[AuditFinding]:
    """Flag the well-known seed account 'admin' when it exists and is enabled."""
    for user in users:
        if user.username == SEED_USERNAME and not user.disabled:
            return [
                _finding(
                    user,
                    Severity.MEDIUM,
                    "Default seed account 'admin' is enabled",
                    "The well-known seed account 'admin' exists and is enabled; "
                    "rename or disable it once real admins exist.",
                    group_key="seed-admin",
                )
            ]
    return []


def _inventory_finding(users: list[UserHygiene]) -> AuditFinding:
    """An informational roll-up of total, active, disabled, and privileged account counts."""
    total = len(users)
    disabled = sum(1 for user in users if user.disabled)
    privileged = sum(1 for user in users if user.is_privileged)
    return AuditFinding(
        check=_CHECK,
        severity=Severity.INFO,
        title="User account inventory",
        detail=f"{total} user(s): {total - disabled} active, {disabled} disabled; {privileged} hold privileged roles.",
        evidence={
            "total": str(total),
            "active": str(total - disabled),
            "disabled": str(disabled),
            "privileged": str(privileged),
        },
    )


def _is_stale(last_login: str, now: datetime, stale_days: int) -> bool:
    """Return True when an ISO last-login timestamp is older than the stale-days threshold."""
    try:
        stamp = datetime.fromisoformat(last_login)
    except ValueError:
        return False
    stamp = stamp.replace(tzinfo=None)
    reference = now.replace(tzinfo=None)
    return (reference - stamp).days > stale_days
