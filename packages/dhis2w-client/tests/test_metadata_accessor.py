"""Tests for `Dhis2Client.metadata.delete_bulk` + `delete_bulk_multi`."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

import httpx
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


@respx.mock
async def test_delete_bulk_posts_minimal_bundle_and_returns_webmessage(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`delete_bulk` POSTs `{resource: [{id: ...}]}` with the DELETE importStrategy."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "httpStatus": "OK",
                "httpStatusCode": 200,
                "status": "OK",
                "message": "",
                "response": {
                    "status": "OK",
                    "stats": {"deleted": 2, "created": 0, "updated": 0, "ignored": 0, "total": 2},
                    "typeReports": [
                        {
                            "klass": "org.hisp.dhis.dataelement.DataElement",
                            "stats": {"deleted": 2, "total": 2},
                        }
                    ],
                },
            },
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.delete_bulk("dataElements", ["deUidAAA0001", "deUidBBB0002"])
    finally:
        await client.close()

    assert route.call_count == 1
    call = route.calls.last
    params = call.request.url.params
    assert params["importStrategy"] == "DELETE"
    assert params["atomicMode"] == "NONE"
    body = json.loads(call.request.content)
    assert body == {"dataElements": [{"id": "deUidAAA0001"}, {"id": "deUidBBB0002"}]}

    report = result.import_report()
    assert report is not None
    assert report.stats is not None
    assert report.stats.deleted == 2


@respx.mock
async def test_delete_bulk_empty_uids_short_circuits_without_http(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """An empty UID list returns a no-op WebMessage without making an HTTP call."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata")

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.delete_bulk("dataElements", [])
    finally:
        await client.close()

    assert route.call_count == 0
    assert result.status == "OK"
    assert result.message == "no uids supplied"


@respx.mock
async def test_delete_bulk_multi_merges_multiple_resource_types(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`delete_bulk_multi` builds one bundle spanning every supplied resource type."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "httpStatus": "OK",
                "httpStatusCode": 200,
                "status": "OK",
                "response": {"status": "OK", "stats": {"deleted": 3, "total": 3}, "typeReports": []},
            },
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.metadata.delete_bulk_multi(
            {
                "dataElements": ["deUidAAA0001"],
                "indicators": ["indUidAAA001", "indUidBBB002"],
            }
        )
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    assert body == {
        "dataElements": [{"id": "deUidAAA0001"}],
        "indicators": [{"id": "indUidAAA001"}, {"id": "indUidBBB002"}],
    }


@respx.mock
async def test_delete_bulk_multi_skips_empty_resource_entries(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Resource keys whose UID list is empty are dropped from the wire bundle."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatus": "OK", "httpStatusCode": 200}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.metadata.delete_bulk_multi(
            {
                "dataElements": ["deUidAAA0001"],
                "indicators": [],  # skipped
            }
        )
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    assert "dataElements" in body
    assert "indicators" not in body


@respx.mock
async def test_dry_run_posts_validate_mode_with_dumped_models(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`dry_run` posts bundle with `importMode=VALIDATE`; pydantic items dump via model_dump."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "httpStatus": "OK",
                "httpStatusCode": 200,
                "response": {"status": "OK", "stats": {"total": 2, "created": 2}},
            },
        ),
    )

    from dhis2w_client.generated.v42.enums import AggregationType, DataElementDomain, ValueType
    from dhis2w_client.generated.v42.schemas.data_element import DataElement

    de_model = DataElement(
        id="modelUidAAA1",
        name="model",
        shortName="mdl",
        aggregationType=AggregationType.SUM,
        domainType=DataElementDomain.AGGREGATE,
        valueType=ValueType.NUMBER,
    )
    de_dict = {"id": "rawUid000001", "name": "raw"}

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.dry_run({"dataElements": [de_model, de_dict]})
    finally:
        await client.close()

    assert result.status == "OK"
    body = json.loads(route.calls.last.request.content)
    params = route.calls.last.request.url.params
    assert params["importMode"] == "VALIDATE"
    assert params["importStrategy"] == "CREATE_AND_UPDATE"
    assert {row["id"] for row in body["dataElements"]} == {"modelUidAAA1", "rawUid000001"}


@respx.mock
async def test_dry_run_forwards_custom_import_strategy(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`import_strategy` flows through as the `importStrategy` query param."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatus": "OK", "httpStatusCode": 200}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.metadata.dry_run(
            {"dataElements": [{"id": "u1", "name": "x"}]},
            import_strategy="UPDATE",
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["importStrategy"] == "UPDATE"
    assert params["importMode"] == "VALIDATE"


@respx.mock
async def test_dry_run_empty_bundle_short_circuits(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Empty `by_resource` (or every list empty) returns a no-op without HTTP."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata")
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        empty = await client.metadata.dry_run({})
        all_lists_empty = await client.metadata.dry_run({"dataElements": [], "indicators": []})
    finally:
        await client.close()

    assert route.call_count == 0
    assert empty.status == "OK"
    assert all_lists_empty.message == "no items supplied"


@respx.mock
async def test_resource_save_bulk_posts_typed_models_to_metadata(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`client.resources.<resource>.save_bulk` dumps typed models + posts to `/api/metadata`."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(
            200,
            json={"status": "OK", "response": {"stats": {"created": 2, "total": 2}}},
        ),
    )

    from dhis2w_client.generated.v42.enums import AggregationType, DataElementDomain, ValueType
    from dhis2w_client.generated.v42.schemas.data_element import DataElement

    elements = [
        DataElement(
            id=f"uidDe{i:08d}",
            name=f"elem-{i}",
            shortName=f"e{i}",
            aggregationType=AggregationType.SUM,
            domainType=DataElementDomain.AGGREGATE,
            valueType=ValueType.NUMBER,
        )
        for i in range(2)
    ]

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        raw = await client.resources.data_elements.save_bulk(elements)
    finally:
        await client.close()

    assert raw["status"] == "OK"
    body = json.loads(route.calls.last.request.content)
    params = route.calls.last.request.url.params
    assert params["importStrategy"] == "CREATE_AND_UPDATE"
    assert params["atomicMode"] == "NONE"
    assert len(body["dataElements"]) == 2
    # Typed-model dump applied aliases + excluded None.
    assert all("id" in row and "name" in row for row in body["dataElements"])


@respx.mock
async def test_resource_save_bulk_dry_run_flag_sets_validate_mode(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`save_bulk(dry_run=True)` adds `importMode=VALIDATE`."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.resources.data_elements.save_bulk(
            [{"id": "uid00000001", "name": "x"}],
            dry_run=True,
            atomic_mode="ALL",
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["importMode"] == "VALIDATE"
    assert params["atomicMode"] == "ALL"


@respx.mock
async def test_resource_save_bulk_empty_list_short_circuits(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Empty list returns a no-op envelope without hitting `/api/metadata`."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata")

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        raw = await client.resources.data_elements.save_bulk([])
    finally:
        await client.close()

    assert route.call_count == 0
    assert raw["status"] == "OK"
    assert raw["message"] == "no items supplied"


@respx.mock
async def test_delete_bulk_multi_all_empty_short_circuits(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Every-list-empty payload never hits the wire."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata")

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.delete_bulk_multi({"dataElements": [], "indicators": []})
    finally:
        await client.close()

    assert route.call_count == 0
    assert result.status == "OK"


@respx.mock
async def test_delete_bulk_forwards_atomic_mode_parameter(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`atomic_mode='ALL'` flows through as a query parameter."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatus": "OK", "httpStatusCode": 200}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.metadata.delete_bulk_multi(
            {"dataElements": ["deUidAAA0001"]},
            atomic_mode="ALL",
        )
    finally:
        await client.close()

    assert route.calls.last.request.url.params["atomicMode"] == "ALL"


# ---- MetadataAccessor.search ----------------------------------------------


def _search_mock_by_field(
    field_to_bundle: Mapping[str, dict[str, Any]],
) -> None:
    """Route `/api/metadata` requests by the filter axis (`id`/`code`/`name`).

    Given `{"id": {...}, "code": {...}, "name": {...}}`, each call's `filter`
    param prefix decides which bundle to return. Unknown prefixes → empty.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        filter_value = request.url.params.get("filter") or ""
        match = re.match(r"^([a-zA-Z]+):", filter_value)
        field = match.group(1) if match else ""
        payload: dict[str, Any] = dict(field_to_bundle.get(field) or {"system": {"version": "2.42.4"}})
        return httpx.Response(200, json=payload)

    respx.get("https://dhis2.example/api/metadata").mock(side_effect=_handler)


@respx.mock
async def test_search_fans_out_one_call_per_match_axis(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Fans out id/code/name filters in parallel and merges the bundles."""
    mock_system_info(server_version)
    _search_mock_by_field(
        {
            "id": {"dataElements": [{"id": "deUid000001", "name": "Hit by id"}]},
            "code": {"dataElements": [{"id": "deUid000002", "name": "Hit by code", "code": "HIT_CODE"}]},
            "name": {"indicators": [{"id": "indUid00001", "name": "Measles coverage"}]},
        },
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.search("measles")
    finally:
        await client.close()

    # Three calls — one per match axis.
    calls = [call.request.url.params.get("filter") for call in respx.calls if "/api/metadata" in str(call.request.url)]
    assert calls == ["id:ilike:measles", "code:ilike:measles", "name:ilike:measles"]
    # Union across axes, sorted by resource name.
    assert list(result.hits) == ["dataElements", "indicators"]
    assert {hit.uid for hit in result.hits["dataElements"]} == {"deUid000001", "deUid000002"}
    assert result.total == 3


@respx.mock
async def test_search_dedupes_hits_matching_on_multiple_axes(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Object matching on both id and name collapses to one merged hit."""
    mock_system_info(server_version)
    same = {"id": "deUid000001", "name": "measles doses", "code": "DE_MEASLES"}
    _search_mock_by_field(
        {
            "id": {"dataElements": [same]},
            "code": {"dataElements": [same]},
            "name": {"dataElements": [same]},
        },
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.search("measles")
    finally:
        await client.close()

    assert result.total == 1
    assert result.hits["dataElements"][0].uid == "deUid000001"


@respx.mock
async def test_search_omits_non_resource_keys_and_empty_sections(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """The `system` + `date` envelope keys don't appear as resource hits."""
    mock_system_info(server_version)
    _search_mock_by_field(
        {
            "name": {
                "system": {"version": "2.42.4"},
                "date": "2024-01-01",
                "dataElements": [{"id": "deUid000001", "name": "A"}],
                "indicators": [],
            },
        },
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.search("any")
    finally:
        await client.close()

    assert list(result.hits.keys()) == ["dataElements"]
    flat = result.flat()
    assert len(flat) == 1
    assert flat[0].uid == "deUid000001"


@respx.mock
async def test_search_returns_empty_results_on_no_matches(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Empty bundles round-trip as `SearchResults(total=0)` — not an error."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"system": {"version": "2.42.4"}}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.search("nothing-here")
    finally:
        await client.close()

    assert result.total == 0
    assert result.hits == {}


@respx.mock
async def test_search_resource_narrows_to_per_resource_endpoint(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`resource='dataElements'` hits `/api/dataElements` directly, not `/api/metadata`."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={"dataElements": [{"id": "deUid000001", "name": "Measles doses"}]},
        ),
    )
    metadata_route = respx.get("https://dhis2.example/api/metadata").mock(return_value=httpx.Response(500))

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.search("measles", resource="dataElements")
    finally:
        await client.close()

    assert route.call_count == 3  # one per match axis (id/code/name)
    assert metadata_route.call_count == 0
    assert list(result.hits.keys()) == ["dataElements"]


@respx.mock
async def test_search_exact_switches_operator_from_ilike_to_eq(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`exact=True` changes the filter operator to `:eq:` on every axis."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"system": {"version": "2.42.4"}}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.metadata.search("deUid000001", exact=True)
    finally:
        await client.close()

    filters = [
        call.request.url.params.get("filter") for call in respx.calls if "/api/metadata" in str(call.request.url)
    ]
    assert filters == [
        "id:eq:deUid000001",
        "code:eq:deUid000001",
        "name:eq:deUid000001",
    ]


@respx.mock
async def test_search_custom_fields_flow_to_extras(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Wider `fields=` selector lands on `SearchHit.extras`."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "system": {"version": "2.42.4"},
                "dataElements": [
                    {
                        "id": "deUid000001",
                        "name": "Measles doses",
                        "valueType": "NUMBER",
                        "domainType": "AGGREGATE",
                    },
                ],
            },
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.search("measles", fields="id,name,valueType,domainType")
    finally:
        await client.close()

    hit = result.hits["dataElements"][0]
    assert hit.extras == {"valueType": "NUMBER", "domainType": "AGGREGATE"}


# ---- MetadataAccessor.usage -----------------------------------------------


@respx.mock
async def test_usage_resolves_resource_then_fans_out_reference_queries(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """DE usage hits `/api/identifiableObjects/{uid}` then the DE reference paths."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/identifiableObjects/deUid000001").mock(
        return_value=httpx.Response(
            200,
            json={"id": "deUid000001", "name": "Measles", "href": "https://dhis2.example/api/dataElements/deUid000001"},
        ),
    )
    respx.get("https://dhis2.example/api/dataSets").mock(
        return_value=httpx.Response(200, json={"dataSets": [{"id": "dsUid000001", "name": "Child Health"}]}),
    )
    respx.get("https://dhis2.example/api/visualizations").mock(
        return_value=httpx.Response(200, json={"visualizations": [{"id": "vizUid00001", "name": "Stacked"}]}),
    )
    respx.get("https://dhis2.example/api/maps").mock(
        return_value=httpx.Response(200, json={"maps": []}),
    )
    respx.get("https://dhis2.example/api/programStages").mock(
        return_value=httpx.Response(200, json={"programStages": []}),
    )
    respx.get("https://dhis2.example/api/programRuleVariables").mock(
        return_value=httpx.Response(200, json={"programRuleVariables": []}),
    )
    respx.get("https://dhis2.example/api/indicators").mock(
        return_value=httpx.Response(200, json={"indicators": []}),
    )
    respx.get("https://dhis2.example/api/predictors").mock(
        return_value=httpx.Response(200, json={"predictors": []}),
    )
    respx.get("https://dhis2.example/api/validationRules").mock(
        return_value=httpx.Response(200, json={"validationRules": []}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.usage("deUid000001")
    finally:
        await client.close()

    # Non-empty resources surface; empty ones are dropped.
    assert set(result.hits.keys()) == {"dataSets", "visualizations"}
    assert result.total == 2


@respx.mock
async def test_usage_on_visualization_finds_owning_dashboards(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Viz usage follows the dashboards -> dashboardItems.visualization.id path."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/identifiableObjects/vizUid00001").mock(
        return_value=httpx.Response(
            200,
            json={"id": "vizUid00001", "name": "V", "href": "https://dhis2.example/api/visualizations/vizUid00001"},
        ),
    )
    route = respx.get("https://dhis2.example/api/dashboards").mock(
        return_value=httpx.Response(200, json={"dashboards": [{"id": "dashUid0001", "name": "Immunization"}]}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.usage("vizUid00001")
    finally:
        await client.close()

    assert route.calls.last.request.url.params["filter"] == "dashboardItems.visualization.id:eq:vizUid00001"
    assert list(result.hits.keys()) == ["dashboards"]


@respx.mock
async def test_usage_unknown_resource_type_returns_empty(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """UID that resolves to a resource with no reference map → empty result."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/identifiableObjects/unknownUid1").mock(
        return_value=httpx.Response(
            200,
            json={"id": "unknownUid1", "href": "https://dhis2.example/api/unmapped/unknownUid1"},
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.usage("unknownUid1")
    finally:
        await client.close()

    assert result.total == 0
    assert result.hits == {}
