"""Per-version parity for the `analytics` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/analytics/test_*.py` routes + assertions, but resolves the service per
`core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted, not just
smoke-imported. The three service trees are byte-identical copies (only the import version differs), so
the assertions are the same on every tree. Mocked (respx); no live stack.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


def _grid_body() -> dict[str, object]:
    """Minimal Grid envelope (headers + rows + metaData) the service validates into a `Grid`."""
    return {
        "headers": [{"name": "dx", "column": "Data"}, {"name": "value", "column": "Value"}],
        "rows": [["DEabc", "12"], ["DEdef", "7"]],
        "metaData": {"items": {}, "dimensions": {}},
        "width": 2,
        "height": 2,
    }


@respx.mock
async def test_query_analytics_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`query_analytics` (shape="table") hits /api/analytics and parses a `Grid`, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("analytics")
    route = respx.get(f"{_HOST}/api/analytics").mock(return_value=httpx.Response(200, json=_grid_body()))

    response = await service.query_analytics(
        resolve_profile("probe"),
        dimensions=["dx:DEabc", "pe:LAST_12_MONTHS", "ou:ouRoot"],
    )

    assert route.called
    assert response.rows is not None
    assert len(response.rows) == 2
    assert route.calls.last.request.url.params.get_list("dimension") == ["dx:DEabc", "pe:LAST_12_MONTHS", "ou:ouRoot"]


@respx.mock
async def test_query_events_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`query_events` hits /api/analytics/events/query/{program} by default, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("analytics")
    route = respx.get(f"{_HOST}/api/analytics/events/query/progUID").mock(
        return_value=httpx.Response(200, json=_grid_body())
    )

    response = await service.query_events(
        resolve_profile("probe"),
        program="progUID",
        dimensions=["pe:LAST_12_MONTHS", "ou:ouRoot"],
        stage="stageUID",
    )

    assert route.called
    request = route.calls.last.request
    assert request.url.params.get_list("dimension") == ["pe:LAST_12_MONTHS", "ou:ouRoot"]
    assert request.url.params["stage"] == "stageUID"
    assert response.rows is not None
    assert len(response.rows) == 2


@respx.mock
async def test_query_enrollments_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`query_enrollments` hits /api/analytics/enrollments/query/{program}, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("analytics")
    route = respx.get(f"{_HOST}/api/analytics/enrollments/query/progUID").mock(
        return_value=httpx.Response(200, json=_grid_body())
    )

    response = await service.query_enrollments(
        resolve_profile("probe"),
        program="progUID",
        dimensions=["pe:THIS_YEAR"],
        start_date="2026-01-01",
        end_date="2026-06-30",
    )

    assert route.called
    request = route.calls.last.request
    assert request.url.params["startDate"] == "2026-01-01"
    assert request.url.params["endDate"] == "2026-06-30"
    assert response.rows is not None
    assert len(response.rows) == 2


@respx.mock
async def test_query_outlier_detection_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`query_outlier_detection` forwards named params to /api/analytics/outlierDetection, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("analytics")
    route = respx.get(f"{_HOST}/api/analytics/outlierDetection").mock(
        return_value=httpx.Response(200, json=_grid_body())
    )

    response = await service.query_outlier_detection(
        resolve_profile("probe"),
        data_elements=["DEa", "DEb"],
        data_sets=["DS1"],
        org_units=["ouX"],
        periods="LAST_12_MONTHS",
        algorithm="Z_SCORE",
        threshold=3.0,
        max_results=100,
        order_by="MEAN_ABS_DEV",
        sort_order="DESC",
    )

    assert route.called
    assert response.rows is not None
    params = route.calls.last.request.url.params
    assert params.get_list("dx") == ["DEa", "DEb"]
    assert params.get_list("ds") == ["DS1"]
    assert params.get_list("ou") == ["ouX"]
    assert params["pe"] == "LAST_12_MONTHS"
    assert params["algorithm"] == "Z_SCORE"
    assert params["threshold"] == "3.0"
    assert params["maxResults"] == "100"
    assert params["orderBy"] == "MEAN_ABS_DEV"
    assert params["sortOrder"] == "DESC"


@respx.mock
async def test_query_tracked_entities_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`query_tracked_entities` hits /api/analytics/trackedEntities/query/{tet}, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("analytics")
    route = respx.get(f"{_HOST}/api/analytics/trackedEntities/query/tetUID").mock(
        return_value=httpx.Response(200, json=_grid_body())
    )

    response = await service.query_tracked_entities(
        resolve_profile("probe"),
        tracked_entity_type="tetUID",
        dimensions=["ou:NORNorway01"],
        filters=["A:eq:foo"],
        program=["progA", "progB"],
        ou_mode="DESCENDANTS",
        page_size=10,
        asc=["created"],
    )

    assert route.called
    assert response.rows is not None
    params = route.calls.last.request.url.params
    assert params.get_list("dimension") == ["ou:NORNorway01"]
    assert params.get_list("filter") == ["A:eq:foo"]
    assert params.get_list("program") == ["progA", "progB"]
    assert params["ouMode"] == "DESCENDANTS"
    assert params["pageSize"] == "10"
    assert params.get_list("asc") == ["created"]
