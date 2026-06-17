"""Credential-probe tests: verdict shaping, the one-attempt guardrail, and end-to-end wiring.

The probe lives in each tree's `plugins.security.audit` (it opens its own
short-lived HTTP Basic client rather than the operator's profile client), so
the guardrail tests exercise it directly per tree and assert it issues exactly
one GET to /api/me with the admin/district pair and never retries.
"""

from __future__ import annotations

import base64
import io
import json
from importlib import import_module
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.security_core import (
    CREDENTIAL_PROBE_PATHS,
    MAX_PROBE_ATTEMPTS,
    CheckStatus,
    CredentialProbeResult,
    ProbeOutcome,
    Severity,
    classify_probe_status,
    evaluate_credential_probe,
)
from dhis2w_core.v42.plugins.security.models import SecuritySettings
from rich.console import Console
from typer.testing import CliRunner

BASE = "https://mock.example"
TREES = ("v41", "v42", "v43")


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _operator_client(*, lockout: bool) -> MagicMock:
    """A stand-in operator client whose only job here is to answer the lockout read."""
    client = MagicMock()
    client.base_url = BASE
    client.get = AsyncMock(return_value=SecuritySettings(keyLockMultipleFailedLogins=lockout))
    return client


def _quiet_console() -> Console:
    """A recording console that writes nowhere visible, so the warning can be inspected."""
    return Console(file=io.StringIO(), width=200, record=True)


# ---------------------------------------------------------------------------
# Verdict shaping (version-invariant, no network)
# ---------------------------------------------------------------------------


def test_classify_probe_status_maps_codes() -> None:
    """200 authenticates, 401 is rejected, anything else is inconclusive."""
    assert classify_probe_status(200) is ProbeOutcome.AUTHENTICATED
    assert classify_probe_status(401) is ProbeOutcome.REJECTED
    assert classify_probe_status(403) is ProbeOutcome.INCONCLUSIVE
    assert classify_probe_status(500) is ProbeOutcome.INCONCLUSIVE


def test_authenticated_probe_is_a_single_critical_finding() -> None:
    """A 200 from the default login yields one CRITICAL finding."""
    findings = evaluate_credential_probe(CredentialProbeResult(outcome=ProbeOutcome.AUTHENTICATED, status_code=200))
    assert len(findings) == 1
    assert findings[0].severity is Severity.CRITICAL
    assert findings[0].check == "credential-probe"


def test_rejected_probe_produces_no_findings() -> None:
    """A 401 means the default login was refused; that is the clean, finding-free path."""
    assert evaluate_credential_probe(CredentialProbeResult(outcome=ProbeOutcome.REJECTED, status_code=401)) == []


def test_inconclusive_probe_is_info_only() -> None:
    """An unexpected status is reported as INFO, never as a false CRITICAL."""
    findings = evaluate_credential_probe(CredentialProbeResult(outcome=ProbeOutcome.INCONCLUSIVE, status_code=500))
    assert len(findings) == 1
    assert findings[0].severity is Severity.INFO


# ---------------------------------------------------------------------------
# The one-attempt guardrail, exercised per tree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tree", TREES)
@respx.mock
async def test_probe_issues_exactly_one_basic_get_to_me(tree: str) -> None:
    """The probe makes a single GET /api/me carrying Basic admin/district, and never retries."""
    route = respx.get(f"{BASE}/api/me").mock(return_value=httpx.Response(401, json={}))
    audit = _audit_module(tree)

    result = await audit._run_credential_probe(_operator_client(lockout=False), _quiet_console())

    assert route.call_count == MAX_PROBE_ATTEMPTS, f"{tree}: probe must make at most one attempt"
    assert len(respx.calls) == 1, f"{tree}: probe must touch no path other than /api/me"
    request = route.calls[0].request
    assert request.method == "GET"
    assert request.url.path in CREDENTIAL_PROBE_PATHS
    scheme, token = request.headers["Authorization"].split(" ", 1)
    assert scheme == "Basic"
    assert base64.b64decode(token).decode() == "admin:district"
    assert result.status is CheckStatus.OK
    assert result.findings == []  # 401 is the clean path


@pytest.mark.parametrize("tree", TREES)
@respx.mock
async def test_probe_flags_critical_when_default_login_succeeds(tree: str) -> None:
    """A 200 from /api/me surfaces a CRITICAL default-credentials finding."""
    respx.get(f"{BASE}/api/me").mock(return_value=httpx.Response(200, json={"username": "admin"}))
    audit = _audit_module(tree)

    result = await audit._run_credential_probe(_operator_client(lockout=False), _quiet_console())

    assert result.status is CheckStatus.OK
    assert [finding.severity for finding in result.findings] == [Severity.CRITICAL]


@pytest.mark.parametrize("tree", TREES)
@respx.mock
async def test_probe_degrades_on_transport_error(tree: str) -> None:
    """An unreachable host degrades the probe instead of crashing the audit."""
    respx.get(f"{BASE}/api/me").mock(side_effect=httpx.ConnectError("unreachable"))
    audit = _audit_module(tree)

    result = await audit._run_credential_probe(_operator_client(lockout=False), _quiet_console())

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []


@pytest.mark.parametrize("tree", TREES)
@respx.mock
async def test_probe_warns_when_lockout_is_active(tree: str) -> None:
    """With keyLockMultipleFailedLogins on, the probe warns before attempting and notes it."""
    respx.get(f"{BASE}/api/me").mock(return_value=httpx.Response(401, json={}))
    audit = _audit_module(tree)
    console = _quiet_console()

    result = await audit._run_credential_probe(_operator_client(lockout=True), console)

    output = console.export_text()
    assert "WARNING" in output
    assert "lockout" in output.lower()
    assert result.note is not None and "lockout" in result.note.lower()


# ---------------------------------------------------------------------------
# Default-on wiring: a full audit runs the probe with no extra flags
# ---------------------------------------------------------------------------


def test_audit_runs_credential_probe_by_default(tmp_path: Path) -> None:
    """`security audit` (no flags) includes the probe and reports a 200 as CRITICAL."""
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=SecuritySettings(keyLockMultipleFailedLogins=False))
    fake_client.get_raw = AsyncMock(return_value={"data": ["F_USER_ADD"]})
    fake_client.base_url = BASE
    fake_client.raw_version = "2.42.0"
    ctx = AsyncMock()
    ctx.__aenter__.return_value = fake_client
    ctx.__aexit__.return_value = None

    with (
        respx.mock(assert_all_called=False) as mock,
        patch("dhis2w_core.v42.plugins.security.audit.open_client", lambda *a, **k: ctx),
    ):
        mock.get(f"{BASE}/api/me").mock(return_value=httpx.Response(200, json={"username": "admin"}))
        result = CliRunner().invoke(
            build_app(), ["--json", "security", "audit", "--output-dir", str(tmp_path), "--no-progress"]
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    probe_results = [entry for entry in payload["results"] if entry["check"] == "credential-probe"]
    assert len(probe_results) == 1, "the probe must run by default"
    assert payload["summary"]["critical"] >= 1
