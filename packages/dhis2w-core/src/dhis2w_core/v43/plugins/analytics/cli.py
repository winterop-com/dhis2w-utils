"""Typer sub-app for the `analytics` plugin (mounted under `d2w analytics`)."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import typer
from dhis2w_client.v43 import DataValueSet, Grid
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import is_json_output
from dhis2w_core.v43.plugins.analytics import service

app = typer.Typer(help="DHIS2 analytics — aggregated queries over the analytics tables.", no_args_is_help=True)
_console = Console()


def _render(response: BaseModel, *, title: str) -> None:
    """Pick the right output mode for an analytics response.

    Honors the global `--json` flag: dump JSON when set; otherwise render a
    Rich table from the `Grid` envelope. `DataValueSet` always falls back to
    JSON — its shape is meant for re-import, not display.
    """
    if is_json_output():
        typer.echo(response.model_dump_json(indent=2, exclude_none=True))
        return
    if isinstance(response, Grid):
        _render_grid(response, title=title)
        return
    if isinstance(response, DataValueSet):
        typer.echo(response.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(response.model_dump_json(indent=2, exclude_none=True))


def _render_grid(grid: Grid, *, title: str) -> None:
    """Render a `Grid` envelope as a Rich table — headers as columns, rows as cells."""
    headers = grid.headers or []
    rows = grid.rows or []
    if not headers or not rows:
        _console.print(f"[dim]{title}: no rows[/dim]")
        return
    table = Table(title=f"{title} ({len(rows)} rows)", title_style="bold", pad_edge=False, expand=False)
    for header in headers:
        table.add_column(header.column or header.name or "", overflow="fold")
    for row in rows:
        table.add_row(*[str(cell) if cell is not None else "-" for cell in row])
    _console.print(table)


@app.command("query")
def query_command(
    dimension: Annotated[
        list[str],
        typer.Option(
            "--dimension",
            "--dim",
            help="Repeatable 'axis:value': dx:<UID>, pe:<period> (both required), ou:<UID>.",
        ),
    ],
    shape: Annotated[
        str,
        typer.Option(
            "--shape",
            help="Response shape: `table` (default, aggregated), `raw` (/api/analytics/rawData), "
            "`dvs` (/api/analytics/dataValueSet — DataValueSet shape).",
        ),
    ] = "table",
    filter: Annotated[
        list[str] | None,
        typer.Option("--filter", help="Filter string (repeatable), same syntax as --dimension."),
    ] = None,
    aggregation_type: Annotated[
        str | None,
        typer.Option("--agg", help="SUM | AVERAGE | COUNT | MIN | MAX | AVERAGE_SUM_ORG_UNIT ..."),
    ] = None,
    output_id_scheme: Annotated[
        str | None,
        typer.Option("--output-id-scheme", help="UID | NAME | CODE | ID — how UIDs appear in the response"),
    ] = None,
    include_num_den: Annotated[
        bool, typer.Option("--num-den/--no-num-den", help="Include indicator numerator/denominator columns.")
    ] = False,
    display_property: Annotated[
        str | None, typer.Option("--display-property", help="NAME | SHORTNAME — which label to render metadata with.")
    ] = None,
    start_date: Annotated[
        str | None,
        typer.Option("--start-date", help="Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension)."),
    ] = None,
    end_date: Annotated[str | None, typer.Option("--end-date", help="Fixed window end, ISO date YYYY-MM-DD.")] = None,
    skip_meta: Annotated[bool, typer.Option("--skip-meta")] = False,
) -> None:
    """Run an aggregate analytics query (requires at least dx + pe dimensions).

    Example: analytics query --dim dx:Uvn6LCg7dVU --dim pe:LAST_12_MONTHS --dim ou:ImspTQPwCqd

    Use `--shape` to pick `table`, `raw`, or `dvs`.
    """
    try:
        response = asyncio.run(
            service.query_analytics(
                profile_from_env(),
                shape=shape,
                dimensions=dimension,
                filters=filter,
                aggregation_type=aggregation_type,
                output_id_scheme=output_id_scheme,
                include_num_den=include_num_den if include_num_den else None,
                display_property=display_property,
                start_date=start_date,
                end_date=end_date,
                skip_meta=skip_meta,
            )
        )
    except ValueError as exc:
        typer.secho(f"error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    _render(response, title=f"analytics {shape}")


events_app = typer.Typer(help="Event analytics — line-lists events or aggregates them.", no_args_is_help=True)
enrollments_app = typer.Typer(help="Enrollment analytics — line-lists enrollments.", no_args_is_help=True)
app.add_typer(events_app, name="events")
app.add_typer(enrollments_app, name="enrollments")


@events_app.command("query")
def events_query_command(
    program: Annotated[str, typer.Argument(help="Program UID.")],
    mode: Annotated[
        str,
        typer.Option("--mode", help="`query` (line-listed events) or `aggregate` (grouped counts)."),
    ] = "query",
    dimension: Annotated[
        list[str] | None,
        typer.Option(
            "--dimension",
            "--dim",
            help="Repeatable 'axis:value': pe:<period>, ou:<UID>. Aggregate value dim = <stage>.<de> (no dx:).",
        ),
    ] = None,
    filter: Annotated[
        list[str] | None,
        typer.Option("--filter", help="Filter string (repeatable), same syntax as --dimension."),
    ] = None,
    stage: Annotated[str | None, typer.Option("--stage", help="Program stage UID to narrow events.")] = None,
    output_type: Annotated[
        str | None,
        typer.Option("--output-type", help="EVENT | ENROLLMENT | TRACKED_ENTITY_INSTANCE (row shape)."),
    ] = None,
    start_date: Annotated[
        str | None,
        typer.Option("--start-date", help="Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension)."),
    ] = None,
    end_date: Annotated[str | None, typer.Option("--end-date", help="Fixed window end, ISO date YYYY-MM-DD.")] = None,
    skip_meta: Annotated[bool, typer.Option("--skip-meta")] = False,
    page: Annotated[int | None, typer.Option("--page")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size")] = None,
) -> None:
    """Run an event analytics query.

    Example: analytics events query <PROGRAM_UID> --mode query --dim pe:LAST_12_MONTHS --dim ou:<ouUID>

    PROGRAM is a program UID; --mode is query (line list) or aggregate.
    """
    try:
        response = asyncio.run(
            service.query_events(
                profile_from_env(),
                program=program,
                mode=mode,
                dimensions=dimension,
                filters=filter,
                stage=stage,
                output_type=output_type,
                start_date=start_date,
                end_date=end_date,
                skip_meta=skip_meta,
                page=page,
                page_size=page_size,
            )
        )
    except ValueError as exc:
        typer.secho(f"error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    _render(response, title=f"events {mode} {program}")


@enrollments_app.command("query")
def enrollments_query_command(
    program: Annotated[str, typer.Argument(help="Program UID.")],
    dimension: Annotated[
        list[str] | None,
        typer.Option("--dimension", "--dim", help="Dimension string (repeatable)."),
    ] = None,
    filter: Annotated[
        list[str] | None,
        typer.Option("--filter", help="Filter string (repeatable)."),
    ] = None,
    start_date: Annotated[
        str | None,
        typer.Option("--start-date", help="Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension)."),
    ] = None,
    end_date: Annotated[str | None, typer.Option("--end-date", help="Fixed window end, ISO date YYYY-MM-DD.")] = None,
    skip_meta: Annotated[bool, typer.Option("--skip-meta")] = False,
    page: Annotated[int | None, typer.Option("--page")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size")] = None,
) -> None:
    """Run an enrollment analytics query (`/api/analytics/enrollments/query/{program}`)."""
    response = asyncio.run(
        service.query_enrollments(
            profile_from_env(),
            program=program,
            dimensions=dimension,
            filters=filter,
            start_date=start_date,
            end_date=end_date,
            skip_meta=skip_meta,
            page=page,
            page_size=page_size,
        )
    )
    _render(response, title=f"enrollments {program}")


@app.command("outlier-detection")
def outlier_detection_command(
    data_element: Annotated[
        list[str] | None,
        typer.Option("--data-element", "--de", help="Data-element UID (repeatable)."),
    ] = None,
    data_set: Annotated[
        list[str] | None,
        typer.Option("--data-set", "--ds", help="Data-set UID (repeatable) — expanded to its dataElements."),
    ] = None,
    org_unit: Annotated[
        list[str] | None,
        typer.Option("--org-unit", "--ou", help="Org-unit UID (repeatable)."),
    ] = None,
    period: Annotated[
        str | None,
        typer.Option("--period", "--pe", help="Period identifier (e.g. LAST_12_MONTHS, 202401)."),
    ] = None,
    start_date: Annotated[str | None, typer.Option("--start-date", help="ISO date YYYY-MM-DD.")] = None,
    end_date: Annotated[str | None, typer.Option("--end-date", help="ISO date YYYY-MM-DD.")] = None,
    algorithm: Annotated[
        str | None,
        typer.Option(
            "--algorithm",
            help="Z_SCORE (default) | MODIFIED_Z_SCORE | MIN_MAX. "
            "(Upstream OAS still shows MOD_Z_SCORE but the server rejects that value — see BUGS.md.)",
        ),
    ] = None,
    threshold: Annotated[
        float | None,
        typer.Option("--threshold", help="Standard-deviation cutoff (default 3.0)."),
    ] = None,
    max_results: Annotated[
        int | None,
        typer.Option("--max-results", help="Cap the number of outliers returned (default 500)."),
    ] = None,
    order_by: Annotated[
        str | None,
        typer.Option("--order-by", help="ABS_DEV | STANDARD_DEVIATION | Z_SCORE | ..."),
    ] = None,
    sort_order: Annotated[
        str | None,
        typer.Option("--sort-order", help="ASC | DESC."),
    ] = None,
) -> None:
    """Run `/api/analytics/outlierDetection` — flag statistical anomalies in data values."""
    response = asyncio.run(
        service.query_outlier_detection(
            profile_from_env(),
            data_elements=data_element,
            data_sets=data_set,
            org_units=org_unit,
            periods=period,
            start_date=start_date,
            end_date=end_date,
            algorithm=algorithm,
            threshold=threshold,
            max_results=max_results,
            order_by=order_by,
            sort_order=sort_order,
        )
    )
    _render(response, title="outliers")


tracked_entities_app = typer.Typer(
    help="Tracked-entity analytics — line-list TEs for a given type.",
    no_args_is_help=True,
)
app.add_typer(tracked_entities_app, name="tracked-entities")


@tracked_entities_app.command("query")
def tracked_entities_query_command(
    tracked_entity_type: Annotated[str, typer.Argument(help="TrackedEntityType UID.")],
    dimension: Annotated[
        list[str] | None,
        typer.Option("--dimension", "--dim", help="Dimension string (repeatable)."),
    ] = None,
    filter: Annotated[  # noqa: A002 — Typer needs the positional name
        list[str] | None,
        typer.Option("--filter", help="Filter string (repeatable)."),
    ] = None,
    program: Annotated[
        list[str] | None,
        typer.Option("--program", help="Program UID (repeatable) to narrow results."),
    ] = None,
    start_date: Annotated[
        str | None,
        typer.Option("--start-date", help="Fixed window start, ISO date YYYY-MM-DD (alternative to a pe: dimension)."),
    ] = None,
    end_date: Annotated[str | None, typer.Option("--end-date", help="Fixed window end, ISO date YYYY-MM-DD.")] = None,
    ou_mode: Annotated[
        str | None,
        typer.Option(
            "--ou-mode",
            help="SELECTED|CHILDREN|DESCENDANTS|ACCESSIBLE|ALL (default SELECTED; DESCENDANTS reaches facilities).",
        ),
    ] = None,
    display_property: Annotated[
        str | None,
        typer.Option("--display-property", help="NAME | SHORTNAME."),
    ] = None,
    skip_meta: Annotated[bool, typer.Option("--skip-meta")] = False,
    skip_data: Annotated[bool, typer.Option("--skip-data")] = False,
    include_metadata_details: Annotated[
        bool,
        typer.Option("--include-metadata-details", help="Include nested objects in the metaData map."),
    ] = False,
    page: Annotated[int | None, typer.Option("--page")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size")] = None,
    asc: Annotated[
        list[str] | None,
        typer.Option("--asc", help="Field to sort ascending (repeatable)."),
    ] = None,
    desc: Annotated[
        list[str] | None,
        typer.Option("--desc", help="Field to sort descending (repeatable)."),
    ] = None,
) -> None:
    """Line-list tracked entities via `/api/analytics/trackedEntities/query/{TET_UID}`."""
    response = asyncio.run(
        service.query_tracked_entities(
            profile_from_env(),
            tracked_entity_type=tracked_entity_type,
            dimensions=dimension,
            filters=filter,
            program=program,
            start_date=start_date,
            end_date=end_date,
            ou_mode=ou_mode,
            display_property=display_property,
            skip_meta=skip_meta,
            skip_data=skip_data,
            include_metadata_details=include_metadata_details,
            page=page,
            page_size=page_size,
            asc=asc,
            desc=desc,
        )
    )
    _render(response, title=f"tracked-entities {tracked_entity_type}")


def register(root_app: Any) -> None:
    """Mount under `d2w analytics`."""
    root_app.add_typer(app, name="analytics", help="DHIS2 analytics queries.")
