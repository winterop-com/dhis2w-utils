"""Guardrail tests for the security plugin: GET-only, allowlisted, no-lockout.

These tests enforce the responsible-use contract documented in
`dhis2w_core.security_core.guardrails` against every public service function
in all three version trees. A new security check inherits enforcement by
being added to `SERVICE_CALLS`; the completeness test fails if a public
service function ships without registering here.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_core.security_core.guardrails import CONNECT_PATHS, GET_ALLOWLIST
from dhis2w_core.v41.plugins.security import service as service_v41
from dhis2w_core.v42.plugins.security import service as service_v42
from dhis2w_core.v43.plugins.security import service as service_v43

BASE = "https://dhis2.example"

# (tree key, service module, version the mocked server reports).
TREES: tuple[tuple[str, ModuleType, str], ...] = (
    ("v41", service_v41, "2.41.3"),
    ("v42", service_v42, "2.42.4"),
    ("v43", service_v43, "2.43.1"),
)

# Every public security service function, with a thunk that exercises it.
# The completeness test below pins this registry to the service surface, so
# a later PR adding a service function must register it here to pass CI.
SERVICE_CALLS: dict[str, Callable[[ModuleType, Profile], Awaitable[Any]]] = {
    "get_security_settings": lambda service, profile: service.get_security_settings(profile),
    "get_account_authorities": lambda service, profile: service.get_account_authorities(profile),
}


@pytest.fixture
def profile() -> Profile:
    return Profile(base_url=BASE, auth="pat", token="test-token")


def _mock_read_surface(version: str) -> None:
    """Canned responses for the connect preamble plus every current read."""
    respx.get(f"{BASE}/").mock(return_value=httpx.Response(200, text=""))
    respx.get(f"{BASE}/api/system/info").mock(return_value=httpx.Response(200, json={"version": version}))
    respx.get(f"{BASE}/api/systemSettings").mock(return_value=httpx.Response(200, json={"minPasswordLength": 8}))
    respx.get(f"{BASE}/api/me/authorization").mock(return_value=httpx.Response(200, json=["ALL", "F_USER_ADD"]))


@pytest.mark.parametrize(("tree", "service", "version"), TREES, ids=[t[0] for t in TREES])
@respx.mock
async def test_service_calls_are_get_only_inside_allowlist(
    tree: str, service: ModuleType, version: str, profile: Profile
) -> None:
    """Every request any service function issues is a GET against the allowlist."""
    _mock_read_surface(version)
    for call in SERVICE_CALLS.values():
        await call(service, profile)
    assert respx.calls, "expected the service calls to issue HTTP requests"
    allowed = GET_ALLOWLIST | CONNECT_PATHS
    for recorded in respx.calls:
        request = recorded.request
        assert request.method == "GET", f"{tree}: non-GET request {request.method} {request.url.path}"
        assert request.url.path in allowed, f"{tree}: path outside the allowlist: {request.url.path}"


@pytest.mark.parametrize(("tree", "service", "version"), TREES, ids=[t[0] for t in TREES])
def test_every_public_service_function_is_guardrail_covered(tree: str, service: ModuleType, version: str) -> None:
    """A public service function that skips `SERVICE_CALLS` fails the suite."""
    public = {
        name for name, _member in inspect.getmembers(service, inspect.iscoroutinefunction) if not name.startswith("_")
    }
    assert public == set(SERVICE_CALLS), f"{tree}: register new service functions in SERVICE_CALLS"


def test_cors_whitelist_path_is_allowlisted() -> None:
    """The settings check's CORS read targets an allowlisted GET path."""
    assert "/api/configuration/corsWhitelist" in GET_ALLOWLIST


def test_routes_path_is_allowlisted() -> None:
    """The routes check's route-inventory read targets an allowlisted GET path."""
    assert "/api/routes" in GET_ALLOWLIST


def test_retry_policy_default_never_retries_auth_failures() -> None:
    """No-lockout: 401/403 are never retried; only 429/5xx are retry candidates."""
    from dhis2w_client.v41 import RetryPolicy as RetryPolicyV41
    from dhis2w_client.v42 import RetryPolicy as RetryPolicyV42
    from dhis2w_client.v43 import RetryPolicy as RetryPolicyV43

    for retry_policy_class in (RetryPolicyV41, RetryPolicyV42, RetryPolicyV43):
        policy = retry_policy_class()
        assert 401 not in policy.retry_statuses
        assert 403 not in policy.retry_statuses
        assert all(status == 429 or status >= 500 for status in policy.retry_statuses)


def test_open_client_defaults_to_no_retry() -> None:
    """No-lockout: the client context the services use defaults to no retry at all."""
    from dhis2w_core.v41.client_context import open_client as open_client_v41
    from dhis2w_core.v42.client_context import open_client as open_client_v42
    from dhis2w_core.v43.client_context import open_client as open_client_v43

    for open_client in (open_client_v41, open_client_v42, open_client_v43):
        default = inspect.signature(open_client).parameters["retry_policy"].default
        assert default is None
