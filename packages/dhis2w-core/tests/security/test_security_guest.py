"""Guest-check tests: anonymous-access probe, self-registration, account recovery, and per-tree wiring.

`evaluate_guest` is version-invariant and tested directly. The `_run_guest` wiring runs an
unauthenticated probe through a throwaway httpx client (intercepted by respx) plus authenticated
reads for the self-registration role and account-recovery setting (a mock client), across all trees.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_core.security_core import (
    ANONYMOUS_PROBE_TARGETS,
    AnonymousResult,
    CheckStatus,
    Severity,
    evaluate_guest,
)

BASE = "https://mock.example"
TREES = ("v41", "v42", "v43")


def _titles(findings: list[Any]) -> set[str]:
    """Collect finding titles for membership assertions."""
    return {finding.title for finding in findings}


# ---------------------------------------------------------------------------
# evaluate_guest (version-invariant)
# ---------------------------------------------------------------------------


def test_anonymous_200_on_users_is_critical() -> None:
    """An unauthenticated 200 on /api/users is a CRITICAL anonymous-readability finding."""
    findings = evaluate_guest(
        anonymous=[AnonymousResult(path="/api/users", status_code=200, content_type="application/json")],
        self_registration_role=None,
        account_recovery=False,
    ).findings
    assert len(findings) == 1
    assert findings[0].title == "Endpoint readable without authentication"
    assert findings[0].severity is Severity.CRITICAL
    assert findings[0].subject == "/api/users"


def test_anonymous_200_on_user_roles_and_me_is_high() -> None:
    """An unauthenticated 200 on /api/userRoles or /api/me is HIGH."""
    findings = evaluate_guest(
        anonymous=[
            AnonymousResult(path="/api/userRoles", status_code=200, content_type="application/json"),
            AnonymousResult(path="/api/me", status_code=200, content_type="application/json; charset=utf-8"),
        ],
        self_registration_role=None,
        account_recovery=False,
    ).findings
    assert {f.subject for f in findings} == {"/api/userRoles", "/api/me"}
    assert all(f.severity is Severity.HIGH for f in findings)


def test_anonymous_200_with_non_json_body_is_not_flagged() -> None:
    """A 200 that is not JSON (e.g. an SSO proxy's HTML login page) is not a leak."""
    findings = evaluate_guest(
        anonymous=[AnonymousResult(path="/api/users", status_code=200, content_type="text/html; charset=utf-8")],
        self_registration_role=None,
        account_recovery=False,
    ).findings
    assert findings == []


def test_non_200_anonymous_results_are_not_flagged() -> None:
    """A 401/403/302 or a transport error (status None) is the expected closed state and not flagged."""
    findings = evaluate_guest(
        anonymous=[
            AnonymousResult(path="/api/users", status_code=401),
            AnonymousResult(path="/api/userRoles", status_code=302),
            AnonymousResult(path="/api/me", status_code=None),
        ],
        self_registration_role=None,
        account_recovery=False,
    ).findings
    assert findings == []


def test_self_registration_role_is_high() -> None:
    """A non-null self-registration role means anyone can register, a HIGH finding naming the role."""
    findings = evaluate_guest(anonymous=[], self_registration_role="Guest", account_recovery=False).findings
    assert len(findings) == 1
    assert findings[0].title == "Self-registration enabled"
    assert findings[0].severity is Severity.HIGH
    assert findings[0].subject == "Guest"


def test_account_recovery_is_info() -> None:
    """Account recovery enabled is an INFO posture note."""
    findings = evaluate_guest(anonymous=[], self_registration_role=None, account_recovery=True).findings
    assert len(findings) == 1
    assert findings[0].title == "Account recovery enabled"
    assert findings[0].severity is Severity.INFO


def test_clean_instance_has_no_guest_findings() -> None:
    """All endpoints closed, no self-registration, no recovery -> no findings."""
    findings = evaluate_guest(
        anonymous=[AnonymousResult(path=target.path, status_code=401) for target in ANONYMOUS_PROBE_TARGETS],
        self_registration_role=None,
        account_recovery=False,
    ).findings
    assert findings == []


# ---------------------------------------------------------------------------
# Per-tree wiring: _run_guest probes anonymously and reads self-registration + recovery
# ---------------------------------------------------------------------------


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _security_settings(tree: str, **fields: Any) -> Any:
    """Build the per-tree SecuritySettings projection with the given fields."""
    model = import_module(f"dhis2w_core.{tree}.plugins.security.models").SecuritySettings
    return model(**fields)


@pytest.mark.parametrize("tree", TREES)
@respx.mock
async def test_run_guest_flags_anonymous_leak_self_registration_and_recovery(tree: str) -> None:
    """_run_guest reports an anonymous /api/users leak, self-registration, and account recovery."""
    respx.get(f"{BASE}/api/users").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/api/userRoles").mock(return_value=httpx.Response(401))
    respx.get(f"{BASE}/api/me").mock(return_value=httpx.Response(401))

    client = MagicMock()
    client.base_url = BASE
    client.get_raw = AsyncMock(return_value={"id": "abc123", "name": "Guest role"})
    client.get = AsyncMock(return_value=_security_settings(tree, keyAccountRecovery=True))

    result = await _audit_module(tree)._run_guest(client)

    assert result.status is CheckStatus.OK
    titles = _titles(result.findings)
    assert "Endpoint readable without authentication" in titles
    leak = next(f for f in result.findings if f.subject == "/api/users")
    assert leak.severity is Severity.CRITICAL
    assert "Self-registration enabled" in titles
    assert "Account recovery enabled" in titles


@pytest.mark.parametrize("tree", TREES)
@respx.mock
async def test_run_guest_clean_instance(tree: str) -> None:
    """With every endpoint closed, no self-registration role, and recovery off, _run_guest finds nothing."""
    for path in ("/api/users", "/api/userRoles", "/api/me"):
        respx.get(f"{BASE}{path}").mock(return_value=httpx.Response(401))

    client = MagicMock()
    client.base_url = BASE
    client.get_raw = AsyncMock(return_value={"data": None})  # selfRegistrationRole null -> self-registration off
    client.get = AsyncMock(return_value=_security_settings(tree, keyAccountRecovery=False))

    result = await _audit_module(tree)._run_guest(client)

    assert result.status is CheckStatus.OK
    assert result.note is None
    assert result.findings == []


@pytest.mark.parametrize("tree", TREES)
@respx.mock
async def test_run_guest_notes_when_settings_unavailable(tree: str) -> None:
    """A systemSettings error degrades to a note but still reports the anonymous-probe findings."""
    respx.get(f"{BASE}/api/users").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/api/userRoles").mock(return_value=httpx.Response(401))
    respx.get(f"{BASE}/api/me").mock(return_value=httpx.Response(401))

    client = MagicMock()
    client.base_url = BASE
    client.get_raw = AsyncMock(return_value={"data": None})
    client.get = AsyncMock(side_effect=Dhis2ApiError(500, "settings boom"))

    result = await _audit_module(tree)._run_guest(client)

    assert result.status is CheckStatus.OK
    assert result.note is not None and "system settings unavailable" in result.note
    assert any(f.subject == "/api/users" for f in result.findings)
