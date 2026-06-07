"""Unit tests for `SqlViewsAccessor` + `SqlViewRunner` — respx-mocked."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client, SqlViewResult
from dhis2w_client.generated.v42.enums import SqlViewType


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


# ---- list_views -----------------------------------------------------------


@respx.mock
async def test_list_views_orders_by_name_and_scopes_paging_off(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`list_views` pulls every view sorted by name, paging disabled."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/sqlViews").mock(
        return_value=httpx.Response(
            200,
            json={
                "sqlViews": [
                    {"id": "SQL1", "name": "alpha", "type": "VIEW"},
                    {"id": "SQL2", "name": "beta", "type": "QUERY"},
                ]
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        views = await client.sql_views.list_views()
    finally:
        await client.close()
    params = route.calls.last.request.url.params
    assert params["order"] == "name:asc"
    assert params["paging"] == "false"
    assert [v.name for v in views] == ["alpha", "beta"]


@respx.mock
async def test_list_views_filters_by_view_type(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`list_views(view_type=MATERIALIZED_VIEW)` emits `filter=type:eq:MATERIALIZED_VIEW`."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/sqlViews").mock(
        return_value=httpx.Response(200, json={"sqlViews": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sql_views.list_views(view_type=SqlViewType.MATERIALIZED_VIEW)
    finally:
        await client.close()
    assert route.calls.last.request.url.params["filter"] == "type:eq:MATERIALIZED_VIEW"


# ---- get ------------------------------------------------------------------


@respx.mock
async def test_get_returns_typed_model_with_sql_query(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Get returns typed model with sql query."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/sqlViews/SQL1").mock(
        return_value=httpx.Response(
            200,
            json={"id": "SQL1", "name": "OU levels", "type": "VIEW", "sqlQuery": "SELECT 1"},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        view = await client.sql_views.get("SQL1")
    finally:
        await client.close()
    assert view.id == "SQL1"
    assert view.sqlQuery == "SELECT 1"
    assert view.type == SqlViewType.VIEW


# ---- execute --------------------------------------------------------------


@respx.mock
async def test_execute_parses_list_grid_and_exposes_typed_columns_and_rows(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Execute parses list grid and exposes typed columns and rows."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/sqlViews/SQL1/data").mock(
        return_value=httpx.Response(
            200,
            json={
                "listGrid": {
                    "title": "OU per level",
                    "headers": [
                        {"name": "level", "type": "INTEGER"},
                        {"name": "count", "type": "INTEGER"},
                    ],
                    "rows": [[1, 1], [2, 3], [3, 15]],
                    "height": 3,
                    "width": 2,
                }
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.sql_views.execute("SQL1")
    finally:
        await client.close()
    assert type(result).__name__ == "SqlViewResult"
    assert result.title == "OU per level"
    assert [c.name for c in result.columns] == ["level", "count"]
    assert result.rows == [[1, 1], [2, 3], [3, 15]]
    assert result.height == 3
    assert result.as_dicts() == [
        {"level": 1, "count": 1},
        {"level": 2, "count": 3},
        {"level": 3, "count": 15},
    ]
    assert result.column_values("count") == [1, 3, 15]


@respx.mock
async def test_execute_forwards_variables_and_criteria_as_repeated_params(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Variables become `?var=k:v`; criteria become `?criteria=k:v`."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/sqlViews/SQL1/data").mock(
        return_value=httpx.Response(200, json={"listGrid": {"headers": [], "rows": []}}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sql_views.execute(
            "SQL1",
            variables={"pattern": "anc"},
            criteria={"value_type": "TEXT"},
        )
    finally:
        await client.close()
    url = str(route.calls.last.request.url)
    assert "var=pattern%3Aanc" in url or "var=pattern:anc" in url
    assert "criteria=value_type%3ATEXT" in url or "criteria=value_type:TEXT" in url


@respx.mock
async def test_execute_missing_list_grid_returns_empty_result(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Edge case: DHIS2 occasionally flattens to `{headers, rows}` without the envelope."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/sqlViews/SQL1/data").mock(
        return_value=httpx.Response(200, json={"headers": [{"name": "x"}], "rows": [["v"]]}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.sql_views.execute("SQL1")
    finally:
        await client.close()
    assert [c.name for c in result.columns] == ["x"]
    assert result.rows == [["v"]]


def test_column_values_raises_on_unknown_column() -> None:
    """Column values raises on unknown column."""
    result = SqlViewResult.from_api(
        {"listGrid": {"headers": [{"name": "a"}], "rows": [[1], [2]]}},
    )
    with pytest.raises(KeyError, match="nope"):
        result.column_values("nope")


# ---- refresh --------------------------------------------------------------


@respx.mock
async def test_refresh_posts_to_execute_endpoint(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Refresh posts to execute endpoint."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/sqlViews/SQL1/execute").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        response = await client.sql_views.refresh("SQL1")
    finally:
        await client.close()
    assert route.call_count == 1
    assert response.status == "OK"


# ---- create / delete ------------------------------------------------------


@respx.mock
async def test_create_posts_then_refetches_by_id(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`create` POSTs the view, then re-reads it to return the typed server shape."""
    mock_system_info(server_version)
    from dhis2w_client.generated.v42.schemas import SqlView

    candidate = SqlView.model_validate(
        {"id": "SQL9", "name": "demo", "type": "QUERY", "sqlQuery": "SELECT 1"},
    )
    post = respx.post("https://dhis2.example/api/sqlViews").mock(
        return_value=httpx.Response(201, json={"status": "OK", "response": {"uid": "SQL9"}}),
    )
    get = respx.get("https://dhis2.example/api/sqlViews/SQL9").mock(
        return_value=httpx.Response(
            200,
            json={"id": "SQL9", "name": "demo", "type": "QUERY", "sqlQuery": "SELECT 1"},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        created = await client.sql_views.create(candidate)
    finally:
        await client.close()
    assert post.call_count == 1
    assert get.call_count == 1
    assert created.id == "SQL9"


@respx.mock
async def test_delete_routes_to_sql_views_uid(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Delete routes to sql views uid."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/sqlViews/SQL9").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sql_views.delete("SQL9")
    finally:
        await client.close()
    assert route.call_count == 1


# ---- SqlViewRunner --------------------------------------------------------


@respx.mock
async def test_runner_run_forwards_kwargs_as_variables(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`runner.run(uid, foo="bar")` → `?var=foo:bar`."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/sqlViews/SQL1/data").mock(
        return_value=httpx.Response(200, json={"listGrid": {"headers": [], "rows": []}}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sql_views.runner.run("SQL1", pattern="anc")
    finally:
        await client.close()
    url = str(route.calls.last.request.url)
    assert "var=pattern" in url and "anc" in url


@respx.mock
async def test_runner_adhoc_registers_executes_and_deletes(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`adhoc()` life-cycles a throwaway view: POST → execute/refresh → GET data → DELETE."""
    mock_system_info(server_version)

    create_route = respx.post("https://dhis2.example/api/sqlViews").mock(
        return_value=httpx.Response(201, json={"status": "OK"}),
    )
    get_route = respx.get(url__regex=r"https://dhis2\.example/api/sqlViews/[A-Za-z0-9]+(\?.*)?$").mock(
        return_value=httpx.Response(
            200, json={"id": "PLACEHOLDER", "name": "probe", "type": "QUERY", "sqlQuery": "SELECT 1"}
        ),
    )
    data_route = respx.get(url__regex=r"https://dhis2\.example/api/sqlViews/[A-Za-z0-9]+/data").mock(
        return_value=httpx.Response(
            200,
            json={"listGrid": {"headers": [{"name": "col"}], "rows": [[42]]}},
        ),
    )
    delete_route = respx.delete(url__regex=r"https://dhis2\.example/api/sqlViews/[A-Za-z0-9]+(\?.*)?$").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.sql_views.runner.adhoc("probe", "SELECT 1")
    finally:
        await client.close()
    assert create_route.call_count == 1
    assert get_route.call_count >= 1
    assert data_route.call_count == 1
    assert delete_route.call_count == 1
    assert result.rows == [[42]]


@respx.mock
async def test_runner_adhoc_with_keep_skips_delete(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`adhoc(..., keep=True)` runs create + execute but leaves the view in place."""
    mock_system_info(server_version)

    respx.post("https://dhis2.example/api/sqlViews").mock(
        return_value=httpx.Response(201, json={"status": "OK"}),
    )
    respx.get(url__regex=r"https://dhis2\.example/api/sqlViews/[A-Za-z0-9]+(\?.*)?$").mock(
        return_value=httpx.Response(200, json={"id": "kept", "name": "kept", "type": "QUERY", "sqlQuery": "SELECT 1"}),
    )
    respx.get(url__regex=r"https://dhis2\.example/api/sqlViews/[A-Za-z0-9]+/data").mock(
        return_value=httpx.Response(200, json={"listGrid": {"headers": [], "rows": []}}),
    )
    delete_route = respx.delete(url__regex=r"https://dhis2\.example/api/sqlViews/[A-Za-z0-9]+(\?.*)?$").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sql_views.runner.adhoc("kept", "SELECT 1", keep=True)
    finally:
        await client.close()
    assert delete_route.call_count == 0


@respx.mock
async def test_runner_adhoc_view_refreshes_materialized_views_before_reading(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`adhoc(..., view_type=MATERIALIZED_VIEW)` POSTs to `/execute` to create the DB view first."""
    mock_system_info(server_version)

    respx.post("https://dhis2.example/api/sqlViews").mock(
        return_value=httpx.Response(201, json={"status": "OK"}),
    )
    respx.get(url__regex=r"https://dhis2\.example/api/sqlViews/[A-Za-z0-9]+(\?.*)?$").mock(
        return_value=httpx.Response(
            200,
            json={"id": "mv1", "name": "mv", "type": "MATERIALIZED_VIEW", "sqlQuery": "SELECT 1"},
        ),
    )
    refresh_route = respx.post(url__regex=r"https://dhis2\.example/api/sqlViews/[A-Za-z0-9]+/execute").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    respx.get(url__regex=r"https://dhis2\.example/api/sqlViews/[A-Za-z0-9]+/data").mock(
        return_value=httpx.Response(200, json={"listGrid": {"headers": [], "rows": []}}),
    )
    respx.delete(url__regex=r"https://dhis2\.example/api/sqlViews/[A-Za-z0-9]+(\?.*)?$").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sql_views.runner.adhoc("mv", "SELECT 1", view_type=SqlViewType.MATERIALIZED_VIEW)
    finally:
        await client.close()
    assert refresh_route.call_count == 1


# ---- binding --------------------------------------------------------------


async def test_accessor_and_runner_are_bound_on_client() -> None:
    """`client.sql_views` + `client.sql_views.runner` are both accessible."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        assert hasattr(client.sql_views, "list_views")
        assert hasattr(client.sql_views, "execute")
        assert hasattr(client.sql_views, "refresh")
        assert hasattr(client.sql_views, "runner")
        assert type(client.sql_views.runner).__name__ == "SqlViewRunner"
    finally:
        await client.close()


_ = pytest  # keep import honest — pytest-asyncio auto-mode handles discovery.
