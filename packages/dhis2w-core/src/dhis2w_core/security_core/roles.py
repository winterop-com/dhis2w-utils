"""Instance role audit: classify user roles by their dangerous authority reach."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.authorities import categorise_authorities
from dhis2w_core.security_core.controls import CheckOutcome, ControlLog
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


def evaluate_roles(roles: list[RoleAudit]) -> CheckOutcome:
    """Record ALL-granting and dangerous-category role controls, flagging each role that trips them."""
    log = ControlLog(_CHECK)
    log.mark_passed("roles-grants-all-in-use", "roles-grants-all-unused", "roles-dangerous-authorities")
    for role in roles:
        if role.is_all:
            log.record(_all_finding(role))
        elif role.categories:
            log.record(_dangerous_finding(role))
    return log.result()


def _all_finding(role: RoleAudit) -> AuditFinding:
    """A role granting ALL: CRITICAL when accounts hold it, HIGH when it is unused."""
    if role.member_count > 0:
        severity = Severity.CRITICAL
        detail = f"Role '{role.name}' grants ALL (full superuser) to {role.member_count} account(s)."
        control = "roles-grants-all-in-use"
    else:
        severity = Severity.HIGH
        detail = f"Role '{role.name}' grants ALL (full superuser) but currently has no members."
        control = "roles-grants-all-unused"
    return AuditFinding(
        check=_CHECK,
        severity=severity,
        title="Role grants ALL (superuser)",
        detail=detail,
        subject=role.name,
        evidence={"role_id": role.id, "members": str(role.member_count)},
        control=control,
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
        control="roles-dangerous-authorities",
    )
