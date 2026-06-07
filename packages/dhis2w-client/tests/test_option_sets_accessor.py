"""Unit tests for `OptionSetsAccessor` — respx-mocked, no live stack."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client, OptionSpec


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


@respx.mock
async def test_list_all_pages_option_sets(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`list_all` pages OptionSets into typed models across every version tree."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/optionSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "optionSets": [
                    {"id": "OS1", "code": "AGE", "name": "Age category", "valueType": "TEXT"},
                    {"id": "OS2", "code": "SEX", "name": "Sex", "valueType": "TEXT"},
                ]
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        sets = await client.option_sets.list_all(page_size=5)
    finally:
        await client.close()
    assert len(sets) == 2
    assert type(sets[0]).__name__ == "OptionSet"
    assert [s.id for s in sets] == ["OS1", "OS2"]


@respx.mock
async def test_get_by_code_returns_none_when_no_match(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Empty `optionSets` list from DHIS2 maps to a None return — not an error."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/optionSets").mock(
        return_value=httpx.Response(200, json={"optionSets": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.option_sets.get_by_code("MISSING_SET")
    finally:
        await client.close()
    assert result is None


@respx.mock
async def test_get_by_code_returns_typed_model_with_options(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Happy path: DHIS2 returns one match → typed `OptionSet` with options populated."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/optionSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "optionSets": [
                    {
                        "id": "OsVaccType1",
                        "code": "VACCINE_TYPE",
                        "name": "Vaccine type",
                        "valueType": "TEXT",
                        "options": [
                            {"id": "OptVacBCG01", "code": "BCG", "name": "BCG", "sortOrder": 0},
                            {"id": "OptVacMes01", "code": "MEASLES", "name": "Measles", "sortOrder": 1},
                        ],
                    }
                ]
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.option_sets.get_by_code("VACCINE_TYPE")
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["filter"] == "code:eq:VACCINE_TYPE"
    assert "options[id,code,name,sortOrder]" in params["fields"]
    assert result is not None
    assert result.id == "OsVaccType1"
    assert result.options is not None
    assert len(result.options) == 2


@respx.mock
async def test_list_options_orders_by_sort_order(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`list_options` hits /api/options with the right filter + order param."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/options").mock(
        return_value=httpx.Response(
            200,
            json={
                "options": [
                    {"id": "o1", "code": "BCG", "name": "BCG", "sortOrder": 0},
                    {"id": "o2", "code": "MEASLES", "name": "Measles", "sortOrder": 1},
                ]
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.option_sets.list_options("OsVaccType1")
    finally:
        await client.close()
    params = route.calls.last.request.url.params
    assert params["filter"] == "optionSet.id:eq:OsVaccType1"
    assert params["order"] == "sortOrder:asc"
    assert [o.code for o in result] == ["BCG", "MEASLES"]


@respx.mock
async def test_find_option_requires_exactly_one_selector(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Callers must pass one of code / name — never both, never neither."""
    mock_system_info(server_version)
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(ValueError, match="exactly one"):
            await client.option_sets.find_option("OsVaccType1")
        with pytest.raises(ValueError, match="exactly one"):
            await client.option_sets.find_option("OsVaccType1", option_code="X", option_name="Y")
    finally:
        await client.close()


@respx.mock
async def test_find_option_filters_server_side_by_code(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`find_option` ships both filters (optionSet.id + code) as repeatable params."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/options").mock(
        return_value=httpx.Response(
            200,
            json={"options": [{"id": "o1", "code": "BCG", "name": "BCG", "sortOrder": 0}]},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.option_sets.find_option("OsVaccType1", option_code="BCG")
    finally:
        await client.close()
    filters = route.calls.last.request.url.params.get_list("filter")
    assert "optionSet.id:eq:OsVaccType1" in filters
    assert "code:eq:BCG" in filters
    assert result is not None
    assert result.code == "BCG"


async def test_upsert_options_rejects_duplicate_codes_in_spec() -> None:
    """Pure-Python guard: passing two specs with the same code is a programming error."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    spec = [
        OptionSpec(code="BCG", name="BCG"),
        OptionSpec(code="BCG", name="BCG again"),
    ]
    with pytest.raises(ValueError, match="duplicate codes"):
        await client.option_sets.upsert_options("OsVaccType1", spec, dry_run=True)


@respx.mock
async def test_upsert_options_dry_run_reports_diff_without_writing(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Dry-run inspects current state but never POSTs / DELETEs."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/options").mock(
        return_value=httpx.Response(
            200,
            json={
                "options": [
                    {"id": "o_bcg", "code": "BCG", "name": "BCG", "sortOrder": 0},
                    {"id": "o_mes", "code": "MEASLES", "name": "Measles", "sortOrder": 1},
                    {"id": "o_pol", "code": "POLIO", "name": "Polio", "sortOrder": 2},
                ]
            },
        ),
    )
    write_route = respx.post("https://dhis2.example/api/metadata")

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        spec = [
            OptionSpec(code="BCG", name="BCG"),  # unchanged → skip
            OptionSpec(code="MEASLES", name="Measles vaccine"),  # name change → update
            OptionSpec(code="HPV", name="HPV vaccine"),  # new → add
        ]
        report = await client.option_sets.upsert_options(
            "OsVaccType1",
            spec,
            remove_missing=True,
            dry_run=True,
        )
    finally:
        await client.close()

    assert report.added == ["HPV"]
    assert report.updated == ["MEASLES"]
    assert report.skipped == ["BCG"]
    assert report.removed == ["POLIO"]  # current POLIO is missing from spec
    assert report.dry_run is True
    # Nothing was written — no /api/metadata calls fired.
    assert write_route.call_count == 0


@respx.mock
async def test_upsert_options_writes_and_deletes_via_metadata_bundle(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Real run uses `save_bulk` for writes + metadata bundle DELETE for removes (BUGS.md #20)."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/options").mock(
        return_value=httpx.Response(
            200,
            json={
                "options": [
                    {"id": "o_bcg", "code": "BCG", "name": "BCG", "sortOrder": 0},
                    {"id": "o_pol", "code": "POLIO", "name": "Polio", "sortOrder": 1},
                ]
            },
        ),
    )
    # Every POST /api/metadata (either save_bulk CREATE_AND_UPDATE or delete_bulk
    # DELETE) returns a success envelope; tests inspect which strategy was sent.
    posts: list[dict[str, Any]] = []

    def capture(request: httpx.Request) -> httpx.Response:
        posts.append(
            {
                "strategy": request.url.params.get("importStrategy"),
                "body": json.loads(request.content),
            },
        )
        return httpx.Response(200, json={"status": "OK", "stats": {"deleted": 1}})

    respx.post("https://dhis2.example/api/metadata").mock(side_effect=capture)

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        spec = [
            OptionSpec(code="BCG", name="BCG"),  # skip
            OptionSpec(code="HPV", name="HPV vaccine"),  # add
        ]
        report = await client.option_sets.upsert_options(
            "OsVaccType1",
            spec,
            remove_missing=True,
        )
    finally:
        await client.close()

    assert report.added == ["HPV"]
    assert report.removed == ["POLIO"]

    # Two POSTs: one save_bulk (CREATE_AND_UPDATE) for HPV, one delete_bulk
    # (DELETE) for POLIO.
    strategies = [p["strategy"] for p in posts]
    assert "CREATE_AND_UPDATE" in strategies
    assert "DELETE" in strategies
    delete_post = next(p for p in posts if p["strategy"] == "DELETE")
    deleted_uids = [entry["id"] for entry in delete_post["body"]["options"]]
    assert deleted_uids == ["o_pol"]


# ---------------------------------------------------------------------------
# Attribute-value helpers
# ---------------------------------------------------------------------------


def _mock_attribute_lookup() -> None:
    """Mock /api/attributes?filter=code:eq:SNOMED_CODE → AttrSnom001."""
    respx.get("https://dhis2.example/api/attributes").mock(
        return_value=httpx.Response(200, json={"attributes": [{"id": "AttrSnom001"}]}),
    )


@respx.mock
async def test_get_option_attribute_value_resolves_code_then_reads(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Business code `SNOMED_CODE` → Attribute UID → attributeValues row match."""
    mock_system_info(server_version)
    _mock_attribute_lookup()
    respx.get("https://dhis2.example/api/options/OptVacBCG01").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "OptVacBCG01",
                "attributeValues": [
                    {"value": "77656005", "attribute": {"id": "AttrSnom001"}},
                ],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        value = await client.option_sets.get_option_attribute_value("OptVacBCG01", "SNOMED_CODE")
    finally:
        await client.close()
    assert value == "77656005"


@respx.mock
async def test_get_option_attribute_value_returns_none_when_not_set(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Missing attribute value → None, not an exception."""
    mock_system_info(server_version)
    _mock_attribute_lookup()
    respx.get("https://dhis2.example/api/options/OptVacBCG01").mock(
        return_value=httpx.Response(200, json={"id": "OptVacBCG01", "attributeValues": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        value = await client.option_sets.get_option_attribute_value("OptVacBCG01", "SNOMED_CODE")
    finally:
        await client.close()
    assert value is None


@respx.mock
async def test_resolve_attribute_uid_raises_on_unknown_code(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Empty /api/attributes result → LookupError with an actionable message."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/attributes").mock(
        return_value=httpx.Response(200, json={"attributes": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(LookupError, match="no Attribute with code"):
            await client.attribute_values.resolve_attribute_uid("NOT_A_REAL_CODE")
    finally:
        await client.close()


@respx.mock
async def test_find_option_by_attribute_uses_uid_as_filter_key(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """BUGS.md #21 workaround: filter uses `<attributeUid>:eq:<value>` not `attributeValues.value`."""
    mock_system_info(server_version)
    _mock_attribute_lookup()
    list_route = respx.get("https://dhis2.example/api/options").mock(
        return_value=httpx.Response(200, json={"options": [{"id": "OptVacMes01"}]}),
    )
    # Delegation through `client.attribute_values` does the filter lookup first
    # (returns UIDs only), then fetches the typed Option in a second call.
    respx.get("https://dhis2.example/api/options/OptVacMes01").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "OptVacMes01",
                "code": "MEASLES",
                "name": "Measles",
                "sortOrder": 1,
                "optionSet": {"id": "OsVaccType1"},
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        option = await client.option_sets.find_option_by_attribute(
            "OsVaccType1",
            "SNOMED_CODE",
            "386661006",
        )
    finally:
        await client.close()
    filters = list_route.calls.last.request.url.params.get_list("filter")
    # The quirk: attribute-value filter is `<uid>:eq:<value>`, not `attributeValues.value:eq:<value>`.
    assert "AttrSnom001:eq:386661006" in filters
    assert "optionSet.id:eq:OsVaccType1" in filters
    assert option is not None
    assert option.code == "MEASLES"


@respx.mock
async def test_set_option_attribute_value_read_merge_writes(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Set: fetch current → merge new value (drop prior same-attribute entry) → PUT back."""
    mock_system_info(server_version)
    _mock_attribute_lookup()
    # Current option carries a stale SNOMED value + an unrelated attribute.
    respx.get("https://dhis2.example/api/options/OptVacBCG01").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "OptVacBCG01",
                "code": "BCG",
                "attributeValues": [
                    {"value": "OLD", "attribute": {"id": "AttrSnom001"}},
                    {"value": "other", "attribute": {"id": "AttrOther01"}},
                ],
            },
        ),
    )
    captured: dict[str, Any] = {}

    def capture_put(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "OK"})

    respx.put("https://dhis2.example/api/options/OptVacBCG01").mock(side_effect=capture_put)

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.option_sets.set_option_attribute_value("OptVacBCG01", "SNOMED_CODE", "NEW")
    finally:
        await client.close()

    new_avs = captured["body"]["attributeValues"]
    # Prior SNOMED value got replaced, unrelated attribute preserved, exactly
    # one entry per attribute UID.
    snomed_entries = [av for av in new_avs if av["attribute"]["id"] == "AttrSnom001"]
    other_entries = [av for av in new_avs if av["attribute"]["id"] == "AttrOther01"]
    assert len(snomed_entries) == 1
    assert snomed_entries[0]["value"] == "NEW"
    assert len(other_entries) == 1
    assert other_entries[0]["value"] == "other"
