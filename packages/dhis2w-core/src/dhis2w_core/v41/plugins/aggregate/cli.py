"""Typer sub-app for aggregate data values (mounted under `d2w data aggregate`)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

import typer

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v41.cli_output import is_json_output, render_webmessage

app = typer.Typer(
    help="Aggregate data values — DHIS2 /api/dataValueSets and /api/dataValues.",
    no_args_is_help=True,
)


@app.command("get")
def get_command(
    data_set: Annotated[str | None, typer.Option("--data-set", "--ds", help="DataSet UID.")] = None,
    period: Annotated[
        str | None,
        typer.Option(
            "--period",
            "--pe",
            help="Period; match the dataSet's periodType (Monthly=202401, Yearly=2024, Weekly=2024W12).",
        ),
    ] = None,
    start_date: Annotated[str | None, typer.Option("--start-date", help="ISO date (YYYY-MM-DD).")] = None,
    end_date: Annotated[str | None, typer.Option("--end-date", help="ISO date (YYYY-MM-DD).")] = None,
    org_unit: Annotated[str | None, typer.Option("--org-unit", "--ou", help="OrganisationUnit UID.")] = None,
    org_unit_group: Annotated[
        str | None,
        typer.Option("--org-unit-group", "--oug", help="OrganisationUnitGroup UID (alternative to --ou)."),
    ] = None,
    children: Annotated[
        bool,
        typer.Option(
            "--children",
            help="Include descendant org units (values usually live at facility level).",
        ),
    ] = False,
    data_element_group: Annotated[
        str | None,
        typer.Option("--data-element-group", "--deg", help="DataElementGroup UID (narrows to its member DEs)."),
    ] = None,
    include_deleted: Annotated[
        bool, typer.Option("--include-deleted", help="Also return soft-deleted values.")
    ] = False,
    last_updated: Annotated[
        str | None,
        typer.Option("--last-updated", help="Only values modified since a date (YYYY-MM-DD) or duration (e.g. 7d)."),
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Max rows to include in output.")] = None,
) -> None:
    """Fetch a data value set. Needs --ds plus a period (--pe or --start-date/--end-date) and --ou.

    Example: data aggregate get --ds <dataSetUID> --pe 202401 --ou <ouUID> --children
    """
    from dhis2w_core.v41.plugins.aggregate import service

    envelope = asyncio.run(
        service.get_data_values(
            profile_from_env(),
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
    )
    if is_json_output():
        typer.echo(envelope.model_dump_json(indent=2, exclude_none=True))
        return
    from dhis2w_core.v41.cli_output import ColumnSpec, render_list

    rows = envelope.dataValues or []
    render_list(
        "data values",
        [r.model_dump(exclude_none=True, mode="json") for r in rows],
        [
            ColumnSpec("dataElement", "dataElement", style="cyan", no_wrap=True),
            ColumnSpec("period", "period", no_wrap=True),
            ColumnSpec("orgUnit", "orgUnit"),
            ColumnSpec("value", "value"),
            ColumnSpec("storedBy", "storedBy", style="dim"),
        ],
    )


@app.command("push")
def push_command(
    file: Annotated[Path, typer.Argument(help="Path to a JSON file containing a dataValues array or envelope.")],
    data_set: Annotated[str | None, typer.Option("--data-set", "--ds")] = None,
    period: Annotated[str | None, typer.Option("--period", "--pe")] = None,
    org_unit: Annotated[str | None, typer.Option("--org-unit", "--ou")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    import_strategy: Annotated[
        str | None, typer.Option("--strategy", help="CREATE | UPDATE | CREATE_AND_UPDATE | DELETE")
    ] = None,
) -> None:
    """Bulk push data values from a JSON file."""
    from dhis2w_core.v41.plugins.aggregate import service

    loaded: Any = json.loads(file.read_text(encoding="utf-8"))
    if isinstance(loaded, list):
        data_values = loaded
    elif isinstance(loaded, dict) and isinstance(loaded.get("dataValues"), list):
        data_values = loaded["dataValues"]
        data_set = data_set or loaded.get("dataSet")
        period = period or loaded.get("period")
        org_unit = org_unit or loaded.get("orgUnit")
    else:
        raise typer.BadParameter("file must contain a dataValues array or an envelope with dataValues[]")

    response = asyncio.run(
        service.push_data_values(
            profile_from_env(),
            data_values,
            data_set=data_set,
            period=period,
            org_unit=org_unit,
            dry_run=dry_run,
            import_strategy=import_strategy,
        )
    )
    render_webmessage(response, action="pushed")


@app.command("set")
def set_command(
    data_element: Annotated[
        str, typer.Option("--data-element", "--de", prompt="DataElement UID", help="DataElement UID.")
    ],
    period: Annotated[str, typer.Option("--period", "--pe", prompt="Period", help="Period (e.g. 202401).")],
    org_unit: Annotated[
        str, typer.Option("--org-unit", "--ou", prompt="OrganisationUnit UID", help="OrganisationUnit UID.")
    ],
    value: Annotated[str, typer.Option("--value", prompt="Value", help="The value to set (as a string).")],
    category_option_combo: Annotated[str | None, typer.Option("--coc", help="CategoryOptionCombo UID.")] = None,
    attribute_option_combo: Annotated[
        str | None, typer.Option("--aoc", help="AttributeOptionCombo UID (category-combo attributes).")
    ] = None,
    comment: Annotated[str | None, typer.Option("--comment")] = None,
) -> None:
    """Set a single data value."""
    from dhis2w_core.v41.plugins.aggregate import service

    response = asyncio.run(
        service.set_data_value(
            profile_from_env(),
            data_element=data_element,
            period=period,
            org_unit=org_unit,
            value=value,
            category_option_combo=category_option_combo,
            attribute_option_combo=attribute_option_combo,
            comment=comment,
        )
    )
    if is_json_output():
        typer.echo(response.model_dump_json(indent=2, exclude_none=True))
    else:
        typer.echo(f"set  {data_element}  {period}  {org_unit}  value={value}")


@app.command("delete")
def delete_command(
    data_element: Annotated[str, typer.Option("--data-element", "--de", prompt="DataElement UID")],
    period: Annotated[str, typer.Option("--period", "--pe", prompt="Period")],
    org_unit: Annotated[str, typer.Option("--org-unit", "--ou", prompt="OrganisationUnit UID")],
    category_option_combo: Annotated[str | None, typer.Option("--coc")] = None,
    attribute_option_combo: Annotated[str | None, typer.Option("--aoc")] = None,
) -> None:
    """Delete a single data value."""
    from dhis2w_core.v41.plugins.aggregate import service

    response = asyncio.run(
        service.delete_data_value(
            profile_from_env(),
            data_element=data_element,
            period=period,
            org_unit=org_unit,
            category_option_combo=category_option_combo,
            attribute_option_combo=attribute_option_combo,
        )
    )
    if is_json_output():
        typer.echo(response.model_dump_json(indent=2, exclude_none=True))
    else:
        typer.echo(f"deleted  {data_element}  {period}  {org_unit}")
