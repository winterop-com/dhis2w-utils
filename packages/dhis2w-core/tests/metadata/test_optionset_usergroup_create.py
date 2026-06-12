"""Tests for the optionSet + userGroup create/delete service verbs."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.metadata.service import create_option_set
from dhis2w_core.v42.plugins.user_group.service import create_user_group


@pytest.fixture
def basic_profile() -> Profile:
    """A minimal basic-auth profile pointed at the mocked host."""
    return Profile(base_url="https://dhis2.example", auth="basic", username="admin", password="district")


def _stub_connect() -> None:
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"})
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))


@respx.mock
async def test_create_option_set_posts_name_and_value_type(basic_profile: Profile) -> None:
    """create_option_set POSTs {name, valueType, code} to /api/optionSets."""
    _stub_connect()
    route = respx.post("https://dhis2.example/api/optionSets").mock(
        return_value=httpx.Response(
            201, json={"status": "OK", "httpStatusCode": 201, "response": {"uid": "opt01234567"}}
        ),
    )

    result = await create_option_set(basic_profile, name="Yes/No", value_type="TEXT", code="YN")

    body = json.loads(route.calls.last.request.content)
    assert body["name"] == "Yes/No"
    assert body["valueType"] == "TEXT"
    assert body["code"] == "YN"
    assert result is not None


@respx.mock
async def test_create_user_group_posts_name(basic_profile: Profile) -> None:
    """create_user_group POSTs {name} to /api/userGroups."""
    _stub_connect()
    route = respx.post("https://dhis2.example/api/userGroups").mock(
        return_value=httpx.Response(
            201, json={"status": "OK", "httpStatusCode": 201, "response": {"uid": "ugr01234567"}}
        ),
    )

    result = await create_user_group(basic_profile, name="Administrators")

    assert json.loads(route.calls.last.request.content)["name"] == "Administrators"
    assert result is not None
