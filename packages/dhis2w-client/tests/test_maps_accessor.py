"""Unit tests for `MapsAccessor` + `MapSpec` + `MapLayerSpec` — respx-mocked."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client, MapLayerSpec, MapSpec
from dhis2w_client.generated.v42.enums import ThematicMapType


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


# ---- MapLayerSpec.to_map_view -------------------------------------------


def test_thematic_layer_populates_dimension_selectors() -> None:
    """Thematic layer populates dimension selectors."""
    layer = MapLayerSpec(
        layer_kind="thematic",
        data_elements=["DE1"],
        periods=["2024"],
        organisation_units=["OU1"],
        organisation_unit_levels=[2],
        classes=4,
        color_low="#aaa",
        color_high="#f00",
    )
    view = layer.to_map_view()
    # Most fields live on the typed MapView; rowDimensions isn't on the
    # generated model (MapView doesn't declare it), so it rides via
    # model_extra.
    assert view.layer == "thematic"
    assert view.thematicMapType == ThematicMapType.CHOROPLETH
    assert view.columnDimensions == ["dx"]
    assert view.filterDimensions == ["pe"]
    assert view.classes == 4
    assert view.colorLow == "#aaa"
    extras = view.model_extra or {}
    assert extras.get("rowDimensions") == ["ou"]


def test_thematic_layer_accepts_indicators_and_legend_set() -> None:
    """Thematic layer accepts indicators and legend set."""
    layer = MapLayerSpec(
        layer_kind="thematic",
        indicators=["IND1", "IND2"],
        periods=["2024"],
        organisation_units=["OU1"],
        organisation_unit_levels=[2],
        legend_set="LEGEND_UID",
    )
    view = layer.to_map_view()
    assert view.dataDimensionItems is not None
    kinds = [item["dataDimensionItemType"] for item in view.dataDimensionItems]
    assert kinds == ["INDICATOR", "INDICATOR"]
    assert view.legendSet is not None
    assert view.legendSet.id == "LEGEND_UID"


def test_thematic_layer_mixes_data_elements_and_indicators() -> None:
    """Thematic layer mixes data elements and indicators."""
    layer = MapLayerSpec(
        layer_kind="thematic",
        data_elements=["DE1"],
        indicators=["IND1"],
        periods=["2024"],
        organisation_units=["OU1"],
        organisation_unit_levels=[2],
    )
    view = layer.to_map_view()
    assert view.dataDimensionItems is not None
    kinds = [item["dataDimensionItemType"] for item in view.dataDimensionItems]
    assert kinds == ["DATA_ELEMENT", "INDICATOR"]


def test_boundary_layer_skips_thematic_fields() -> None:
    """Boundary layer skips thematic fields."""
    layer = MapLayerSpec(
        layer_kind="boundary",
        organisation_units=["OU1"],
        organisation_unit_levels=[1],
    )
    view = layer.to_map_view()
    assert view.layer == "boundary"
    # No thematic-specific fields on a boundary-only layer.
    assert view.thematicMapType is None
    assert view.dataDimensionItems is None


# ---- MapSpec.to_map -----------------------------------------------------


def test_map_spec_materialises_layers_and_viewport() -> None:
    """Map spec materialises layers and viewport."""
    spec = MapSpec(
        name="Probe map",
        description="Test fixture",
        uid="MapTestSpec",
        longitude=10.5,
        latitude=60.0,
        zoom=6,
        basemap="osm-light",
        layers=[
            MapLayerSpec(
                layer_kind="thematic",
                data_elements=["DE1"],
                periods=["2024"],
                organisation_unit_levels=[2],
                organisation_units=["OU1"],
            ),
        ],
    )
    m = spec.to_map()
    assert m.id == "MapTestSpec"
    assert m.zoom == 6
    assert m.longitude == 10.5
    assert m.mapViews is not None
    assert len(m.mapViews) == 1


def test_map_spec_auto_generates_uid_when_omitted() -> None:
    """Map spec auto generates uid when omitted."""
    spec = MapSpec(
        name="auto",
        layers=[MapLayerSpec(data_elements=["DE1"], periods=["2024"], organisation_unit_levels=[2])],
    )
    m = spec.to_map()
    assert m.id is not None
    assert len(m.id) == 11


# ---- MapsAccessor.list_all ----------------------------------------------


@respx.mock
async def test_list_all_orders_by_name_paging_off(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """List all orders by name paging off."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/maps").mock(
        return_value=httpx.Response(
            200,
            json={"maps": [{"id": "M1", "name": "alpha"}, {"id": "M2", "name": "beta"}]},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        maps = await client.maps.list_all()
    finally:
        await client.close()
    assert route.calls.last.request.url.params["order"] == "name:asc"
    assert route.calls.last.request.url.params["paging"] == "false"
    assert [m.name for m in maps] == ["alpha", "beta"]


@respx.mock
async def test_get_returns_typed_model_with_map_views(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Get returns typed model with map views."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/maps/M1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "M1",
                "name": "thematic",
                "zoom": 5,
                "mapViews": [{"layer": "thematic", "thematicMapType": "CHOROPLETH"}],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        m = await client.maps.get("M1")
    finally:
        await client.close()
    assert m.id == "M1"
    assert m.zoom == 5
    assert m.mapViews is not None
    assert len(m.mapViews) == 1


# ---- create_from_spec ---------------------------------------------------


@respx.mock
async def test_create_from_spec_posts_through_api_metadata(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Create from spec posts through api metadata."""
    mock_system_info(server_version)
    metadata_route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    respx.get("https://dhis2.example/api/maps/MapTestSpec").mock(
        return_value=httpx.Response(200, json={"id": "MapTestSpec", "name": "probe"}),
    )
    spec = MapSpec(
        name="probe",
        uid="MapTestSpec",
        layers=[MapLayerSpec(data_elements=["DE1"], periods=["2024"], organisation_unit_levels=[2])],
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        created = await client.maps.create_from_spec(spec)
    finally:
        await client.close()
    assert metadata_route.call_count == 1
    assert created.id == "MapTestSpec"
    assert metadata_route.calls.last.request.url.params["importStrategy"] == "CREATE_AND_UPDATE"


# ---- clone --------------------------------------------------------------


@respx.mock
async def test_clone_strips_server_owned_and_nested_view_uids(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Clone must drop server-owned fields + the source's nested MapView UIDs."""
    mock_system_info(server_version)
    respx.get(url__regex=r"https://dhis2\.example/api/maps/SRC00000001(\?.*)?$").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "SRC00000001",
                "name": "source",
                "zoom": 5,
                "mapViews": [
                    {"id": "MView000001", "layer": "thematic", "created": "2026-04-20T00:00:00Z"},
                ],
                "created": "2026-04-20T00:00:00Z",
                "lastUpdated": "2026-04-20T00:00:00Z",
            },
        ),
    )
    metadata_route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    respx.get(url__regex=r"https://dhis2\.example/api/maps/NEW00000001(\?.*)?$").mock(
        return_value=httpx.Response(200, json={"id": "NEW00000001", "name": "clone"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        cloned = await client.maps.clone("SRC00000001", new_name="clone", new_uid="NEW00000001")
    finally:
        await client.close()
    assert cloned.id == "NEW00000001"
    body = metadata_route.calls.last.request.content
    assert b'"id":"NEW00000001"' in body
    assert b'"id":"MView000001"' not in body  # nested view UID was stripped
    assert b'"created"' not in body


# ---- delete + binding ---------------------------------------------------


@respx.mock
async def test_delete_routes_to_maps_uid(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Delete routes to maps uid."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/maps/M1").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.maps.delete("M1")
    finally:
        await client.close()
    assert route.call_count == 1


async def test_accessor_is_bound_on_client() -> None:
    """Accessor is bound on client."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        for attr in ("list_all", "get", "create_from_spec", "clone", "delete"):
            assert hasattr(client.maps, attr), f"missing {attr}"
    finally:
        await client.close()


_ = pytest
