"""Unit tests for the `resolve_tracked_entity_type` name-or-UID resolver."""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.tracker.service import resolve_tracked_entity_type


@pytest.fixture
def basic_profile() -> Profile:
    return Profile(base_url="https://dhis2.example", auth="basic", username="admin", password="district")


@respx.mock
async def test_uid_pattern_returns_as_is(basic_profile: Profile) -> None:
    """An 11-char DHIS2-shaped UID skips the API lookup entirely."""
    uid = await resolve_tracked_entity_type(basic_profile, "tet01234567")
    assert uid == "tet01234567"
    # Verify no request was made.
    assert not respx.routes


@respx.mock
async def test_name_resolves_via_filter(basic_profile: Profile) -> None:
    """Name resolves via filter."""
    respx.get("https://dhis2.example/api/trackedEntityTypes").mock(
        return_value=httpx.Response(
            200,
            json={"trackedEntityTypes": [{"id": "abcDEFghiJK", "name": "Person"}]},
        ),
    )
    # Accept any system/info probe the client may make on connect.
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))

    uid = await resolve_tracked_entity_type(basic_profile, "Person")
    assert uid == "abcDEFghiJK"


@respx.mock
async def test_name_case_insensitive_via_ilike(basic_profile: Profile) -> None:
    """The resolver uses DHIS2's `ilike` operator so 'person' matches 'Person'."""
    route = respx.get("https://dhis2.example/api/trackedEntityTypes").mock(
        return_value=httpx.Response(
            200,
            json={"trackedEntityTypes": [{"id": "abcDEFghiJK", "name": "Person"}]},
        ),
    )
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))

    await resolve_tracked_entity_type(basic_profile, "person")
    sent_params = dict(route.calls.last.request.url.params)
    assert sent_params["filter"] == "name:ilike:person"


@respx.mock
async def test_no_match_raises(basic_profile: Profile) -> None:
    """No match raises."""
    respx.get("https://dhis2.example/api/trackedEntityTypes").mock(
        return_value=httpx.Response(200, json={"trackedEntityTypes": []}),
    )
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))

    with pytest.raises(ValueError, match="no TrackedEntityType matches") as excinfo:
        await resolve_tracked_entity_type(basic_profile, "DefinitelyNotRealHere")
    assert "d2w data tracker type" in str(excinfo.value)


@respx.mock
async def test_ambiguous_name_raises(basic_profile: Profile) -> None:
    """Ambiguous name raises."""
    respx.get("https://dhis2.example/api/trackedEntityTypes").mock(
        return_value=httpx.Response(
            200,
            json={
                "trackedEntityTypes": [
                    {"id": "abcDEFghiJK", "name": "Patient"},
                    {"id": "xyzABCdefGH", "name": "Patient Historical"},
                ]
            },
        ),
    )
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))

    with pytest.raises(ValueError, match="ambiguous"):
        await resolve_tracked_entity_type(basic_profile, "Patient")
