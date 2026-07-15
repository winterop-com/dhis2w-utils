"""Enforcement tests for the read-only guardrail: the hook itself, a full run, resume, and escaping.

These cover the load-bearing safety properties the security audit promises but that the
per-check unit tests do not exercise end-to-end: the request hook rejects any off-contract
request, a complete audit run issues only allowlisted GETs, a resumed run rebuilds the sharing
explorer from the persisted graph without re-scanning, and a hostile instance's markup stays inert
in the rendered report and explorer bundles.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_core.security_core import (
    CONNECT_PATHS,
    GET_ALLOWLIST,
    AuditFinding,
    AuditOptions,
    AuditReport,
    AuditSummary,
    CheckResult,
    CheckStatus,
    ExplorerRenderer,
    GuardrailViolation,
    HtmlRenderer,
    ObjectNode,
    RoleNode,
    RunManifest,
    Severity,
    SharingGraph,
    UserNode,
    build_sharing_view,
    guardrail_request_hook,
)
from dhis2w_core.security_core.guardrails import ALLOWED_AUDIT_PATHS

BASE = "https://dhis2.example"

TREES: tuple[tuple[str, str], ...] = (("v41", "2.41.8.1"), ("v42", "2.42.0"), ("v43", "2.43.0"))

# The full set of endpoints a complete audit run touches (minus the version check's external release
# feed). Enumerated from a real run so a future check that reaches a new endpoint fails assert_all_mocked.
_RUN_ENDPOINTS: dict[str, object] = {
    "/api/systemSettings": {"minPasswordLength": 4, "keyAccountRecovery": True, "keyLockMultipleFailedLogins": False},
    "/api/me/authorization": {"data": ["ALL"]},
    "/api/me": {"id": "abc"},
    "/api/userRoles": {"userRoles": []},
    "/api/users": {"users": []},
    "/api/userGroups": {"userGroups": []},
    "/api/schemas": {"schemas": [{"name": "dataSet", "plural": "dataSets", "shareable": True, "dataShareable": True}]},
    # The one schema stubbed shareable above (dataSet), so the sharing scan's data-driven
    # `f"/api/{focus.plural}"` request (built from the /api/schemas response, not hardcoded) is
    # actually issued and exercised, not just the never-taken static allowlist entry.
    "/api/dataSets": {
        "dataSets": [
            {
                "id": "ds1",
                "name": "HIV",
                "sharing": {"public": "--------", "external": False, "users": {}, "userGroups": {}},
            }
        ],
        "pager": {"page": 1, "pageCount": 1, "total": 1},
    },
    "/api/apps": [],
    "/api/appHub": [],
    "/api/routes": {"routes": []},
    "/api/apiToken": {"apiToken": []},
    "/api/loginConfig": {"oidcProviders": []},
    # Both envelopes so the v41 `data` and v42/v43 `oAuth2Clients` wire shapes each read empty.
    "/api/oAuth2Clients": {"oAuth2Clients": [], "data": []},
    "/api/configuration/corsWhitelist": {"data": []},
    "/api/configuration/selfRegistrationRole": {},
    "/api/users/twoFactor/summary": {
        "totalUsers": 0,
        "enabled": 0,
        "disabled": 0,
        "coveragePercent": 0.0,
        "privileged": {},
    },
    "/api/users/twoFactor": {"users": []},
}

# The hostile payload a compromised instance could plant in a username, role name, or app name.
_XSS_PAYLOAD = "<script>alert(1)</script>"
_XSS_CLOSER = "</script><img src=x onerror=alert(2)>"


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _audit_options() -> AuditOptions:
    """Build the run-time audit options with the shipped defaults."""
    return AuditOptions(stale_days=90, max_password_age_days=365, two_factor_detail=False, max_objects=5000)


# ---------------------------------------------------------------------------
# 1) guardrail_request_hook: the enforcement primitive, exercised directly
# ---------------------------------------------------------------------------


async def test_guardrail_hook_rejects_non_get_method() -> None:
    """A POST to an allowlisted path is rejected because the method is not read-only."""
    hook = guardrail_request_hook(ALLOWED_AUDIT_PATHS)
    request = httpx.Request("POST", f"{BASE}/api/me")
    with pytest.raises(GuardrailViolation, match="method POST"):
        await hook(request)


async def test_guardrail_hook_rejects_off_allowlist_path() -> None:
    """A GET to a path outside the allowlist is rejected even though the method is read-only."""
    hook = guardrail_request_hook(ALLOWED_AUDIT_PATHS)
    request = httpx.Request("GET", f"{BASE}/api/dataValueSets")
    with pytest.raises(GuardrailViolation, match="not on the audit allowlist"):
        await hook(request)


async def test_guardrail_hook_allows_get_to_allowlisted_path() -> None:
    """A GET to an allowlisted plugin-read path passes the hook without raising."""
    hook = guardrail_request_hook(ALLOWED_AUDIT_PATHS)
    await hook(httpx.Request("GET", f"{BASE}/api/me"))


async def test_guardrail_hook_allows_connect_probe_paths() -> None:
    """The connect-time GET / and a HEAD to a connect path both pass the hook."""
    hook = guardrail_request_hook(ALLOWED_AUDIT_PATHS)
    for connect_path in CONNECT_PATHS:
        await hook(httpx.Request("GET", f"{BASE}{connect_path}"))
    await hook(httpx.Request("HEAD", f"{BASE}/api/system/info"))


async def test_guardrail_hook_strips_context_path_before_matching() -> None:
    """With a context `base_path`, a GET to a prefixed allowlist path passes after the prefix is stripped."""
    hook = guardrail_request_hook(ALLOWED_AUDIT_PATHS, base_path="/dev-2-42")
    await hook(httpx.Request("GET", "https://x.example/dev-2-42/api/system/info"))


async def test_guardrail_hook_maps_context_root_to_connect_slash() -> None:
    """A GET to the bare context root under `base_path` maps to `/`, an allowlisted connect probe."""
    hook = guardrail_request_hook(ALLOWED_AUDIT_PATHS, base_path="/dev-2-42")
    await hook(httpx.Request("GET", "https://x.example/dev-2-42/"))


async def test_guardrail_hook_rejects_off_allowlist_path_under_context_prefix() -> None:
    """A GET to an off-allowlist path under the context prefix is still rejected after stripping."""
    hook = guardrail_request_hook(ALLOWED_AUDIT_PATHS, base_path="/dev-2-42")
    with pytest.raises(GuardrailViolation, match="not on the audit allowlist"):
        await hook(httpx.Request("GET", "https://x.example/dev-2-42/api/dataValueSets"))


async def test_guardrail_hook_rejects_non_get_under_context_prefix() -> None:
    """A non-GET to a prefixed allowlist path is rejected on the method before any path stripping."""
    hook = guardrail_request_hook(ALLOWED_AUDIT_PATHS, base_path="/dev-2-42")
    with pytest.raises(GuardrailViolation, match="method POST"):
        await hook(httpx.Request("POST", "https://x.example/dev-2-42/api/me"))


async def test_guardrail_hook_empty_base_path_matches_exactly() -> None:
    """The default empty `base_path` leaves the request path untouched, so context-prefixed paths are rejected."""
    hook = guardrail_request_hook(ALLOWED_AUDIT_PATHS, base_path="")
    await hook(httpx.Request("GET", f"{BASE}/api/me"))
    with pytest.raises(GuardrailViolation, match="not on the audit allowlist"):
        await hook(httpx.Request("GET", "https://x.example/dev-2-42/api/me"))


# ---------------------------------------------------------------------------
# 2) A full audit run issues only allowlisted GETs (the primary missing test)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("tree", "wire_version"), TREES, ids=[t[0] for t in TREES])
async def test_full_audit_run_is_get_only_inside_allowlist(tree: str, wire_version: str, tmp_path: Path) -> None:
    """Every request a complete audit run records is a read-only GET/HEAD against ALLOWED_AUDIT_PATHS.

    Also asserts no check result comes back ERROR: per the orchestrator's isolation contract
    (`run_audit`), any exception a check raises -- including a guardrail false-positive that turns
    an in-allowlist request into a `GuardrailViolation` -- is caught and folded into an ERROR
    CheckResult rather than aborting the run. Asserting only on `router.calls` would stay green
    even if every check silently errored out, so this also checks the produced report directly.
    """
    audit = _audit_module(tree)
    # assert_all_mocked (default) makes any unmocked endpoint raise, so a new off-allowlist read fails
    # loudly here; assert_all_called is disabled because the version trees hit divergent 2FA endpoints.
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE}/").mock(return_value=httpx.Response(200, text=""))
        router.get(f"{BASE}/api/system/info").mock(return_value=httpx.Response(200, json={"version": wire_version}))
        for path, body in _RUN_ENDPOINTS.items():
            router.get(f"{BASE}{path}").mock(return_value=httpx.Response(200, json=body))
        profile = Profile(base_url=BASE, auth="pat", token="test-token")
        report = await audit.run_security_audit(
            profile,
            output_dir=tmp_path,
            profile_name="probe",
            started_at="2026-01-01T00:00:00+00:00",
            options=_audit_options(),
            skip=["version"],
            formats=["md"],
        )
        recorded = list(router.calls)

    assert recorded, "expected the audit run to issue HTTP requests"
    for call in recorded:
        request = call.request
        assert request.method in {"GET", "HEAD"}, f"{tree}: non-read-only request {request.method} {request.url.path}"
        assert request.url.host == "dhis2.example", f"{tree}: request left the target host: {request.url}"
        assert request.url.path in ALLOWED_AUDIT_PATHS, f"{tree}: path outside the allowlist: {request.url.path}"

    errored = [r for r in report.results if r.status is CheckStatus.ERROR]
    error_detail = ", ".join(f"{r.check}: {r.note}" for r in errored)
    assert not errored, f"{tree}: check(s) came back ERROR (guardrail false-positive?): {error_detail}"

    # The sharing scan's data-driven `/api/<plural>` request (built from the /api/schemas response,
    # not a hardcoded literal) must actually have been issued and admitted by the allowlist.
    recorded_paths = {call.request.url.path for call in recorded}
    assert "/api/dataSets" in recorded_paths, (
        f"{tree}: the data-driven sharing-scan request for the stubbed shareable schema never fired"
    )
    assert "/api/dataSets" in ALLOWED_AUDIT_PATHS, "the data-driven plural must itself be allowlisted"


def test_allowed_audit_paths_is_the_read_surface_plus_connect() -> None:
    """ALLOWED_AUDIT_PATHS is exactly the plugin read allowlist unioned with the connect probes."""
    assert ALLOWED_AUDIT_PATHS == GET_ALLOWLIST | CONNECT_PATHS


# ---------------------------------------------------------------------------
# 4) Resume rebuilds the sharing explorer from the persisted graph, not a re-scan
# ---------------------------------------------------------------------------


def _sharing_fake_context() -> AsyncMock:
    """Build a fake open_client context whose reads yield an empty-but-valid sharing surface."""
    fake_client = MagicMock()
    fake_client.base_url = BASE
    fake_client.raw_version = "2.42.0"
    fake_client.get_raw = AsyncMock(return_value={})
    context = AsyncMock()
    context.__aenter__.return_value = fake_client
    context.__aexit__.return_value = None
    return context


@pytest.mark.parametrize(("tree", "wire_version"), TREES, ids=[t[0] for t in TREES])
async def test_resume_rebuilds_explorer_from_persisted_graph(
    tree: str, wire_version: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resumed run emits sharing-explorer.html from the persisted sharing-graph.json without re-scanning."""
    audit = _audit_module(tree)
    monkeypatch.setattr(audit, "open_client", lambda *args, **kwargs: _sharing_fake_context())
    profile = Profile(base_url=BASE, auth="pat", token="test-token")
    folder = tmp_path / "run"
    await audit.run_security_audit(
        profile,
        output_dir=folder,
        profile_name="probe",
        started_at="2026-01-01T00:00:00+00:00",
        options=_audit_options(),
        only=["sharing"],
        formats=["md"],
        visualize=True,
    )
    assert (folder / "sharing-graph.json").exists(), "the initial run must persist the sharing graph"

    # Remove the rendered explorer so the resume must rebuild it from the persisted graph alone.
    (folder / "sharing-explorer.html").unlink()
    (folder / "sharing-data.js").unlink()

    await audit.resume_security_audit(  # completed run short-circuits to a re-render that re-emits the explorer
        profile,
        folder=folder,
        profile_name="probe",
        options=_audit_options(),
        formats=["md"],
        visualize=True,
    )

    assert (folder / "sharing-explorer.html").exists(), "resume must re-emit the explorer from the persisted graph"
    assert "window.__SHARING__" in (folder / "sharing-data.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 5) A hostile instance's markup stays inert in the rendered bundles
# ---------------------------------------------------------------------------


def _hostile_report() -> AuditReport:
    """Build an AuditReport whose finding text carries active-markup payloads."""
    manifest = RunManifest(
        target=BASE,
        profile="probe",
        scanner_version="0.0.0-test",
        started_at="2026-01-01T00:00:00+00:00",
        dhis2_version="2.42.0",
        check_order=["hygiene"],
    )
    findings = [
        AuditFinding(
            check="hygiene",
            severity=Severity.HIGH,
            title=f"Stale account {_XSS_PAYLOAD}",
            detail=f"Account {_XSS_CLOSER} last logged in long ago.",
            subject=f"user {_XSS_PAYLOAD}",
            group_key="stale",
        ),
        AuditFinding(
            check="hygiene",
            severity=Severity.HIGH,
            title=f"Stale account {_XSS_PAYLOAD}",
            detail="A second folded account.",
            subject=f"other {_XSS_CLOSER}",
            group_key="stale",
        ),
    ]
    result = CheckResult(check="hygiene", label="User account hygiene", status=CheckStatus.OK, findings=findings)
    return AuditReport(manifest=manifest, results=[result], summary=AuditSummary.from_results([result]))


def test_html_report_confines_hostile_markup_to_the_data_js(tmp_path: Path) -> None:
    """The HTML report keeps hostile markup out of the .html template and only as JSON data in report-data.js."""
    HtmlRenderer().emit(tmp_path, _hostile_report())
    html = (tmp_path / "report.dc.html").read_text(encoding="utf-8")
    data_js = (tmp_path / "report-data.js").read_text(encoding="utf-8")

    # The template is a fixed shell that loads the data externally; the hostile string never lands in it.
    assert _XSS_PAYLOAD not in html
    assert _XSS_CLOSER not in html
    assert 'src="report-data.js"' in html or "report-data.js" in html

    # In the external data file the payload survives only as a JSON string value, not as executable markup.
    body = data_js.strip()
    assert body.startswith("window.__REPORT__ = ")
    assert body.endswith(";")
    payload = json.loads(body[len("window.__REPORT__ = ") : -1])
    serialized = json.dumps(payload)
    assert _XSS_PAYLOAD in serialized
    assert any(_XSS_PAYLOAD in section["groups"][0]["finding"] for section in payload["sections"])


def _hostile_sharing_graph() -> SharingGraph:
    """Build a SharingGraph whose user, role, and object names carry active-markup payloads."""
    return SharingGraph(
        target=BASE,
        generated_at="2026-01-01T00:00:00+00:00",
        objects=[ObjectNode(uid="o1", type="dashboard", name=f"dashboard {_XSS_PAYLOAD}")],
        users=[UserNode(uid="u1", username=f"admin {_XSS_CLOSER}", display_name=f"Admin {_XSS_PAYLOAD}")],
        roles=[RoleNode(uid="r1", name=f"role {_XSS_PAYLOAD}", authorities=["ALL"], grants_all=True)],
    )


def test_sharing_explorer_confines_hostile_markup_to_the_data_js(tmp_path: Path) -> None:
    """The sharing explorer keeps hostile names out of the .html template and only as JSON data in sharing-data.js."""
    view = build_sharing_view(_hostile_sharing_graph(), profile="probe", version="2.42.0", scanner="0.0.0-test")
    ExplorerRenderer().emit(tmp_path, view)
    html = (tmp_path / "sharing-explorer.html").read_text(encoding="utf-8")
    data_js = (tmp_path / "sharing-data.js").read_text(encoding="utf-8")

    assert _XSS_PAYLOAD not in html
    assert _XSS_CLOSER not in html

    body = data_js.strip()
    assert body.startswith("window.__SHARING__ = ")
    assert body.endswith(";")
    payload = json.loads(body[len("window.__SHARING__ = ") : -1])
    serialized = json.dumps(payload)
    assert _XSS_PAYLOAD in serialized
    assert payload["graph"]["users"][0]["username"] == f"admin {_XSS_CLOSER}"
    assert payload["graph"]["roles"][0]["name"] == f"role {_XSS_PAYLOAD}"
