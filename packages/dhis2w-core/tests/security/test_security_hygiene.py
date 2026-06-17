"""Hygiene-check tests: per-user flags, the per-version 2FA source split, and wiring."""

from __future__ import annotations

from datetime import datetime
from importlib import import_module
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_core.security_core import (
    CheckStatus,
    Severity,
    TwoFactorSummary,
    UserHygiene,
    build_user_hygiene,
    evaluate_hygiene,
    evaluate_two_factor_from_endpoint,
    evaluate_two_factor_from_user_field,
)

NOW = datetime(2026, 6, 18)
TREES = ("v41", "v42", "v43")


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _user(
    *,
    username: str = "user",
    disabled: bool = False,
    email: str | None = "user@example.org",
    last_login: str | None = "2026-06-17T00:00:00",
    two_factor: bool | None = None,
    superuser: bool = False,
    privileged: bool = False,
) -> UserHygiene:
    """Construct a hygiene view directly, bypassing the role join."""
    return UserHygiene(
        id=username,
        username=username,
        disabled=disabled,
        email=email,
        last_login=last_login,
        two_factor=two_factor,
        is_superuser=superuser,
        is_privileged=privileged or superuser,
    )


def _titles(findings: list[Any]) -> set[str]:
    """Collect finding titles for membership assertions."""
    return {finding.title for finding in findings}


# ---------------------------------------------------------------------------
# Role join
# ---------------------------------------------------------------------------


def test_build_user_hygiene_derives_superuser_and_privileged() -> None:
    """Membership in an ALL role marks superuser; a dangerous role marks privileged."""
    superuser = build_user_hygiene(
        user_id="u1",
        username="root",
        disabled=False,
        email=None,
        last_login=None,
        two_factor=None,
        role_ids=["ALLROLE"],
        all_role_ids={"ALLROLE"},
        dangerous_role_ids={"ALLROLE", "SQL"},
    )
    assert superuser.is_superuser and superuser.is_privileged
    plain = build_user_hygiene(
        user_id="u2",
        username="clerk",
        disabled=False,
        email=None,
        last_login=None,
        two_factor=None,
        role_ids=["DE"],
        all_role_ids={"ALLROLE"},
        dangerous_role_ids={"ALLROLE", "SQL"},
    )
    assert not plain.is_superuser and not plain.is_privileged


# ---------------------------------------------------------------------------
# Per-user hygiene (version-invariant)
# ---------------------------------------------------------------------------


def test_privileged_never_logged_in_is_high() -> None:
    """A privileged account that has never logged in is HIGH."""
    findings = evaluate_hygiene([_user(username="ghost", last_login=None, privileged=True)], stale_days=90, now=NOW)
    high = [f for f in findings if f.title == "Privileged account never logged in"]
    assert high and high[0].severity is Severity.HIGH


def test_privileged_stale_is_medium() -> None:
    """A privileged account past the stale threshold is MEDIUM."""
    findings = evaluate_hygiene(
        [_user(username="rusty", last_login="2026-01-01T00:00:00", privileged=True)], stale_days=90, now=NOW
    )
    assert any(f.title == "Stale privileged account" and f.severity is Severity.MEDIUM for f in findings)


def test_disabled_privileged_is_medium_and_skips_other_user_flags() -> None:
    """A disabled privileged account reports the latent-access flag only."""
    findings = evaluate_hygiene(
        [_user(username="ex", disabled=True, email=None, last_login=None, privileged=True)], stale_days=90, now=NOW
    )
    titles = _titles(findings)
    assert "Disabled account holds privileged roles" in titles
    assert "Privileged account never logged in" not in titles


def test_privileged_missing_email_is_warn() -> None:
    """A privileged account with no email is WARN (the catalog's low tier)."""
    findings = evaluate_hygiene([_user(username="noemail", email=None, privileged=True)], stale_days=90, now=NOW)
    assert any(f.title == "Privileged account has no email" and f.severity is Severity.WARN for f in findings)


def test_seed_admin_enabled_is_flagged() -> None:
    """The well-known enabled 'admin' account is flagged regardless of privilege."""
    findings = evaluate_hygiene([_user(username="admin")], stale_days=90, now=NOW)
    assert "Default seed account 'admin' is enabled" in _titles(findings)


def test_non_privileged_user_yields_only_inventory() -> None:
    """A clean non-privileged account contributes nothing but the inventory roll-up."""
    findings = evaluate_hygiene([_user(username="clerk")], stale_days=90, now=NOW)
    assert _titles(findings) == {"User account inventory"}
    inventory = findings[0]
    assert inventory.severity is Severity.INFO
    assert (inventory.evidence or {}).get("total") == "1"


# ---------------------------------------------------------------------------
# 2FA verdict shaping (the per-version source split)
# ---------------------------------------------------------------------------


def test_two_factor_user_field_flags_superuser_without_2fa() -> None:
    """v41 path: an enabled superuser with 2FA off is CRITICAL."""
    users = [
        _user(username="root", superuser=True, two_factor=False),
        _user(username="safe", superuser=True, two_factor=True),
    ]
    findings = evaluate_two_factor_from_user_field(users)
    assert [f.subject for f in findings] == ["root"]
    assert findings[0].severity is Severity.CRITICAL


def test_two_factor_endpoint_summary_reports_count() -> None:
    """v42/v43 path without detail: the privileged-missing count is a single CRITICAL."""
    summary = TwoFactorSummary(privileged_with_all=5, privileged_missing_2fa=2)
    findings = evaluate_two_factor_from_endpoint(summary=summary, users=[], disabled_2fa_ids=None)
    assert len(findings) == 1
    assert findings[0].severity is Severity.CRITICAL
    assert (findings[0].evidence or {}).get("missing_2fa") == "2"


def test_two_factor_endpoint_detail_names_superusers() -> None:
    """v42/v43 path with detail: superusers in the disabled-2FA set are named individually."""
    users = [_user(username="root", superuser=True), _user(username="clerk", privileged=True)]
    findings = evaluate_two_factor_from_endpoint(
        summary=TwoFactorSummary(privileged_missing_2fa=1), users=users, disabled_2fa_ids={"root", "clerk"}
    )
    # Only the superuser is named, even though both are in the disabled-2FA set.
    assert [f.subject for f in findings] == ["root"]


def test_two_factor_endpoint_missing_summary_is_silent() -> None:
    """When the summary is unavailable, the endpoint path emits no findings (the note carries the reason)."""
    assert evaluate_two_factor_from_endpoint(summary=None, users=[], disabled_2fa_ids=None) == []


# ---------------------------------------------------------------------------
# Per-tree wiring
# ---------------------------------------------------------------------------


def _client_for(payloads: dict[str, Any]) -> MagicMock:
    """A client whose get_raw dispatches by path, raising payloads that are exceptions."""
    client = MagicMock()
    client.base_url = "https://mock.example"

    async def get_raw(path: str, params: dict[str, Any] | None = None) -> Any:
        value = payloads[path]
        if isinstance(value, Exception):
            raise value
        return value

    client.get_raw = get_raw
    return client


_ROLES = {"userRoles": [{"id": "ALLROLE", "authorities": ["ALL"]}, {"id": "DE", "authorities": ["F_DATAVALUE_ADD"]}]}


async def test_run_hygiene_v41_flags_superuser_without_2fa() -> None:
    """v41 reads twoFactorEnabled from /api/users and flags a superuser whose 2FA is off."""
    audit = _audit_module("v41")
    users = {
        "users": [
            {
                "id": "u1",
                "username": "admin",
                "disabled": False,
                "email": "a@x.org",
                "lastLogin": "2026-06-17T00:00:00",
                "twoFactorEnabled": False,
                "userRoles": [{"id": "ALLROLE"}],
            }
        ]
    }
    client = _client_for({"/api/userRoles": _ROLES, "/api/users": users})

    result = await audit._run_hygiene(client, stale_days=90, now=NOW, two_factor_detail=False)

    assert result.status is CheckStatus.OK
    assert any(f.title == "Superuser without 2FA" and f.severity is Severity.CRITICAL for f in result.findings)


@pytest.mark.parametrize("tree", ("v42", "v43"))
async def test_run_hygiene_endpoint_reports_privileged_missing_count(tree: str) -> None:
    """v42/v43 read the 2FA summary endpoint and surface the privileged-missing count."""
    audit = _audit_module(tree)
    users = {
        "users": [
            {
                "id": "u1",
                "username": "admin",
                "disabled": False,
                "email": "a@x.org",
                "lastLogin": "2026-06-17T00:00:00",
                "userRoles": [{"id": "ALLROLE"}],
            }
        ]
    }
    summary = {"totalUsers": 3, "privileged": {"withAllAuthority": 2, "withAllAuthorityMissing2FA": 1}}
    client = _client_for({"/api/userRoles": _ROLES, "/api/users": users, "/api/users/twoFactor/summary": summary})

    result = await audit._run_hygiene(client, stale_days=90, now=NOW, two_factor_detail=False)

    assert result.status is CheckStatus.OK
    assert any(f.title == "Superusers without 2FA" for f in result.findings)


@pytest.mark.parametrize("tree", ("v42", "v43"))
async def test_run_hygiene_endpoint_degrades_when_not_backported(tree: str) -> None:
    """A 404/403 from the 2FA endpoint degrades to a note, not a false all-clear."""
    audit = _audit_module(tree)
    users = {"users": [{"id": "u1", "username": "admin", "disabled": False, "userRoles": [{"id": "ALLROLE"}]}]}
    client = _client_for(
        {
            "/api/userRoles": _ROLES,
            "/api/users": users,
            "/api/users/twoFactor/summary": Dhis2ApiError(404, "Not Found"),
        }
    )

    result = await audit._run_hygiene(client, stale_days=90, now=NOW, two_factor_detail=False)

    assert result.note is not None and "2FA audit endpoint unavailable" in result.note
    assert not any(f.title.startswith("Superuser") for f in result.findings)
