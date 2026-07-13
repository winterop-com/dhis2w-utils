"""Unit tests for build_report_view: finding grouping, ordering, scorecard invariant, payload shape.

The view is version-invariant (it projects an already-built AuditReport), so these tests are not
parametrised over the version trees.
"""

from __future__ import annotations

import json

from dhis2w_core.security_core import (
    AuditFinding,
    AuditReport,
    AuditSummary,
    CheckResult,
    CheckStatus,
    ControlOutcome,
    ControlStatus,
    RunManifest,
    Severity,
    build_report_view,
)

_MANIFEST = RunManifest(
    target="https://test.example",
    profile="default",
    scanner_version="0.0.1-test",
    started_at="2026-01-01T00:00:00+00:00",
    dhis2_version="2.42.0",
    check_order=["hygiene"],
)


def _finding(
    severity: Severity,
    title: str,
    *,
    subject: str | None = None,
    group_key: str | None = None,
    last: str | None = None,
    check: str = "hygiene",
) -> AuditFinding:
    """Build an AuditFinding for view tests, optionally carrying a group key and last-seen stamp."""
    evidence = {"last": last} if last is not None else None
    return AuditFinding(
        check=check,
        severity=severity,
        title=title,
        detail=f"Detail for {title}.",
        subject=subject,
        evidence=evidence,
        group_key=group_key,
    )


def _report(results: list[CheckResult]) -> AuditReport:
    """Wrap check results into a full AuditReport with the rolled-up summary."""
    return AuditReport(manifest=_MANIFEST, results=results, summary=AuditSummary.from_results(results))


def _section(label: str, findings: list[AuditFinding], *, note: str | None = None) -> CheckResult:
    """Build one OK CheckResult for the given findings."""
    return CheckResult(check="hygiene", label=label, status=CheckStatus.OK, findings=findings, note=note)


def test_findings_sharing_group_key_fold_into_one_collapsible_group() -> None:
    """Per-account findings with the same group_key fold into a single group whose count is the total."""
    findings = [
        _finding(Severity.HIGH, "Never logged in", subject="arabicB", group_key="never"),
        _finding(Severity.HIGH, "Never logged in", subject="bengali", group_key="never"),
        _finding(Severity.HIGH, "Never logged in", subject="khmer", group_key="never"),
    ]
    view = build_report_view(_report([_section("Hygiene", findings)]))
    groups = view.sections[0].groups
    assert len(groups) == 1
    group = groups[0]
    assert group.count == 3
    assert [item.name for item in group.items] == ["arabicB", "bengali", "khmer"]


def test_group_items_carry_last_seen_from_evidence() -> None:
    """A folded group surfaces each finding's evidence['last'] as the item's last stamp."""
    findings = [
        _finding(Severity.MEDIUM, "Stale", subject="traore", group_key="stale", last="2013-12-30T17:16:43.235"),
        _finding(Severity.MEDIUM, "Stale", subject="konan", group_key="stale", last="2019-04-29T16:13:04.047"),
    ]
    view = build_report_view(_report([_section("Hygiene", findings)]))
    items = view.sections[0].groups[0].items
    assert {item.name: item.last for item in items} == {
        "traore": "2013-12-30T17:16:43.235",
        "konan": "2019-04-29T16:13:04.047",
    }


def test_findings_without_group_key_each_render_as_their_own_row() -> None:
    """group_key=None findings stay separate single rows even when they share a title."""
    findings = [
        _finding(Severity.HIGH, "Role holds dangerous authorities", subject="M and E Officer", check="roles"),
        _finding(Severity.HIGH, "Role holds dangerous authorities", subject="Superuser", check="roles"),
    ]
    view = build_report_view(_report([_section("Roles", findings)]))
    groups = view.sections[0].groups
    assert len(groups) == 2
    assert all(group.count == 1 for group in groups)


def test_single_count_group_has_no_items() -> None:
    """A group with a single finding renders as a static row and carries no item list."""
    findings = [_finding(Severity.MEDIUM, "Default seed account", subject="admin", group_key="seed")]
    view = build_report_view(_report([_section("Hygiene", findings)]))
    group = view.sections[0].groups[0]
    assert group.count == 1
    assert group.items == []


def test_same_group_key_different_severity_does_not_merge() -> None:
    """Findings sharing a group_key but differing in severity stay separate so the scorecard invariant holds."""
    findings = [
        _finding(Severity.HIGH, "Flag", subject="a", group_key="k"),
        _finding(Severity.HIGH, "Flag", subject="b", group_key="k"),
        _finding(Severity.MEDIUM, "Flag", subject="c", group_key="k"),
    ]
    view = build_report_view(_report([_section("Sec", findings)]))
    groups = view.sections[0].groups
    # Never one mixed-severity group: HIGH folds to count 2, MEDIUM stays count 1.
    assert sorted((group.sev.value, group.count) for group in groups) == [("HIGH", 2), ("MEDIUM", 1)]
    tally: dict[str, int] = {}
    for group in groups:
        tally[group.sev.value] = tally.get(group.sev.value, 0) + group.count
    assert view.scorecard.high == tally["HIGH"] == 2
    assert view.scorecard.medium == tally["MEDIUM"] == 1


def test_groups_sorted_most_urgent_first_then_by_title() -> None:
    """Groups within a section sort by severity rank, then alphabetically by finding title."""
    findings = [
        _finding(Severity.INFO, "Inventory", group_key="inv"),
        _finding(Severity.WARN, "No email", subject="a", group_key="email"),
        _finding(Severity.HIGH, "Never logged in", subject="b", group_key="never"),
        _finding(Severity.MEDIUM, "Stale", subject="c", group_key="stale"),
        _finding(Severity.MEDIUM, "Default seed", subject="admin", group_key="seed"),
    ]
    view = build_report_view(_report([_section("Hygiene", findings)]))
    order = [(group.sev.value, group.finding) for group in view.sections[0].groups]
    assert order == [
        ("HIGH", "Never logged in"),
        ("MEDIUM", "Default seed"),
        ("MEDIUM", "Stale"),
        ("WARN", "No email"),
        ("INFO", "Inventory"),
    ]


def test_scorecard_equals_sum_of_group_counts_per_severity() -> None:
    """The hero scorecard total for each severity equals the sum of group counts of that severity."""
    hygiene = _section(
        "Hygiene",
        [
            _finding(Severity.HIGH, "Never logged in", subject="a", group_key="never"),
            _finding(Severity.HIGH, "Never logged in", subject="b", group_key="never"),
            _finding(Severity.WARN, "No email", subject="a", group_key="email"),
            _finding(Severity.MEDIUM, "Stale", subject="c", group_key="stale"),
            _finding(Severity.INFO, "Inventory", group_key="inv"),
        ],
    )
    roles = _section(
        "Roles",
        [
            _finding(Severity.CRITICAL, "Role grants ALL", subject="Sysadmin", check="roles"),
            _finding(Severity.HIGH, "Role holds dangerous authorities", subject="Superuser", check="roles"),
        ],
    )
    view = build_report_view(_report([hygiene, roles]))

    tally: dict[str, int] = {}
    for section in view.sections:
        for group in section.groups:
            tally[group.sev.value] = tally.get(group.sev.value, 0) + group.count

    scorecard = view.scorecard
    assert scorecard.critical == tally.get("CRITICAL", 0) == 1
    assert scorecard.high == tally.get("HIGH", 0) == 3
    assert scorecard.medium == tally.get("MEDIUM", 0) == 1
    assert scorecard.warn == tally.get("WARN", 0) == 1
    assert scorecard.info == tally.get("INFO", 0) == 1


def test_section_status_carries_label_and_optional_note() -> None:
    """The status model carries the raw check-status label and the optional note when present."""
    findings = [_finding(Severity.INFO, "Inventory", group_key="inv")]
    view = build_report_view(_report([_section("Hygiene", findings, note="2FA endpoint unavailable")]))
    assert view.sections[0].status.label == "ok"
    assert view.sections[0].status.note == "2FA endpoint unavailable"
    plain = build_report_view(_report([_section("Hygiene", findings)]))
    assert plain.sections[0].status.label == "ok"
    assert plain.sections[0].status.note is None


def test_meta_uses_unknown_when_dhis2_version_missing() -> None:
    """meta.version falls back to 'unknown' when the manifest has no detected DHIS2 version."""
    manifest = _MANIFEST.model_copy(update={"dhis2_version": None})
    report = AuditReport(manifest=manifest, results=[], summary=AuditSummary.from_results([]))
    assert build_report_view(report).meta.version == "unknown"


def test_section_projects_control_outcomes_with_status_and_severity() -> None:
    """build_report_view projects each CheckResult.controls entry into the section's control list."""
    controls = [
        ControlOutcome(id="settings-lockout-disabled", label="Failed-login lockout", status=ControlStatus.PASSED),
        ControlOutcome(
            id="settings-can-grant-own-authorities",
            label="Self-grant of authorities",
            status=ControlStatus.FLAGGED,
            severity=Severity.HIGH,
            finding_titles=["x"],
        ),
        ControlOutcome(
            id="settings-cors-wildcard",
            label="CORS wildcard origin",
            status=ControlStatus.SKIPPED,
            note="CORS whitelist not fetched",
        ),
    ]
    result = CheckResult(check="settings", label="Settings", status=CheckStatus.OK, controls=controls)
    section = build_report_view(_report([result])).sections[0]
    assert [(control.label, control.status) for control in section.controls] == [
        ("Failed-login lockout", "PASS"),
        ("Self-grant of authorities", "FLAGGED"),
        ("CORS wildcard origin", "SKIPPED"),
    ]
    assert section.controls[0].severity is None  # a PASS carries no severity
    assert section.controls[1].severity is Severity.HIGH
    assert section.controls[2].note == "CORS whitelist not fetched"


def test_control_outcomes_serialise_into_report_data_js() -> None:
    """to_report_data_js carries each section's controls with status and severity for the template runtime."""
    controls = [
        ControlOutcome(
            id="roles-grants-all-in-use",
            label="Roles granting ALL that are in use",
            status=ControlStatus.FLAGGED,
            severity=Severity.CRITICAL,
            finding_titles=["r"],
        )
    ]
    result = CheckResult(check="roles", label="Roles", status=CheckStatus.OK, controls=controls)
    js = build_report_view(_report([result])).to_report_data_js()
    payload = json.loads(js.removeprefix("window.__REPORT__ = ").rstrip().removesuffix(";"))
    control = payload["sections"][0]["controls"][0]
    assert control["status"] == "FLAGGED"
    assert control["severity"] == "CRITICAL"
    assert control["label"] == "Roles granting ALL that are in use"


def test_to_report_data_js_is_an_assignable_json_payload() -> None:
    """to_report_data_js emits `window.__REPORT__ = <json>;` with uppercase scorecard and camel keys."""
    findings = [
        _finding(Severity.HIGH, "Never logged in", subject="a", group_key="never"),
        _finding(Severity.HIGH, "Never logged in", subject="b", group_key="never"),
    ]
    js = build_report_view(_report([_section("Hygiene", findings)])).to_report_data_js()
    assert js.startswith("window.__REPORT__ = ")
    assert js.rstrip().endswith(";")
    payload = json.loads(js.removeprefix("window.__REPORT__ = ").rstrip().removesuffix(";"))
    assert set(payload["scorecard"]) == {"CRITICAL", "HIGH", "MEDIUM", "WARN", "INFO"}
    assert payload["meta"]["target"] == "https://test.example"
    group = payload["sections"][0]["groups"][0]
    assert group["sampleDetail"]  # camelCase key the template reads
    assert group["count"] == 2
