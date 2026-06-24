"""Negative test: a secret value in a dhis.conf copy must never reach any rendered audit output.

Redaction in `dhisconf.py` is enforced by construction (`RedactedSecret` has no value field), so this test
is the proof: it writes a dhis.conf with a known sentinel password on every confidential key, parses it,
renders the resulting AuditReport through every format (md / txt / csv / html / json), and asserts the
sentinel string appears in none of them while `is_set` is reported correctly. A blank confidential key must
report `is_set=False`.
"""

from __future__ import annotations

from pathlib import Path

from dhis2w_core.security_core import (
    AuditReport,
    AuditSummary,
    CheckResult,
    CheckStatus,
    CsvRenderer,
    HtmlRenderer,
    MarkdownRenderer,
    RunManifest,
    TextRenderer,
    evaluate_audit_config,
    parse_dhis_conf,
)

# The sentinel that must never appear in any rendered output. It contains "=" to exercise the path where a
# confidential key's value includes the separator character (the parser must still read it correctly and the
# redaction model must suppress the entire value -- including the embedded "=").
_SENTINEL = "SUPER=SECRET=SENTINEL-9c3f1a"

_CONFIDENTIAL_KEYS = (
    "encryption.password",
    "connection.password",
    "analytics.connection.password",
    "ldap.manager.password",
    "redis.password",
    "artemis.password",
    "oauth2.server.jwt.keystore.password",
    "oauth2.server.jwt.keystore.key-password",
    "system.monitoring.password",
)


def _write_conf(tmp_path: Path) -> Path:
    """Write a dhis.conf copy with the sentinel on every confidential key plus a blank one to test is_set."""
    lines = [
        "# dhis.conf copy",
        "system.audit.enabled = on",
        "audit.logger = off",
        "audit.database = off",
        "audit.metadata =",
        "audit.aggregate =",
        "audit.tracker =",
        "audit.api =",
    ]
    # Every confidential key carries the sentinel except connection.password, which is blank (is_set=False).
    for key in _CONFIDENTIAL_KEYS:
        if key == "connection.password":
            lines.append(f"{key} =")
        else:
            lines.append(f"{key} = {_SENTINEL}")
    conf = tmp_path / "dhis.conf"
    conf.write_text("\n".join(lines), encoding="utf-8")
    return conf


def _report_from_conf(conf: Path) -> AuditReport:
    """Parse the conf, evaluate the posture, and wrap it in a one-check AuditReport."""
    posture = parse_dhis_conf(conf)
    result = CheckResult(
        check="audit-config",
        label="Audit logging configuration",
        status=CheckStatus.OK,
        findings=evaluate_audit_config(posture),
    )
    manifest = RunManifest(
        target="https://mock.example",
        profile="demo",
        scanner_version="0.0.0",
        started_at="2026-06-24T00:00:00+00:00",
        check_order=["audit-config"],
    )
    return AuditReport(manifest=manifest, results=[result], summary=AuditSummary.from_results([result]))


def test_secret_value_never_appears_in_any_rendered_format(tmp_path: Path) -> None:
    """The sentinel password must not appear in md / txt / csv / html / json output of the audit report."""
    conf = _write_conf(tmp_path)
    report = _report_from_conf(conf)

    rendered = {
        "md": MarkdownRenderer().render(report),
        "txt": TextRenderer().render(report),
        "csv": CsvRenderer().render(report),
        "html": HtmlRenderer().render(report),
        "json": report.model_dump_json(indent=2),
    }
    for fmt, text in rendered.items():
        assert _SENTINEL not in text, f"sentinel leaked into {fmt} output"

    # Emitting the full HTML bundle to disk must not leak the sentinel into any written file either.
    folder = tmp_path / "run"
    folder.mkdir()
    HtmlRenderer().emit(folder, report)
    for written in folder.iterdir():
        if written.suffix in (".png",):
            continue
        assert _SENTINEL not in written.read_text(encoding="utf-8"), f"sentinel leaked into {written.name}"


def test_posture_records_is_set_without_storing_the_value(tmp_path: Path) -> None:
    """A present confidential value reports is_set=True; a blank one reports is_set=False; no value is kept."""
    conf = _write_conf(tmp_path)
    posture = parse_dhis_conf(conf)
    by_key = {secret.key: secret for secret in posture.secrets}

    # connection.password is blank -> is_set False; every other confidential key is set -> is_set True.
    assert by_key["connection.password"].is_set is False
    for key in _CONFIDENTIAL_KEYS:
        if key == "connection.password":
            continue
        assert by_key[key].is_set is True, key

    # RedactedSecret has no value field, so the model dump can only carry the key and the flag.
    assert _SENTINEL not in posture.model_dump_json()
    assert set(by_key["encryption.password"].model_dump().keys()) == {"key", "is_set"}
