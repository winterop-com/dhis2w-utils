"""Regression tests for /api/tracker list envelope field parsing."""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.tracker.service import list_relationships, list_tracked_entities


@pytest.fixture
def basic_profile() -> Profile:
    return Profile(base_url="https://dhis2.example", auth="basic", username="admin", password="district")


@respx.mock
async def test_list_tracked_entities_reads_tracked_entities_key(basic_profile: Profile) -> None:
    """/api/tracker/trackedEntities returns `{pager, trackedEntities: [...]}`, not `{instances}`."""
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.get("https://dhis2.example/api/tracker/trackedEntities").mock(
        return_value=httpx.Response(
            200,
            json={
                "pager": {"page": 1, "pageSize": 50},
                "trackedEntities": [
                    {"trackedEntity": "abcDEFghiJK", "trackedEntityType": "tet01234567"},
                    {"trackedEntity": "zzzYYYwwwVV", "trackedEntityType": "tet01234567"},
                ],
            },
        ),
    )

    result = await list_tracked_entities(basic_profile, tracked_entity_type="tet01234567")
    assert [te.trackedEntity for te in result] == ["abcDEFghiJK", "zzzYYYwwwVV"]


@respx.mock
async def test_list_relationships_reads_relationships_key(basic_profile: Profile) -> None:
    """/api/tracker/relationships returns `{pager, relationships: [...]}`, not `{instances}`."""
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.get("https://dhis2.example/api/tracker/relationships").mock(
        return_value=httpx.Response(
            200,
            json={
                "pager": {"page": 1, "pageSize": 50},
                "relationships": [
                    {"relationship": "rel01234567", "relationshipType": "rtyp1234567"},
                ],
            },
        ),
    )

    result = await list_relationships(basic_profile, tracked_entity="abcDEFghiJK")
    assert [r.relationship for r in result] == ["rel01234567"]
