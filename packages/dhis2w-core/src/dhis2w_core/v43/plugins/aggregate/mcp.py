"""FastMCP tools for aggregate data values — registered under `data_aggregate_*`."""

from __future__ import annotations

from typing import Any

from dhis2w_client.v43 import DataValue, DataValueSet, WebMessageResponse

from dhis2w_core.profile import resolve_profile
from dhis2w_core.v43.plugins.aggregate import service
from dhis2w_core.v43.plugins.aggregate.models import FollowUpResult


def register(mcp: Any) -> None:
    """Register aggregate data-value tools on the MCP server."""

    @mcp.tool()
    async def data_aggregate_get(
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
        limit: int = 100,
        profile: str | None = None,
    ) -> DataValueSet:
        """Fetch a DHIS2 aggregate data value set.

        Use either `period` for a single period (e.g. `202401`, `2024W12`, `2024`)
        or `start_date`+`end_date` (ISO YYYY-MM-DD). `org_unit` is the UID of
        the org-unit (or `org_unit_group`); set `children=True` to include
        descendants. `include_deleted` also returns soft-deleted values;
        `last_updated` keeps only values modified since a date (YYYY-MM-DD) or
        duration (e.g. `7d`). `limit` truncates the `dataValues` array
        client-side (default 100). `profile` selects a named profile; omit for
        the default.
        """
        return await service.get_data_values(
            resolve_profile(profile),
            data_set=data_set,
            period=period,
            start_date=start_date,
            end_date=end_date,
            org_unit=org_unit,
            org_unit_group=org_unit_group,
            children=children,
            data_element_group=data_element_group,
            include_deleted=include_deleted,
            last_updated=last_updated,
            limit=limit,
        )

    @mcp.tool()
    async def data_aggregate_push(
        data_values: list[dict[str, Any]],
        data_set: str | None = None,
        period: str | None = None,
        org_unit: str | None = None,
        dry_run: bool = False,
        import_strategy: str | None = None,
        profile: str | None = None,
    ) -> WebMessageResponse:
        """Bulk push aggregate data values via POST /api/dataValueSets.

        Each `data_values` item must include at minimum `dataElement`, `period`,
        `orgUnit`, and `value`. Optional: `categoryOptionCombo`, `attributeOptionCombo`,
        `comment`, `followup`. `import_strategy` is one of `CREATE`, `UPDATE`,
        `CREATE_AND_UPDATE`, `DELETE` (server default: `CREATE_AND_UPDATE`).
        Set `dry_run=True` to validate without writing.
        """
        return await service.push_data_values(
            resolve_profile(profile),
            [DataValue.model_validate(item) for item in data_values],
            data_set=data_set,
            period=period,
            org_unit=org_unit,
            dry_run=dry_run,
            import_strategy=import_strategy,
        )

    @mcp.tool()
    async def data_aggregate_set(
        data_element: str,
        period: str,
        org_unit: str,
        value: str,
        category_option_combo: str | None = None,
        attribute_option_combo: str | None = None,
        comment: str | None = None,
        profile: str | None = None,
    ) -> WebMessageResponse:
        """Set a single aggregate data value via POST /api/dataValues."""
        return await service.set_data_value(
            resolve_profile(profile),
            data_element=data_element,
            period=period,
            org_unit=org_unit,
            value=value,
            category_option_combo=category_option_combo,
            attribute_option_combo=attribute_option_combo,
            comment=comment,
        )

    @mcp.tool()
    async def data_aggregate_delete(
        data_element: str,
        period: str,
        org_unit: str,
        category_option_combo: str | None = None,
        attribute_option_combo: str | None = None,
        profile: str | None = None,
    ) -> WebMessageResponse:
        """Delete a single aggregate data value via DELETE /api/dataValues."""
        return await service.delete_data_value(
            resolve_profile(profile),
            data_element=data_element,
            period=period,
            org_unit=org_unit,
            category_option_combo=category_option_combo,
            attribute_option_combo=attribute_option_combo,
        )

    @mcp.tool()
    async def data_aggregate_followup(
        data_element: str,
        period: str,
        org_unit: str,
        followup: bool = True,
        category_option_combo: str | None = None,
        attribute_option_combo: str | None = None,
        profile: str | None = None,
    ) -> FollowUpResult:
        """Set or clear the follow-up flag on a single aggregate data value (PUT /api/dataValues/followup)."""
        return await service.set_data_value_followup(
            resolve_profile(profile),
            data_element=data_element,
            period=period,
            org_unit=org_unit,
            followup=followup,
            category_option_combo=category_option_combo,
            attribute_option_combo=attribute_option_combo,
        )
