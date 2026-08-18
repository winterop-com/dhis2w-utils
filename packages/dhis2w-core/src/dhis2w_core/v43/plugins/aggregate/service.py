"""Service layer for the `aggregate` plugin — DHIS2 aggregate data values.

Reads return a typed `DataValueSet` (with nested `DataValue` rows). Writes
return a typed `WebMessageResponse` envelope.
"""

from __future__ import annotations

import re
from typing import Any

from dhis2w_client.v43 import DataValue, DataValueSet, WebMessageResponse

from dhis2w_core.profile import Profile
from dhis2w_core.v43.client_context import open_client
from dhis2w_core.v43.plugins.aggregate.models import FollowUpResult

#: The DHIS2 duration shape (`7d`, `12h`, `30m`, `45s`, `4w`), which is not a date.
_DURATION_PATTERN = re.compile(r"\d+[smhdw]")


async def get_data_values(
    profile: Profile,
    *,
    data_set: str | None = None,
    period: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    org_unit: str | None = None,
    org_unit_group: str | None = None,
    children: bool = False,
    data_element_group: str | None = None,
    include_deleted: bool = False,
    last_updated: str | None = None,
    limit: int | None = None,
) -> DataValueSet:
    """Fetch a data value set via GET /api/dataValueSets.

    DHIS2 requires a coherent combination of params — typically `dataSet`,
    `period` (or `startDate`+`endDate`), and `orgUnit` (or `orgUnitGroup`).
    `include_deleted` returns soft-deleted values; `last_updated` filters to
    values modified since a date/duration (e.g. `2024-01-01` or `7d`) - DHIS2
    takes the two spellings on two different parameters, so a duration goes to
    `lastUpdatedDuration` and anything else to `lastUpdated`; `limit`
    truncates the `dataValues` list client-side after the response is parsed.
    """
    params: dict[str, Any] = {}
    if data_set is not None:
        params["dataSet"] = data_set
    if period is not None:
        params["period"] = period
    if start_date is not None:
        params["startDate"] = start_date
    if end_date is not None:
        params["endDate"] = end_date
    if org_unit is not None:
        params["orgUnit"] = org_unit
    if org_unit_group is not None:
        params["orgUnitGroup"] = org_unit_group
    if children:
        params["children"] = "true"
    if data_element_group is not None:
        params["dataElementGroup"] = data_element_group
    if include_deleted:
        params["includeDeleted"] = "true"
    if last_updated is not None:
        params[_last_updated_parameter(last_updated)] = last_updated

    async with open_client(profile) as client:
        raw = await client.get_raw("/api/dataValueSets", params=params)
    envelope = DataValueSet.model_validate(raw)
    if limit is not None:
        envelope.dataValues = (envelope.dataValues or [])[:limit]
    return envelope


def _last_updated_parameter(value: str) -> str:
    """Which wire parameter one `last_updated` value belongs on: duration or date.

    `/api/dataValueSets` takes `lastUpdatedDuration` for the `7d` / `12h` shape and
    `lastUpdated` for a date, and refuses a duration on the date parameter with a 400 -
    so the split the CLI help promises is decided here rather than left to the caller.
    """
    return "lastUpdatedDuration" if _DURATION_PATTERN.fullmatch(value) else "lastUpdated"


async def push_data_values(
    profile: Profile,
    data_values: list[DataValue],
    *,
    data_set: str | None = None,
    period: str | None = None,
    org_unit: str | None = None,
    dry_run: bool = False,
    preheat_cache: bool = True,
    import_strategy: str | None = None,
) -> WebMessageResponse:
    """Bulk push typed `DataValue` rows via POST /api/dataValueSets.

    `import_strategy` can be CREATE, UPDATE, CREATE_AND_UPDATE, DELETE (DHIS2 defaults
    to CREATE_AND_UPDATE). `dry_run=True` validates without writing. Use
    `response.import_count()` to get the typed ImportCount counters.
    """
    body: dict[str, Any] = {
        "dataValues": [row.model_dump(by_alias=True, exclude_none=True, mode="json") for row in data_values]
    }
    if data_set is not None:
        body["dataSet"] = data_set
    if period is not None:
        body["period"] = period
    if org_unit is not None:
        body["orgUnit"] = org_unit

    params: dict[str, Any] = {}
    if dry_run:
        params["dryRun"] = "true"
    if not preheat_cache:
        params["preheatCache"] = "false"
    if import_strategy is not None:
        params["importStrategy"] = import_strategy

    async with open_client(profile) as client:
        return await client.post("/api/dataValueSets", body, params=params, model=WebMessageResponse)


def _apply_attribute_option_combo(
    params: dict[str, Any],
    attribute_combo: str | None,
    attribute_options: list[str] | None,
) -> None:
    """Add the `cc` + `cp` attribute-option-combo params, or neither.

    DHIS2's /api/dataValues resolves an attribute option combo from the
    attribute CategoryCombo UID (`cc`) plus its category-option UIDs (`cp`,
    `;`-joined) — there is no attributeOptionCombo param. The two must be
    supplied together; one without the other is a caller error (BUGS.md #50).
    """
    has_combo = attribute_combo is not None
    has_options = bool(attribute_options)
    if has_combo != has_options:
        raise ValueError(
            "attribute_combo (cc) and attribute_options (cp) must be provided together — DHIS2's "
            "/api/dataValues resolves an attribute option combo from the category-combo UID plus its "
            "category-option UIDs, and rejects one without the other",
        )
    if attribute_combo is not None and attribute_options:
        params["cc"] = attribute_combo
        params["cp"] = ";".join(attribute_options)


async def set_data_value(
    profile: Profile,
    *,
    data_element: str,
    period: str,
    org_unit: str,
    value: str,
    category_option_combo: str | None = None,
    attribute_combo: str | None = None,
    attribute_options: list[str] | None = None,
    comment: str | None = None,
) -> WebMessageResponse:
    """Set a single data value via POST /api/dataValues (params-based).

    DHIS2's /api/dataValues has no attributeOptionCombo query param: an
    attribute option combo is addressed by `cc` (the attribute CategoryCombo
    UID) plus `cp` (its category-option UIDs). Pass `attribute_combo` and
    `attribute_options` together — the server resolves them into the option
    combo (BUGS.md #50).
    """
    params: dict[str, Any] = {
        "de": data_element,
        "pe": period,
        "ou": org_unit,
        "value": value,
    }
    if category_option_combo is not None:
        params["co"] = category_option_combo
    _apply_attribute_option_combo(params, attribute_combo, attribute_options)
    if comment is not None:
        params["comment"] = comment

    async with open_client(profile) as client:
        return await client.post("/api/dataValues", body=None, params=params, model=WebMessageResponse)


async def delete_data_value(
    profile: Profile,
    *,
    data_element: str,
    period: str,
    org_unit: str,
    category_option_combo: str | None = None,
    attribute_combo: str | None = None,
    attribute_options: list[str] | None = None,
) -> WebMessageResponse:
    """Delete a single data value via DELETE /api/dataValues.

    Attribute option combos are addressed by `cc` (attribute CategoryCombo
    UID) plus `cp` (its category-option UIDs), never a bare
    attributeOptionCombo param (BUGS.md #50).
    """
    params: dict[str, Any] = {"de": data_element, "pe": period, "ou": org_unit}
    if category_option_combo is not None:
        params["co"] = category_option_combo
    _apply_attribute_option_combo(params, attribute_combo, attribute_options)

    async with open_client(profile) as client:
        return await client.delete("/api/dataValues", params=params, model=WebMessageResponse)


async def set_data_value_followup(
    profile: Profile,
    *,
    data_element: str,
    period: str,
    org_unit: str,
    followup: bool,
    category_option_combo: str | None = None,
    attribute_option_combo: str | None = None,
) -> FollowUpResult:
    """Set or clear the follow-up flag on a single data value via PUT /api/dataValues/followup.

    DHIS2 returns an empty 200; a non-2xx raises. Returns a small typed summary. The body is built
    as a dict at the HTTP boundary rather than via the generated `DataValueFollowUpRequest`, whose
    v43 schema types `period` as an object the live wire doesn't require (BUGS.md #49).
    """
    body: dict[str, Any] = {
        "dataElement": data_element,
        "period": period,
        "orgUnit": org_unit,
        "followup": followup,
    }
    if category_option_combo is not None:
        body["categoryOptionCombo"] = category_option_combo
    if attribute_option_combo is not None:
        body["attributeOptionCombo"] = attribute_option_combo
    async with open_client(profile) as client:
        await client.put_raw("/api/dataValues/followup", body)
    return FollowUpResult(count=1, followup=followup)
