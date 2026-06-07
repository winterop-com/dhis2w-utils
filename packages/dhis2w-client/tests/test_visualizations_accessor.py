"""Unit tests for `VisualizationsAccessor` + `VisualizationSpec` — respx-mocked."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client, RelativePeriod, VisualizationSpec
from dhis2w_client.generated.v42.enums import VisualizationType


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


# ---- VisualizationSpec._resolve_placement ---------------------------------


def test_spec_defaults_line_to_pe_rows_ou_columns_dx_filters() -> None:
    """Spec defaults line to pe rows ou columns dx filters."""
    spec = VisualizationSpec(
        name="ANC monthly",
        viz_type=VisualizationType.LINE,
        data_elements=["DE1"],
        periods=["202401", "202402"],
        organisation_units=["OU1", "OU2"],
    )
    rows, cols, filters = spec._resolve_placement()
    assert rows == ["pe"]
    assert cols == ["ou"]
    assert filters == ["dx"]


def test_spec_defaults_pivot_to_ou_rows_pe_columns_dx_filters() -> None:
    """Spec defaults pivot to ou rows pe columns dx filters."""
    spec = VisualizationSpec(
        name="OPD by province",
        viz_type=VisualizationType.PIVOT_TABLE,
        data_elements=["DE1"],
        periods=["202401"],
        organisation_units=["OU1"],
    )
    rows, cols, filters = spec._resolve_placement()
    assert rows == ["ou"]
    assert cols == ["pe"]
    assert filters == ["dx"]


def test_spec_defaults_single_value_to_dx_columns_empty_rows_pe_ou_filters() -> None:
    """SINGLE_VALUE collapses to one cell: columns=[dx], rows=[], filters=[pe, ou]."""
    spec = VisualizationSpec(
        name="KPI",
        viz_type=VisualizationType.SINGLE_VALUE,
        data_elements=["DE1"],
        periods=["202412"],
        organisation_units=["OU1"],
    )
    rows, cols, filters = spec._resolve_placement()
    assert rows == []
    assert cols == ["dx"]
    assert sorted(filters) == ["ou", "pe"]


def test_spec_honours_explicit_dimension_overrides() -> None:
    """Explicit category/series/filter take precedence over defaults."""
    spec = VisualizationSpec(
        name="custom",
        viz_type=VisualizationType.COLUMN,
        data_elements=["DE1", "DE2"],
        periods=["202401"],
        organisation_units=["OU1"],
        category_dimension="ou",
        series_dimension="dx",
        filter_dimension="pe",
    )
    rows, cols, filters = spec._resolve_placement()
    assert rows == ["ou"]
    assert cols == ["dx"]
    assert filters == ["pe"]


# ---- VisualizationSpec.to_visualization ----------------------------------


def test_to_visualization_populates_dimension_selectors_and_items() -> None:
    """To visualization populates dimension selectors and items."""
    spec = VisualizationSpec(
        name="ANC trend",
        viz_type=VisualizationType.LINE,
        data_elements=["DEancVisit1"],
        periods=["202401", "202402", "202403"],
        organisation_units=["OU1", "OU2"],
        uid="VizTestLine",
    )
    viz = spec.to_visualization()
    assert viz.id == "VizTestLine"
    assert viz.type == VisualizationType.LINE
    assert viz.rowDimensions == ["pe"]
    assert viz.columnDimensions == ["ou"]
    assert viz.filterDimensions == ["dx"]
    assert viz.rawPeriods == ["202401", "202402", "202403"]
    assert viz.organisationUnits == [{"id": "OU1"}, {"id": "OU2"}]
    assert viz.dataDimensionItems is not None
    assert len(viz.dataDimensionItems) == 1


def test_to_visualization_auto_generates_uid_when_omitted() -> None:
    """To visualization auto generates uid when omitted."""
    spec = VisualizationSpec(
        name="auto uid",
        data_elements=["DE1"],
        periods=["202401"],
        organisation_units=["OU1"],
    )
    viz = spec.to_visualization()
    assert viz.id is not None
    assert len(viz.id) == 11


def test_to_visualization_emits_relative_periods_block() -> None:
    """To visualization emits relative periods block."""
    spec = VisualizationSpec(
        name="rolling coverage",
        viz_type=VisualizationType.COLUMN,
        data_elements=["DE1"],
        relative_periods=frozenset({RelativePeriod.LAST_12_MONTHS, RelativePeriod.THIS_YEAR}),
        organisation_units=["OU1"],
    )
    viz = spec.to_visualization()
    dumped = viz.model_dump(by_alias=True, exclude_none=True)
    assert dumped["relativePeriods"] == {"last12Months": True, "thisYear": True}
    assert not viz.rawPeriods


def test_to_visualization_accepts_periods_and_relative_periods_together() -> None:
    """To visualization accepts periods and relative periods together."""
    spec = VisualizationSpec(
        name="explicit + rolling",
        data_elements=["DE1"],
        periods=["202401"],
        relative_periods=frozenset({RelativePeriod.LAST_6_MONTHS}),
        organisation_units=["OU1"],
    )
    viz = spec.to_visualization()
    dumped = viz.model_dump(by_alias=True, exclude_none=True)
    assert viz.rawPeriods == ["202401"]
    assert dumped["relativePeriods"] == {"last6Months": True}


def test_spec_rejects_empty_period_selection() -> None:
    """Spec rejects empty period selection."""
    with pytest.raises(ValueError, match="requires either `periods` or `relative_periods`"):
        VisualizationSpec(
            name="no periods",
            data_elements=["DE1"],
            organisation_units=["OU1"],
        )


def test_to_visualization_omits_relative_periods_when_unset() -> None:
    """To visualization omits relative periods when unset."""
    spec = VisualizationSpec(
        name="explicit only",
        data_elements=["DE1"],
        periods=["202401"],
        organisation_units=["OU1"],
    )
    viz = spec.to_visualization()
    dumped = viz.model_dump(by_alias=True, exclude_none=True)
    assert "relativePeriods" not in dumped


def test_to_visualization_emits_indicator_dimension_items() -> None:
    """To visualization emits indicator dimension items."""
    spec = VisualizationSpec(
        name="coverage by indicator",
        indicators=["IND1", "IND2"],
        periods=["202401"],
        organisation_units=["OU1"],
    )
    viz = spec.to_visualization()
    assert viz.dataDimensionItems is not None
    kinds = [item["dataDimensionItemType"] for item in viz.dataDimensionItems]
    assert kinds == ["INDICATOR", "INDICATOR"]
    ids = [item["indicator"]["id"] for item in viz.dataDimensionItems]
    assert ids == ["IND1", "IND2"]


def test_to_visualization_mixes_data_elements_and_indicators() -> None:
    """To visualization mixes data elements and indicators."""
    spec = VisualizationSpec(
        name="mixed dx",
        data_elements=["DE1"],
        indicators=["IND1"],
        periods=["202401"],
        organisation_units=["OU1"],
    )
    viz = spec.to_visualization()
    assert viz.dataDimensionItems is not None
    kinds = [item["dataDimensionItemType"] for item in viz.dataDimensionItems]
    assert kinds == ["DATA_ELEMENT", "INDICATOR"]


def test_to_visualization_emits_legend_block_when_set() -> None:
    """To visualization emits legend block when set."""
    spec = VisualizationSpec(
        name="with legend",
        data_elements=["DE1"],
        periods=["202401"],
        organisation_units=["OU1"],
        legend_set="LEGEND_UID",
    )
    viz = spec.to_visualization()
    dumped = viz.model_dump(by_alias=True, exclude_none=True)
    assert dumped["legend"] == {
        "set": {"id": "LEGEND_UID"},
        "strategy": "FIXED",
        "style": "FILL",
        "showKey": True,
    }


def test_to_visualization_omits_legend_when_unset() -> None:
    """To visualization omits legend when unset."""
    spec = VisualizationSpec(
        name="no legend",
        data_elements=["DE1"],
        periods=["202401"],
        organisation_units=["OU1"],
    )
    viz = spec.to_visualization()
    dumped = viz.model_dump(by_alias=True, exclude_none=True)
    assert "legend" not in dumped


def test_spec_rejects_empty_data_dimension() -> None:
    """Spec rejects empty data dimension."""
    with pytest.raises(ValueError, match="requires at least one `data_elements` or `indicators`"):
        VisualizationSpec(
            name="no data",
            periods=["202401"],
            organisation_units=["OU1"],
        )


# ---- VisualizationsAccessor.list_all -------------------------------------


@respx.mock
async def test_list_all_orders_by_name_and_disables_paging(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """List all orders by name and disables paging."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/visualizations").mock(
        return_value=httpx.Response(
            200,
            json={
                "visualizations": [
                    {"id": "V1", "name": "alpha", "type": "LINE"},
                    {"id": "V2", "name": "beta", "type": "COLUMN"},
                ],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        vizes = await client.visualizations.list_all()
    finally:
        await client.close()
    params = route.calls.last.request.url.params
    assert params["order"] == "name:asc"
    assert params["paging"] == "false"
    assert [v.name for v in vizes] == ["alpha", "beta"]


@respx.mock
async def test_list_all_filters_by_viz_type(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """List all filters by viz type."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/visualizations").mock(
        return_value=httpx.Response(200, json={"visualizations": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.visualizations.list_all(viz_type=VisualizationType.PIVOT_TABLE)
    finally:
        await client.close()
    assert route.calls.last.request.url.params["filter"] == "type:eq:PIVOT_TABLE"


# ---- VisualizationsAccessor.get ------------------------------------------


@respx.mock
async def test_get_returns_typed_model(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Get returns typed model."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/visualizations/V1").mock(
        return_value=httpx.Response(
            200,
            json={"id": "V1", "name": "x", "type": "LINE", "columnDimensions": ["ou"]},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        viz = await client.visualizations.get("V1")
    finally:
        await client.close()
    assert viz.id == "V1"
    assert viz.columnDimensions == ["ou"]


# ---- VisualizationsAccessor.create_from_spec -----------------------------


@respx.mock
async def test_create_from_spec_posts_through_api_metadata(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Creation always routes through `/api/metadata` so DHIS2 populates derived axes."""
    mock_system_info(server_version)
    metadata_route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    respx.get("https://dhis2.example/api/visualizations/VizTest1234").mock(
        return_value=httpx.Response(
            200,
            json={"id": "VizTest1234", "name": "probe", "type": "LINE"},
        ),
    )
    spec = VisualizationSpec(
        name="probe",
        viz_type=VisualizationType.LINE,
        data_elements=["DE1"],
        periods=["202401"],
        organisation_units=["OU1"],
        uid="VizTest1234",
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        created = await client.visualizations.create_from_spec(spec)
    finally:
        await client.close()
    assert metadata_route.call_count == 1
    assert created.id == "VizTest1234"
    # Confirm the importStrategy query param is correct.
    assert metadata_route.calls.last.request.url.params["importStrategy"] == "CREATE_AND_UPDATE"


# ---- VisualizationsAccessor.clone ----------------------------------------


@respx.mock
async def test_clone_strips_server_owned_fields_and_reuses_data_axes(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Clone fetches the source, strips id/created/lastUpdated, and POSTs with a new UID + name."""
    mock_system_info(server_version)
    respx.get(url__regex=r"https://dhis2\.example/api/visualizations/SRC00000001(\?.*)?$").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "SRC00000001",
                "name": "original",
                "type": "LINE",
                "rowDimensions": ["pe"],
                "columnDimensions": ["ou"],
                "filterDimensions": ["dx"],
                "periods": [{"id": "202401"}],
                "organisationUnits": [{"id": "OU1"}],
                "dataDimensionItems": [{"dataDimensionItemType": "DATA_ELEMENT", "dataElement": {"id": "DE1"}}],
                "created": "2026-04-20T00:00:00Z",
                "lastUpdated": "2026-04-20T00:00:00Z",
            },
        ),
    )
    metadata_route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    respx.get(url__regex=r"https://dhis2\.example/api/visualizations/NEW00000001(\?.*)?$").mock(
        return_value=httpx.Response(
            200,
            json={"id": "NEW00000001", "name": "clone", "type": "LINE"},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        cloned = await client.visualizations.clone(
            "SRC00000001",
            new_name="clone",
            new_uid="NEW00000001",
        )
    finally:
        await client.close()
    assert cloned.id == "NEW00000001"
    body = metadata_route.calls.last.request.content
    assert b'"id":"NEW00000001"' in body
    assert b'"name":"clone"' in body
    # created / lastUpdated should have been stripped off the clone payload.
    assert b'"created"' not in body
    assert b'"lastUpdated"' not in body


# ---- VisualizationsAccessor.delete ---------------------------------------


@respx.mock
async def test_delete_routes_to_visualizations_uid(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Delete routes to visualizations uid."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/visualizations/V1").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.visualizations.delete("V1")
    finally:
        await client.close()
    assert route.call_count == 1


# ---- Binding check --------------------------------------------------------


async def test_accessor_is_bound_on_client() -> None:
    """Accessor is bound on client."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        for attr in ("list_all", "get", "create_from_spec", "clone", "delete"):
            assert hasattr(client.visualizations, attr), f"missing {attr}"
    finally:
        await client.close()


_ = pytest  # keep import honest
