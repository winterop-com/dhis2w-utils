"""Route + URL tests for outlier-detection + trackedEntities analytics."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_client import Grid, GridHeader
from dhis2w_client.generated.v42.oas._enums import ValueType
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.analytics import service
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Raw-env profile so `profile_from_env()` resolves without TOML."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DHIS2_URL", "https://dhis2.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")
    yield


@pytest.fixture
def profile() -> Profile:
    return Profile(base_url="https://dhis2.example", auth="pat", token="test-token")


def _mock_preamble() -> None:
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )


def _outlier_body() -> dict[str, object]:
    """DHIS2 v42 returns outliers in the Grid envelope (headers + rows), not a bespoke shape.

    Built via the typed `Grid` so the fixture can't drift from the production model.
    """
    return Grid(
        headers=[
            GridHeader(name="dx", column="Data", valueType=ValueType.TEXT, type="java.lang.String"),
            GridHeader(name="value", column="Value", valueType=ValueType.NUMBER, type="java.lang.Double"),
            GridHeader(name="zscore", column="Z-score", valueType=ValueType.NUMBER, type="java.lang.Double"),
        ],
        rows=[["DEabc", "4189.0", "2.4"]],
        metaData={},
        width=3,
        height=1,
    ).model_dump(exclude_none=True, mode="json")


def _tracked_entities_body() -> dict[str, object]:
    return Grid(
        headers=[
            GridHeader(name="trackedentityinstance", column="Tracked entity"),
            GridHeader(name="ou", column="Organisation unit"),
        ],
        rows=[["teUID1", "ouX"]],
        metaData={},
        width=2,
        height=1,
    ).model_dump(exclude_none=True, mode="json")


@respx.mock
async def test_query_outlier_detection_forwards_all_params(profile: Profile) -> None:
    """Query outlier detection forwards all params."""
    _mock_preamble()
    route = respx.get("https://dhis2.example/api/analytics/outlierDetection").mock(
        return_value=httpx.Response(200, json=_outlier_body()),
    )
    response = await service.query_outlier_detection(
        profile,
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
    assert response.height == 1
    assert response.rows is not None
    assert len(response.rows) == 1
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
async def test_query_outlier_detection_omits_unset_params(profile: Profile) -> None:
    """Passing only the required bits leaves the rest off the URL (DHIS2 defaults kick in)."""
    _mock_preamble()
    route = respx.get("https://dhis2.example/api/analytics/outlierDetection").mock(
        return_value=httpx.Response(200, json=_outlier_body()),
    )
    await service.query_outlier_detection(
        profile,
        data_elements=["DEa"],
        org_units=["ouX"],
        periods="2024Q1",
    )
    params = route.calls.last.request.url.params
    assert "algorithm" not in params
    assert "threshold" not in params
    assert "maxResults" not in params


@respx.mock
async def test_query_tracked_entities_hits_tet_path(profile: Profile) -> None:
    """Query tracked entities hits tet path."""
    _mock_preamble()
    route = respx.get("https://dhis2.example/api/analytics/trackedEntities/query/tetUID").mock(
        return_value=httpx.Response(200, json=_tracked_entities_body())
    )
    await service.query_tracked_entities(
        profile,
        tracked_entity_type="tetUID",
        dimensions=["ou:NORNorway01"],
        filters=["A:eq:foo"],
        program=["progA", "progB"],
        ou_mode="DESCENDANTS",
        page_size=10,
        asc=["created"],
    )
    assert route.called
    params = route.calls.last.request.url.params
    assert params.get_list("dimension") == ["ou:NORNorway01"]
    assert params.get_list("filter") == ["A:eq:foo"]
    assert params.get_list("program") == ["progA", "progB"]
    assert params["ouMode"] == "DESCENDANTS"
    assert params["pageSize"] == "10"
    assert params.get_list("asc") == ["created"]


@respx.mock
async def test_query_tracked_entities_skip_flags_only_set_when_true(profile: Profile) -> None:
    """`skip_meta=False` should leave `skipMeta` off the URL entirely."""
    _mock_preamble()
    route = respx.get("https://dhis2.example/api/analytics/trackedEntities/query/tetUID").mock(
        return_value=httpx.Response(200, json=_tracked_entities_body())
    )
    await service.query_tracked_entities(profile, tracked_entity_type="tetUID", skip_meta=False, skip_data=False)
    params = route.calls.last.request.url.params
    assert "skipMeta" not in params
    assert "skipData" not in params


@respx.mock
def test_cli_outlier_detection_forwards_flags() -> None:
    """`d2w analytics outlier-detection` routes every flag to the service signature."""
    _mock_preamble()
    route = respx.get("https://dhis2.example/api/analytics/outlierDetection").mock(
        return_value=httpx.Response(200, json=_outlier_body()),
    )
    result = CliRunner().invoke(
        build_app(),
        [
            "analytics",
            "outlier-detection",
            "--data-set",
            "DS1",
            "--org-unit",
            "ouX",
            "--period",
            "LAST_12_MONTHS",
            "--algorithm",
            "MODIFIED_Z_SCORE",
            "--threshold",
            "2.0",
        ],
    )
    assert result.exit_code == 0, result.output
    params = route.calls.last.request.url.params
    assert params["algorithm"] == "MODIFIED_Z_SCORE"
    assert params["threshold"] == "2.0"


@respx.mock
def test_cli_tracked_entities_query_routes_positional_tet() -> None:
    """`d2w analytics tracked-entities query TET_UID` uses TET_UID as the URL path segment."""
    _mock_preamble()
    route = respx.get("https://dhis2.example/api/analytics/trackedEntities/query/FsgEX4d3Fc5").mock(
        return_value=httpx.Response(200, json=_tracked_entities_body())
    )
    result = CliRunner().invoke(
        build_app(),
        [
            "analytics",
            "tracked-entities",
            "query",
            "FsgEX4d3Fc5",
            "--dimension",
            "ou:NOROsloProv",
            "--page-size",
            "5",
        ],
    )
    assert result.exit_code == 0, result.output
    assert route.called
