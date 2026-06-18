"""Per-version parity for the `maintenance` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/maintenance/test_maintenance_plugin.py` routes + assertions, but resolves the
service per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted, not
just smoke-imported. The three service trees are byte-identical copies (only the import version differs), so
the assertions are the same on every tree. Mocked (respx); no live stack.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_list_task_types_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_task_types` surfaces sorted job-type keys from /api/system/tasks, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    respx.get(f"{_HOST}/api/system/tasks").mock(
        return_value=httpx.Response(200, json={"ANALYTICS_TABLE": {}, "HOUSEKEEPING": {}, "DATA_INTEGRITY": {}}),
    )

    types = await service.list_task_types(resolve_profile("probe"))

    assert types == ["ANALYTICS_TABLE", "DATA_INTEGRITY", "HOUSEKEEPING"]


@respx.mock
async def test_list_task_ids_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_task_ids` surfaces sorted task UIDs for a job type, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    respx.get(f"{_HOST}/api/system/tasks/ANALYTICS_TABLE").mock(
        return_value=httpx.Response(200, json={"ccc11111aaa": [], "aaa11111bbb": [], "bbb11111ccc": []}),
    )

    ids = await service.list_task_ids(resolve_profile("probe"), "ANALYTICS_TABLE")

    assert ids == ["aaa11111bbb", "bbb11111ccc", "ccc11111aaa"]


@respx.mock
async def test_get_task_notifications_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_task_notifications` reverses DHIS2's newest-first feed to chronological, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    respx.get(f"{_HOST}/api/system/tasks/ANALYTICS_TABLE/abc").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"message": "completed", "completed": True, "time": "2026-04-19T08:00:10", "uid": "n2"},
                {"message": "started", "completed": False, "time": "2026-04-19T08:00:01", "uid": "n1"},
            ],
        ),
    )

    notifications = await service.get_task_notifications(resolve_profile("probe"), "ANALYTICS_TABLE", "abc")

    assert [n.message for n in notifications] == ["started", "completed"]
    assert notifications[-1].completed


@respx.mock
async def test_watch_task_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`watch_task` yields notifications until a `completed=true` row, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    respx.get(f"{_HOST}/api/system/tasks/ANALYTICS_TABLE/abc").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"message": "done", "completed": True, "time": "2026-04-19T08:00:10", "uid": "final"},
                {"message": "started", "completed": False, "time": "2026-04-19T08:00:01", "uid": "begin"},
            ],
        ),
    )

    messages = [
        notification.message
        async for notification in service.watch_task(
            resolve_profile("probe"), "ANALYTICS_TABLE", "abc", interval=0.01, timeout=5.0
        )
    ]

    assert messages == ["started", "done"]


@respx.mock
async def test_clear_cache_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`clear_cache` POSTs to /api/maintenance/cache, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.post(f"{_HOST}/api/maintenance/cache").mock(return_value=httpx.Response(204, content=b""))

    await service.clear_cache(resolve_profile("probe"))

    assert route.called


@respx.mock
async def test_remove_soft_deleted_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`remove_soft_deleted` POSTs to the target's purge endpoint, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.post(f"{_HOST}/api/maintenance/softDeletedDataValueRemoval").mock(
        return_value=httpx.Response(204, content=b""),
    )

    await service.remove_soft_deleted(resolve_profile("probe"), service.SoftDeleteTarget.DATA_VALUES)

    assert route.called


@respx.mock
async def test_list_dataintegrity_checks_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_dataintegrity_checks` parses /api/dataIntegrity into typed checks, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    respx.get(f"{_HOST}/api/dataIntegrity").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "check_a", "severity": "WARNING", "section": "Org units"},
                {"name": "check_b", "severity": "SEVERE"},
            ],
        ),
    )

    checks = await service.list_dataintegrity_checks(resolve_profile("probe"))

    assert [c.name for c in checks] == ["check_a", "check_b"]
    assert checks[0].severity == "WARNING"


@respx.mock
async def test_run_dataintegrity_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`run_dataintegrity` POSTs the summary endpoint with the checks param, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.post(f"{_HOST}/api/dataIntegrity").mock(
        return_value=httpx.Response(
            200,
            json={
                "httpStatus": "OK",
                "status": "OK",
                "response": {"id": "taskUid0001", "jobType": "DATA_INTEGRITY"},
            },
        ),
    )

    envelope = await service.run_dataintegrity(resolve_profile("probe"), checks=["check_a"])

    assert route.calls.last.request.url.params.get_list("checks") == ["check_a"]
    assert envelope.response is not None
    assert envelope.response.get("id") == "taskUid0001"


@respx.mock
async def test_get_dataintegrity_summary_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_dataintegrity_summary` parses the per-check `count` report, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    respx.get(f"{_HOST}/api/dataIntegrity/summary").mock(
        return_value=httpx.Response(
            200,
            json={
                "check_a": {"name": "check_a", "severity": "WARNING", "count": 3},
                "check_b": {"name": "check_b", "severity": "SEVERE", "count": 0},
            },
        ),
    )

    report = await service.get_dataintegrity_summary(resolve_profile("probe"))

    assert sorted(report.results.keys()) == ["check_a", "check_b"]
    assert report.results["check_a"].count == 3


@respx.mock
async def test_get_dataintegrity_details_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_dataintegrity_details` parses the per-check `issues[]` report, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    respx.get(f"{_HOST}/api/dataIntegrity/details").mock(
        return_value=httpx.Response(
            200,
            json={
                "check_a": {"name": "check_a", "severity": "WARNING", "issues": [{"id": "ou1", "name": "Bad OU"}]},
            },
        ),
    )

    report = await service.get_dataintegrity_details(resolve_profile("probe"))

    assert list(report.results.keys()) == ["check_a"]


@respx.mock
async def test_refresh_analytics_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`refresh_analytics` POSTs /api/resourceTables/analytics with the tuning params, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.post(f"{_HOST}/api/resourceTables/analytics").mock(
        return_value=httpx.Response(
            200,
            json={"status": "OK", "response": {"id": "analyticsTask1", "jobType": "ANALYTICS_TABLE"}},
        ),
    )

    envelope = await service.refresh_analytics(resolve_profile("probe"), skip_resource_tables=True, last_years=2)

    params = route.calls.last.request.url.params
    assert params["skipResourceTables"] == "true"
    assert params["lastYears"] == "2"
    assert envelope.response is not None


@respx.mock
async def test_refresh_resource_tables_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`refresh_resource_tables` POSTs /api/resourceTables, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.post(f"{_HOST}/api/resourceTables").mock(
        return_value=httpx.Response(
            200,
            json={"status": "OK", "response": {"id": "resourceTask1", "jobType": "RESOURCE_TABLE"}},
        ),
    )

    envelope = await service.refresh_resource_tables(resolve_profile("probe"))

    assert route.called
    assert envelope.response is not None


@respx.mock
async def test_refresh_monitoring_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`refresh_monitoring` POSTs /api/resourceTables/monitoring, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.post(f"{_HOST}/api/resourceTables/monitoring").mock(
        return_value=httpx.Response(
            200,
            json={"status": "OK", "response": {"id": "monitoringTask1", "jobType": "MONITORING"}},
        ),
    )

    envelope = await service.refresh_monitoring(resolve_profile("probe"))

    assert route.called
    assert envelope.response is not None


@respx.mock
async def test_run_validation_analysis_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`run_validation_analysis` POSTs /api/dataAnalysis/validationRules + returns violations, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.post(f"{_HOST}/api/dataAnalysis/validationRules").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"validationRuleId": "vr01234567X", "organisationUnitId": "ou001234567", "leftSideValue": 5.0},
            ],
        ),
    )

    results = await service.run_validation_analysis(
        resolve_profile("probe"), org_unit="ou001234567", start_date="2026-01-01", end_date="2026-03-31"
    )

    assert [r.validationRuleId for r in results] == ["vr01234567X"]
    assert route.called


@respx.mock
async def test_list_validation_results_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_validation_results` unwraps the `{validationResults: [...]}` envelope, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.get(f"{_HOST}/api/validationResults").mock(
        return_value=httpx.Response(200, json={"validationResults": [{"id": 1}, {"id": 2}]}),
    )

    results = await service.list_validation_results(resolve_profile("probe"), org_unit="ou001234567")

    assert [r.id for r in results] == [1, 2]
    assert route.calls.last.request.url.params["ou"] == "ou001234567"


@respx.mock
async def test_get_validation_result_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_validation_result` fetches one persisted result by id, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.get(f"{_HOST}/api/validationResults/42").mock(return_value=httpx.Response(200, json={"id": 42}))

    result = await service.get_validation_result(resolve_profile("probe"), 42)

    assert result.id == 42
    assert route.called


@respx.mock
async def test_delete_validation_results_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_validation_results` DELETEs /api/validationResults with the filters, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.delete(f"{_HOST}/api/validationResults").mock(return_value=httpx.Response(200, json={}))

    await service.delete_validation_results(resolve_profile("probe"), org_units=["ou001234567"])

    assert route.calls.last.request.url.params["ou"] == "ou001234567"


@respx.mock
async def test_send_validation_notifications_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`send_validation_notifications` POSTs /api/validation/sendNotifications, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.post(f"{_HOST}/api/validation/sendNotifications").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.send_validation_notifications(resolve_profile("probe"))

    assert response.status == "OK"
    assert route.called


@respx.mock
async def test_describe_expression_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`describe_expression` GETs /api/expressions/description for the generic context, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.get(f"{_HOST}/api/expressions/description").mock(
        return_value=httpx.Response(200, json={"status": "OK", "message": "Valid", "description": "ANC 1st visit"}),
    )

    description = await service.describe_expression(resolve_profile("probe"), "#{de.coc}")

    assert description.valid
    assert route.calls.last.request.url.params["expression"] == "#{de.coc}"


@respx.mock
async def test_run_predictors_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`run_predictors` POSTs /api/predictors/run with the date range when no UID is given, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("maintenance")
    route = respx.post(f"{_HOST}/api/predictors/run").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    response = await service.run_predictors(resolve_profile("probe"), start_date="2026-01-01", end_date="2026-03-31")

    assert response.status == "OK"
    params = route.calls.last.request.url.params
    assert params["startDate"] == "2026-01-01"
    assert params["endDate"] == "2026-03-31"
