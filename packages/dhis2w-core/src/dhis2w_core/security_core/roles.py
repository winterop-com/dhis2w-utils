"""Instance role audit: classify user roles by their dangerous authority reach."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.authorities import categorise_authorities
from dhis2w_core.security_core.findings import AuditFinding, Severity, role_severity

_CHECK = "roles"


class RoleAudit(BaseModel):
    """One user role with its authority reach and member count."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    authorities: list[str] = []
    member_count: int = 0
    is_all: bool = False
    categories: list[str] = []


def build_role_audit(*, role_id: str, name: str, authorities: list[str], member_count: int) -> RoleAudit:
    """Classify a role's authorities into the typed audit view-model."""
    auth_set = set(authorities)
    categories = [category.key for category in categorise_authorities(auth_set) if category.key != "superuser"]
    return RoleAudit(
        id=role_id,
        name=name,
        authorities=sorted(auth_set),
        member_count=member_count,
        is_all="ALL" in auth_set,
        categories=categories,
    )


def evaluate_roles(roles: list[RoleAudit]) -> list[AuditFinding]:
    """Turn the role inventory into findings: ALL-granting roles, then dangerous-category roles."""
    findings: list[AuditFinding] = []
    for role in roles:
        if role.is_all:
            findings.append(_all_finding(role))
        elif role.categories:
            findings.append(_dangerous_finding(role))
    return findings


def _all_finding(role: RoleAudit) -> AuditFinding:
    """A role granting ALL: CRITICAL when accounts hold it, HIGH when it is unused."""
    if role.member_count > 0:
        severity = Severity.CRITICAL
        detail = f"Role '{role.name}' grants ALL (full superuser) to {role.member_count} account(s)."
    else:
        severity = Severity.HIGH
        detail = f"Role '{role.name}' grants ALL (full superuser) but currently has no members."
    return AuditFinding(
        check=_CHECK,
        severity=severity,
        title="Role grants ALL (superuser)",
        detail=detail,
        subject=role.name,
        evidence={"role_id": role.id, "members": str(role.member_count)},
    )


def _dangerous_finding(role: RoleAudit) -> AuditFinding:
    """A non-ALL role in one or more dangerous categories: HIGH for high-impact, else MEDIUM."""
    severity = role_severity(role.categories)
    return AuditFinding(
        check=_CHECK,
        severity=severity,
        title="Role holds dangerous authorities",
        detail=(
            f"Role '{role.name}' holds {', '.join(role.categories)} authorities across {role.member_count} member(s)."
        ),
        subject=role.name,
        evidence={"role_id": role.id, "categories": ", ".join(role.categories), "members": str(role.member_count)},
    )
