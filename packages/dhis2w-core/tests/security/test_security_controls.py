"""Unit tests for the control catalog and ControlLog: catalog integrity plus PASS/FLAGGED/SKIPPED bookkeeping.

The catalog is version-invariant (one shared tree), so these tests are not parametrised over the version trees.
"""

from __future__ import annotations

import pytest
from dhis2w_core.security_core import (
    CONTROL_CATALOG,
    AuditFinding,
    CheckOutcome,
    ControlLog,
    ControlStatus,
    Severity,
    canonical_keys,
)


def _finding(control: str | None, severity: Severity = Severity.HIGH, *, check: str = "settings") -> AuditFinding:
    """Build a minimal finding carrying a control id for ControlLog tests."""
    return AuditFinding(check=check, severity=severity, title="t", detail="d", control=control)


def test_catalog_covers_every_canonical_check() -> None:
    """CONTROL_CATALOG has an entry for every catalog check key and no stray keys."""
    assert set(CONTROL_CATALOG) == set(canonical_keys())


def test_control_ids_are_globally_unique() -> None:
    """No two controls, in any check, share an id."""
    ids = [spec.id for specs in CONTROL_CATALOG.values() for spec in specs]
    assert len(ids) == len(set(ids))


def test_every_control_has_a_nonempty_label() -> None:
    """Each control carries a human label for the report."""
    for specs in CONTROL_CATALOG.values():
        for spec in specs:
            assert spec.label.strip()


def test_fresh_log_defaults_every_control_to_skipped() -> None:
    """A ControlLog with no activity reports every catalog control as SKIPPED, not falsely passed."""
    outcome = ControlLog("settings").result()
    assert isinstance(outcome, CheckOutcome)
    assert outcome.findings == []
    assert {control.status for control in outcome.controls} == {ControlStatus.SKIPPED}
    assert len(outcome.controls) == len(CONTROL_CATALOG["settings"])


def test_mark_passed_promotes_untouched_control() -> None:
    """mark_passed turns an untouched control PASS and clears its skip note."""
    log = ControlLog("settings")
    log.mark_passed("settings-lockout-disabled")
    control = next(c for c in log.result().controls if c.id == "settings-lockout-disabled")
    assert control.status is ControlStatus.PASSED
    assert control.note is None


def test_record_flags_the_findings_control_and_appends_the_finding() -> None:
    """record appends the finding and flags its control at the finding's severity."""
    log = ControlLog("settings")
    log.record(_finding("settings-can-grant-own-authorities"))
    outcome = log.result()
    assert len(outcome.findings) == 1
    control = next(c for c in outcome.controls if c.id == "settings-can-grant-own-authorities")
    assert control.status is ControlStatus.FLAGGED
    assert control.severity is Severity.HIGH
    assert control.finding_titles == ["t"]


def test_record_keeps_the_most_severe_of_repeated_flags() -> None:
    """A control flagged more than once reports its worst severity and keeps every title."""
    log = ControlLog("roles")
    log.record(_finding("roles-dangerous-authorities", Severity.MEDIUM, check="roles"))
    log.record(_finding("roles-dangerous-authorities", Severity.HIGH, check="roles"))
    control = next(c for c in log.result().controls if c.id == "roles-dangerous-authorities")
    assert control.severity is Severity.HIGH
    assert len(control.finding_titles) == 2


def test_record_with_no_control_appends_finding_but_flags_nothing() -> None:
    """An informational finding (control=None) is kept in findings but flags no control."""
    log = ControlLog("credential-probe")
    log.record(_finding(None, Severity.INFO, check="credential-probe"))
    outcome = log.result()
    assert len(outcome.findings) == 1
    assert all(c.status is ControlStatus.SKIPPED for c in outcome.controls)


def test_mark_skipped_sets_status_and_reason() -> None:
    """mark_skipped records the reason a control could not run this run."""
    log = ControlLog("settings")
    log.mark_skipped("settings-cors-wildcard", "CORS whitelist not fetched")
    control = next(c for c in log.result().controls if c.id == "settings-cors-wildcard")
    assert control.status is ControlStatus.SKIPPED
    assert control.note == "CORS whitelist not fetched"


def test_flag_wins_over_later_mark_passed() -> None:
    """A control flagged during a collection scan stays FLAGGED even if mark_passed runs afterward."""
    log = ControlLog("roles")
    log.record(_finding("roles-grants-all-in-use", Severity.CRITICAL, check="roles"))
    log.mark_passed("roles-grants-all-in-use")
    control = next(c for c in log.result().controls if c.id == "roles-grants-all-in-use")
    assert control.status is ControlStatus.FLAGGED


def test_controls_are_returned_in_catalog_order() -> None:
    """result() lists controls in the catalog's declared display order."""
    outcome = ControlLog("transport").result()
    assert [c.id for c in outcome.controls] == [spec.id for spec in CONTROL_CATALOG["transport"]]


def test_unknown_control_id_raises() -> None:
    """Referencing a control id outside the check's catalog fails loudly, catching typos."""
    log = ControlLog("settings")
    with pytest.raises(KeyError):
        log.mark_passed("settings-not-a-real-control")
    with pytest.raises(KeyError):
        log.record(_finding("settings-not-a-real-control"))
