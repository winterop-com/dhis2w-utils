"""Roles-check tests: authority classification and per-tree wiring over /api/userRoles."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest
from dhis2w_core.security_core import (
    CheckStatus,
    Severity,
    build_role_audit,
    evaluate_roles,
)

TREES = ("v41", "v42", "v43")


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _client_with_roles(payload: list[dict[str, object]]) -> MagicMock:
    """A stand-in client whose /api/userRoles read returns the given payload."""
    client = MagicMock()
    client.get_raw = AsyncMock(return_value={"userRoles": payload})
    return client


# ---------------------------------------------------------------------------
# Classification (version-invariant)
# ---------------------------------------------------------------------------


def test_all_role_with_members_is_critical() -> None:
    """A role granting ALL with at least one member is CRITICAL."""
    role = build_role_audit(role_id="r1", name="Sysadmin", authorities=["ALL"], member_count=5)
    assert role.is_all
    assert [finding.severity for finding in evaluate_roles([role])] == [Severity.CRITICAL]


def test_all_role_without_members_is_high() -> None:
    """A role granting ALL but with no members is HIGH (latent, not active)."""
    role = build_role_audit(role_id="r1", name="Empty ALL", authorities=["ALL"], member_count=0)
    assert [finding.severity for finding in evaluate_roles([role])] == [Severity.HIGH]


def test_high_risk_category_role_is_high() -> None:
    """A non-ALL role in a high-risk category (SQL views) is HIGH."""
    role = build_role_audit(role_id="r2", name="SQL authors", authorities=["F_SQLVIEW_PUBLIC_ADD"], member_count=2)
    findings = evaluate_roles([role])
    assert len(findings) == 1
    assert findings[0].severity is Severity.HIGH
    assert "sql_views" in (findings[0].evidence or {}).get("categories", "")


def test_benign_role_produces_no_findings() -> None:
    """A role with only harmless data-entry authorities yields no findings."""
    role = build_role_audit(role_id="r3", name="Data entry", authorities=["F_DATAVALUE_ADD"], member_count=10)
    assert not role.is_all
    assert evaluate_roles([role]) == []


def test_impersonate_user_role_is_flagged_high() -> None:
    """A role granting F_IMPERSONATE_USER (account takeover) is HIGH in user_management."""
    role = build_role_audit(role_id="r4", name="Support", authorities=["F_IMPERSONATE_USER"], member_count=3)
    assert role.categories == ["user_management"]
    findings = evaluate_roles([role])
    assert len(findings) == 1
    assert findings[0].severity is Severity.HIGH
    assert "user_management" in (findings[0].evidence or {}).get("categories", "")


def test_public_route_role_is_flagged_high() -> None:
    """A role granting F_ROUTE_PUBLIC_ADD (SSRF-relay creation) is HIGH in route_management."""
    role = build_role_audit(role_id="r5", name="Integrations", authorities=["F_ROUTE_PUBLIC_ADD"], member_count=2)
    assert role.categories == ["route_management"]
    findings = evaluate_roles([role])
    assert len(findings) == 1
    assert findings[0].severity is Severity.HIGH
    assert "route_management" in (findings[0].evidence or {}).get("categories", "")


# ---------------------------------------------------------------------------
# Per-tree wiring over the live /api/userRoles shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tree", TREES)
async def test_run_roles_classifies_all_role_with_member_count(tree: str) -> None:
    """_run_roles maps the users~size count onto a CRITICAL ALL-role finding."""
    audit = _audit_module(tree)
    client = _client_with_roles(
        [
            {"id": "LGW", "name": "System administrator (ALL)", "authorities": ["ALL"], "users": 71},
            {"id": "DE", "name": "Data entry", "authorities": ["F_DATAVALUE_ADD"], "users": 10},
        ]
    )

    result = await audit._run_roles(client)

    assert result.status is CheckStatus.OK
    critical = [finding for finding in result.findings if finding.severity is Severity.CRITICAL]
    assert len(critical) == 1
    assert (critical[0].evidence or {}).get("members") == "71"


@pytest.mark.parametrize("tree", TREES)
async def test_run_roles_degrades_on_unexpected_payload(tree: str) -> None:
    """A payload without a userRoles list degrades the check rather than crashing."""
    audit = _audit_module(tree)
    client = MagicMock()
    client.get_raw = AsyncMock(return_value={"unexpected": True})

    result = await audit._run_roles(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
