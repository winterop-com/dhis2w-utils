"""Tests for `Dhis2Client.validation` + `.predictors` — workflow accessors."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


# ---- validation.run_analysis ------------------------------------------------


@respx.mock
async def test_run_analysis_posts_params_and_parses_violations(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Full happy path: request body + JSON envelope + typed `ValidationAnalysisResult` parse."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/dataAnalysis/validationRules").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "validationRuleId": "vrAAA000001",
                        "validationRuleDescription": "ANC 1st >= ANC 4th",
                        "organisationUnitId": "ouAAA000001",
                        "organisationUnitDisplayName": "Oslo",
                        "organisationUnitPath": "/root/ouAAA000001",
                        "organisationUnitAncestorNames": "Norway / ",
                        "periodId": "202501",
                        "periodDisplayName": "January 2025",
                        "attributeOptionComboId": "HllvX50cXC0",
                        "attributeOptionComboDisplayName": "default",
                        "importance": "HIGH",
                        "leftSideValue": 10.0,
                        "operator": ">=",
                        "rightSideValue": 500.0,
                    }
                ]
            },
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        violations = await client.validation.run_analysis(
            org_unit="ouAAA000001",
            start_date="2025-01-01",
            end_date="2025-12-31",
            validation_rule_group="vrgAAA00001",
            notification=True,
            persist=True,
        )
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    assert body == {
        "ou": "ouAAA000001",
        "startDate": "2025-01-01",
        "endDate": "2025-12-31",
        "notification": True,
        "persist": True,
        "vrg": "vrgAAA00001",
    }
    assert len(violations) == 1
    hit = violations[0]
    assert hit.validationRuleId == "vrAAA000001"
    assert hit.organisationUnitDisplayName == "Oslo"
    assert hit.periodId == "202501"
    assert hit.leftSideValue == 10.0
    assert hit.rightSideValue == 500.0
    assert hit.operator == ">="
    assert hit.importance is not None and hit.importance.value == "HIGH"


@respx.mock
async def test_run_analysis_omits_optional_params(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Defaults don't emit `vrg` / `maxResults` keys."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/dataAnalysis/validationRules").mock(
        return_value=httpx.Response(200, json={"data": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.validation.run_analysis(
            org_unit="root",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    assert "vrg" not in body
    assert "maxResults" not in body
    assert body["notification"] is False
    assert body["persist"] is False


# ---- validation.list_results + get_result + delete_results --------------------


@respx.mock
async def test_list_results_forwards_filters(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Each filter lands as its DHIS2 short-key (`ou` / `pe` / `vr` / `createdDate`)."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/validationResults").mock(
        return_value=httpx.Response(200, json={"validationResults": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.validation.list_results(
            org_unit="ouAAA000001",
            period="202501",
            validation_rule="vrAAA000001",
            created_date="2026-04-20",
            page=2,
            page_size=10,
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["ou"] == "ouAAA000001"
    assert params["pe"] == "202501"
    assert params["vr"] == "vrAAA000001"
    assert params["createdDate"] == "2026-04-20"
    assert params["page"] == "2"
    assert params["pageSize"] == "10"
    # Default `fields` selector pulls nested displayName + importance + operator
    # so the persisted shape renders without a second lookup (BUGS.md #19).
    assert "validationRule[id,displayName,importance,operator]" in params["fields"]
    assert "organisationUnit[id,displayName]" in params["fields"]
    assert "period[id,displayName]" in params["fields"]


@respx.mock
async def test_get_result_parses_typed_model(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Single-result GET returns a typed `ValidationResult`."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/validationResults/42").mock(
        return_value=httpx.Response(
            200,
            json={"id": 42, "leftsideValue": 10.0, "rightsideValue": 5.0},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.validation.get_result(42)
    finally:
        await client.close()

    assert result.id == 42


async def test_delete_results_rejects_empty_filters() -> None:
    """An empty-filter delete would wipe the whole table — fail loud."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    with pytest.raises(ValueError, match="at least one of"):
        await client.validation.delete_results()


@respx.mock
async def test_delete_results_forwards_list_filters(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`org_units` / `periods` / `validation_rules` map to repeated query params."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/validationResults").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.validation.delete_results(
            org_units=["ouA", "ouB"],
            periods=["202501"],
            validation_rules=["vr1"],
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params.get_list("ou") == ["ouA", "ouB"]
    assert params.get_list("pe") == ["202501"]
    assert params.get_list("vr") == ["vr1"]


# ---- validation.describe_expression ----------------------------------------


@respx.mock
async def test_describe_expression_generic_uses_get(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`context=generic` uses GET /api/expressions/description?expression=…"""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/expressions/description").mock(
        return_value=httpx.Response(
            200,
            json={"httpStatus": "OK", "status": "OK", "message": "Valid", "description": "ANC 1st visit"},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        description = await client.validation.describe_expression("#{DEancVisit1}")
    finally:
        await client.close()

    assert route.calls.last.request.url.params["expression"] == "#{DEancVisit1}"
    assert description.valid is True
    assert description.description == "ANC 1st visit"


@respx.mock
async def test_describe_expression_validation_rule_uses_post_with_text_body(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`context=validation-rule` POSTs to the per-context path with text/plain."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/validationRules/expression/description").mock(
        return_value=httpx.Response(200, json={"status": "ERROR", "message": "Data element not found"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        description = await client.validation.describe_expression(
            "#{deMissing}",
            context="validation-rule",
        )
    finally:
        await client.close()

    assert route.calls.last.request.content == b"#{deMissing}"
    assert route.calls.last.request.headers["content-type"] == "text/plain"
    assert description.valid is False


# ---- predictors -------------------------------------------------------------


@respx.mock
async def test_predictors_run_all_forwards_date_params(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`run_all` POSTs /api/predictors/run with startDate + endDate query params."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/predictors/run").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "httpStatus": "OK",
                "httpStatusCode": 200,
                "response": {"importCount": {"imported": 3, "updated": 0, "ignored": 0, "deleted": 0}},
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        envelope = await client.predictors.run_all(start_date="2025-01-01", end_date="2025-12-31")
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["startDate"] == "2025-01-01"
    assert params["endDate"] == "2025-12-31"
    count = envelope.import_count()
    assert count is not None
    assert count.imported == 3


@respx.mock
async def test_predictors_run_one_uses_uid_path(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`run_one(uid)` uses /api/predictors/{uid}/run."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/predictors/predUid0001/run").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.predictors.run_one("predUid0001", start_date="2025-01-01", end_date="2025-12-31")
    finally:
        await client.close()

    assert route.call_count == 1


@respx.mock
async def test_predictors_run_group_uses_group_path(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`run_group(group_uid)` uses /api/predictorGroups/{uid}/run."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/predictorGroups/pgrpUid00001/run").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.predictors.run_group("pgrpUid00001", start_date="2025-01-01", end_date="2025-12-31")
    finally:
        await client.close()

    assert route.call_count == 1
