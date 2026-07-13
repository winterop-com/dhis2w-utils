"""Tests for `push_tracker` taking a typed `TrackerBundle` (wire body drops the empty lists)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from dhis2w_client.generated.v42.tracker import TrackerBundle
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.tracker.service import push_tracker


@pytest.fixture
def basic_profile() -> Profile:
    """A minimal basic-auth profile pointed at the mocked host."""
    return Profile(base_url="https://dhis2.example", auth="basic", username="admin", password="district")


@respx.mock
async def test_push_tracker_body_names_only_populated_kinds(basic_profile: Profile) -> None:
    """The POST /api/tracker body carries only the bundle lists that hold objects."""
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"})
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    route = respx.post("https://dhis2.example/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    bundle = TrackerBundle.model_validate(
        {"events": [{"event": "evt01234567", "program": "prg01234567", "status": "COMPLETED"}]}
    )
    response = await push_tracker(basic_profile, bundle, import_strategy="CREATE_AND_UPDATE", dry_run=True)

    assert response.status == "OK"
    request = route.calls.last.request
    assert request.url.params["importStrategy"] == "CREATE_AND_UPDATE"
    body = json.loads(request.content)
    assert set(body) == {"events"}  # empty trackedEntities/enrollments/relationships lists are dropped
    assert body["events"] == [{"event": "evt01234567", "program": "prg01234567", "status": "COMPLETED"}]


@respx.mock
async def test_push_tracker_dry_run_sends_validate_import_mode(basic_profile: Profile) -> None:
    """`dry_run=True` sends importMode=VALIDATE (validate-only) and never sends a dryRun param.

    POST /api/tracker has no dryRun param — the validate-only path is importMode=VALIDATE.
    A dryRun param would be silently ignored and the objects would COMMIT.
    """
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"})
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    route = respx.post("https://dhis2.example/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    bundle = TrackerBundle.model_validate({"events": [{"event": "evt01234567"}]})
    await push_tracker(basic_profile, bundle, import_strategy="CREATE_AND_UPDATE", dry_run=True)

    params = route.calls.last.request.url.params
    assert params["importMode"] == "VALIDATE"
    assert "dryRun" not in params


@respx.mock
async def test_push_tracker_default_is_synchronous(basic_profile: Profile) -> None:
    """A normal push sends async=false so per-object errors surface inline, and no importMode."""
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"})
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    route = respx.post("https://dhis2.example/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    bundle = TrackerBundle.model_validate({"events": [{"event": "evt01234567"}]})
    await push_tracker(basic_profile, bundle, import_strategy="CREATE_AND_UPDATE")

    params = route.calls.last.request.url.params
    assert params["async"] == "false"
    assert "importMode" not in params  # server default COMMIT


@respx.mock
async def test_push_tracker_async_mode_sends_async_true(basic_profile: Profile) -> None:
    """`async_mode=True` sends async=true to return a job reference immediately."""
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"})
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    route = respx.post("https://dhis2.example/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    bundle = TrackerBundle.model_validate({"events": [{"event": "evt01234567"}]})
    await push_tracker(basic_profile, bundle, async_mode=True)

    assert route.calls.last.request.url.params["async"] == "true"
