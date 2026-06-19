"""Sharing findings: the security reduction over the `SharingGraph`.

These findings are a projection of the one graph, never derived independently. Each object node
carries its decoded public access and external flag, so the findings are a per-object scan: objects
reachable with no login at all (external) are the worst case, then public write to data-bearing
objects, then public write to plain metadata, then broad public read of data or of SQL views. The
explicit user/group share edges are explorer detail, not findings, so they are not flagged here.
"""

from __future__ import annotations

from dhis2w_core.security_core.findings import AuditFinding, Severity
from dhis2w_core.security_core.sharing.model import ObjectNode, SharingGraph

_CHECK = "sharing"
_SQL_VIEW_TYPE = "sqlView"


def evaluate_sharing(graph: SharingGraph) -> list[AuditFinding]:
    """Reduce the graph's object nodes into sharing-exposure findings, most-urgent concerns first."""
    findings: list[AuditFinding] = []
    for obj in graph.objects:
        findings.extend(_object_findings(obj))
    return findings


def _object_findings(obj: ObjectNode) -> list[AuditFinding]:
    """Findings for one object: external exposure, public write, then public read.

    The read finding is suppressed when the object is already external or publicly writable, since
    anonymous reach and write access both dominate a public-read concern.
    """
    findings: list[AuditFinding] = []
    if obj.external:
        findings.append(_external_finding(obj))
    write = _public_write_finding(obj)
    if write is not None:
        findings.append(write)
    elif not obj.external:
        read = _public_read_finding(obj)
        if read is not None:
            findings.append(read)
    return findings


def _external_finding(obj: ObjectNode) -> AuditFinding:
    """An externally-accessible object is reachable with no login at all (anonymous read)."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.HIGH,
        title="Object accessible without authentication",
        detail=(
            f"{obj.type} '{obj.name}' has external access enabled; it is reachable anonymously, with no "
            "login. Anything its sharing exposes is readable by anyone on the network."
        ),
        subject=obj.name,
        group_key="sharing-external",
        evidence=_evidence(obj),
    )


def _public_write_finding(obj: ObjectNode) -> AuditFinding | None:
    """Public write: HIGH on data-bearing objects, MEDIUM on plain metadata; None when not writable."""
    if obj.data_bearing and obj.public.has_write:
        return AuditFinding(
            check=_CHECK,
            severity=Severity.HIGH,
            title="Public write access to data-bearing object",
            detail=(
                f"{obj.type} '{obj.name}' grants write to every authenticated user (public {_axes(obj)}). "
                "On a data-bearing type this lets any logged-in account alter its definition or its data."
            ),
            subject=obj.name,
            group_key="sharing-public-write-data",
            evidence=_evidence(obj),
        )
    if not obj.data_bearing and obj.public.meta_write:
        return AuditFinding(
            check=_CHECK,
            severity=Severity.MEDIUM,
            title="Public write access to metadata object",
            detail=(
                f"{obj.type} '{obj.name}' grants metadata write to every authenticated user (public "
                f"{_axes(obj)}); any logged-in account can change it."
            ),
            subject=obj.name,
            group_key="sharing-public-write-metadata",
            evidence=_evidence(obj),
        )
    return None


def _public_read_finding(obj: ObjectNode) -> AuditFinding | None:
    """Broad public read: SQL views readable by everyone, or public data read on data-bearing types."""
    if obj.type == _SQL_VIEW_TYPE and obj.public.meta_read:
        return AuditFinding(
            check=_CHECK,
            severity=Severity.MEDIUM,
            title="SQL view readable by all users",
            detail=(
                f"SQL view '{obj.name}' is readable by every authenticated user; any logged-in account can "
                "run it and read whatever it queries, including tables the user could not otherwise reach."
            ),
            subject=obj.name,
            group_key="sharing-public-sql-view",
            evidence=_evidence(obj),
        )
    if obj.data_bearing and obj.public.data_read:
        return AuditFinding(
            check=_CHECK,
            severity=Severity.MEDIUM,
            title="Public read access to data-bearing object",
            detail=(
                f"{obj.type} '{obj.name}' grants data read to every authenticated user (public {_axes(obj)}); "
                "its data is visible to any logged-in account, subject to org-unit scope."
            ),
            subject=obj.name,
            group_key="sharing-public-read-data",
            evidence=_evidence(obj),
        )
    return None


def _axes(obj: ObjectNode) -> str:
    """Render an object's decoded public access as a compact `meta rw / data r-` summary."""
    meta = f"{'r' if obj.public.meta_read else '-'}{'w' if obj.public.meta_write else '-'}"
    data = f"{'r' if obj.public.data_read else '-'}{'w' if obj.public.data_write else '-'}"
    return f"meta {meta} / data {data}"


def _evidence(obj: ObjectNode) -> dict[str, str]:
    """Render-only evidence bag for a sharing finding: the object's uid, type, and public access."""
    return {"uid": obj.uid, "type": obj.type, "public": _axes(obj), "external": "true" if obj.external else "false"}
