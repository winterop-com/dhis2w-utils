"""Tests for inline tracker delete (`delete_tracker_objects` -> importStrategy=DELETE)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.tracker.service import delete_tracker_objects


@pytest.fixture
def basic_profile() -> Profile:
    """A minimal basic-auth profile pointed at the mocked host."""
    return Profile(base_url="https://dhis2.example", auth="basic", username="admin", password="district")


@respx.mock
async def test_delete_events_builds_minimal_bundle_with_delete_strategy(basic_profile: Profile) -> None:
    """`delete_tracker_objects(kind='events')` POSTs {events:[{event:uid}]} with importStrategy=DELETE."""
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"})
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    route = respx.post("https://dhis2.example/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    await delete_tracker_objects(basic_profile, kind="events", uids=["evt01234567", "evt7654321X"])

    request = route.calls.last.request
    assert request.url.params.get("importStrategy") == "DELETE"
    assert json.loads(request.content) == {"events": [{"event": "evt01234567"}, {"event": "evt7654321X"}]}


@respx.mock
async def test_delete_tracked_entities_uses_trackedEntity_id_field(basic_profile: Profile) -> None:
    """trackedEntities map to the `trackedEntity` id field in the bundle."""
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"})
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    route = respx.post("https://dhis2.example/api/tracker").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    await delete_tracker_objects(basic_profile, kind="trackedEntities", uids=["teI01234567"])

    assert json.loads(route.calls.last.request.content) == {"trackedEntities": [{"trackedEntity": "teI01234567"}]}
