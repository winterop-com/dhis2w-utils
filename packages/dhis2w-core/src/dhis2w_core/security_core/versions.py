"""DHIS2 version classification: EOL lines, patch currency, and the advisory patch floor.

DHIS2 supports a rolling window of the most recent version lines at once (e.g.
2.41 / 2.42 / 2.43), so running a supported line that is not the newest is a
normal, healthy state: a newer line is reported as an INFO note, never a
problem. The graded signals are an end-of-life line (outside the support
window, HIGH), a version below its line's security-advisory patch floor (HIGH),
and being behind on the latest patch OR hotfix within the line (WARN).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.findings import AuditFinding, Severity
from dhis2w_core.security_core.releases import ReleaseFeed

_CHECK = "version"

# The oldest version line this tooling supports; the client refuses to connect
# below it, so a parsed line under this floor is EOL by definition.
MIN_SUPPORTED_LINE = 41


class ParsedVersion(BaseModel):
    """A DHIS2 version string decomposed into comparable parts."""

    model_config = ConfigDict(frozen=True)

    major: int
    line: int
    patch: int = 0
    hotfix: int = 0
    is_snapshot: bool = False
    raw: str


class AdvisoryFloor(BaseModel):
    """The lowest patch on a version line that clears all published DHIS2 advisories."""

    model_config = ConfigDict(frozen=True)

    line: int
    min_patch: int
    min_hotfix: int = 0
    advisories: list[str] = []
    note: str = ""


class VersionPosture(BaseModel):
    """The running DHIS2 version, its parsed parts, and the version findings.

    The single-request version read shared by the CLI and the MCP `security_version`
    tool: the raw version string, its decomposed parts (None when unparseable), and
    the findings from classifying it against the static advisory floor and EOL line
    rules. `findings` carries the EOL/below-floor verdicts without the external
    release-feed refinement, so this posture is derivable from one DHIS2 request.
    """

    model_config = ConfigDict(frozen=True)

    version: str | None
    parsed: ParsedVersion | None
    findings: tuple[AuditFinding, ...]


def build_version_posture(raw: str | None) -> VersionPosture:
    """Parse a DHIS2 version string and classify it with no external release feed (feed=None).

    Passing `feed=None` keeps the posture a pure function of the single version
    read: the EOL-line and advisory-floor verdicts still fire, but the
    behind-latest-patch refinement (which needs releases.dhis2.org) is omitted.
    """
    parsed = parse_dhis2_version(raw)
    return VersionPosture(version=raw, parsed=parsed, findings=tuple(evaluate_version(parsed, feed=None)))


# Curated from the DHIS2 GitHub security advisories
# (https://github.com/dhis2/dhis2-core/security/advisories). Each entry is the
# lowest patch.hotfix on that line that clears every advisory published so far.
# Keep this in step with new advisories; bump ADVISORY_PATCH_FLOOR_REVIEWED when
# re-checked. A running version below its line's floor is HIGH (known unfixed
# security issue). Re-verify against the advisory list, not from memory.
ADVISORY_PATCH_FLOOR_REVIEWED = "2026-06-18"
ADVISORY_PATCH_FLOOR: dict[int, AdvisoryFloor] = {
    41: AdvisoryFloor(
        line=41,
        min_patch=8,
        min_hotfix=2,
        advisories=["GHSA-pwmg-mvjw-4m23"],
        note="SQL injection in SqlView filter parameter (arbitrary database read).",
    ),
    42: AdvisoryFloor(
        line=42,
        min_patch=5,
        min_hotfix=1,
        advisories=["GHSA-pwmg-mvjw-4m23", "GHSA-3fr2-wvqx-cmr5", "GHSA-6785-hj47-c27h"],
        note="SQLi (SqlView filter), unsafe Java deserialization RCE, and reflected XSS (OpenAPI scope param).",
    ),
    43: AdvisoryFloor(
        line=43,
        min_patch=0,
        min_hotfix=1,
        advisories=["GHSA-pwmg-mvjw-4m23", "GHSA-3fr2-wvqx-cmr5", "GHSA-6785-hj47-c27h"],
        note="SQLi (SqlView filter), unsafe Java deserialization RCE, and reflected XSS (OpenAPI scope param).",
    ),
}


def parse_dhis2_version(raw: str | None) -> ParsedVersion | None:
    """Decompose a `/api/system/info` version string; None when it is missing or unparseable."""
    if not raw:
        return None
    head, _, suffix = raw.partition("-")
    parts = head.split(".")
    numbers: list[int] = []
    for token in parts:
        try:
            numbers.append(int(token))
        except ValueError:
            return None
    if len(numbers) < 2:
        return None
    return ParsedVersion(
        major=numbers[0],
        line=numbers[1],
        patch=numbers[2] if len(numbers) > 2 else 0,
        hotfix=numbers[3] if len(numbers) > 3 else 0,
        is_snapshot=suffix.upper().startswith("SNAPSHOT"),
        raw=raw,
    )


def evaluate_version(parsed: ParsedVersion | None, feed: ReleaseFeed | None) -> list[AuditFinding]:
    """Classify the running version: stripped (INFO), EOL line (HIGH), advisory floor (HIGH), else patch currency."""
    if parsed is None:
        return [
            AuditFinding(
                check=_CHECK,
                severity=Severity.INFO,
                title="DHIS2 version not exposed",
                detail="The server did not report a parseable version; patch and advisory checks cannot run.",
            )
        ]
    findings: list[AuditFinding] = []
    findings.extend(_eol_findings(parsed, feed))
    findings.extend(_newer_line_findings(parsed, feed))
    floor_finding = _advisory_floor_finding(parsed)
    if floor_finding is not None:
        findings.append(floor_finding)
    else:
        findings.extend(_patch_currency_findings(parsed, feed))
    return findings


def _eol_findings(parsed: ParsedVersion, feed: ReleaseFeed | None) -> list[AuditFinding]:
    """Flag an unsupported (EOL) version line."""
    if parsed.line < MIN_SUPPORTED_LINE:
        return [
            AuditFinding(
                check=_CHECK,
                severity=Severity.HIGH,
                title="End-of-life DHIS2 version",
                detail=f"DHIS2 2.{parsed.line} is older than 2.{MIN_SUPPORTED_LINE} and is EOL by definition.",
                evidence={"version": parsed.raw},
            )
        ]
    entry = feed.line(parsed.line) if feed is not None else None
    if entry is not None and not entry.supported:
        return [
            AuditFinding(
                check=_CHECK,
                severity=Severity.HIGH,
                title="End-of-life DHIS2 version",
                detail=f"DHIS2 2.{parsed.line} is no longer supported; it receives no security fixes.",
                evidence={"version": parsed.raw},
            )
        ]
    return []


def _newer_line_findings(parsed: ParsedVersion, feed: ReleaseFeed | None) -> list[AuditFinding]:
    """Note (INFO) that a newer version line exists; a supported older line is still a fine state."""
    if feed is None:
        return []
    latest = feed.latest_line()
    if latest is None or parsed.line >= latest:
        return []
    return [
        AuditFinding(
            check=_CHECK,
            severity=Severity.INFO,
            title="Newer DHIS2 version line available",
            detail=f"Running the 2.{parsed.line} line; 2.{latest} is the latest released line.",
            evidence={"running_line": f"2.{parsed.line}", "latest_line": f"2.{latest}"},
        )
    ]


def _patch_currency_findings(parsed: ParsedVersion, feed: ReleaseFeed | None) -> list[AuditFinding]:
    """Flag being behind on the latest patch OR hotfix within the running line."""
    entry = feed.line(parsed.line) if feed is not None else None
    if entry is None or (parsed.patch, parsed.hotfix) >= (entry.latest_patch, entry.latest_hotfix):
        return []
    latest = _format_version(parsed.line, entry.latest_patch, entry.latest_hotfix)
    return [
        AuditFinding(
            check=_CHECK,
            severity=Severity.WARN,
            title="Patch or hotfix update available",
            detail=f"Running {parsed.raw}; the latest on the 2.{parsed.line} line is {latest}.",
            evidence={"running": parsed.raw, "latest": latest},
        )
    ]


def _format_version(line: int, patch: int, hotfix: int) -> str:
    """Render a line/patch/hotfix triple, omitting a zero hotfix (2.42.5 vs 2.42.5.1)."""
    base = f"2.{line}.{patch}"
    return f"{base}.{hotfix}" if hotfix else base


def _advisory_floor_finding(parsed: ParsedVersion) -> AuditFinding | None:
    """Flag a version below its line's advisory patch floor (known unfixed security issues)."""
    floor = ADVISORY_PATCH_FLOOR.get(parsed.line)
    if floor is None or (parsed.patch, parsed.hotfix) >= (floor.min_patch, floor.min_hotfix):
        return None
    fixed = f"2.{floor.line}.{floor.min_patch}.{floor.min_hotfix}"
    return AuditFinding(
        check=_CHECK,
        severity=Severity.HIGH,
        title="Running below the security-advisory patch floor",
        detail=(f"{parsed.raw} is below {fixed}, which fixes: {floor.note} Advisories: {', '.join(floor.advisories)}."),
        evidence={"version": parsed.raw, "fixed_in": fixed, "advisories": ", ".join(floor.advisories)},
    )
