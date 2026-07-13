"""Sharing findings: the security reduction over the `SharingGraph`.

These findings are a projection of the one graph, never derived independently. Each object node
carries its decoded public access and external flag, so the findings are a per-object scan: objects
reachable with no login at all (external) are the worst case, then public write to data-bearing
objects, then public write to plain metadata, then broad public read of data or of SQL views. The
explicit user/group share edges are explorer detail, not findings, so they are not flagged here.
"""

from __future__ import annotations

from dhis2w_core.security_core.controls import CheckOutcome, ControlLog
from dhis2w_core.security_core.findings import AuditFinding, Severity
from dhis2w_core.security_core.sharing.model import ExposureKind, ObjectNode, SharingGraph, public_exposure_kind

_CHECK = "sharing"


def evaluate_sharing(graph: SharingGraph) -> CheckOutcome:
    """Reduce the graph's object nodes into a sharing-exposure outcome, most-urgent concerns first."""
    log = ControlLog(_CHECK)
    log.mark_passed(
        "sharing-external",
        "sharing-public-write-data",
        "sharing-public-write-metadata",
        "sharing-public-sql-view",
        "sharing-public-read-data",
    )
    for obj in graph.objects:
        for finding in _object_findings(obj):
            log.record(finding)
    return log.result()


def _object_findings(obj: ObjectNode) -> list[AuditFinding]:
    """Findings for one object: external exposure plus its dominant public exposure.

    The exposure precedence lives once in `public_exposure_kind`; the read findings it resolves are
    suppressed when the object is external, since anonymous reach already dominates a public-read concern.
    """
    findings: list[AuditFinding] = []
    if obj.external:
        findings.append(_external_finding(obj))
    public = _public_finding(obj)
    if public is not None:
        findings.append(public)
    return findings


def _public_finding(obj: ObjectNode) -> AuditFinding | None:
    """The one public-exposure finding for an object, keyed off the shared precedence kind."""
    kind = public_exposure_kind(obj)
    if kind is ExposureKind.PUBLIC_WRITE_DATA:
        return _public_write_data_finding(obj)
    if kind is ExposureKind.PUBLIC_WRITE_METADATA:
        return _public_write_metadata_finding(obj)
    if obj.external:
        return None
    if kind is ExposureKind.SQL_VIEW_READ:
        return _sql_view_read_finding(obj)
    if kind is ExposureKind.PUBLIC_DATA_READ:
        return _public_data_read_finding(obj)
    return None


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
        control="sharing-external",
    )


def _public_write_data_finding(obj: ObjectNode) -> AuditFinding:
    """Public write to a data-bearing object: HIGH, since any account can alter its definition or data."""
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
        control="sharing-public-write-data",
    )


def _public_write_metadata_finding(obj: ObjectNode) -> AuditFinding:
    """Public metadata write on a non-data-bearing object: MEDIUM, since any account can change it."""
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
        control="sharing-public-write-metadata",
    )


def _sql_view_read_finding(obj: ObjectNode) -> AuditFinding:
    """A publicly-readable SQL view: MEDIUM, since any account can run it and read what it queries."""
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
        control="sharing-public-sql-view",
    )


def _public_data_read_finding(obj: ObjectNode) -> AuditFinding:
    """Public data read on a data-bearing object: MEDIUM, since its data is visible to any account."""
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
        control="sharing-public-read-data",
    )


def _axes(obj: ObjectNode) -> str:
    """Render an object's decoded public access as a compact `meta rw / data r-` summary."""
    meta = f"{'r' if obj.public.meta_read else '-'}{'w' if obj.public.meta_write else '-'}"
    data = f"{'r' if obj.public.data_read else '-'}{'w' if obj.public.data_write else '-'}"
    return f"meta {meta} / data {data}"


def _evidence(obj: ObjectNode) -> dict[str, str]:
    """Render-only evidence bag for a sharing finding: the object's uid, type, and public access."""
    return {"uid": obj.uid, "type": obj.type, "public": _axes(obj), "external": "true" if obj.external else "false"}
