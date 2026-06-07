"""Unit tests for `AttributeValuesAccessor` — respx-mocked, no live stack."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


def _mock_attribute_lookup(code: str = "ICD10_CODE", attribute_uid: str = "AttrIcd01234") -> None:
    """Mock `/api/attributes?filter=code:eq:<code>` → single-attribute result."""
    respx.get("https://dhis2.example/api/attributes").mock(
        return_value=httpx.Response(200, json={"attributes": [{"id": attribute_uid}]}),
    )


# ---- resolve_attribute_uid ---------------------------------------------------


@respx.mock
async def test_resolve_attribute_uid_passes_uids_through(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Valid 11-char UID returns unchanged without any HTTP call."""
    mock_system_info(server_version)
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.attribute_values.resolve_attribute_uid("AttrSnom001")
    finally:
        await client.close()
    assert result == "AttrSnom001"


@respx.mock
async def test_resolve_attribute_uid_resolves_business_code(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Non-UID input → /api/attributes lookup by code."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/attributes").mock(
        return_value=httpx.Response(200, json={"attributes": [{"id": "AttrIcd01234"}]}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.attribute_values.resolve_attribute_uid("ICD10_CODE")
    finally:
        await client.close()
    assert result == "AttrIcd01234"
    assert route.calls.last.request.url.params["filter"] == "code:eq:ICD10_CODE"


@respx.mock
async def test_resolve_attribute_uid_raises_when_code_has_no_match(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Empty /api/attributes → LookupError with actionable hint."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/attributes").mock(
        return_value=httpx.Response(200, json={"attributes": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(LookupError, match="no Attribute with code"):
            await client.attribute_values.resolve_attribute_uid("NO_SUCH_CODE")
    finally:
        await client.close()


# ---- get_value ---------------------------------------------------------------


@respx.mock
async def test_get_value_reads_nested_attribute_entry(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`attributeValues[].attribute.id` matches → value returned."""
    mock_system_info(server_version)
    _mock_attribute_lookup()
    respx.get("https://dhis2.example/api/dataElements/DE001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "DE001",
                "attributeValues": [{"value": "A09", "attribute": {"id": "AttrIcd01234"}}],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.attribute_values.get_value("dataElements", "DE001", "ICD10_CODE")
    finally:
        await client.close()
    assert result == "A09"


@respx.mock
async def test_get_value_returns_none_when_missing(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Resource has `attributeValues=[]` → None."""
    mock_system_info(server_version)
    _mock_attribute_lookup()
    respx.get("https://dhis2.example/api/dataElements/DE001").mock(
        return_value=httpx.Response(200, json={"id": "DE001", "attributeValues": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.attribute_values.get_value("dataElements", "DE001", "ICD10_CODE")
    finally:
        await client.close()
    assert result is None


# ---- set_value + delete_value -----------------------------------------------


@respx.mock
async def test_set_value_read_merges_existing_attribute_values(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Existing attribute entry is replaced; unrelated attribute entries survive."""
    mock_system_info(server_version)
    _mock_attribute_lookup()
    respx.get("https://dhis2.example/api/dataElements/DE001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "DE001",
                "code": "DE_CODE",
                "attributeValues": [
                    {"value": "OLD", "attribute": {"id": "AttrIcd01234"}},
                    {"value": "other", "attribute": {"id": "OtherAttr01"}},
                ],
            },
        ),
    )
    captured: dict[str, Any] = {}

    def capture_put(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "OK"})

    respx.put("https://dhis2.example/api/dataElements/DE001").mock(side_effect=capture_put)

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.attribute_values.set_value("dataElements", "DE001", "ICD10_CODE", "NEW")
    finally:
        await client.close()
    new_avs = captured["body"]["attributeValues"]
    icd_rows = [av for av in new_avs if av["attribute"]["id"] == "AttrIcd01234"]
    other_rows = [av for av in new_avs if av["attribute"]["id"] == "OtherAttr01"]
    assert len(icd_rows) == 1
    assert icd_rows[0]["value"] == "NEW"
    assert len(other_rows) == 1 and other_rows[0]["value"] == "other"


@respx.mock
async def test_delete_value_removes_one_entry_and_returns_true(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Known attribute → filtered out + PUT fires + returns True."""
    mock_system_info(server_version)
    _mock_attribute_lookup()
    respx.get("https://dhis2.example/api/dataElements/DE001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "DE001",
                "attributeValues": [{"value": "A09", "attribute": {"id": "AttrIcd01234"}}],
            },
        ),
    )
    put_route = respx.put("https://dhis2.example/api/dataElements/DE001").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        removed = await client.attribute_values.delete_value("dataElements", "DE001", "ICD10_CODE")
    finally:
        await client.close()
    assert removed is True
    assert put_route.call_count == 1


@respx.mock
async def test_delete_value_returns_false_when_attribute_not_set(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """No matching entry → no PUT, returns False (avoids churn on `lastUpdated`)."""
    mock_system_info(server_version)
    _mock_attribute_lookup()
    respx.get("https://dhis2.example/api/dataElements/DE001").mock(
        return_value=httpx.Response(200, json={"id": "DE001", "attributeValues": []}),
    )
    put_route = respx.put("https://dhis2.example/api/dataElements/DE001")
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        removed = await client.attribute_values.delete_value("dataElements", "DE001", "ICD10_CODE")
    finally:
        await client.close()
    assert removed is False
    assert put_route.call_count == 0


# ---- find_uids_by_value ------------------------------------------------------


@respx.mock
async def test_find_uids_by_value_emits_uid_as_filter_key(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """BUGS.md #21 quirk: filter is `<attrUid>:eq:<value>`, applies to every resource."""
    mock_system_info(server_version)
    _mock_attribute_lookup(code="SNOMED_CODE", attribute_uid="AttrSnom001")
    route = respx.get("https://dhis2.example/api/organisationUnits").mock(
        return_value=httpx.Response(
            200,
            json={"organisationUnits": [{"id": "OU_A"}, {"id": "OU_B"}]},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        uids = await client.attribute_values.find_uids_by_value(
            "organisationUnits",
            "SNOMED_CODE",
            "12345",
            extra_filters=["level:eq:3"],
        )
    finally:
        await client.close()
    assert uids == ["OU_A", "OU_B"]
    filters = route.calls.last.request.url.params.get_list("filter")
    assert "AttrSnom001:eq:12345" in filters
    assert "level:eq:3" in filters


@respx.mock
async def test_find_one_uid_by_value_returns_first_or_none(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Convenience wrapper — first UID or None on empty result."""
    mock_system_info(server_version)
    _mock_attribute_lookup(code="SNOMED_CODE", attribute_uid="AttrSnom001")
    respx.get("https://dhis2.example/api/options").mock(
        return_value=httpx.Response(200, json={"options": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        miss = await client.attribute_values.find_one_uid_by_value("options", "SNOMED_CODE", "NOPE")
    finally:
        await client.close()
    assert miss is None
