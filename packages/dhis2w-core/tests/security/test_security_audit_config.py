"""Audit-config tests: the dhis.conf-posture reducer and the per-tree _run_audit_config wiring.

`evaluate_audit_config` is version-invariant and tested directly with hand-built `AuditPosture` inputs: the
API-only INFO when the posture is unparsed, the system-disabled / both-sinks-off / narrow-scope MEDIUMs,
and a healthy posture that yields no MEDIUM. The `_run_audit_config` wiring (no dhis.conf -> the API-only
INFO; a parsed tmp file -> the parsed verdicts; an unreadable path -> a degraded note) is exercised across
all three version trees.

DHIS2 matrix semantics (from `AuditMatrixConfigurer.java`):
- Absent or empty matrix key: DEFAULT_AUDIT_CONFIGURATION = {CREATE, UPDATE, DELETE, SECURITY} applied.
- Explicit non-empty matrix: parsed as semicolon-separated AuditType names.
- DISABLED token: explicitly disables the scope (empty type set).
- A default posture with NO audit.* config is therefore audited on all scopes and produces NO MEDIUM.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from dhis2w_core.security_core import (
    AuditPosture,
    AuditScopeMatrix,
    CheckStatus,
    Severity,
    evaluate_audit_config,
)

TREES = ("v41", "v42", "v43")


def _titles(findings: list[Any]) -> set[str]:
    """Collect finding titles for membership assertions."""
    return {finding.title for finding in findings}


def _severities(findings: list[Any]) -> set[Severity]:
    """Collect finding severities for tier assertions."""
    return {finding.severity for finding in findings}


def _default_scope(scope: str) -> AuditScopeMatrix:
    """A scope with no explicit matrix: DHIS2 default {CREATE, UPDATE, DELETE, SECURITY} applied."""
    return AuditScopeMatrix(scope=scope, explicit=False, audit_types=("CREATE", "UPDATE", "DELETE", "SECURITY"))


def _explicit_full_matrix(scope: str) -> AuditScopeMatrix:
    """A scope with an explicitly-set matrix covering all forensic change types plus READ/SEARCH."""
    return AuditScopeMatrix(
        scope=scope,
        explicit=True,
        audit_types=("CREATE", "READ", "UPDATE", "DELETE", "SEARCH", "SECURITY"),
    )


def _healthy_posture() -> AuditPosture:
    """A parsed posture with auditing on, a sink on, and a full explicit matrix on every scope."""
    return AuditPosture(
        system_enabled=True,
        logger_enabled=True,
        database_enabled=False,
        scopes=tuple(_explicit_full_matrix(scope) for scope in ("METADATA", "AGGREGATE", "TRACKER", "API")),
        source_path="/etc/dhis2/dhis.conf",
        parsed=True,
    )


def _default_config_posture() -> AuditPosture:
    """A parsed posture with NO audit.* matrix keys: DHIS2 applies its default to every scope."""
    return AuditPosture(
        system_enabled=True,
        logger_enabled=True,
        database_enabled=False,
        scopes=tuple(_default_scope(scope) for scope in ("METADATA", "AGGREGATE", "TRACKER", "API")),
        source_path="/etc/dhis2/dhis.conf",
        parsed=True,
    )


# ---------------------------------------------------------------------------
# evaluate_audit_config (version-invariant)
# ---------------------------------------------------------------------------


def test_unparsed_posture_yields_api_only_info() -> None:
    """An unparsed posture (no dhis.conf) yields exactly the not-API-readable INFO, never a MEDIUM."""
    findings = evaluate_audit_config(AuditPosture(parsed=False)).findings
    assert _titles(findings) == {"Audit configuration is not API-readable"}
    assert findings[0].severity is Severity.INFO
    # The wording must state it is not API-readable and explicitly deny that this means auditing is off.
    assert "not api-readable" in findings[0].title.lower()
    assert "not a statement that auditing is off" in findings[0].detail.lower()


def test_system_disabled_is_medium_and_short_circuits() -> None:
    """system.audit.enabled off flags the instance-wide MEDIUM and suppresses the scope findings."""
    posture = _healthy_posture().model_copy(update={"system_enabled": False})
    findings = evaluate_audit_config(posture).findings
    assert _titles(findings) == {"Auditing is disabled instance-wide"}
    assert findings[0].severity is Severity.MEDIUM


def test_both_sinks_off_is_medium() -> None:
    """audit.logger off AND audit.database off flags the both-sinks-off MEDIUM."""
    posture = _healthy_posture().model_copy(update={"logger_enabled": False, "database_enabled": False})
    findings = evaluate_audit_config(posture).findings
    assert "Both audit sinks are off" in _titles(findings)
    by_title = {f.title: f for f in findings}
    assert by_title["Both audit sinks are off"].severity is Severity.MEDIUM


def test_one_sink_on_does_not_flag_both_sinks_off() -> None:
    """With at least one sink on (database here), the both-sinks-off finding does not fire."""
    posture = _healthy_posture().model_copy(update={"logger_enabled": False, "database_enabled": True})
    assert "Both audit sinks are off" not in _titles(evaluate_audit_config(posture).findings)


def test_default_config_posture_has_no_medium() -> None:
    """A posture with NO explicit audit.* matrix keys (DHIS2 applies its default) yields no MEDIUM.

    This is the key correctness test: a fresh DHIS2 instance with no audit.* configuration in dhis.conf
    gets {CREATE, UPDATE, DELETE, SECURITY} on every scope by default and must NOT be flagged.
    """
    findings = evaluate_audit_config(_default_config_posture()).findings
    assert Severity.MEDIUM not in _severities(findings)


def test_explicit_narrow_matrix_is_medium() -> None:
    """An explicitly-configured matrix that omits forensic types flags the narrow-scope MEDIUM."""
    posture = AuditPosture(
        system_enabled=True,
        logger_enabled=True,
        scopes=(
            # METADATA: explicit but only CREATE and READ; omits UPDATE, DELETE, SECURITY.
            AuditScopeMatrix(scope="METADATA", explicit=True, audit_types=("CREATE", "READ")),
            # All other scopes: default (not explicit) -> no finding.
            _default_scope("AGGREGATE"),
            _default_scope("TRACKER"),
            _default_scope("API"),
        ),
        parsed=True,
    )
    findings = evaluate_audit_config(posture).findings
    by_title = {f.title: f for f in findings}
    narrow = by_title["Audit scope coverage is narrower than the DHIS2 default"]
    assert narrow.severity is Severity.MEDIUM
    # METADATA omits UPDATE/DELETE/SECURITY from the forensic set.
    assert "METADATA omits" in narrow.detail
    assert "UPDATE" in narrow.detail
    assert "DELETE" in narrow.detail
    assert "SECURITY" in narrow.detail


def test_explicit_disabled_scope_is_medium() -> None:
    """An explicitly-DISABLED scope omits all forensic types and is flagged as narrowly scoped."""
    posture = AuditPosture(
        system_enabled=True,
        logger_enabled=True,
        scopes=(
            # TRACKER: explicit DISABLED -> empty type set, omits all forensic types.
            AuditScopeMatrix(scope="TRACKER", explicit=True, audit_types=()),
            _default_scope("METADATA"),
            _default_scope("AGGREGATE"),
            _default_scope("API"),
        ),
        parsed=True,
    )
    findings = evaluate_audit_config(posture).findings
    by_title = {f.title: f for f in findings}
    narrow = by_title["Audit scope coverage is narrower than the DHIS2 default"]
    assert narrow.severity is Severity.MEDIUM
    assert "TRACKER omits" in narrow.detail


def test_healthy_posture_has_no_medium() -> None:
    """A fully-configured posture (auditing on, a sink on, every scope explicitly full) yields no MEDIUM findings."""
    findings = evaluate_audit_config(_healthy_posture()).findings
    assert Severity.MEDIUM not in _severities(findings)


# ---------------------------------------------------------------------------
# Per-tree wiring: _run_audit_config
# ---------------------------------------------------------------------------


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


@pytest.mark.parametrize("tree", TREES)
async def test_run_audit_config_no_path_is_api_only_info(tree: str) -> None:
    """With no --dhis-conf, the check is OK and emits only the not-API-readable INFO (posture unparsed)."""
    result = await _audit_module(tree)._run_audit_config(client=None, dhis_conf_path=None)
    assert result.status is CheckStatus.OK
    assert _titles(result.findings) == {"Audit configuration is not API-readable"}
    assert result.findings[0].severity is Severity.INFO


@pytest.mark.parametrize("tree", TREES)
async def test_run_audit_config_parsed_file_flags_weak_posture(tree: str, tmp_path: Path) -> None:
    """A dhis.conf with auditing on, both sinks off, and an explicit DISABLED scope flags the weak-posture MEDIUMs."""
    conf = tmp_path / "dhis.conf"
    conf.write_text(
        "\n".join(
            [
                "# audit posture",
                "system.audit.enabled = on",
                "audit.logger = off",
                "audit.database = off",
                # Explicit DISABLED scope: triggers narrowly-scoped finding.
                "audit.metadata = DISABLED",
            ]
        ),
        encoding="utf-8",
    )
    result = await _audit_module(tree)._run_audit_config(client=None, dhis_conf_path=conf)
    assert result.status is CheckStatus.OK
    titles = _titles(result.findings)
    assert "Both audit sinks are off" in titles
    assert "Audit scope coverage is narrower than the DHIS2 default" in titles


@pytest.mark.parametrize("tree", TREES)
async def test_run_audit_config_default_config_no_medium(tree: str, tmp_path: Path) -> None:
    """A dhis.conf with no audit.* matrix keys (DHIS2 default applied) produces no MEDIUM findings."""
    conf = tmp_path / "dhis.conf"
    conf.write_text(
        "\n".join(
            [
                "# minimal dhis.conf; no audit matrix keys",
                "system.audit.enabled = on",
                "audit.logger = on",
                "connection.url = jdbc:postgresql://localhost/dhis2",
            ]
        ),
        encoding="utf-8",
    )
    result = await _audit_module(tree)._run_audit_config(client=None, dhis_conf_path=conf)
    assert result.status is CheckStatus.OK
    severities = _severities(result.findings)
    assert Severity.MEDIUM not in severities


@pytest.mark.parametrize("tree", TREES)
async def test_run_audit_config_unreadable_path_degrades(tree: str, tmp_path: Path) -> None:
    """A missing --dhis-conf path degrades the check with a note rather than a finding about the instance."""
    missing = tmp_path / "does-not-exist.conf"
    result = await _audit_module(tree)._run_audit_config(client=None, dhis_conf_path=missing)
    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
    assert result.note is not None and "unreadable" in result.note


@pytest.mark.parametrize("tree", TREES)
async def test_run_audit_config_blank_file_degrades(tree: str, tmp_path: Path) -> None:
    """A dhis.conf copy with no readable key/value lines degrades with a note (ValueError path)."""
    conf = tmp_path / "dhis.conf"
    conf.write_text("# only comments\n! another comment\n\n", encoding="utf-8")
    result = await _audit_module(tree)._run_audit_config(client=None, dhis_conf_path=conf)
    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
    assert result.note is not None
