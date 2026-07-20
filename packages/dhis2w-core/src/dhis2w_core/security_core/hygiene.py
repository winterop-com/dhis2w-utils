"""Per-user account hygiene: privileged accounts joined to login and 2FA posture."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.controls import CheckOutcome, ControlLog
from dhis2w_core.security_core.findings import AuditFinding, Severity

_CHECK = "hygiene"

# The well-known seed account DHIS2 installs on a fresh database.
SEED_USERNAME = "admin"

# How many usernames an aggregate non-privileged finding names before truncating to a count.
# Mirrors the auditor app's SAMPLE_LIMIT so a 5000-user instance emits one row, not thousands.
SAMPLE_LIMIT = 10

# Default age (in days) past which a password is treated as stale. Mirrors the auditor app's 365-day floor.
DEFAULT_MAX_PASSWORD_AGE_DAYS = 365


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
    password_last_updated: str | None = None
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
    password_last_updated: str | None,
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
        password_last_updated=password_last_updated,
        two_factor=two_factor,
        is_superuser=is_superuser,
        is_privileged=is_privileged,
    )


def evaluate_hygiene(
    users: list[UserHygiene],
    *,
    stale_days: int,
    max_password_age_days: int = DEFAULT_MAX_PASSWORD_AGE_DAYS,
    now: datetime,
    two_factor_findings: list[AuditFinding] | None = None,
) -> CheckOutcome:
    """Per-user hygiene over privileged accounts plus aggregate never-logged-in / stale signals for the rest.

    Privileged accounts keep their high-signal per-user rows (privileged sets are small). Active
    non-privileged accounts that never logged in or have gone stale are rolled up into at most two
    aggregate WARN findings so a large instance never emits a row per account. A third aggregate WARN
    rolls up every active account (privileged or not) whose password is older than the threshold or has
    never been set, since password age is a hardening signal independent of privilege.

    `two_factor_findings` carries the pre-computed superuser-2FA findings (each tagged
    `hygiene-2fa-superuser`); they are recorded last so the outcome's findings equal the main hygiene
    findings followed by the 2FA findings. `None` means the per-user 2FA endpoint was unreadable, so the
    2FA control is marked skipped; an empty list leaves it PASS.
    """
    log = ControlLog(_CHECK)
    log.mark_passed(
        "hygiene-priv-disabled-holds-roles",
        "hygiene-priv-never-logged-in",
        "hygiene-priv-stale",
        "hygiene-priv-no-email",
        "hygiene-agg-never-logged-in",
        "hygiene-agg-stale",
        "hygiene-agg-stale-password",
        "hygiene-seed-admin-enabled",
    )
    findings: list[AuditFinding] = []
    never_logged_in: list[str] = []
    stale_accounts: list[str] = []
    stale_passwords: list[str] = []
    for user in users:
        if not user.disabled and _has_stale_password(user.password_last_updated, now, max_password_age_days):
            stale_passwords.append(user.username)
        if not user.is_privileged:
            if not user.disabled:
                if user.last_login is None:
                    never_logged_in.append(user.username)
                elif _is_stale(user.last_login, now, stale_days):
                    stale_accounts.append(user.username)
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
                    control="hygiene-priv-disabled-holds-roles",
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
                    control="hygiene-priv-never-logged-in",
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
                    control="hygiene-priv-stale",
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
                    control="hygiene-priv-no-email",
                )
            )
    findings.extend(
        _aggregate_finding(
            never_logged_in,
            title="Active accounts that never logged in",
            detail_lead="non-privileged active account(s) have never logged in",
            group_key="active-never-logged-in",
            control="hygiene-agg-never-logged-in",
        )
    )
    findings.extend(
        _aggregate_finding(
            stale_accounts,
            title="Stale active accounts",
            detail_lead=f"non-privileged active account(s) have not logged in for over {stale_days} days",
            group_key="active-stale",
            control="hygiene-agg-stale",
        )
    )
    findings.extend(
        _aggregate_finding(
            stale_passwords,
            title="Accounts with stale or unset passwords",
            detail_lead=f"active account(s) have a password older than {max_password_age_days} days or never set",
            group_key="stale-password",
            control="hygiene-agg-stale-password",
        )
    )
    findings.extend(_seed_admin_findings(users))
    findings.append(_inventory_finding(users))
    for finding in findings:
        log.record(finding)
    if two_factor_findings is None:
        log.mark_skipped("hygiene-2fa-superuser", "per-user 2FA endpoint unreadable")
    else:
        log.mark_passed("hygiene-2fa-superuser")
        for finding in two_factor_findings:
            log.record(finding)
    return log.result()


def _aggregate_finding(
    usernames: list[str], *, title: str, detail_lead: str, group_key: str, control: str
) -> list[AuditFinding]:
    """Roll up non-privileged accounts into one WARN finding with a count and a capped username sample."""
    count = len(usernames)
    if count == 0:
        return []
    sample = usernames[:SAMPLE_LIMIT]
    more = count - len(sample)
    detail = f"{count} {detail_lead}: {', '.join(sample)}"
    if more > 0:
        detail += f" and {more} more"
    detail += "."
    return [
        AuditFinding(
            check=_CHECK,
            severity=Severity.WARN,
            title=title,
            detail=detail,
            evidence={"count": str(count), "sample": ", ".join(sample)},
            group_key=group_key,
            control=control,
        )
    ]


def evaluate_two_factor_from_user_field(users: list[UserHygiene]) -> list[AuditFinding]:
    """v41 path: flag each enabled superuser whose per-user 2FA flag is off."""
    return [
        _finding(
            user,
            Severity.CRITICAL,
            "Superuser without 2FA",
            f"Superuser '{user.username}' does not have two-factor authentication enabled.",
            group_key="superuser-no-2fa",
            control="hygiene-2fa-superuser",
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
                control="hygiene-2fa-superuser",
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
                control="hygiene-2fa-superuser",
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
    control: str,
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
        control=control,
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
                    control="hygiene-seed-admin-enabled",
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
        control="hygiene-inventory",
    )


def _as_utc(moment: datetime) -> datetime:
    """Normalise a timestamp to aware UTC: convert an offset-bearing value, assume UTC for a naive one.

    DHIS2 usually serialises naive timestamps (assumed UTC here); when a wire format DOES carry an
    offset, it must be converted, not dropped: `.replace(tzinfo=None)` would shift the day-boundary
    comparison by the offset.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _is_stale(last_login: str, now: datetime, stale_days: int) -> bool:
    """Return True when an ISO last-login timestamp is older than the stale-days threshold."""
    try:
        stamp = datetime.fromisoformat(last_login)
    except ValueError:
        return False
    return (_as_utc(now) - _as_utc(stamp)).days > stale_days


def _has_stale_password(password_last_updated: str | None, now: datetime, max_password_age_days: int) -> bool:
    """Return True when a password was never set (null) or last changed before the max-age threshold.

    An unparseable timestamp is treated as a recent password (not flagged) rather than as unset:
    DHIS2 always serializes a real java.util.Date, so an unparseable value indicates corrupt data or
    an unforeseen wire format, and treating it as stale would risk a mass false positive across every
    account if a format ever slips past fromisoformat. The null/never-set case (password_last_updated
    is None) IS still flagged via the union with the older-than-threshold branch.
    """
    if password_last_updated is None:
        return True
    try:
        stamp = datetime.fromisoformat(password_last_updated)
    except ValueError:
        return False
    return (_as_utc(now) - _as_utc(stamp)).days > max_password_age_days
