"""Typer sub-app for the `metadata` plugin (mounted under `dhis2 metadata`)."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from dhis2w_client.v43 import JsonPatchOpAdapter
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from dhis2w_core.plugin import resolve_startup_version
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.cli_output import is_json_output, render_conflicts, render_webmessage
from dhis2w_core.v43.plugins.metadata import service
from dhis2w_core.v43.plugins.metadata.models import MetadataBundle, MetadataCount, MetadataWriteResult
from dhis2w_core.v43.plugins.schema import service as schema_service

app = typer.Typer(help="Inspect and list DHIS2 metadata (wraps generated CRUD resources).", no_args_is_help=True)
type_app = typer.Typer(help="Metadata resource types (the catalog).", no_args_is_help=True)
app.add_typer(type_app, name="type")
options_app = typer.Typer(help="OptionSet workflows (get / find / sync).", no_args_is_help=True)
app.add_typer(options_app, name="option-sets")
options_attribute_app = typer.Typer(
    help="External-system code mapping on Options via Attribute values.",
    no_args_is_help=True,
)
options_app.add_typer(options_attribute_app, name="attributes")
attribute_app = typer.Typer(
    help="Cross-resource AttributeValue workflows (get / set / delete / find).",
    no_args_is_help=True,
)
app.add_typer(attribute_app, name="attributes")
program_rule_app = typer.Typer(
    help="Program rule workflows (get / vars-for / validate / where-de-is-used).",
    no_args_is_help=True,
)
app.add_typer(program_rule_app, name="program-rules")
sql_view_app = typer.Typer(
    help="SQL view workflows (get / execute / refresh / adhoc).",
    no_args_is_help=True,
)
app.add_typer(sql_view_app, name="sql-views")
viz_app = typer.Typer(
    help="Visualization authoring (get / create / clone / delete).",
    no_args_is_help=True,
)
app.add_typer(viz_app, name="visualizations")
dashboard_app = typer.Typer(
    help="Dashboard composition (get / add-item / remove-item).",
    no_args_is_help=True,
)
app.add_typer(dashboard_app, name="dashboards")
map_app = typer.Typer(
    help="Map authoring (get / create / clone / delete).",
    no_args_is_help=True,
)
app.add_typer(map_app, name="maps")
data_elements_app = typer.Typer(
    help="DataElement authoring (get / create / rename / delete + legend-sets).",
    no_args_is_help=True,
)
app.add_typer(data_elements_app, name="data-elements")
data_element_groups_app = typer.Typer(
    help="DataElementGroup workflows (get / members / create / add-members / remove-members / delete).",
    no_args_is_help=True,
)
app.add_typer(data_element_groups_app, name="data-element-groups")
data_element_group_sets_app = typer.Typer(
    help="DataElementGroupSet workflows (get / create / add-groups / remove-groups / delete).",
    no_args_is_help=True,
)
app.add_typer(data_element_group_sets_app, name="data-element-group-sets")
indicators_app = typer.Typer(
    help="Indicator authoring (get / create / rename / validate-expression / delete).",
    no_args_is_help=True,
)
app.add_typer(indicators_app, name="indicators")
indicator_groups_app = typer.Typer(
    help="IndicatorGroup workflows (get / members / create / add-members / remove-members / delete).",
    no_args_is_help=True,
)
app.add_typer(indicator_groups_app, name="indicator-groups")
indicator_group_sets_app = typer.Typer(
    help="IndicatorGroupSet workflows (get / create / add-groups / remove-groups / delete).",
    no_args_is_help=True,
)
app.add_typer(indicator_group_sets_app, name="indicator-group-sets")
program_indicators_app = typer.Typer(
    help="ProgramIndicator authoring (get / create / rename / validate-expression / delete).",
    no_args_is_help=True,
)
app.add_typer(program_indicators_app, name="program-indicators")
program_indicator_groups_app = typer.Typer(
    help="ProgramIndicatorGroup workflows (get / members / create / add-members / remove-members / delete).",
    no_args_is_help=True,
)
app.add_typer(program_indicator_groups_app, name="program-indicator-groups")
category_options_app = typer.Typer(
    help="CategoryOption authoring (get / create / rename / set-validity / delete).",
    no_args_is_help=True,
)
app.add_typer(category_options_app, name="category-options")
category_option_groups_app = typer.Typer(
    help="CategoryOptionGroup workflows (get / members / create / add-members / remove-members / delete).",
    no_args_is_help=True,
)
app.add_typer(category_option_groups_app, name="category-option-groups")
category_option_group_sets_app = typer.Typer(
    help="CategoryOptionGroupSet workflows (get / create / add-groups / remove-groups / delete).",
    no_args_is_help=True,
)
app.add_typer(category_option_group_sets_app, name="category-option-group-sets")
categories_app = typer.Typer(
    help="Category authoring (get / create / rename / add-option / remove-option / delete).",
    no_args_is_help=True,
)
app.add_typer(categories_app, name="categories")
category_combos_app = typer.Typer(
    help=("CategoryCombo authoring (get / create / rename / add-category / remove-category / wait-for-cocs / delete)."),
    no_args_is_help=True,
)
app.add_typer(category_combos_app, name="category-combos")
category_option_combos_app = typer.Typer(
    help="CategoryOptionCombo read access (get / list-for-combo). DHIS2 owns writes.",
    no_args_is_help=True,
)
app.add_typer(category_option_combos_app, name="category-option-combos")
data_sets_app = typer.Typer(
    help="DataSet authoring (get / create / rename / add-element / remove-element / delete).",
    no_args_is_help=True,
)
app.add_typer(data_sets_app, name="data-sets")
sections_app = typer.Typer(
    help="Section authoring (get / create / rename / add-element / remove-element / reorder / delete).",
    no_args_is_help=True,
)
app.add_typer(sections_app, name="sections")
validation_rules_app = typer.Typer(
    help="ValidationRule authoring (get / create / rename / delete).",
    no_args_is_help=True,
)
app.add_typer(validation_rules_app, name="validation-rules")
validation_rule_groups_app = typer.Typer(
    help="ValidationRuleGroup workflows (get / members / create / add-members / remove-members / delete).",
    no_args_is_help=True,
)
app.add_typer(validation_rule_groups_app, name="validation-rule-groups")
predictors_app = typer.Typer(
    help="Predictor authoring (get / create / rename / delete).",
    no_args_is_help=True,
)
app.add_typer(predictors_app, name="predictors")
predictor_groups_app = typer.Typer(
    help="PredictorGroup workflows (get / members / create / add-members / remove-members / delete).",
    no_args_is_help=True,
)
app.add_typer(predictor_groups_app, name="predictor-groups")
tracked_entity_attributes_app = typer.Typer(
    help="TrackedEntityAttribute authoring (get / create / rename / delete).",
    no_args_is_help=True,
)
app.add_typer(tracked_entity_attributes_app, name="tracked-entity-attributes")
tracked_entity_types_app = typer.Typer(
    help="TrackedEntityType authoring (get / create / rename / add-attribute / remove-attribute / delete).",
    no_args_is_help=True,
)
app.add_typer(tracked_entity_types_app, name="tracked-entity-types")
programs_app = typer.Typer(
    help=(
        "Program authoring (get / create / rename / add-attribute / remove-attribute "
        "/ add-to-ou / remove-from-ou / delete)."
    ),
    no_args_is_help=True,
)
app.add_typer(programs_app, name="programs")
program_stages_app = typer.Typer(
    help=("ProgramStage authoring (get / create / rename / add-element / remove-element / reorder / delete)."),
    no_args_is_help=True,
)
app.add_typer(program_stages_app, name="program-stages")
organisation_units_app = typer.Typer(
    help="OrganisationUnit hierarchy workflows (get / tree / create / move / delete).",
    no_args_is_help=True,
)
app.add_typer(organisation_units_app, name="organisation-units")
organisation_unit_groups_app = typer.Typer(
    help="OrganisationUnitGroup workflows (get / members / create / add-members / remove-members / delete).",
    no_args_is_help=True,
)
app.add_typer(organisation_unit_groups_app, name="organisation-unit-groups")
organisation_unit_group_sets_app = typer.Typer(
    help="OrganisationUnitGroupSet workflows (get / create / add-groups / remove-groups / delete).",
    no_args_is_help=True,
)
app.add_typer(organisation_unit_group_sets_app, name="organisation-unit-group-sets")
organisation_unit_levels_app = typer.Typer(
    help="OrganisationUnitLevel naming (get / rename).",
    no_args_is_help=True,
)
app.add_typer(organisation_unit_levels_app, name="organisation-unit-levels")
legend_sets_app = typer.Typer(
    help="LegendSet authoring (get / create / clone / delete).",
    no_args_is_help=True,
)
app.add_typer(legend_sets_app, name="legend-sets")
_console = Console()


_RICH_MARKUP = re.compile(r"\[/?[a-z0-9 #]+\]")


def _emit_mutation(*parts: str) -> None:
    """Emit a write summary: a JSON {ok, summary} object under --json, else the rich line(s)."""
    if is_json_output():
        text = " ".join(parts)
        typer.echo(json.dumps({"ok": True, "summary": _RICH_MARKUP.sub("", text).strip()}))
    else:
        _console.print(*parts)


@type_app.command("list")
@type_app.command("ls", hidden=True)
def type_list_command() -> None:
    """List the metadata resource types exposed by the connected DHIS2 instance."""
    names = asyncio.run(service.list_resource_types(profile_from_env()))
    if is_json_output():
        typer.echo(json.dumps(names, indent=2))
        return
    if not names:
        typer.echo("no metadata types reported by this instance")
        return
    table = Table(title=f"DHIS2 metadata types ({len(names)})")
    table.add_column("resource type", style="cyan", no_wrap=True)
    for name in names:
        table.add_row(name)
    _console.print(table)


@app.command("list")
@app.command("ls", hidden=True)
def list_command(
    resource: Annotated[str, typer.Argument(help="Resource type, e.g. dataElements, indicators")],
    fields: Annotated[
        str,
        typer.Option(
            "--fields",
            help="DHIS2 field selector: plain ('id,name'), presets (':identifiable', ':nameable', ':owner', ':all'), "
            "nested ('children[id,name]'), or exclusions (':all,!lastUpdated').",
        ),
    ] = "id,name",
    filters: Annotated[
        list[str] | None,
        typer.Option(
            "--filter",
            help=(
                "Filter as `property:operator:value`. Repeatable — AND'd by default, use "
                "--root-junction OR. Operators: eq (exact), ilike (contains), $ilike (starts-with), "
                "ilike$ (ends-with), token (word), gt/ge/lt/le (numbers/dates), in:[a,b] (any-of), "
                "null / !null (presence); drop the `i` for case-sensitive. Nested paths use dots, e.g. "
                "dataSetElements.dataSet.id:eq:<uid> or categoryCombo.id:eq:<uid>. "
                "E.g. name:$ilike:anc lists names starting with 'anc'."
            ),
        ),
    ] = None,
    root_junction: Annotated[
        str,
        typer.Option("--root-junction", help="Combine repeated --filter as AND (default) or OR."),
    ] = "AND",
    order: Annotated[
        list[str] | None,
        typer.Option(
            "--order",
            help="Sort clause like 'name:asc' or 'created:desc'. Repeatable (later clauses tie-break).",
        ),
    ] = None,
    page: Annotated[
        int | None,
        typer.Option(
            "--page",
            help="Server-side page number (1-based). With NO paging flag the FULL collection is "
            "returned; passing --page switches to paged mode (pageSize defaults to 50). "
            "Ignored when --all is set.",
        ),
    ] = None,
    page_size: Annotated[
        int | None,
        typer.Option(
            "--page-size",
            help="Rows per page; applies only in paged mode (when --page/--page-size is given), "
            "default 50. Omit all paging flags to get everything. Ignored when --all is set.",
        ),
    ] = None,
    fetch_all: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Stream every page server-side (ignores --page/--page-size). Useful for dumping a full catalog.",
        ),
    ] = False,
    translate: Annotated[
        bool | None,
        typer.Option("--translate/--no-translate", help="Return server-side translations for i18n fields."),
    ] = None,
    locale: Annotated[str | None, typer.Option("--locale", help="Locale for --translate, e.g. 'fr'.")] = None,
    count: Annotated[
        bool,
        typer.Option(
            "--count",
            help="Print only the total number of matching items (DHIS2 pager total), not the rows. "
            "Respects --filter; ignores --fields / --page / --page-size / --all.",
        ),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Write the result JSON to this file and print a one-line summary instead of the rows. "
            "Combine with --fields / --filter / --all to dump a full slice without flooding the caller.",
        ),
    ] = None,
) -> None:
    """List instances of a metadata resource."""
    rj = root_junction if filters and len(filters) > 1 else None
    if count:
        total = asyncio.run(service.count_metadata(profile_from_env(), resource, filters=filters, root_junction=rj))
        result = MetadataCount(resource=resource, total=total)
        if is_json_output():
            typer.echo(result.model_dump_json(indent=2))
        else:
            typer.echo(f"{resource}: {total}")
        return
    _warn_unknown_fields(resource, fields)
    if fetch_all:
        items = asyncio.run(
            _collect_all(
                resource,
                fields=fields,
                filters=filters,
                root_junction=rj,
                order=order,
                translate=translate,
                locale=locale,
            )
        )
    else:
        items = asyncio.run(
            service.list_metadata(
                profile_from_env(),
                resource,
                fields=fields,
                filters=filters,
                root_junction=rj,
                order=order,
                page=page,
                page_size=page_size,
                translate=translate,
                locale=locale,
            )
        )
    rows = [_dump_for_cli(model) for model in items]
    if output is not None:
        destination = output.expanduser()
        destination.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        written = MetadataWriteResult(resource=resource, written=len(rows), path=str(destination.resolve()))
        if is_json_output():
            typer.echo(written.model_dump_json(indent=2))
        else:
            typer.echo(f"wrote {written.written} {resource} to {written.path}")
        return
    if is_json_output():
        typer.echo(json.dumps(rows, indent=2))
        return
    _print_table(resource, rows, fields.split(","))


def _warn_unknown_fields(resource: str, fields: str) -> None:
    """Emit a soft stderr warning when `--fields` names a field absent from the generated model.

    Best-effort and non-blocking: uses the offline plugin-tree version and the generated models,
    so a model that guessed a field name gets a corrective signal the DHIS2 API never gives (it
    silently drops unknown fields). Only plain comma-lists are checked (see `schema` service).
    """
    version = resolve_startup_version()
    missing = schema_service.unknown_fields(version, resource, fields)
    if missing:
        typer.secho(
            f"WARNING: --fields not in the generated {version} model for {resource}: "
            f"{', '.join(missing)} (possible typo, or a field this client doesn't model)",
            fg="yellow",
            err=True,
        )


def _dump_for_cli(model: Any) -> dict[str, Any]:
    """Dump a typed generated model to a JSON-friendly dict for CLI table/JSON rendering.

    Edge-of-world carveout: the service returns typed models; CLI (like MCP)
    dumps at the boundary where the output format is JSON/table text rather
    than further Python code.
    """
    if hasattr(model, "model_dump"):
        dumped = model.model_dump(by_alias=True, exclude_none=True, mode="json")
        if isinstance(dumped, dict):
            return dumped
    if isinstance(model, dict):
        return model
    raise TypeError(f"cannot render {type(model).__name__} as a CLI row")


async def _collect_all(
    resource: str,
    *,
    fields: str,
    filters: list[str] | None,
    root_junction: str | None,
    order: list[str] | None,
    translate: bool | None,
    locale: str | None,
) -> list[BaseModel]:
    """Drain `iter_metadata` into a list for table/JSON rendering."""
    collected: list[BaseModel] = []
    async for item in service.iter_metadata(
        profile_from_env(),
        resource,
        fields=fields,
        filters=filters,
        root_junction=root_junction,
        order=order,
        translate=translate,
        locale=locale,
    ):
        collected.append(item)
    return collected


@app.command("search")
def search_command(
    query: Annotated[str, typer.Argument(help="UID, code, or name fragment to search for.")],
    page_size: Annotated[
        int,
        typer.Option("--page-size", help="Max hits per resource type (default 50)."),
    ] = 50,
    resource: Annotated[
        str | None,
        typer.Option("--resource", help="Narrow to one DHIS2 resource (e.g. dataElements, dashboards)."),
    ] = None,
    fields: Annotated[
        str | None,
        typer.Option(
            "--fields",
            help="DHIS2 fields selector; extras land on SearchHit.extras (rendered as trailing columns).",
        ),
    ] = None,
    exact: Annotated[
        bool,
        typer.Option("--exact", help="Use `:eq:` instead of `:ilike:` — strict UID / code match."),
    ] = False,
) -> None:
    """Cross-resource metadata search.

    Three concurrent `/api/metadata?filter=<field>:<op>:<q>` calls (one
    per match axis: id, code, name) merged client-side with UID dedup.
    Paste whatever you have — UID, partial UID, business code, or name
    fragment — to find every matching object grouped by resource.

    `--resource dataElements` narrows to one resource kind. `--fields
    id,name,code,valueType` asks DHIS2 for extra columns (rendered
    after the standard four). `--exact` switches from ilike substring
    to `eq` strict match — useful when a partial UID would otherwise
    match too many siblings.
    """
    result = asyncio.run(
        service.search_metadata(
            profile_from_env(),
            query,
            page_size=page_size,
            resource=resource,
            fields=fields,
            exact=exact,
        ),
    )
    if is_json_output():
        typer.echo(result.model_dump_json(indent=2))
        return
    if result.total == 0:
        _console.print(f"[dim]no matches for[/dim] [bold]{query}[/bold]")
        return
    _render_hits_table(f"matches for '{query}' ({result.total} total)", result, extra_fields=fields)


@app.command("usage")
def usage_command(
    uid: Annotated[str, typer.Argument(help="UID to reverse-lookup — find every object that references it.")],
    page_size: Annotated[
        int,
        typer.Option("--page-size", help="Max hits per reference path (default 100)."),
    ] = 100,
) -> None:
    """Reverse lookup — find every object that references the given UID.

    Useful as a deletion-safety check: any dataset / visualization / map /
    dashboard / program that references the UID shows up in the table.
    Empty result means no reference was found on any covered path, but
    is not a hard proof that the UID is safe to delete — coverage is
    best-effort (see `_USAGE_PATTERNS` in the client).

    Internally: resolves the UID's owning resource via
    `/api/identifiableObjects/{uid}` first, then fans out concurrent
    `/api/<target>?filter=<path>:eq:<uid>` calls over every known
    reference-shape for that owning type.
    """
    result = asyncio.run(service.usage_metadata(profile_from_env(), uid, page_size=page_size))
    if is_json_output():
        typer.echo(result.model_dump_json(indent=2))
        return
    if result.total == 0:
        _console.print(f"[dim]no references found to[/dim] [bold]{uid}[/bold]")
        return
    _render_hits_table(f"objects referencing {uid} ({result.total} total)", result)


def _render_hits_table(title: str, result: object, *, extra_fields: str | None = None) -> None:
    """Render a `SearchResults` as a Rich table — used by `search` + `usage`."""
    from dhis2w_client.v43 import SearchResults  # noqa: PLC0415 — local import avoids circular

    if not isinstance(result, SearchResults):
        return
    extra_cols: list[str] = []
    if extra_fields:
        # Strip the core four so we don't render duplicate columns.
        core = {"id", "name", "code", "href", "displayName"}
        extra_cols = [col.strip() for col in extra_fields.split(",") if col.strip() and col.strip() not in core]
    table = Table(title=title)
    table.add_column("resource", style="cyan")
    table.add_column("uid")
    table.add_column("name")
    table.add_column("code", style="dim")
    for col in extra_cols:
        table.add_column(col, style="dim")
    for resource_name in sorted(result.hits):
        for hit in result.hits[resource_name]:
            row = [resource_name, hit.uid, hit.name, hit.code or ""]
            for col in extra_cols:
                row.append(str(hit.extras.get(col, "") if col in hit.extras else ""))
            table.add_row(*row)
    _console.print(table)


@app.command("get")
def get_command(
    resource: Annotated[str, typer.Argument(help="Resource type, e.g. dataElements")],
    uid: Annotated[str, typer.Argument(help="Object UID")],
    fields: Annotated[str | None, typer.Option("--fields", help="DHIS2 fields selector.")] = None,
) -> None:
    """Fetch one metadata object by UID.

    Prints a concise Rich summary by default (id, name, code, common metadata +
    notable extras). Use `--json` for the full payload when debugging or
    piping into jq. Pass `--fields` to narrow what DHIS2 returns.
    """
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{10}", uid):
        typer.secho(
            f"error: {uid!r} is not a valid DHIS2 UID (11 chars: a letter then 10 letters/digits)",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(2)
    from dhis2w_core.v43.cli_output import DetailRow, render_detail

    model = asyncio.run(
        service.get_metadata(profile_from_env(), resource, uid, fields=fields),
    )
    payload = _dump_for_cli(model)
    if is_json_output():
        typer.echo(json.dumps(payload, indent=2))
        return
    # Standard top-level identity fields (present on almost every DHIS2 resource).
    rows: list[DetailRow] = []
    for key in ("id", "name", "displayName", "shortName", "code", "description", "href", "created", "lastUpdated"):
        if key in payload:
            rows.append(DetailRow(key, _summary_cell(payload[key])))
    # Pull a few more keys if they're present + interesting (type-specific).
    extras = [
        k
        for k in (
            "valueType",
            "aggregationType",
            "domainType",
            "periodType",
            "url",
            "disabled",
            "publicAccess",
            "programType",
            "level",
            "parent",
            "openingDate",
            "closedDate",
        )
        if k in payload
    ]
    for key in extras:
        rows.append(DetailRow(key, _summary_cell(payload[key])))
    # List all other top-level keys with a compact summary.
    shown = {row.label for row in rows}
    rest = sorted(k for k in payload if k not in shown and not k.startswith("_"))
    if rest:
        rows.append(DetailRow("[dim]more keys[/dim]", ", ".join(rest)))
    render_detail(f"{resource}/{uid}", rows)


def _summary_cell(value: Any) -> str:
    """Compact cell renderer for the metadata-get summary — references as `name (id)`."""
    from dhis2w_core.v43.cli_output import format_ref, format_reflist

    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], (dict, str)):
            return format_reflist(value)
        return str(value)
    if isinstance(value, dict):
        return format_ref(value)
    return str(value)


def _print_table(resource: str, items: list[dict[str, Any]], columns: list[str]) -> None:
    columns = [c.strip() for c in columns if c.strip() and not c.startswith(":")]
    if not columns:
        # Fallback when a preset (`:identifiable`, etc.) was used — infer keys from the first row.
        columns = sorted(items[0].keys()) if items else ["id"]
    table = Table(title=f"{resource} ({len(items)} row{'s' if len(items) != 1 else ''})")
    for column in columns:
        table.add_column(column, overflow="fold")
    for item in items:
        table.add_row(*[_cell(item.get(column)) for column in columns])
    _console.print(table)


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


@app.command("export")
def export_command(
    resource: Annotated[
        list[str] | None,
        typer.Option(
            "--resource",
            help="Resource type to include (repeatable). Omit for every type DHIS2 exports by default.",
        ),
    ] = None,
    fields: Annotated[
        str | None,
        typer.Option(
            "--fields",
            help="DHIS2 field selector. Defaults to ':owner' for a lossless round-trip import.",
        ),
    ] = ":owner",
    resource_filter: Annotated[
        list[str] | None,
        typer.Option(
            "--filter",
            help=(
                "Per-resource filter in the form `RESOURCE:property:operator:value`. Repeatable. "
                "Example: `--filter dataElements:name:like:ANC`. "
                "Same DSL as `dhis2 metadata list --filter`, prefixed with the resource name."
            ),
        ),
    ] = None,
    resource_fields: Annotated[
        list[str] | None,
        typer.Option(
            "--resource-fields",
            help=(
                "Per-resource field selector in the form `RESOURCE:SELECTOR`. Repeatable. "
                "Overrides the global `--fields` for the named resource. "
                "Example: `--resource-fields dataElements::identifiable`."
            ),
        ),
    ] = None,
    skip_sharing: Annotated[
        bool, typer.Option("--skip-sharing", help="Exclude sharing blocks from exported objects.")
    ] = False,
    skip_translation: Annotated[bool, typer.Option("--skip-translation", help="Exclude translation blocks.")] = False,
    skip_validation: Annotated[
        bool,
        typer.Option("--skip-validation", help="Skip validation during export (matches DHIS2's server-side option)."),
    ] = False,
    check_references: Annotated[
        bool,
        typer.Option(
            "--check-references/--no-check-references",
            help=(
                "After export, walk the bundle and warn on references to UIDs not in the bundle "
                "(e.g. a dataElement's categoryCombo missing from a filtered export). On by default."
            ),
        ),
    ] = True,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Write the bundle to this file (JSON). A full-catalog export is tens of MB "
                "(org-unit geometry) — prefer this; omitting prints the whole bundle to stdout."
            ),
        ),
    ] = None,
    pretty: Annotated[bool, typer.Option("--pretty/--no-pretty", help="Indent JSON output (default: pretty).")] = True,
) -> None:
    """Download a metadata bundle from `GET /api/metadata`.

    Prints a per-resource count summary to stderr so stdout stays pipe-friendly
    when `--output` is omitted. With `--check-references` (default), walks the
    exported bundle and warns on any reference to a UID not in the bundle —
    so a filtered `--resource dataElements` export doesn't silently produce a
    bundle that won't round-trip because categoryCombos / optionSets / ...
    are missing.
    """
    per_resource_filters = _parse_prefixed_multi(resource_filter or [], flag_name="--filter")
    per_resource_fields_map = _parse_prefixed_single(resource_fields or [], flag_name="--resource-fields")
    bundle = asyncio.run(
        service.export_metadata(
            profile_from_env(),
            resources=resource,
            fields=fields,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
            skip_validation=skip_validation,
            per_resource_filters=per_resource_filters or None,
            per_resource_fields=per_resource_fields_map or None,
        )
    )
    summary = bundle.summary()
    total = bundle.total()
    payload = bundle.model_dump_json(indent=2 if pretty else None, exclude_none=True, by_alias=True)
    if output is None:
        sys.stdout.write(payload)
        sys.stdout.write("\n")
    else:
        output.write_text(payload + "\n", encoding="utf-8")
        typer.secho(f"wrote {output} ({total} objects across {len(summary)} resource types)", err=True)
    _render_bundle_summary(summary, destination=f"written to {output}" if output else "stdout")
    if check_references:
        refs = service.bundle_dangling_references(bundle)
        _render_dangling_references(refs)


def _parse_prefixed_multi(values: list[str], *, flag_name: str) -> dict[str, list[str]]:
    """Parse repeatable `RESOURCE:expr` flags into `{resource: [exprs...]}`.

    Splits on the first colon so the `property:operator:value` portion stays
    intact. Raises a Typer error on values with no colon.
    """
    parsed: dict[str, list[str]] = {}
    for raw in values:
        resource, sep, expr = raw.partition(":")
        if not sep or not resource or not expr:
            raise typer.BadParameter(
                f"{flag_name} value {raw!r} must be `RESOURCE:expr` (e.g. `dataElements:name:like:ANC`)"
            )
        parsed.setdefault(resource, []).append(expr)
    return parsed


def _parse_prefixed_single(values: list[str], *, flag_name: str) -> dict[str, str]:
    """Parse repeatable `RESOURCE:selector` flags into `{resource: selector}` (last wins)."""
    parsed: dict[str, str] = {}
    for raw in values:
        resource, sep, selector = raw.partition(":")
        if not sep or not resource or not selector:
            raise typer.BadParameter(
                f"{flag_name} value {raw!r} must be `RESOURCE:selector` (e.g. `dataElements::identifiable`)"
            )
        parsed[resource] = selector
    return parsed


def _render_dangling_references(refs: service.DanglingReferences) -> None:
    """Print a Rich warning + per-field breakdown when the bundle has dangling references."""
    if refs.is_clean:
        _console.print(
            f"[dim]reference check: {refs.bundle_uid_count} UIDs in bundle, no dangling references.[/dim]",
            highlight=False,
        )
        return
    _console.print(
        f"[yellow]WARNING[/yellow]: {refs.total_missing} dangling reference(s) — "
        f"UIDs referenced by objects in the bundle but not present in the bundle itself.",
        highlight=False,
    )
    table = Table(show_edge=False, show_header=True, pad_edge=False)
    table.add_column("field", style="yellow")
    table.add_column("missing", justify="right")
    table.add_column("sample UIDs", overflow="fold", style="dim")
    for item in refs.items:
        sample = ", ".join(item.missing_uids[:3])
        if item.count > 3:
            sample += f" (+{item.count - 3} more)"
        table.add_row(item.field_name, str(item.count), sample)
    _console.print(table)
    _console.print(
        "[dim]Re-run with the referenced resource types added (e.g. "
        "`--resource categoryCombos --resource optionSets`) "
        "or silence this check with `--no-check-references`.[/dim]",
        highlight=False,
    )


@app.command("import")
def import_command(
    file: Annotated[Path, typer.Argument(help="Path to the metadata bundle JSON.")],
    import_strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            help="CREATE | UPDATE | CREATE_AND_UPDATE | DELETE (default CREATE_AND_UPDATE).",
        ),
    ] = "CREATE_AND_UPDATE",
    atomic_mode: Annotated[
        str,
        typer.Option(
            "--atomic-mode",
            help="ALL (rollback on any failure) or NONE (commit surviving objects).",
        ),
    ] = "ALL",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Validate + preheat without committing. Output is the import report DHIS2 would have produced.",
        ),
    ] = False,
    identifier: Annotated[
        str,
        typer.Option("--identifier", help="UID | CODE | AUTO (default UID)."),
    ] = "UID",
    skip_sharing: Annotated[bool, typer.Option("--skip-sharing")] = False,
    skip_translation: Annotated[bool, typer.Option("--skip-translation")] = False,
    skip_validation: Annotated[bool, typer.Option("--skip-validation")] = False,
    merge_mode: Annotated[
        str | None,
        typer.Option("--merge-mode", help="REPLACE (overwrite) or MERGE (patch) existing objects."),
    ] = None,
    preheat_mode: Annotated[
        str | None,
        typer.Option("--preheat-mode", help="REFERENCE (default), ALL, or NONE."),
    ] = None,
    flush_mode: Annotated[
        str | None,
        typer.Option("--flush-mode", help="AUTO (default) or OBJECT."),
    ] = None,
) -> None:
    """Upload a metadata bundle via `POST /api/metadata` and print the import report."""
    raw = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise typer.BadParameter(f"{file} must contain a metadata bundle object (got {type(raw).__name__})")
    bundle = MetadataBundle.from_raw(raw)
    typer.secho(f"posting {file} → /api/metadata (dry_run={dry_run})", err=True)
    summary = bundle.summary()
    if summary:
        _render_bundle_summary(summary, destination=f"source: {file}")
    response = asyncio.run(
        service.import_metadata(
            profile_from_env(),
            bundle,
            import_strategy=import_strategy,
            atomic_mode=atomic_mode,
            dry_run=dry_run,
            identifier=identifier,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
            skip_validation=skip_validation,
            merge_mode=merge_mode,
            preheat_mode=preheat_mode,
            flush_mode=flush_mode,
        )
    )
    render_webmessage(response, action="imported")


@app.command("patch")
def patch_command(
    resource: Annotated[str, typer.Argument(help="Resource type, e.g. dataElements, indicators.")],
    uid: Annotated[str, typer.Argument(help="UID of the object to patch.")],
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            help="JSON file with a RFC 6902 patch array. Mutually exclusive with --set/--remove.",
        ),
    ] = None,
    set_ops: Annotated[
        list[str] | None,
        typer.Option(
            "--set",
            help=(
                "Inline `replace` op as `path=value`. Repeatable. Values are JSON-decoded "
                'when they parse as JSON (`{"a":1}`, `true`, `42`) and treated as strings otherwise.'
            ),
        ),
    ] = None,
    remove_ops: Annotated[
        list[str] | None,
        typer.Option(
            "--remove",
            help="Inline `remove` op as `path`. Repeatable.",
        ),
    ] = None,
) -> None:
    """Apply an RFC 6902 JSON Patch to a metadata object (`PATCH /api/<resource>/{uid}`).

    Two input modes:

    - `--file patch.json` — full patch array on disk, one op per entry:
      `[{"op": "replace", "path": "/name", "value": "New"}, ...]`
    - `--set path=value` / `--remove path` (each repeatable) — inline shorthand
      for the common replace/remove cases. Values parse as JSON when possible
      (so `--set /valueType=INTEGER` sends a string, `--set /disabled=true`
      sends a boolean).
    """
    if (file is None) == (not set_ops and not remove_ops):
        raise typer.BadParameter("pass either --file OR --set/--remove inline ops (not both, not neither)")

    ops_raw: list[dict[str, Any]]
    if file is not None:
        parsed = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(parsed, list):
            raise typer.BadParameter(f"{file} must contain a JSON Patch array (got {type(parsed).__name__})")
        ops_raw = parsed
    else:
        ops_raw = []
        for assign in set_ops or []:
            path, sep, raw_value = assign.partition("=")
            if not sep:
                raise typer.BadParameter(f"--set value {assign!r} must be `path=value`")
            try:
                value: Any = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value
            ops_raw.append({"op": "replace", "path": path, "value": value})
        for path in remove_ops or []:
            ops_raw.append({"op": "remove", "path": path})

    ops = [JsonPatchOpAdapter.validate_python(op) for op in ops_raw]
    typer.secho(f"patching {resource}/{uid} ({len(ops)} op{'s' if len(ops) != 1 else ''})", err=True)
    response = asyncio.run(service.patch_metadata(profile_from_env(), resource, uid, ops))
    render_webmessage(response, action=f"patched {resource}/{uid}")


@app.command("rename")
def rename_command(
    resource: Annotated[str, typer.Argument(help="Resource type, e.g. dataElements, indicators.")],
    filters: Annotated[
        list[str] | None,
        typer.Option(
            "--filter",
            help=(
                "DHIS2 filter DSL (`<prop>:<op>:<value>`), repeatable. "
                "Example: `--filter code:like:DE_ANC` to narrow the cohort."
            ),
        ),
    ] = None,
    root_junction: Annotated[
        str | None,
        typer.Option("--root-junction", help="Combine repeated --filter as AND (default) or OR."),
    ] = None,
    name_prefix: Annotated[
        str | None,
        typer.Option("--name-prefix", help="Prefix each matched object's `name` (idempotent)."),
    ] = None,
    name_suffix: Annotated[
        str | None,
        typer.Option("--name-suffix", help="Suffix each matched object's `name` (idempotent)."),
    ] = None,
    name_strip_prefix: Annotated[
        str | None,
        typer.Option(
            "--name-strip-prefix",
            help="Remove this prefix from each matched object's `name` (idempotent; no-op when absent).",
        ),
    ] = None,
    name_strip_suffix: Annotated[
        str | None,
        typer.Option(
            "--name-strip-suffix",
            help="Remove this suffix from each matched object's `name` (idempotent; no-op when absent).",
        ),
    ] = None,
    short_name_prefix: Annotated[
        str | None,
        typer.Option("--short-name-prefix", help="Prefix each matched object's `shortName` (idempotent)."),
    ] = None,
    short_name_suffix: Annotated[
        str | None,
        typer.Option("--short-name-suffix", help="Suffix each matched object's `shortName` (idempotent)."),
    ] = None,
    short_name_strip_prefix: Annotated[
        str | None,
        typer.Option(
            "--short-name-strip-prefix",
            help="Remove this prefix from each matched object's `shortName` (idempotent).",
        ),
    ] = None,
    short_name_strip_suffix: Annotated[
        str | None,
        typer.Option(
            "--short-name-strip-suffix",
            help="Remove this suffix from each matched object's `shortName` (idempotent).",
        ),
    ] = None,
    set_description: Annotated[
        str | None,
        typer.Option("--set-description", help="Replace every matched object's `description` with this string."),
    ] = None,
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", help="Max concurrent PATCH requests (default 8)."),
    ] = 8,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the planned patches without sending them."),
    ] = False,
) -> None:
    """Bulk-rename metadata objects by RFC 6902 patch.

    Fans out concurrent `PATCH /api/<resource>/{uid}` requests via the
    shared `client.metadata.patch_bulk` primitive (#187); per-UID
    failures render through the same conflict table used by
    `metadata import` instead of raising. Prefix / suffix flags are
    idempotent — re-running won't double-prefix already-prefixed
    objects.

    Use `--dry-run` to preview which objects match + what the
    before/after labels would be, then drop the flag to apply.
    """
    mutations = [
        name_prefix,
        name_suffix,
        name_strip_prefix,
        name_strip_suffix,
        short_name_prefix,
        short_name_suffix,
        short_name_strip_prefix,
        short_name_strip_suffix,
        set_description,
    ]
    if not any(m is not None for m in mutations):
        raise typer.BadParameter(
            "pass at least one of --name-prefix / --name-suffix / --name-strip-prefix / "
            "--name-strip-suffix / --short-name-prefix / --short-name-suffix / "
            "--short-name-strip-prefix / --short-name-strip-suffix / --set-description",
        )
    result = asyncio.run(
        service.bulk_rename_metadata(
            profile_from_env(),
            resource,
            filters=filters,
            root_junction=root_junction,
            name_prefix=name_prefix,
            name_suffix=name_suffix,
            name_strip_prefix=name_strip_prefix,
            name_strip_suffix=name_strip_suffix,
            short_name_prefix=short_name_prefix,
            short_name_suffix=short_name_suffix,
            short_name_strip_prefix=short_name_strip_prefix,
            short_name_strip_suffix=short_name_strip_suffix,
            set_description=set_description,
            concurrency=concurrency,
            dry_run=dry_run,
        ),
    )

    if is_json_output():
        typer.echo(result.model_dump_json(indent=2, exclude_none=True))
        return

    if not result.entries:
        typer.echo(f"no {resource} matched the filter + rename flags — nothing to do")
        return

    mode = "preview" if result.dry_run else "applied"
    title = f"{resource} rename {mode} ({result.matched} object{'s' if result.matched != 1 else ''})"
    table = Table(title=title)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name before", overflow="fold")
    table.add_column("name after", overflow="fold")
    table.add_column("shortName before", style="dim", overflow="fold")
    table.add_column("shortName after", style="dim", overflow="fold")
    for entry in result.entries:
        table.add_row(
            entry.uid,
            entry.name_before or "-",
            entry.name_after or "-",
            entry.short_name_before or "-",
            entry.short_name_after or "-",
        )
    _console.print(table)

    if result.dry_run:
        _console.print(
            f"[yellow]dry-run[/yellow] — drop --dry-run to apply {result.matched} patch"
            f"{'es' if result.matched != 1 else ''}",
        )
        return
    patch_result = result.patch_result
    if patch_result is None:
        return
    if patch_result.ok:
        _console.print(f"[green]applied[/green] {result.succeeded} rename{'s' if result.succeeded != 1 else ''}")
    else:
        _console.print(
            f"[green]applied[/green] {result.succeeded}  [red]failed[/red] {result.failed}",
        )
        failure_table = Table(title=f"{resource} rename failures")
        failure_table.add_column("uid", style="cyan", no_wrap=True)
        failure_table.add_column("status", justify="right")
        failure_table.add_column("message", overflow="fold")
        for failure in patch_result.failures:
            failure_table.add_row(failure.uid, str(failure.status_code), failure.message)
        _console.print(failure_table)


@app.command("retag")
def retag_command(
    resource: Annotated[str, typer.Argument(help="Resource type, e.g. dataElements, indicators.")],
    filters: Annotated[
        list[str] | None,
        typer.Option(
            "--filter",
            help="DHIS2 filter DSL (`<prop>:<op>:<value>`), repeatable.",
        ),
    ] = None,
    root_junction: Annotated[
        str | None,
        typer.Option("--root-junction", help="Combine repeated --filter as AND (default) or OR."),
    ] = None,
    category_combo: Annotated[
        str | None,
        typer.Option("--category-combo", help="Replace `/categoryCombo` with the given CategoryCombo UID."),
    ] = None,
    option_set: Annotated[
        str | None,
        typer.Option("--option-set", help="Replace `/optionSet` with the given OptionSet UID."),
    ] = None,
    clear_option_set: Annotated[
        bool,
        typer.Option("--clear-option-set", help="Remove `/optionSet` (null out the ref)."),
    ] = False,
    aggregation_type: Annotated[
        str | None,
        typer.Option("--aggregation-type", help="Replace `/aggregationType` (e.g. SUM, AVERAGE)."),
    ] = None,
    domain_type: Annotated[
        str | None,
        typer.Option("--domain-type", help="Replace `/domainType` (AGGREGATE / TRACKER)."),
    ] = None,
    legend_sets: Annotated[
        list[str] | None,
        typer.Option("--legend-set", help="Replace `/legendSets` with the given UIDs (repeatable)."),
    ] = None,
    clear_legend_sets: Annotated[
        bool,
        typer.Option("--clear-legend-sets", help="Empty `/legendSets`."),
    ] = False,
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", help="Max concurrent PATCH requests (default 8)."),
    ] = 8,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without sending patches.")] = False,
) -> None:
    """Bulk-rewrite ref / enum fields on metadata objects.

    Sister verb to `metadata rename`. Flags map to RFC 6902 patches:
    `--category-combo <uid>` → `replace /categoryCombo`, `--option-set
    <uid>` → `replace /optionSet`, `--clear-option-set` → `remove
    /optionSet`, `--aggregation-type TYPE` → `replace
    /aggregationType`, `--legend-set <uid>` (repeatable) → `replace
    /legendSets` with the whole list, `--clear-legend-sets` → empty
    that list. Stack multiple flags in one invocation.

    Per-UID failures render through the shared `ConflictRow` renderer
    — e.g. `--domain-type TRACKER` against an Indicator surfaces as
    409s instead of raising.
    """
    if not any(
        [
            category_combo,
            option_set,
            clear_option_set,
            aggregation_type,
            domain_type,
            legend_sets,
            clear_legend_sets,
        ],
    ):
        raise typer.BadParameter(
            "pass at least one of --category-combo / --option-set / --clear-option-set / "
            "--aggregation-type / --domain-type / --legend-set / --clear-legend-sets",
        )
    result = asyncio.run(
        service.bulk_retag_metadata(
            profile_from_env(),
            resource,
            filters=filters,
            root_junction=root_junction,
            category_combo_uid=category_combo,
            option_set_uid=option_set,
            clear_option_set=clear_option_set,
            aggregation_type=aggregation_type,
            domain_type=domain_type,
            legend_set_uids=legend_sets,
            clear_legend_sets=clear_legend_sets,
            concurrency=concurrency,
            dry_run=dry_run,
        ),
    )

    if is_json_output():
        typer.echo(result.model_dump_json(indent=2, exclude_none=True))
        return

    if not result.entries:
        typer.echo(f"no {resource} matched the filter + retag flags — nothing to do")
        return

    mode = "preview" if result.dry_run else "applied"
    title = f"{resource} retag {mode} ({result.matched} object{'s' if result.matched != 1 else ''})"
    table = Table(title=title)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("field", style="dim")
    table.add_column("before", overflow="fold")
    table.add_column("after", overflow="fold")
    for entry in result.entries:
        for field, before_value in entry.before.items():
            after_value = entry.after.get(field)
            table.add_row(entry.uid, field, before_value or "-", after_value or "-")
    _console.print(table)

    if result.dry_run:
        _console.print(
            f"[yellow]dry-run[/yellow] — drop --dry-run to apply {result.matched} patch"
            f"{'es' if result.matched != 1 else ''}",
        )
        return
    patch_result = result.patch_result
    if patch_result is None:
        return
    if patch_result.ok:
        _console.print(f"[green]applied[/green] {result.succeeded} retag{'s' if result.succeeded != 1 else ''}")
    else:
        _console.print(
            f"[green]applied[/green] {result.succeeded}  [red]failed[/red] {result.failed}",
        )
        failure_table = Table(title=f"{resource} retag failures")
        failure_table.add_column("uid", style="cyan", no_wrap=True)
        failure_table.add_column("status", justify="right")
        failure_table.add_column("message", overflow="fold")
        for failure in patch_result.failures:
            failure_table.add_row(failure.uid, str(failure.status_code), failure.message)
        _console.print(failure_table)


def _render_bundle_summary(summary: dict[str, int], *, destination: str) -> None:
    """Print a Rich table of `{resource: count}` + total to stderr (keeps stdout pipe-friendly)."""
    total = sum(summary.values())
    err_console = Console(stderr=True)
    table = Table(title=f"metadata bundle ({total} objects, {destination})")
    table.add_column("resource", overflow="fold")
    table.add_column("count", justify="right")
    for resource_name in sorted(summary, key=lambda k: (-summary[k], k)):
        table.add_row(resource_name, str(summary[resource_name]))
    err_console.print(table)


def _share_type(resource_type: str) -> str:
    """Normalize a resource type to the SINGULAR form `/api/sharing?type=` expects.

    Accepts the singular (`dataElement`) or the plural used by get/list (`dataElements`).
    """
    if resource_type.endswith("ies"):
        return resource_type[:-3] + "y"
    if resource_type.endswith("s") and not resource_type.endswith("ss"):
        return resource_type[:-1]
    return resource_type


@app.command("share")
def share_command(
    resource_type: Annotated[
        str,
        typer.Argument(
            help=(
                "DHIS2 resource type — singular or plural, e.g. `dataElement`/`dataElements`, "
                "`dataSet`/`dataSets`, `program`. Normalized to the singular `/api/sharing?type=` form."
            ),
        ),
    ],
    uids: Annotated[
        list[str] | None,
        typer.Argument(
            help="UIDs to share. Pass `-` to read one UID per line from stdin.",
        ),
    ] = None,
    public_access: Annotated[
        str | None,
        typer.Option(
            "--public-access",
            help=(
                "Replace the public-access string. 8-char DHIS2 pattern "
                "(`rwrw----`, `r-------`, `--------`). Defaults to `r-------` if omitted "
                "and at least one grant is supplied."
            ),
        ),
    ] = None,
    user_access: Annotated[
        list[str] | None,
        typer.Option(
            "--user-access",
            help="Repeatable; grant a user access in `UID:access` form (e.g. `U_ALICE:rw------`).",
        ),
    ] = None,
    user_group_access: Annotated[
        list[str] | None,
        typer.Option(
            "--user-group-access",
            help="Repeatable; grant a user-group access in `UID:access` form.",
        ),
    ] = None,
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", help="Max concurrent POSTs (default 8)."),
    ] = 8,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the planned grants without sending them."),
    ] = False,
) -> None:
    """Apply one sharing block across many UIDs of one resource.

    Fans out concurrent `POST /api/sharing?type=<resource_type>&id=<uid>`
    requests via the shared `client.metadata.apply_sharing_bulk` primitive.
    Per-UID failures render through the same row table used by
    `metadata rename` instead of raising.

    Use `--dry-run` to preview the planned grants, then drop the flag to
    apply. UIDs come from positional args or stdin (`-`); pipe from
    `dhis2 --json metadata list ... | jq -r '.[].id'` to filter-then-share without
    leaving the shell.
    """
    resource_type = _share_type(resource_type)
    if not user_access and not user_group_access and public_access is None:
        raise typer.BadParameter(
            "pass at least one of --public-access / --user-access / --user-group-access",
        )
    resolved_uids = list(uids) if uids else []
    if "-" in resolved_uids:
        resolved_uids.remove("-")
        resolved_uids.extend(line.strip() for line in sys.stdin if line.strip())
    if not resolved_uids:
        typer.echo(f"no UIDs supplied for {resource_type} — nothing to do")
        return

    try:
        result = asyncio.run(
            service.bulk_share_metadata(
                profile_from_env(),
                resource_type,
                resolved_uids,
                public_access=public_access,
                user_access=user_access,
                user_group_access=user_group_access,
                concurrency=concurrency,
                dry_run=dry_run,
            )
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if is_json_output():
        typer.echo(result.model_dump_json(indent=2, exclude_none=True))
        return

    mode = "preview" if result.dry_run else "applied"
    title = f"{resource_type} share {mode} ({result.matched} object{'s' if result.matched != 1 else ''})"
    table = Table(title=title)
    table.add_column("uid", style="cyan", no_wrap=True)
    table.add_column("public", justify="center")
    table.add_column("user grants", overflow="fold")
    table.add_column("user-group grants", overflow="fold")
    for entry in result.entries:
        table.add_row(
            entry.uid,
            entry.public_access,
            ", ".join(entry.user_grants) or "-",
            ", ".join(entry.user_group_grants) or "-",
        )
    _console.print(table)

    if result.dry_run:
        _console.print(
            f"[yellow]dry-run[/yellow] — drop --dry-run to apply {result.matched} sharing change"
            f"{'s' if result.matched != 1 else ''}",
        )
        return
    sharing_result = result.sharing_result
    if sharing_result is None:
        return
    if sharing_result.ok:
        _console.print(f"[green]applied[/green] {result.succeeded} share{'s' if result.succeeded != 1 else ''}")
    else:
        _console.print(
            f"[green]applied[/green] {result.succeeded}  [red]failed[/red] {result.failed}",
        )
        failure_table = Table(title=f"{resource_type} share failures")
        failure_table.add_column("uid", style="cyan", no_wrap=True)
        failure_table.add_column("status", justify="right")
        failure_table.add_column("message", overflow="fold")
        for failure in sharing_result.failures:
            failure_table.add_row(failure.uid, str(failure.status_code), failure.message)
        _console.print(failure_table)


@app.command("diff")
def diff_command(
    left: Annotated[
        Path,
        typer.Argument(help="Left-hand bundle — the 'source of truth' you're comparing against."),
    ],
    right: Annotated[
        Path | None,
        typer.Argument(
            help="Right-hand bundle. Omit with `--live` to diff against the connected DHIS2 instance.",
        ),
    ] = None,
    live: Annotated[
        bool,
        typer.Option(
            "--live",
            help=(
                "Use the connected DHIS2 instance as the right-hand side. "
                "Exports only the resource types present in the left bundle "
                "(no full-catalog fetch). Incompatible with a positional right arg."
            ),
        ),
    ] = False,
    show_uids: Annotated[
        bool,
        typer.Option("--show-uids", help="List up to 5 offending UIDs per per-resource row."),
    ] = False,
    ignore: Annotated[
        list[str] | None,
        typer.Option(
            "--ignore",
            help=(
                "Fields to skip when deciding if an object changed. Repeatable. "
                "Defaults cover DHIS2's per-instance noise (lastUpdated, createdBy, access, ...); "
                "pass `--ignore sharing` etc. to extend."
            ),
        ),
    ] = None,
) -> None:
    """Compare two metadata bundles (or one bundle against the live instance).

    Per-resource counts of create/update/delete. Objects that differ only on
    DHIS2's per-instance noise (lastUpdated, createdBy, etc.) are treated as
    unchanged by default — `--ignore` extends that list.
    """
    if (right is None) == (not live):
        raise typer.BadParameter("provide exactly one of a second positional bundle or --live")

    left_raw = json.loads(left.read_text(encoding="utf-8"))
    if not isinstance(left_raw, dict):
        raise typer.BadParameter(f"{left} is not a metadata bundle (expected a JSON object)")
    left_bundle = MetadataBundle.from_raw(left_raw)

    ignored = frozenset({*service._DEFAULT_IGNORED_FIELDS, *(ignore or ())})  # noqa: SLF001

    if live:
        profile = profile_from_env()
        typer.secho(f"exporting live instance ({profile.base_url}) to compare against {left.name} ...", err=True)
        diff = asyncio.run(
            service.diff_bundle_against_instance(
                profile,
                left_bundle,
                bundle_label=str(left),
                ignored_fields=ignored,
            )
        )
        # Swap label order so the table reads `left vs live` consistently (diff_bundle_against_instance
        # puts the instance on the left to match "what's on the instance vs what's in the file").
    else:
        right_raw = json.loads(right.read_text(encoding="utf-8"))  # type: ignore[union-attr]
        if not isinstance(right_raw, dict):
            raise typer.BadParameter(f"{right} is not a metadata bundle")
        right_bundle = MetadataBundle.from_raw(right_raw)
        diff = service.diff_bundles(
            left_bundle,
            right_bundle,
            left_label=str(left),
            right_label=str(right),
            ignored_fields=ignored,
        )

    if is_json_output():
        typer.echo(diff.model_dump_json(indent=2, exclude_none=True))
        return
    _render_diff(diff, show_uids=show_uids)


def _render_diff(diff: service.MetadataDiff, *, show_uids: bool) -> None:
    """Rich-render a MetadataDiff as a per-resource table + totals summary."""
    total_changed = diff.total_created + diff.total_updated + diff.total_deleted
    title = f"metadata diff — {diff.left_label} → {diff.right_label} ({total_changed} changed)"
    table = Table(title=title)
    table.add_column("resource", overflow="fold")
    table.add_column("created", justify="right", style="green")
    table.add_column("updated", justify="right", style="yellow")
    table.add_column("deleted", justify="right", style="red")
    table.add_column("unchanged", justify="right", style="dim")
    if show_uids:
        table.add_column("sample UIDs", overflow="fold", style="dim")

    for resource in diff.resources:
        if resource.total_changed == 0 and resource.unchanged_count == 0:
            continue
        row = [
            resource.resource,
            str(len(resource.created)),
            str(len(resource.updated)),
            str(len(resource.deleted)),
            str(resource.unchanged_count),
        ]
        if show_uids:
            sample = []
            for change in (*resource.created, *resource.updated, *resource.deleted)[:5]:
                label = change.name or "-"
                sample.append(f"{change.id} · {label}")
            row.append("\n".join(sample))
        table.add_row(*row)
    _console.print(table)
    summary = (
        f"[green]+{diff.total_created} created[/green] / "
        f"[yellow]~{diff.total_updated} updated[/yellow] / "
        f"[red]-{diff.total_deleted} deleted[/red] / "
        f"[dim]{diff.total_unchanged} unchanged[/dim]"
    )
    _console.print(summary)
    if diff.ignored_fields:
        _console.print(f"[dim]ignored fields: {', '.join(diff.ignored_fields)}[/dim]")


@app.command("diff-profiles")
def diff_profiles_command(
    profile_a: Annotated[str, typer.Argument(help="Name of the 'left' profile (source of truth).")],
    profile_b: Annotated[str, typer.Argument(help="Name of the 'right' profile (candidate).")],
    resources: Annotated[
        list[str] | None,
        typer.Option(
            "--resource",
            "-r",
            help=(
                "Resource type to compare (e.g. dataElements, indicators). Repeatable. "
                "Required — whole-instance diffs are almost always noise."
            ),
        ),
    ] = None,
    filters: Annotated[
        list[str] | None,
        typer.Option(
            "--filter",
            help=(
                "Per-resource filter in `resource:property:operator:value` form. Repeatable. "
                "Example: `--filter dataElements:name:like:ANC` only compares data elements whose "
                "name contains 'ANC'. Same DHIS2 filter DSL as `dhis2 metadata list --filter`."
            ),
        ),
    ] = None,
    fields: Annotated[
        str,
        typer.Option(
            "--fields",
            help=(
                "DHIS2 field selector applied on both profiles. Defaults to ':owner' — the selector "
                "DHIS2 itself uses for cross-instance imports (preserves every field needed for a "
                "faithful round-trip)."
            ),
        ),
    ] = ":owner",
    ignore: Annotated[
        list[str] | None,
        typer.Option(
            "--ignore",
            help=(
                "Additional fields to skip when deciding if an object changed. Repeatable. "
                "Defaults already cover DHIS2's per-instance noise (lastUpdated, createdBy, access, ...). "
                "Common extensions for drift checks: `--ignore sharing --ignore translations`."
            ),
        ),
    ] = None,
    show_uids: Annotated[
        bool,
        typer.Option("--show-uids", help="List up to 5 offending UIDs per per-resource row."),
    ] = False,
    exit_on_drift: Annotated[
        bool,
        typer.Option(
            "--exit-on-drift",
            help="Exit 1 when any object differs. CI-friendly (default is always exit 0).",
        ),
    ] = False,
) -> None:
    """Diff a metadata slice between two registered profiles (staging vs prod drift).

    Runs both exports in parallel, narrows to `--resource` types, optionally
    filters each resource (`--filter resource:prop:op:val`), then structurally
    diffs the two bundles ignoring DHIS2's per-instance noise
    (timestamps, createdBy, access strings, …).

    A whole-instance diff is almost never useful — staging and prod diverge on
    user accounts, org-unit assignments, and incidental settings by design. Pick
    a narrow resource slice (`-r dataElements -r indicators`), filter further
    with `--filter`, and extend `--ignore` for anything else that's expected to
    differ.

    Exit code is `0` by default regardless of drift (so operators running this
    interactively aren't tripped by per-command-exit conventions). Pass
    `--exit-on-drift` for the CI shape.
    """
    from dhis2w_core.profile import UnknownProfileError, resolve_profile

    if not resources:
        raise typer.BadParameter("pass at least one --resource (see `dhis2 metadata type ls`)")

    try:
        resolved_a = resolve_profile(profile_a)
        resolved_b = resolve_profile(profile_b)
    except UnknownProfileError as exc:
        raise typer.BadParameter(str(exc)) from exc

    per_resource_filters = _parse_per_resource_filters(filters or [])
    ignored = frozenset({*service._DEFAULT_IGNORED_FIELDS, *(ignore or ())})  # noqa: SLF001

    typer.secho(
        f"exporting {','.join(resources)} from {profile_a!r} ({resolved_a.base_url}) "
        f"and {profile_b!r} ({resolved_b.base_url}) ...",
        err=True,
    )
    diff = asyncio.run(
        service.diff_profiles(
            resolved_a,
            resolved_b,
            resources=list(resources),
            left_label=profile_a,
            right_label=profile_b,
            fields=fields,
            per_resource_filters=per_resource_filters,
            ignored_fields=ignored,
        )
    )

    if is_json_output():
        typer.echo(diff.model_dump_json(indent=2, exclude_none=True))
    else:
        _render_diff(diff, show_uids=show_uids)

    if exit_on_drift and (diff.total_created + diff.total_updated + diff.total_deleted) > 0:
        raise typer.Exit(1)


@app.command("merge")
def merge_command(
    source_profile: Annotated[str, typer.Argument(help="Source profile — the `--from` side of the merge.")],
    target_profile: Annotated[str, typer.Argument(help="Target profile — where the source's resources land.")],
    resources: Annotated[
        list[str] | None,
        typer.Option(
            "--resource",
            "-r",
            help=(
                "Resource type to merge (e.g. dataElements, indicators). Repeatable. "
                "Required — whole-instance merges are almost never what you want."
            ),
        ),
    ] = None,
    filters: Annotated[
        list[str] | None,
        typer.Option(
            "--filter",
            help=(
                "Per-resource filter in `resource:property:operator:value` form. Repeatable. "
                "Same DSL as `dhis2 metadata list --filter` and `dhis2 metadata diff-profiles`."
            ),
        ),
    ] = None,
    fields: Annotated[
        str,
        typer.Option(
            "--fields",
            help="DHIS2 field selector applied on the source export. Defaults to ':owner' (faithful round-trip).",
        ),
    ] = ":owner",
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            help="Import strategy — CREATE / UPDATE / CREATE_AND_UPDATE / DELETE (default: CREATE_AND_UPDATE).",
        ),
    ] = "CREATE_AND_UPDATE",
    atomic: Annotated[
        str,
        typer.Option(
            "--atomic",
            help="atomicMode — ALL / NONE (default: ALL; one broken object aborts the whole import).",
        ),
    ] = "ALL",
    include_sharing: Annotated[
        bool,
        typer.Option(
            "--include-sharing/--skip-sharing",
            help=(
                "Carry sharing blocks across. OFF by default — different instances typically have "
                "different user / group UIDs and sharing imports fail with false-positive conflicts."
            ),
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Send `importMode=VALIDATE` to the target; reports conflicts + counts without committing.",
        ),
    ] = False,
) -> None:
    """Export resources from one profile and import them into another.

    Pairs with `dhis2 metadata diff-profiles` (which reads the same shape
    of narrow resource slice + filters). Preview first with
    `diff-profiles`, then apply the same `--resource` + `--filter` args
    through `merge` to land the changes on the target.

    Require `--resource` — a whole-instance merge would overwrite users,
    org units, and incidental settings that staging and prod routinely
    differ on for non-drift reasons.

    `--dry-run` flips the target import into `importMode=VALIDATE`.
    DHIS2 walks the bundle, reports conflicts + stats, and commits
    nothing. Use to catch "this object references a user UID that
    doesn't exist on the target" before the real run.
    """
    from dhis2w_core.profile import UnknownProfileError, resolve_profile

    if not resources:
        raise typer.BadParameter("pass at least one --resource (see `dhis2 metadata type ls`)")

    try:
        resolved_source = resolve_profile(source_profile)
        resolved_target = resolve_profile(target_profile)
    except UnknownProfileError as exc:
        raise typer.BadParameter(str(exc)) from exc

    per_resource_filters = _parse_per_resource_filters(filters or [])

    typer.secho(
        f"merging {','.join(resources)} from {source_profile!r} ({resolved_source.base_url}) "
        f"into {target_profile!r} ({resolved_target.base_url})"
        f"{' [DRY-RUN]' if dry_run else ''} ...",
        err=True,
    )
    result = asyncio.run(
        service.merge_metadata(
            resolved_source,
            resolved_target,
            resources=list(resources),
            per_resource_filters=per_resource_filters,
            fields=fields,
            import_strategy=strategy,
            atomic_mode=atomic,
            dry_run=dry_run,
            skip_sharing=not include_sharing,
        ),
    )

    if is_json_output():
        typer.echo(result.model_dump_json(indent=2, exclude_none=True))
        return

    counts = result.export_counts
    total_exported = sum(counts.values())
    badge = "[yellow]DRY RUN[/yellow]" if result.dry_run else "[green]APPLIED[/green]"
    _console.print(f"{badge}  {total_exported} exported objects across {len(counts)} resource types")
    table = Table(title=f"exported objects by resource (source: {result.source_base_url})")
    table.add_column("resource", style="cyan", no_wrap=True)
    table.add_column("exported", justify="right")
    for resource, count in counts.items():
        table.add_row(resource, str(count))
    _console.print(table)
    envelope = result.import_report
    status = (envelope.status or "OK").upper()
    status_color = "green" if status == "OK" else "red"
    _console.print(
        f"\nimport target: {result.target_base_url}\n"
        f"  [bold {status_color}]{status}[/bold {status_color}]  {envelope.message or '(no message)'}",
    )
    import_count = envelope.import_count()
    if import_count is not None:
        _console.print(
            f"  imported={import_count.imported}  updated={import_count.updated}  "
            f"ignored={import_count.ignored}  deleted={import_count.deleted}",
        )
    conflict_rows = envelope.conflict_rows()
    if conflict_rows:
        _console.print(f"\n  [red]conflicts: {len(conflict_rows)}[/red]")
        render_conflicts(conflict_rows, limit=25, console=_console)


@app.command("merge-bundle")
def merge_bundle_command(
    target_profile: Annotated[str, typer.Argument(help="Target profile — where the bundle's resources land.")],
    bundle: Annotated[
        Path,
        typer.Argument(
            help="Path to a JSON metadata bundle (the shape `GET /api/metadata` returns).",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    resources: Annotated[
        list[str] | None,
        typer.Option(
            "--resource",
            "-r",
            help=(
                "Resource type to include in the count summary (e.g. dataElements). Repeatable. "
                "Optional — when omitted, every resource section in the bundle is reported."
            ),
        ),
    ] = None,
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            help="Import strategy — CREATE / UPDATE / CREATE_AND_UPDATE / DELETE (default: CREATE_AND_UPDATE).",
        ),
    ] = "CREATE_AND_UPDATE",
    atomic: Annotated[
        str,
        typer.Option(
            "--atomic",
            help="atomicMode — ALL / NONE (default: ALL; one broken object aborts the whole import).",
        ),
    ] = "ALL",
    include_sharing: Annotated[
        bool,
        typer.Option(
            "--include-sharing/--skip-sharing",
            help=(
                "Carry sharing blocks across. OFF by default — different instances typically have "
                "different user / group UIDs and sharing imports fail with false-positive conflicts."
            ),
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Send `importMode=VALIDATE` to the target; reports conflicts + counts without committing.",
        ),
    ] = False,
) -> None:
    """Import a saved bundle file into a target profile.

    The bundle-source variant of `dhis2 metadata merge`: instead of
    exporting from a source profile, read the bundle from disk. Useful
    when the bundle came from a saved `metadata export`, was hand-crafted
    by an operator, or was produced by a non-DHIS2 tool. All other
    semantics match `merge` — atomic + sharing skipped by default,
    `--dry-run` flips to `importMode=VALIDATE`.
    """
    from dhis2w_core.profile import UnknownProfileError, resolve_profile

    try:
        resolved_target = resolve_profile(target_profile)
    except UnknownProfileError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.secho(
        f"merging bundle {bundle} into {target_profile!r} ({resolved_target.base_url})"
        f"{' [DRY-RUN]' if dry_run else ''} ...",
        err=True,
    )
    result = asyncio.run(
        service.merge_metadata_from_bundle(
            resolved_target,
            bundle,
            resources=list(resources) if resources else None,
            import_strategy=strategy,
            atomic_mode=atomic,
            dry_run=dry_run,
            skip_sharing=not include_sharing,
        ),
    )

    if is_json_output():
        typer.echo(result.model_dump_json(indent=2, exclude_none=True))
        return

    counts = result.export_counts
    total_exported = sum(counts.values())
    typer.secho(
        f"\nbundle: {total_exported} object{'s' if total_exported != 1 else ''} across "
        f"{len(counts)} resource{'s' if len(counts) != 1 else ''}",
        err=True,
    )
    for name in sorted(counts):
        typer.secho(f"  {name}: {counts[name]}", err=True)

    envelope = result.import_report
    typer.secho(
        f"\nimport [{envelope.status or '?'}] http={envelope.httpStatusCode or '?'}"
        f"{' [DRY-RUN]' if result.dry_run else ''}",
        err=True,
    )
    import_count = envelope.import_count()
    if import_count is not None:
        typer.secho(
            f"  imported={import_count.imported}  updated={import_count.updated}  "
            f"ignored={import_count.ignored}  deleted={import_count.deleted}",
        )
    conflict_rows = envelope.conflict_rows()
    if conflict_rows:
        _console.print(f"\n  [red]conflicts: {len(conflict_rows)}[/red]")
        render_conflicts(conflict_rows, limit=25, console=_console)


def _parse_per_resource_filters(specs: list[str]) -> dict[str, list[str]]:
    """Parse `resource:property:operator:value` strings into a per-resource filter map.

    Only the first `:` separates resource name from the filter expression; the
    rest is forwarded verbatim to DHIS2 (it already takes `property:operator:value`
    as a single string). So `dataElements:name:like:ANC` parses to
    `{"dataElements": ["name:like:ANC"]}` — multiple filters on the same resource
    merge into the list.
    """
    parsed: dict[str, list[str]] = {}
    for spec in specs:
        if ":" not in spec:
            raise typer.BadParameter(
                f"--filter {spec!r}: expected `resource:property:operator:value` "
                "(first `:` splits the resource from the filter expression)."
            )
        resource, _, expression = spec.partition(":")
        if not resource or not expression:
            raise typer.BadParameter(
                f"--filter {spec!r}: both resource and filter expression must be non-empty.",
            )
        parsed.setdefault(resource, []).append(expression)
    return parsed


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `dhis2 metadata`."""
    root_app.add_typer(app, name="metadata", help="DHIS2 metadata inspection.")


# ---------------------------------------------------------------------------
# `dhis2 metadata options ...` — OptionSet workflow commands
# ---------------------------------------------------------------------------


@options_app.command("get")
def options_get_command(
    uid_or_code: Annotated[str, typer.Argument(help="OptionSet UID (11 chars) or business code.")],
) -> None:
    """Show one OptionSet with its options resolved inline."""
    option_set = asyncio.run(service.show_option_set(profile_from_env(), uid_or_code))
    if option_set is None:
        typer.secho(f"no OptionSet with code/uid {uid_or_code!r}", err=True, fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    if is_json_output():
        typer.echo(option_set.model_dump_json(indent=2, exclude_none=True))
        return
    header = (
        f"[bold]{option_set.name or '-'}[/bold]  "
        f"code=[cyan]{option_set.code or '-'}[/cyan]  "
        f"uid=[dim]{option_set.id or '-'}[/dim]  "
        f"valueType={option_set.valueType or '-'}"
    )
    _console.print(header)
    options = option_set.options or []
    if not options:
        typer.echo("  (no options)")
        return
    table = Table(title=f"options ({len(options)})")
    table.add_column("sort", justify="right", style="dim")
    table.add_column("code", style="cyan")
    table.add_column("name", overflow="fold")
    table.add_column("uid", style="dim")
    for opt in options:
        if isinstance(opt, dict):
            sort_order = opt.get("sortOrder")
            code = opt.get("code") or "-"
            name = opt.get("name") or "-"
            uid = opt.get("id") or "-"
        else:
            sort_order = getattr(opt, "sortOrder", None)
            code = getattr(opt, "code", None) or "-"
            name = getattr(opt, "name", None) or "-"
            uid = getattr(opt, "id", None) or "-"
        table.add_row(str(sort_order) if sort_order is not None else "-", code, name, uid)
    _console.print(table)


@options_app.command("find")
def options_find_command(
    set_ref: Annotated[str, typer.Option("--set", help="OptionSet UID or business code.")],
    option_code: Annotated[
        str | None,
        typer.Option("--code", help="Business code of the option to locate."),
    ] = None,
    option_name: Annotated[
        str | None,
        typer.Option("--name", help="Display name of the option (exact match)."),
    ] = None,
) -> None:
    """Locate a single option inside a set by code or name; exit 1 if no match."""
    if (option_code is None) == (option_name is None):
        raise typer.BadParameter("exactly one of --code / --name is required")
    option = asyncio.run(
        service.find_option_in_set(
            profile_from_env(),
            option_set_uid_or_code=set_ref,
            option_code=option_code,
            option_name=option_name,
        )
    )
    if option is None:
        typer.secho("no match", err=True, fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    if is_json_output():
        typer.echo(option.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[cyan]{option.code or '-'}[/cyan]  {option.name or '-'!r}  "
        f"uid=[dim]{option.id or '-'}[/dim]  "
        f"sort=[dim]{option.sortOrder if option.sortOrder is not None else '-'}[/dim]"
    )


@options_app.command("create")
def options_create_command(
    name: Annotated[str, typer.Option("--name", help="OptionSet name.")],
    value_type: Annotated[str, typer.Option("--value-type", help="DHIS2 ValueType, e.g. TEXT / NUMBER / INTEGER.")],
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create an OptionSet (then add its options with `options sync`)."""
    from dhis2w_core.v43.cli_output import render_webmessage  # noqa: PLC0415

    response = asyncio.run(
        service.create_option_set(profile_from_env(), name=name, value_type=value_type, code=code, uid=uid)
    )
    render_webmessage(response, action="created")


@options_app.command("delete")
def options_delete_command(
    uid: Annotated[str, typer.Argument(help="OptionSet UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Delete an OptionSet by UID."""
    if not yes and not typer.confirm(f"Delete optionSet {uid}?"):
        raise typer.Abort()
    asyncio.run(service.delete_option_set(profile_from_env(), uid))
    _emit_mutation(f"deleted optionSet {uid}")


@options_app.command("sync")
def options_sync_command(
    set_ref: Annotated[str, typer.Argument(help="OptionSet UID or business code.")],
    spec_file: Annotated[
        Path,
        typer.Argument(
            help="JSON file — list of `{code, name, sort_order?}` objects.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    remove_missing: Annotated[
        bool,
        typer.Option(
            "--remove-missing",
            help="Also delete options whose code isn't in the spec. Off by default — safer for partial refreshes.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Compute the diff without writing anything."),
    ] = False,
) -> None:
    """Idempotently sync an OptionSet to match a JSON spec file.

    The spec is a JSON array of `{code, name, sort_order?}` objects. Codes
    not currently in the set get **added**; codes present but with changed
    names or sort order get **updated**; exact matches are **skipped**.
    Pass `--remove-missing` to also drop options whose code isn't in the
    spec. `--dry-run` previews the diff without writing.
    """
    from dhis2w_client.v43 import OptionSpec  # noqa: PLC0415 — avoid top-level import for CLI fast-path

    raw = json.loads(spec_file.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise typer.BadParameter(f"spec file {spec_file} must contain a JSON array of objects")
    spec: list[OptionSpec] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise typer.BadParameter(f"spec[{index}] is not a JSON object")
        spec.append(OptionSpec.model_validate(entry))

    report = asyncio.run(
        service.sync_option_set(
            profile_from_env(),
            option_set_uid_or_code=set_ref,
            spec=spec,
            remove_missing=remove_missing,
            dry_run=dry_run,
        )
    )
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    title = "sync report (dry-run)" if dry_run else "sync report"
    table = Table(title=title)
    table.add_column("action", style="cyan")
    table.add_column("count", justify="right")
    table.add_column("codes", overflow="fold")
    for action, codes, style in (
        ("added", report.added, "green"),
        ("updated", report.updated, "yellow"),
        ("removed", report.removed, "red"),
        ("skipped", report.skipped, "dim"),
    ):
        table.add_row(f"[{style}]{action}[/{style}]", str(len(codes)), ", ".join(codes) or "-")
    _console.print(table)


# ---------------------------------------------------------------------------
# `dhis2 metadata options attribute ...` — external-system code mapping
# ---------------------------------------------------------------------------


@options_attribute_app.command("get")
def options_attribute_get_command(
    option_uid: Annotated[str, typer.Argument(help="Option UID (11 chars).")],
    attribute: Annotated[
        str,
        typer.Argument(help="Attribute UID or business code (e.g. 'SNOMED_CODE')."),
    ],
) -> None:
    """Read one attribute value off an Option; exit 1 if unset."""
    value = asyncio.run(
        service.get_option_attribute_value(
            profile_from_env(),
            option_uid=option_uid,
            attribute_code_or_uid=attribute,
        )
    )
    if value is None:
        typer.secho(f"no value for attribute {attribute!r} on {option_uid}", err=True, fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    typer.echo(value)


@options_attribute_app.command("set")
def options_attribute_set_command(
    option_uid: Annotated[str, typer.Argument(help="Option UID (11 chars).")],
    attribute: Annotated[
        str,
        typer.Argument(help="Attribute UID or business code (e.g. 'SNOMED_CODE')."),
    ],
    value: Annotated[str, typer.Argument(help="New attribute value.")],
) -> None:
    """Set / replace an attribute value on an Option.

    Reads the full Option, merges the new value (replaces any prior value
    for the same attribute UID), PUTs the payload back. DHIS2's
    attribute-value list is identity-keyed by attribute UID, so this is
    idempotent — calling twice with the same value is a no-op.
    """
    asyncio.run(
        service.set_option_attribute_value(
            profile_from_env(),
            option_uid=option_uid,
            attribute_code_or_uid=attribute,
            value=value,
        )
    )
    typer.secho(f"set {attribute}={value!r} on {option_uid}", fg=typer.colors.GREEN)


@options_attribute_app.command("find")
def options_attribute_find_command(
    set_ref: Annotated[str, typer.Option("--set", help="OptionSet UID or business code.")],
    attribute: Annotated[
        str,
        typer.Option("--attribute", help="Attribute UID or business code (e.g. 'SNOMED_CODE')."),
    ],
    value: Annotated[str, typer.Option("--value", help="Attribute value to match exactly.")],
) -> None:
    """Reverse lookup — find the Option whose attribute matches a value.

    The killer integration helper: external systems know a SNOMED / ICD /
    LOINC code; this command returns the DHIS2 Option it maps to. Exits 1
    on miss with a stderr hint.
    """
    option = asyncio.run(
        service.find_option_by_attribute(
            profile_from_env(),
            option_set_uid_or_code=set_ref,
            attribute_code_or_uid=attribute,
            value=value,
        )
    )
    if option is None:
        typer.secho(f"no Option with {attribute}={value!r} in set {set_ref!r}", err=True, fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    if is_json_output():
        typer.echo(option.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[cyan]{option.code or '-'}[/cyan]  {option.name or '-'!r}  "
        f"uid=[dim]{option.id or '-'}[/dim]  "
        f"sort=[dim]{option.sortOrder if option.sortOrder is not None else '-'}[/dim]"
    )


# ---------------------------------------------------------------------------
# `dhis2 metadata attribute ...` — cross-resource AttributeValue workflows
# ---------------------------------------------------------------------------


@attribute_app.command("get")
def attribute_get_command(
    resource: Annotated[
        str,
        typer.Argument(help="Plural DHIS2 resource name (e.g. `dataElements`, `options`, `organisationUnits`)."),
    ],
    resource_uid: Annotated[str, typer.Argument(help="UID of the resource instance.")],
    attribute: Annotated[
        str,
        typer.Argument(help="Attribute UID or business code (e.g. `ICD10_CODE`)."),
    ],
) -> None:
    """Read one attribute value off any resource; exit 1 if unset."""
    value = asyncio.run(
        service.get_attribute_value(
            profile_from_env(),
            resource=resource,
            resource_uid=resource_uid,
            attribute_code_or_uid=attribute,
        )
    )
    if value is None:
        typer.secho(
            f"no value for attribute {attribute!r} on {resource}/{resource_uid}",
            err=True,
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    typer.echo(value)


@attribute_app.command("set")
def attribute_set_command(
    resource: Annotated[str, typer.Argument(help="Plural DHIS2 resource name.")],
    resource_uid: Annotated[str, typer.Argument(help="UID of the resource instance.")],
    attribute: Annotated[str, typer.Argument(help="Attribute UID or business code.")],
    value: Annotated[str, typer.Argument(help="New attribute value.")],
) -> None:
    """Set / replace one attribute value on any resource (read-merge-write)."""
    asyncio.run(
        service.set_attribute_value(
            profile_from_env(),
            resource=resource,
            resource_uid=resource_uid,
            attribute_code_or_uid=attribute,
            value=value,
        )
    )
    typer.secho(f"set {attribute}={value!r} on {resource}/{resource_uid}", fg=typer.colors.GREEN)


@attribute_app.command("delete")
def attribute_delete_command(
    resource: Annotated[str, typer.Argument(help="Plural DHIS2 resource name.")],
    resource_uid: Annotated[str, typer.Argument(help="UID of the resource instance.")],
    attribute: Annotated[str, typer.Argument(help="Attribute UID or business code.")],
) -> None:
    """Remove one attribute value from any resource; exit 0 regardless of whether it existed."""
    removed = asyncio.run(
        service.delete_attribute_value(
            profile_from_env(),
            resource=resource,
            resource_uid=resource_uid,
            attribute_code_or_uid=attribute,
        )
    )
    if removed:
        typer.secho(f"removed {attribute} on {resource}/{resource_uid}", fg=typer.colors.GREEN)
    else:
        typer.secho(
            f"no-op — {attribute} was not set on {resource}/{resource_uid}",
            fg=typer.colors.YELLOW,
        )


@attribute_app.command("find")
def attribute_find_command(
    resource: Annotated[str, typer.Argument(help="Plural DHIS2 resource name.")],
    attribute: Annotated[str, typer.Argument(help="Attribute UID or business code.")],
    value: Annotated[str, typer.Argument(help="Attribute value to match exactly.")],
    extra_filter: Annotated[
        list[str] | None,
        typer.Option(
            "--filter",
            help=("Extra DHIS2 filter constraints to narrow the search (e.g. `domainType:eq:AGGREGATE`). Repeatable."),
        ),
    ] = None,
) -> None:
    """Reverse lookup across any resource — list every UID whose attribute value matches.

    Returns UIDs only (one per line) to keep the helper generic across
    resource types. Pipe into `dhis2 metadata get <resource> <uid>` or
    `dhis2 metadata list <resource> --filter id:in:[...]` for typed
    follow-ups.
    """
    uids = asyncio.run(
        service.find_resources_by_attribute(
            profile_from_env(),
            resource=resource,
            attribute_code_or_uid=attribute,
            value=value,
            extra_filters=extra_filter,
        )
    )
    if not uids:
        typer.secho(
            f"no {resource} with {attribute}={value!r}",
            err=True,
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    for uid in uids:
        typer.echo(uid)


# ---------------------------------------------------------------------------
# `dhis2 metadata program-rule ...` — tracker business-logic workflows
# ---------------------------------------------------------------------------


@program_rule_app.command("get")
def program_rule_get_command(
    rule_uid: Annotated[str, typer.Argument(help="ProgramRule UID.")],
) -> None:
    """Show one ProgramRule with its condition, priority, and every action."""
    rule = asyncio.run(service.show_program_rule(profile_from_env(), rule_uid))
    if is_json_output():
        typer.echo(rule.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[bold]{rule.name or '-'}[/bold]  "
        f"uid=[dim]{rule.id or '-'}[/dim]  "
        f"priority=[dim]{rule.priority if rule.priority is not None else '-'}[/dim]",
    )
    if rule.description:
        _console.print(f"  {rule.description}")
    _console.print(f"  condition: [cyan]{rule.condition or '-'}[/cyan]")
    actions = rule.programRuleActions or []
    if not actions:
        _console.print("  (no actions)")
        return
    table = Table(title=f"actions ({len(actions)})")
    table.add_column("type", style="cyan")
    table.add_column("target", overflow="fold")
    table.add_column("content / data", overflow="fold")
    for action in actions:
        if isinstance(action, dict):
            action_type = action.get("programRuleActionType") or "-"
            de_id = (action.get("dataElement") or {}).get("id") if isinstance(action.get("dataElement"), dict) else None
            tea_id = (action.get("attribute") or {}).get("id") if isinstance(action.get("attribute"), dict) else None
            content = action.get("content") or action.get("data") or "-"
        else:
            extras = getattr(action, "model_extra", None) or {}
            action_type = extras.get("programRuleActionType") or getattr(action, "programRuleActionType", None) or "-"
            de = getattr(action, "dataElement", None)
            de_id = getattr(de, "id", None) if de is not None else None
            attr = extras.get("attribute") if isinstance(extras.get("attribute"), dict) else None
            tea_id = attr.get("id") if attr else None
            content = action.content or action.data or "-"
        target = de_id or tea_id or "-"
        table.add_row(str(action_type), target, str(content))
    _console.print(table)


@program_rule_app.command("vars-for")
def program_rule_vars_for_command(
    program_uid: Annotated[str, typer.Argument(help="Program UID.")],
) -> None:
    """List every `ProgramRuleVariable` in scope for a program, sorted by name."""
    variables = asyncio.run(service.list_program_rule_variables(profile_from_env(), program_uid))
    if is_json_output():
        typer.echo("[" + ",".join(v.model_dump_json(exclude_none=True) for v in variables) + "]")
        return
    if not variables:
        typer.echo("no program rule variables for this program")
        return
    table = Table(title=f"variables ({len(variables)})")
    table.add_column("name", style="cyan")
    table.add_column("source type", style="dim")
    table.add_column("target", overflow="fold")
    table.add_column("uid", style="dim", no_wrap=True)
    for var in variables:
        extras = getattr(var, "model_extra", None) or {}
        source_type = (
            getattr(var, "programRuleVariableSourceType", None) or extras.get("programRuleVariableSourceType") or "-"
        )
        de = getattr(var, "dataElement", None)
        de_id = getattr(de, "id", None) if de is not None else None
        attr = extras.get("trackedEntityAttribute") or extras.get("attribute")
        tea_id = attr.get("id") if isinstance(attr, dict) else None
        target = de_id or tea_id or "-"
        table.add_row(var.name or "-", str(source_type), target, var.id or "-")
    _console.print(table)


@program_rule_app.command("validate-expression")
def program_rule_validate_expression_command(
    expression: Annotated[str, typer.Argument(help="Program-rule condition expression.")],
    context: Annotated[
        str,
        typer.Option(
            "--context",
            help=(
                "Which DHIS2 expression parser to use: program-indicator (default), "
                "validation-rule, indicator, predictor, or generic."
            ),
        ),
    ] = "program-indicator",
) -> None:
    """Parse-check a program-rule condition expression.

    DHIS2 doesn't expose a dedicated program-rule expression validator —
    the closest is the program-indicator parser (used by default here),
    which enforces stricter `#{stage.de}` syntax than program rules
    accept. For the common `#{variableName}` shorthand program rules
    use, the PI validator flags "Invalid Program Stage / DataElement
    syntax" — not a real error, just the parser mismatch. Trust a clean
    OK as definitely valid; read the specific message on ERROR to
    distinguish parser mismatches from real syntax problems.
    """
    result = asyncio.run(
        service.validate_program_rule_expression(profile_from_env(), expression, context=context),
    )
    status_colour = "green" if result.valid else "red"
    _console.print(
        f"[{status_colour}]{result.status or '-'}[/{status_colour}]  message: {result.message or '-'}",
    )
    if result.description:
        _console.print(f"  rendered: {result.description}")
    if not result.valid:
        raise typer.Exit(1)


@program_rule_app.command("where-de-is-used")
def program_rule_where_de_is_used_command(
    data_element_uid: Annotated[str, typer.Argument(help="DataElement UID.")],
) -> None:
    """Impact analysis — list every rule whose actions reference this DataElement.

    Useful before renaming / removing a DE: catches rules that'd stop
    firing once the reference breaks. Exit 1 if nothing matches (safe
    shorthand for `grep -q` pipelines).
    """
    rules = asyncio.run(
        service.program_rules_using_data_element(profile_from_env(), data_element_uid),
    )
    if not rules:
        typer.secho(
            f"no rules reference dataElement {data_element_uid!r}",
            err=True,
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    table = Table(title=f"rules referencing {data_element_uid} ({len(rules)})")
    table.add_column("uid", style="cyan", no_wrap=True)
    table.add_column("priority", justify="right", style="dim")
    table.add_column("name", overflow="fold")
    for rule in rules:
        table.add_row(
            rule.id or "-",
            str(rule.priority if rule.priority is not None else "-"),
            rule.name or "-",
        )
    _console.print(table)


def _parse_key_value_pairs(values: list[str] | None, *, flag_name: str) -> dict[str, str]:
    """Split `key:value` CLI flags (repeated) into a flat dict. Raises typer.Exit(2) on malformed input."""
    result: dict[str, str] = {}
    if not values:
        return result
    for entry in values:
        if ":" not in entry:
            typer.secho(
                f"invalid --{flag_name} value {entry!r}: expected key:value",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(2)
        key, _, value = entry.partition(":")
        result[key.strip()] = value
    return result


def _render_sql_view_result(result: Any, *, fmt: str) -> None:
    """Render a SqlViewResult to stdout — Rich table, JSON array of dicts, or CSV."""
    import csv as _csv  # noqa: PLC0415
    import io as _io  # noqa: PLC0415

    columns = [column.name for column in result.columns]
    if fmt == "json":
        typer.echo(json.dumps(result.as_dicts(), indent=2, default=str))
        return
    if fmt == "csv":
        buffer = _io.StringIO()
        writer = _csv.writer(buffer)
        writer.writerow(columns)
        for row in result.rows:
            writer.writerow(row)
        typer.echo(buffer.getvalue().rstrip("\n"))
        return
    title = result.title or f"{len(result.rows)} rows"
    table = Table(title=title)
    for name in columns:
        table.add_column(name, overflow="fold")
    for row in result.rows:
        padded = list(row) + [None] * (len(columns) - len(row))
        table.add_row(*[("-" if cell is None else str(cell)) for cell in padded[: len(columns)]])
    _console.print(table)


@sql_view_app.command("get")
def sql_view_get_command(
    view_uid: Annotated[str, typer.Argument(help="SqlView UID.")],
) -> None:
    """Show one SqlView's metadata + its stored SQL body."""
    view = asyncio.run(service.show_sql_view(profile_from_env(), view_uid))
    if is_json_output():
        typer.echo(view.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[bold]{view.name or '-'}[/bold]  uid=[dim]{view.id or '-'}[/dim]  type=[dim]{view.type or '-'}[/dim]",
    )
    if view.description:
        _console.print(f"  {view.description}")
    if view.sqlQuery:
        _console.print("  [dim]sqlQuery:[/dim]")
        for line in view.sqlQuery.splitlines() or [view.sqlQuery]:
            _console.print(f"    [cyan]{line}[/cyan]")


@sql_view_app.command("execute")
def sql_view_execute_command(
    view_uid: Annotated[str, typer.Argument(help="SqlView UID.")],
    variables: Annotated[
        list[str] | None,
        typer.Option(
            "--var",
            help=(
                "`${name}` substitution for QUERY views, in `name:value` form. Repeatable. "
                "DHIS2 strips non-alphanumeric characters from values server-side — wildcards belong in the SQL."
            ),
        ),
    ] = None,
    criteria: Annotated[
        list[str] | None,
        typer.Option(
            "--criteria",
            help="Column filter for VIEW / MATERIALIZED_VIEW results, in `column:value` form. Repeatable.",
        ),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table (default), json, or csv."),
    ] = "table",
) -> None:
    """Run a SqlView and render its rows as a table, JSON array, or CSV."""
    if fmt not in {"table", "json", "csv"}:
        typer.secho(f"unknown --format {fmt!r}: expected table, json, or csv", err=True, fg=typer.colors.RED)
        raise typer.Exit(2)
    var_map = _parse_key_value_pairs(variables, flag_name="var")
    criteria_map = _parse_key_value_pairs(criteria, flag_name="criteria")
    result = asyncio.run(
        service.execute_sql_view(
            profile_from_env(),
            view_uid,
            variables=var_map or None,
            criteria=criteria_map or None,
        ),
    )
    _render_sql_view_result(result, fmt=fmt)


@sql_view_app.command("refresh")
def sql_view_refresh_command(
    view_uid: Annotated[str, typer.Argument(help="SqlView UID.")],
) -> None:
    """Refresh a MATERIALIZED_VIEW or lazily create a VIEW's DB object.

    `POST /api/sqlViews/{uid}/execute` is idempotent for VIEW types — the
    first call creates the Postgres view; subsequent calls are no-ops.
    MATERIALIZED_VIEW types re-run the underlying SQL each call.
    """
    response = asyncio.run(service.refresh_sql_view(profile_from_env(), view_uid))
    render_webmessage(response, as_json=False, action="refreshed")


@sql_view_app.command("adhoc")
def sql_view_adhoc_command(
    name: Annotated[str, typer.Argument(help="Display name for the throwaway view.")],
    sql_path: Annotated[Path, typer.Argument(help=".sql file containing the query body.")],
    view_type: Annotated[
        str,
        typer.Option("--type", help="SqlViewType — QUERY (default), VIEW, or MATERIALIZED_VIEW."),
    ] = "QUERY",
    keep: Annotated[
        bool,
        typer.Option("--keep", help="Leave the view in place afterwards instead of deleting."),
    ] = False,
    variables: Annotated[
        list[str] | None,
        typer.Option("--var", help="`${name}` substitution in `name:value` form. Repeatable."),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table (default), json, or csv."),
    ] = "table",
) -> None:
    """Register a throwaway SqlView from a .sql file, execute once, delete it on the way out.

    Designed for iterating on SQL without leaving test metadata behind.
    Subject to DHIS2's SQL allowlist — for fully free-form queries, see
    the Postgres injector example.
    """
    if not sql_path.is_file():
        typer.secho(f"SQL file not found: {sql_path}", err=True, fg=typer.colors.RED)
        raise typer.Exit(2)
    if fmt not in {"table", "json", "csv"}:
        typer.secho(f"unknown --format {fmt!r}: expected table, json, or csv", err=True, fg=typer.colors.RED)
        raise typer.Exit(2)
    sql = sql_path.read_text()
    var_map = _parse_key_value_pairs(variables, flag_name="var")
    result = asyncio.run(
        service.adhoc_sql_view(
            profile_from_env(),
            name,
            sql,
            view_type=view_type,
            keep=keep,
            variables=var_map or None,
        ),
    )
    _render_sql_view_result(result, fmt=fmt)


def _collect_dataDimensionItem_targets(items: Any) -> list[str]:
    """Pull `dataElement.id` out of each dataDimensionItem for display."""
    uids: list[str] = []
    for entry in items or []:
        if isinstance(entry, dict):
            de = entry.get("dataElement")
            if isinstance(de, dict):
                uid = de.get("id")
                if isinstance(uid, str):
                    uids.append(uid)
            continue
        de = getattr(entry, "dataElement", None)
        if de is not None:
            uid = getattr(de, "id", None)
            if isinstance(uid, str):
                uids.append(uid)
    return uids


@viz_app.command("get")
def viz_get_command(
    viz_uid: Annotated[str, typer.Argument(help="Visualization UID.")],
) -> None:
    """Show one Visualization with axes + data dimensions + period / ou selection."""
    viz = asyncio.run(service.show_visualization(profile_from_env(), viz_uid))
    if is_json_output():
        typer.echo(viz.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[bold]{viz.name or '-'}[/bold]  uid=[dim]{viz.id or '-'}[/dim]  type=[dim]{viz.type or '-'}[/dim]",
    )
    if viz.description:
        _console.print(f"  {viz.description}")
    rows = viz.rowDimensions or []
    columns = viz.columnDimensions or []
    filters = viz.filterDimensions or []
    _console.print(f"  axes: [cyan]rows={rows}  columns={columns}  filters={filters}[/cyan]")
    de_uids = _collect_dataDimensionItem_targets(viz.dataDimensionItems)
    if de_uids:
        _console.print(f"  data elements: {', '.join(de_uids)}")
    pe_uids = [p.get("id") if isinstance(p, dict) else getattr(p, "id", None) for p in (viz.periods or [])]
    if pe_uids:
        _console.print(f"  periods ({len(pe_uids)}): {', '.join(str(p) for p in pe_uids[:6])}")
    ou_uids = [o.get("id") if isinstance(o, dict) else getattr(o, "id", None) for o in (viz.organisationUnits or [])]
    if ou_uids:
        _console.print(f"  organisation units ({len(ou_uids)}): {', '.join(str(o) for o in ou_uids[:6])}")


@viz_app.command("create")
def viz_create_command(
    name: Annotated[str, typer.Option("--name", help="Display name for the new Visualization.")],
    viz_type: Annotated[
        str,
        typer.Option(
            "--type",
            help="VisualizationType: LINE, COLUMN, STACKED_COLUMN, BAR, PIVOT_TABLE, SINGLE_VALUE, etc.",
        ),
    ],
    data_element: Annotated[
        list[str],
        typer.Option("--data-element", "--de", help="DataElement UID (repeat for multi-DE charts)."),
    ],
    period: Annotated[
        list[str],
        typer.Option("--period", "--pe", help="Period ID (e.g. 202401, 2024Q1, 2024). Repeat for multi-period."),
    ],
    org_unit: Annotated[
        list[str],
        typer.Option("--org-unit", "--ou", help="OrganisationUnit UID. Repeat for multi-OU."),
    ],
    description: Annotated[str | None, typer.Option("--description", help="Optional long description.")] = None,
    uid: Annotated[
        str | None, typer.Option("--uid", help="Explicit UID (11 chars). Auto-generates when omitted.")
    ] = None,
    category_dimension: Annotated[
        str | None,
        typer.Option("--category-dim", help="Override category axis: dx / pe / ou."),
    ] = None,
    series_dimension: Annotated[
        str | None,
        typer.Option("--series-dim", help="Override series dimension: dx / pe / ou."),
    ] = None,
    filter_dimension: Annotated[
        str | None,
        typer.Option("--filter-dim", help="Override filter dimension: dx / pe / ou."),
    ] = None,
) -> None:
    """Create a Visualization from flags — one command, no hand-rolled JSON.

    Uses `VisualizationSpec` defaults per chart type: LINE / COLUMN / BAR /
    etc. default to rows=[pe] / columns=[ou] / filters=[dx]; PIVOT_TABLE
    defaults to rows=[ou] / columns=[pe] / filters=[dx]; SINGLE_VALUE
    collapses to columns=[dx] / filters=[pe, ou]. Override any slot with
    --category-dim / --series-dim / --filter-dim.
    """
    viz = asyncio.run(
        service.create_visualization(
            profile_from_env(),
            name=name,
            viz_type=viz_type,
            data_elements=data_element,
            periods=period,
            organisation_units=org_unit,
            description=description,
            uid=uid,
            category_dimension=category_dimension,
            series_dimension=series_dimension,
            filter_dimension=filter_dimension,
        ),
    )
    if is_json_output():
        typer.echo(viz.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[green]created[/green] [cyan]{viz.id}[/cyan]  type=[dim]{viz.type}[/dim]  name={viz.name!r}",
    )
    _console.print(
        f"  axes: rows={viz.rowDimensions}  columns={viz.columnDimensions}  filters={viz.filterDimensions}",
    )


@viz_app.command("clone")
def viz_clone_command(
    source_uid: Annotated[str, typer.Argument(help="Source Visualization UID.")],
    new_name: Annotated[str, typer.Option("--new-name", help="Display name for the cloned Visualization.")],
    new_uid: Annotated[
        str | None,
        typer.Option("--new-uid", help="Explicit UID for the clone (11 chars). Auto-generates when omitted."),
    ] = None,
    new_description: Annotated[
        str | None,
        typer.Option("--new-description", help="Override the source's description on the clone."),
    ] = None,
) -> None:
    """Clone an existing Visualization with a fresh UID + new name."""
    clone = asyncio.run(
        service.clone_visualization(
            profile_from_env(),
            source_uid,
            new_name=new_name,
            new_uid=new_uid,
            new_description=new_description,
        ),
    )
    if is_json_output():
        typer.echo(clone.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]cloned[/green] {source_uid} -> [cyan]{clone.id}[/cyan]  name={clone.name!r}")


@viz_app.command("delete")
def viz_delete_command(
    viz_uid: Annotated[str, typer.Argument(help="Visualization UID to delete.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Delete a Visualization."""
    if not yes:
        typer.confirm(f"really delete visualization {viz_uid}?", abort=True)
    asyncio.run(service.delete_visualization(profile_from_env(), viz_uid))
    _emit_mutation(f"deleted visualization {viz_uid}")


@dashboard_app.command("get")
def dashboard_get_command(
    dashboard_uid: Annotated[str, typer.Argument(help="Dashboard UID.")],
) -> None:
    """Show one Dashboard with every dashboardItem resolved inline."""
    dashboard = asyncio.run(service.show_dashboard(profile_from_env(), dashboard_uid))
    if is_json_output():
        typer.echo(dashboard.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[bold]{dashboard.name or '-'}[/bold]  uid=[dim]{dashboard.id or '-'}[/dim]",
    )
    if dashboard.description:
        _console.print(f"  {dashboard.description}")
    items = list(dashboard.dashboardItems or [])
    if not items:
        _console.print("  (no items)")
        return
    table = Table(title=f"items ({len(items)})")
    table.add_column("item uid", style="cyan")
    table.add_column("type", style="dim")
    table.add_column("target", overflow="fold")
    table.add_column("slot (x,y wxh)", style="dim")
    for item in items:
        item_uid = item.id if not isinstance(item, dict) else item.get("id")
        item_type = (item.type if not isinstance(item, dict) else item.get("type")) or "-"
        if isinstance(item, dict):
            viz_ref = item.get("visualization") or {}
            target = viz_ref.get("id") if isinstance(viz_ref, dict) else "-"
        else:
            viz_ref = getattr(item, "visualization", None)
            target = getattr(viz_ref, "id", None) if viz_ref is not None else "-"
        x = (item.x if not isinstance(item, dict) else item.get("x")) or 0
        y = (item.y if not isinstance(item, dict) else item.get("y")) or 0
        w = (item.width if not isinstance(item, dict) else item.get("width")) or 0
        h = (item.height if not isinstance(item, dict) else item.get("height")) or 0
        table.add_row(str(item_uid or "-"), str(item_type), str(target or "-"), f"({x},{y} {w}x{h})")
    _console.print(table)


@dashboard_app.command("add-item")
def dashboard_add_item_command(
    dashboard_uid: Annotated[str, typer.Argument(help="Dashboard UID.")],
    visualization_uid: Annotated[
        str | None,
        typer.Option("--viz", help="Visualization UID (mutually exclusive with --map)."),
    ] = None,
    map_uid: Annotated[
        str | None,
        typer.Option("--map", help="Map UID to add as a MAP-type dashboard item."),
    ] = None,
    x: Annotated[int | None, typer.Option("--x", help="Grid x coordinate (0-60). Auto-stacks when omitted.")] = None,
    y: Annotated[
        int | None, typer.Option("--y", help="Grid y coordinate. Auto-stacks below existing when omitted.")
    ] = None,
    width: Annotated[int | None, typer.Option("--width", help="Slot width (1-60). Defaults to 60 when auto.")] = None,
    height: Annotated[int | None, typer.Option("--height", help="Slot height. Defaults to 20 when auto.")] = None,
) -> None:
    """Add a Visualization or Map item to a dashboard.

    Pass --viz to add a VISUALIZATION item or --map to add a MAP item
    (exactly one required). Omit --x / --y / --width / --height to
    auto-stack below existing items (full width); supply them when
    you want side-by-side tiling.
    """
    if (visualization_uid is None) == (map_uid is None):
        typer.secho("pass exactly one of --viz or --map", err=True, fg=typer.colors.RED)
        raise typer.Exit(2)
    target_uid = visualization_uid or map_uid
    assert target_uid is not None
    kind = "visualization" if visualization_uid is not None else "map"
    dashboard = asyncio.run(
        service.dashboard_add_item(
            profile_from_env(),
            dashboard_uid,
            target_uid,
            kind=kind,
            x=x,
            y=y,
            width=width,
            height=height,
        ),
    )
    item_count = len(dashboard.dashboardItems or [])
    _emit_mutation(
        f"[green]added[/green] {kind} [cyan]{target_uid}[/cyan] to dashboard {dashboard_uid} (now {item_count} items)",
    )


@dashboard_app.command("remove-item")
def dashboard_remove_item_command(
    dashboard_uid: Annotated[str, typer.Argument(help="Dashboard UID.")],
    item_uid: Annotated[str, typer.Argument(help="DashboardItem UID to remove.")],
) -> None:
    """Remove one dashboardItem by its UID."""
    dashboard = asyncio.run(
        service.dashboard_remove_item(profile_from_env(), dashboard_uid, item_uid),
    )
    item_count = len(dashboard.dashboardItems or [])
    _emit_mutation(
        f"[green]removed[/green] item [cyan]{item_uid}[/cyan] from dashboard {dashboard_uid} (now {item_count} items)",
    )


@map_app.command("get")
def map_get_command(
    map_uid: Annotated[str, typer.Argument(help="Map UID.")],
) -> None:
    """Show one Map with its viewport + every mapViews layer."""
    m = asyncio.run(service.show_map(profile_from_env(), map_uid))
    if is_json_output():
        typer.echo(m.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[bold]{m.name or '-'}[/bold]  uid=[dim]{m.id or '-'}[/dim]",
    )
    if m.description:
        _console.print(f"  {m.description}")
    _console.print(
        f"  viewport: lon={m.longitude}  lat={m.latitude}  zoom={m.zoom}  basemap={m.basemap}",
    )
    views = list(m.mapViews or [])
    if not views:
        _console.print("  (no layers)")
        return
    table = Table(title=f"layers ({len(views)})")
    table.add_column("layer", style="cyan")
    table.add_column("type", style="dim")
    table.add_column("classes", justify="right")
    table.add_column("colors", overflow="fold")
    for view in views:
        layer = view.get("layer") if isinstance(view, dict) else getattr(view, "layer", None)
        thematic = view.get("thematicMapType") if isinstance(view, dict) else getattr(view, "thematicMapType", None)
        classes = view.get("classes") if isinstance(view, dict) else getattr(view, "classes", None)
        color_low = view.get("colorLow") if isinstance(view, dict) else getattr(view, "colorLow", None)
        color_high = view.get("colorHigh") if isinstance(view, dict) else getattr(view, "colorHigh", None)
        colors = f"{color_low or '-'} -> {color_high or '-'}"
        table.add_row(str(layer or "-"), str(thematic or "-"), str(classes or "-"), colors)
    _console.print(table)


@map_app.command("create")
def map_create_command(
    name: Annotated[str, typer.Option("--name", help="Display name for the new Map.")],
    data_element: Annotated[
        list[str],
        typer.Option("--data-element", "--de", help="DataElement UID for the thematic layer."),
    ],
    period: Annotated[list[str], typer.Option("--period", "--pe", help="Period ID. Repeat for multi-period.")],
    org_unit: Annotated[
        list[str],
        typer.Option(
            "--org-unit",
            "--ou",
            help="OrganisationUnit UID (usually the parent boundary). Repeat for multi.",
        ),
    ],
    org_unit_level: Annotated[
        list[int],
        typer.Option("--ou-level", help="OU hierarchy level(s) to render (e.g. 2 for provinces). Repeat for multi."),
    ],
    description: Annotated[str | None, typer.Option("--description")] = None,
    uid: Annotated[
        str | None, typer.Option("--uid", help="Explicit UID (11 chars). Auto-generates when omitted.")
    ] = None,
    longitude: Annotated[float, typer.Option("--longitude")] = 15.0,
    latitude: Annotated[float, typer.Option("--latitude")] = 0.0,
    zoom: Annotated[int, typer.Option("--zoom")] = 4,
    basemap: Annotated[str, typer.Option("--basemap")] = "openStreetMap",
    classes: Annotated[int, typer.Option("--classes", help="Number of color classes on the choropleth.")] = 5,
    color_low: Annotated[str, typer.Option("--color-low", help="Choropleth low-value colour (#hex).")] = "#fef0d9",
    color_high: Annotated[str, typer.Option("--color-high", help="Choropleth high-value colour (#hex).")] = "#b30000",
) -> None:
    """Create a single-layer thematic choropleth Map from flags.

    Multi-layer maps need raw `Map` / `MapView` construction — use
    `client.maps.create_from_spec(MapSpec(layers=[...]))` from the
    library side and extend the spec to include boundary / facility
    / event layers.
    """
    m = asyncio.run(
        service.create_map(
            profile_from_env(),
            name=name,
            data_elements=data_element,
            periods=period,
            organisation_units=org_unit,
            organisation_unit_levels=org_unit_level,
            description=description,
            uid=uid,
            longitude=longitude,
            latitude=latitude,
            zoom=zoom,
            basemap=basemap,
            classes=classes,
            color_low=color_low,
            color_high=color_high,
        ),
    )
    if is_json_output():
        typer.echo(m.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[green]created[/green] [cyan]{m.id}[/cyan]  name={m.name!r}  zoom={m.zoom}  layers={len(m.mapViews or [])}",
    )


@map_app.command("clone")
def map_clone_command(
    source_uid: Annotated[str, typer.Argument(help="Source Map UID.")],
    new_name: Annotated[str, typer.Option("--new-name", help="Display name for the cloned Map.")],
    new_uid: Annotated[str | None, typer.Option("--new-uid", help="Explicit UID for the clone.")] = None,
    new_description: Annotated[str | None, typer.Option("--new-description")] = None,
) -> None:
    """Clone an existing Map with a fresh UID + new name."""
    clone = asyncio.run(
        service.clone_map(
            profile_from_env(),
            source_uid,
            new_name=new_name,
            new_uid=new_uid,
            new_description=new_description,
        ),
    )
    if is_json_output():
        typer.echo(clone.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]cloned[/green] {source_uid} -> [cyan]{clone.id}[/cyan]  name={clone.name!r}")


@map_app.command("delete")
def map_delete_command(
    map_uid: Annotated[str, typer.Argument(help="Map UID to delete.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Delete a Map."""
    if not yes:
        typer.confirm(f"really delete map {map_uid}?", abort=True)
    asyncio.run(service.delete_map(profile_from_env(), map_uid))
    _emit_mutation(f"deleted map {map_uid}")


# ---------------------------------------------------------------------------
# LegendSet authoring — `dhis2 metadata legend-sets ...`
# ---------------------------------------------------------------------------


def _parse_legend_spec(spec: str) -> tuple[float, float, str, str | None]:
    """Parse `start:end:color[:name]` into the 4-tuple `create_legend_set` expects."""
    parts = spec.split(":", 3)
    if len(parts) < 3:
        raise typer.BadParameter(
            f"--legend {spec!r}: expected `start:end:color[:name]` (4 parts separated by `:`)",
        )
    try:
        start = float(parts[0])
        end = float(parts[1])
    except ValueError as exc:
        raise typer.BadParameter(f"--legend {spec!r}: start and end must be numeric.") from exc
    color = parts[2].strip()
    if not color.startswith("#"):
        raise typer.BadParameter(f"--legend {spec!r}: color must be a `#RRGGBB` / `#RRGGBBAA` hex string.")
    name = parts[3] if len(parts) == 4 else None
    return (start, end, color, name)


@legend_sets_app.command("get")
def legend_sets_get_command(
    uid: Annotated[str, typer.Argument(help="LegendSet UID.")],
) -> None:
    """Show one LegendSet with its ordered legends (colour ranges)."""
    legend_set = asyncio.run(service.show_legend_set(profile_from_env(), uid))
    if is_json_output():
        typer.echo(legend_set.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{legend_set.name} ({legend_set.id}) code={legend_set.code or '-'}")
    legends = list(legend_set.legends or [])
    if not legends:
        typer.echo("  (no legends)")
        return

    # DHIS2 returns legends unordered (DB insertion order), which is
    # confusing when rendering — an 8-entry age-range legend shows ranges
    # out of numeric order. Sort ascending on `startValue` so the visual
    # matches how users think about a legend ("low -> high").
    def _sort_key(row: object) -> float:
        if not isinstance(row, dict):
            return 0.0
        value = row.get("startValue")
        return float(value) if isinstance(value, int | float) else 0.0

    legends.sort(key=_sort_key)
    table = Table(title=f"legends in {legend_set.name}")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("start", justify="right")
    table.add_column("end", justify="right")
    table.add_column("color")
    for legend in legends:
        if not isinstance(legend, dict):
            continue
        color = legend.get("color") or ""
        table.add_row(
            str(legend.get("id") or "-"),
            str(legend.get("name") or "-"),
            str(legend.get("startValue") if legend.get("startValue") is not None else "-"),
            str(legend.get("endValue") if legend.get("endValue") is not None else "-"),
            f"[on {color}]    [/on {color}]  {color}" if color.startswith("#") else color or "-",
        )
    _console.print(table)


@legend_sets_app.command("create")
def legend_sets_create_command(
    name: Annotated[str, typer.Option("--name", help="Display name for the new LegendSet.")],
    legends: Annotated[
        list[str],
        typer.Option(
            "--legend",
            help=(
                "One legend (colour range) in `start:end:color[:name]` form. Repeatable, at least one required. "
                "Example: `--legend 0:1000:#d73027:Low --legend 1000:5000:#1a9850:High`."
            ),
        ),
    ],
    code: Annotated[str | None, typer.Option("--code", help="Business code (unique).")] = None,
    uid: Annotated[
        str | None,
        typer.Option("--uid", help="Fixed 11-char UID. Omit to let the client generate one."),
    ] = None,
) -> None:
    """Create a LegendSet with ordered colour-range legends.

    Each `--legend start:end:color[:name]` defines one entry — `start`
    must be strictly less than `end`, `color` is a `#RRGGBB` /
    `#RRGGBBAA` hex string, `name` is optional (auto-generated from the
    numeric range when omitted). At least one `--legend` is required.

    Posts through `/api/metadata` so the LegendSet + its child Legends
    land atomically. Returns the freshly-fetched record so DHIS2's
    computed fields are populated.
    """
    if not legends:
        raise typer.BadParameter("pass at least one --legend (e.g. `--legend 0:100:#d73027:Low`)")
    parsed_legends = [_parse_legend_spec(spec) for spec in legends]
    result = asyncio.run(
        service.create_legend_set(
            profile_from_env(),
            name=name,
            legends=parsed_legends,
            uid=uid,
            code=code,
        ),
    )
    if is_json_output():
        typer.echo(result.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[green]created[/green] legendSet [cyan]{result.id}[/cyan]  name={result.name!r}  "
        f"legends={len(result.legends or [])}",
    )


@legend_sets_app.command("clone")
def legend_sets_clone_command(
    source_uid: Annotated[str, typer.Argument(help="Source LegendSet UID to clone.")],
    new_name: Annotated[
        str | None,
        typer.Option("--new-name", help="Name of the clone (default: append ' (clone)' to the source's name)."),
    ] = None,
    new_uid: Annotated[
        str | None,
        typer.Option("--new-uid", help="Fixed 11-char UID for the clone. Omit for auto-generated."),
    ] = None,
    new_code: Annotated[str | None, typer.Option("--new-code", help="Business code on the clone.")] = None,
) -> None:
    """Duplicate an existing LegendSet with the same bands + fresh UIDs.

    Useful for forking a base set ("Coverage 0-100") into a variant
    without rebuilding the bands by hand.
    """
    result = asyncio.run(
        service.clone_legend_set(
            profile_from_env(),
            source_uid,
            new_uid=new_uid,
            new_name=new_name,
            new_code=new_code,
        ),
    )
    if is_json_output():
        typer.echo(result.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]cloned[/green] {source_uid} -> [cyan]{result.id}[/cyan]  name={result.name!r}")


@legend_sets_app.command("delete")
def legend_sets_delete_command(
    uid: Annotated[str, typer.Argument(help="LegendSet UID to delete.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Delete a LegendSet."""
    if not yes:
        typer.confirm(f"really delete legendSet {uid}?", abort=True)
    asyncio.run(service.delete_legend_set(profile_from_env(), uid))
    _emit_mutation(f"deleted legendSet {uid}")


# ---------------------------------------------------------------------------
# DataElement workflows — `dhis2 metadata data-elements ...`
# ---------------------------------------------------------------------------


@data_elements_app.command("get")
def data_elements_get_command(
    uid: Annotated[str, typer.Argument(help="DataElement UID.")],
) -> None:
    """Show one DataElement with its references resolved inline."""
    de = asyncio.run(service.show_data_element(profile_from_env(), uid))
    if is_json_output():
        typer.echo(de.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{de.name} ({de.id}) code={de.code or '-'}")
    typer.echo(f"  valueType:        {de.valueType.value if de.valueType else '-'}")
    typer.echo(f"  domainType:       {de.domainType.value if de.domainType else '-'}")
    typer.echo(f"  aggregationType:  {de.aggregationType.value if de.aggregationType else '-'}")
    cc = getattr(de.categoryCombo, "id", None) if de.categoryCombo else None
    typer.echo(f"  categoryCombo:    {cc or '-'}")
    os_id = getattr(de.optionSet, "id", None) if de.optionSet else None
    typer.echo(f"  optionSet:        {os_id or '-'}")
    typer.echo(f"  legendSets:       {len(de.legendSets or [])}")
    if de.description:
        typer.echo(f"  description:      {de.description}")


@data_elements_app.command("create")
def data_elements_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    value_type: Annotated[
        str, typer.Option("--value-type", help="DHIS2 ValueType, e.g. NUMBER / TEXT / INTEGER_POSITIVE.")
    ],
    domain_type: Annotated[str, typer.Option("--domain-type", help="AGGREGATE or TRACKER.")] = "AGGREGATE",
    aggregation_type: Annotated[str, typer.Option("--aggregation-type", help="Default SUM.")] = "SUM",
    category_combo_uid: Annotated[
        str | None,
        typer.Option("--category-combo", help="CategoryCombo UID (defaults to the instance default)."),
    ] = None,
    option_set_uid: Annotated[str | None, typer.Option("--option-set", help="OptionSet UID.")] = None,
    legend_set_uid: Annotated[
        list[str] | None,
        typer.Option("--legend-set", help="LegendSet UID. Repeat for multiple."),
    ] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="Form name override.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
    zero_is_significant: Annotated[
        bool,
        typer.Option("--zero-significant/--no-zero-significant", help="Treat 0 as data, not absence."),
    ] = False,
) -> None:
    """Create a DataElement (defaults aggregate + SUM + instance default categoryCombo)."""
    de = asyncio.run(
        service.create_data_element(
            profile_from_env(),
            name=name,
            short_name=short_name,
            value_type=value_type,
            domain_type=domain_type,
            aggregation_type=aggregation_type,
            category_combo_uid=category_combo_uid,
            option_set_uid=option_set_uid,
            legend_set_uids=legend_set_uid,
            code=code,
            form_name=form_name,
            description=description,
            uid=uid,
            zero_is_significant=zero_is_significant,
        ),
    )
    if is_json_output():
        typer.echo(de.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] dataElement [cyan]{de.id}[/cyan]  name={de.name!r}")


@data_elements_app.command("rename")
def data_elements_rename_command(
    uid: Annotated[str, typer.Argument(help="DataElement UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="New form name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update the label fields on a DataElement (read, mutate, PUT)."""
    de = asyncio.run(
        service.rename_data_element(
            profile_from_env(),
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(de.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] dataElement [cyan]{de.id}[/cyan]  name={de.name!r}")


@data_elements_app.command("set-legend-sets")
def data_elements_set_legend_sets_command(
    uid: Annotated[str, typer.Argument(help="DataElement UID.")],
    legend_set_uids: Annotated[
        list[str],
        typer.Option("--legend-set", help="LegendSet UID to attach. Repeat for multiple. Empty list clears."),
    ],
) -> None:
    """Replace the legend-set refs on one DataElement."""
    de = asyncio.run(
        service.set_data_element_legend_sets(profile_from_env(), uid, legend_set_uids=legend_set_uids),
    )
    _console.print(
        f"[green]legend sets[/green] on [cyan]{uid}[/cyan]: {[getattr(ls, 'id', ls) for ls in de.legendSets or []]}",
    )


@data_elements_app.command("delete")
def data_elements_delete_command(
    uid: Annotated[str, typer.Argument(help="DataElement UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a DataElement — DHIS2 rejects deletes on DEs with saved values."""
    if not yes:
        typer.confirm(f"really delete dataElement {uid}?", abort=True)
    asyncio.run(service.delete_data_element(profile_from_env(), uid))
    _emit_mutation(f"deleted dataElement {uid}")


# ---------------------------------------------------------------------------
# DataElementGroup — `dhis2 metadata data-element-groups ...`
# ---------------------------------------------------------------------------


@data_element_groups_app.command("get")
def data_element_groups_get_command(
    uid: Annotated[str, typer.Argument(help="DataElementGroup UID.")],
) -> None:
    """Show one group with its member refs and group-sets it belongs to."""
    group = asyncio.run(service.show_data_element_group(profile_from_env(), uid))
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{group.name} ({group.id}) code={group.code or '-'}")
    if group.description:
        typer.echo(f"  description: {group.description}")
    typer.echo(f"  members:     {len(group.dataElements or [])}")
    typer.echo(f"  group sets:  {len(group.groupSets or [])}")


@data_element_groups_app.command("members")
def data_element_groups_members_command(
    uid: Annotated[str, typer.Argument(help="DataElementGroup UID.")],
    page: Annotated[int, typer.Option("--page", help="1-based page number.")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="Rows per page.")] = 50,
) -> None:
    """Page through DataElements inside one group."""
    members = asyncio.run(
        service.list_data_element_group_members(profile_from_env(), uid, page=page, page_size=page_size),
    )
    if is_json_output():
        typer.echo(
            json.dumps([m.model_dump(by_alias=True, exclude_none=True, mode="json") for m in members], indent=2),
        )
        return
    if not members:
        typer.echo(f"no DEs in group {uid} on page {page}")
        return
    table = Table(title=f"members of {uid} (page {page})")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("code", style="dim")
    table.add_column("valueType", style="magenta")
    for row in members:
        table.add_row(
            str(row.id or "-"),
            str(row.name or "-"),
            str(row.code or "-"),
            str(row.valueType.value if row.valueType else "-"),
        )
    _console.print(table)


@data_element_groups_app.command("create")
def data_element_groups_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name.")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name.")],
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
) -> None:
    """Create an empty DataElementGroup."""
    group = asyncio.run(
        service.create_data_element_group(
            profile_from_env(),
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] dataElementGroup [cyan]{group.id}[/cyan]  name={group.name!r}")


@data_element_groups_app.command("add-members")
def data_element_groups_add_members_command(
    uid: Annotated[str, typer.Argument(help="DataElementGroup UID.")],
    data_element_uids: Annotated[
        list[str],
        typer.Option("--data-element", "-e", help="DataElement UID to add. Repeat for multiple."),
    ],
) -> None:
    """Add `--data-element` members via the per-item POST shortcut."""
    group = asyncio.run(
        service.add_data_element_group_members(profile_from_env(), uid, data_element_uids=data_element_uids),
    )
    total = len(group.dataElements or [])
    _emit_mutation(f"[green]added[/green] {len(data_element_uids)} DE(s) to {uid}  total members={total}")


@data_element_groups_app.command("remove-members")
def data_element_groups_remove_members_command(
    uid: Annotated[str, typer.Argument(help="DataElementGroup UID.")],
    data_element_uids: Annotated[
        list[str],
        typer.Option("--data-element", "-e", help="DataElement UID to drop. Repeat for multiple."),
    ],
) -> None:
    """Drop `--data-element` members via the per-item DELETE shortcut."""
    group = asyncio.run(
        service.remove_data_element_group_members(
            profile_from_env(),
            uid,
            data_element_uids=data_element_uids,
        ),
    )
    total = len(group.dataElements or [])
    _emit_mutation(f"[green]removed[/green] {len(data_element_uids)} DE(s) from {uid}  total members={total}")


@data_element_groups_app.command("delete")
def data_element_groups_delete_command(
    uid: Annotated[str, typer.Argument(help="DataElementGroup UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete the grouping row — member DEs stay."""
    if not yes:
        typer.confirm(f"really delete dataElementGroup {uid}?", abort=True)
    asyncio.run(service.delete_data_element_group(profile_from_env(), uid))
    _emit_mutation(f"deleted dataElementGroup {uid}")


# ---------------------------------------------------------------------------
# DataElementGroupSet — `dhis2 metadata data-element-group-sets ...`
# ---------------------------------------------------------------------------


@data_element_group_sets_app.command("get")
def data_element_group_sets_get_command(
    uid: Annotated[str, typer.Argument(help="DataElementGroupSet UID.")],
) -> None:
    """Show one group set with its groups."""
    group_set = asyncio.run(service.show_data_element_group_set(profile_from_env(), uid))
    if is_json_output():
        typer.echo(group_set.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{group_set.name} ({group_set.id}) code={group_set.code or '-'}")
    if group_set.description:
        typer.echo(f"  description: {group_set.description}")
    typer.echo(f"  compulsory:    {'yes' if group_set.compulsory else 'no'}")
    typer.echo(f"  data dimension:{'yes' if group_set.dataDimension else 'no'}")
    groups = list(group_set.dataElementGroups or [])
    if not groups:
        typer.echo("  (no groups)")
        return
    table = Table(title=f"groups in {group_set.name}")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("code", style="dim")
    for group in groups:
        if not isinstance(group, dict):
            continue
        table.add_row(
            str(group.get("id") or "-"),
            str(group.get("name") or "-"),
            str(group.get("code") or "-"),
        )
    _console.print(table)


@data_element_group_sets_app.command("create")
def data_element_group_sets_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name.")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name.")],
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    compulsory: Annotated[
        bool, typer.Option("--compulsory/--not-compulsory", help="Require DEs to land in exactly one member group.")
    ] = False,
    data_dimension: Annotated[
        bool, typer.Option("--data-dimension/--no-data-dimension", help="Expose as analytics axis.")
    ] = True,
) -> None:
    """Create an empty DataElementGroupSet."""
    gs = asyncio.run(
        service.create_data_element_group_set(
            profile_from_env(),
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
            compulsory=compulsory,
            data_dimension=data_dimension,
        ),
    )
    if is_json_output():
        typer.echo(gs.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] dataElementGroupSet [cyan]{gs.id}[/cyan]  name={gs.name!r}")


@data_element_group_sets_app.command("add-groups")
def data_element_group_sets_add_groups_command(
    uid: Annotated[str, typer.Argument(help="DataElementGroupSet UID.")],
    group_uids: Annotated[list[str], typer.Option("--group", help="DataElementGroup UID to add. Repeat for multiple.")],
) -> None:
    """Add `--group` members to a group set."""
    gs = asyncio.run(service.add_data_element_group_set_groups(profile_from_env(), uid, group_uids=group_uids))
    total = len(gs.dataElementGroups or [])
    _emit_mutation(f"[green]added[/green] {len(group_uids)} group(s) to {uid}  total groups={total}")


@data_element_group_sets_app.command("remove-groups")
def data_element_group_sets_remove_groups_command(
    uid: Annotated[str, typer.Argument(help="DataElementGroupSet UID.")],
    group_uids: Annotated[
        list[str], typer.Option("--group", help="DataElementGroup UID to drop. Repeat for multiple.")
    ],
) -> None:
    """Drop `--group` members from a group set."""
    gs = asyncio.run(service.remove_data_element_group_set_groups(profile_from_env(), uid, group_uids=group_uids))
    total = len(gs.dataElementGroups or [])
    _emit_mutation(f"[green]removed[/green] {len(group_uids)} group(s) from {uid}  total groups={total}")


@data_element_group_sets_app.command("delete")
def data_element_group_sets_delete_command(
    uid: Annotated[str, typer.Argument(help="DataElementGroupSet UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a DataElementGroupSet — member groups stay."""
    if not yes:
        typer.confirm(f"really delete dataElementGroupSet {uid}?", abort=True)
    asyncio.run(service.delete_data_element_group_set(profile_from_env(), uid))
    _emit_mutation(f"deleted dataElementGroupSet {uid}")


# ---------------------------------------------------------------------------
# Indicator workflows — `dhis2 metadata indicators ...`
# ---------------------------------------------------------------------------


@indicators_app.command("get")
def indicators_get_command(
    uid: Annotated[str, typer.Argument(help="Indicator UID.")],
) -> None:
    """Show one Indicator with expression pair + indicatorType resolved inline."""
    ind = asyncio.run(service.show_indicator(profile_from_env(), uid))
    if is_json_output():
        typer.echo(ind.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{ind.name} ({ind.id}) code={ind.code or '-'}")
    itype = getattr(ind.indicatorType, "id", None) if ind.indicatorType else None
    typer.echo(f"  indicatorType: {itype or '-'}")
    typer.echo(f"  numerator:     {ind.numerator or '-'}")
    typer.echo(f"  denominator:   {ind.denominator or '-'}")
    typer.echo(f"  annualized:    {'yes' if ind.annualized else 'no'}")
    typer.echo(f"  decimals:      {ind.decimals if ind.decimals is not None else '-'}")
    typer.echo(f"  legendSets:    {len(ind.legendSets or [])}")
    if ind.description:
        typer.echo(f"  description:   {ind.description}")


@indicators_app.command("create")
def indicators_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    indicator_type_uid: Annotated[
        str, typer.Option("--indicator-type", help="IndicatorType UID (pins the output scale).")
    ],
    numerator: Annotated[str, typer.Option("--numerator", help="DHIS2 numerator expression, e.g. '#{deUid}'.")],
    denominator: Annotated[str, typer.Option("--denominator", help="DHIS2 denominator expression.")],
    numerator_description: Annotated[
        str | None, typer.Option("--numerator-desc", help="Human label for the numerator.")
    ] = None,
    denominator_description: Annotated[
        str | None, typer.Option("--denominator-desc", help="Human label for the denominator.")
    ] = None,
    legend_set_uid: Annotated[
        list[str] | None, typer.Option("--legend-set", help="LegendSet UID. Repeat for multiple.")
    ] = None,
    annualized: Annotated[
        bool, typer.Option("--annualized/--not-annualized", help="Multiply by 365 / period days on aggregation.")
    ] = False,
    decimals: Annotated[int | None, typer.Option("--decimals", help="Rendered decimal places.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create an Indicator from a numerator / denominator expression pair."""
    ind = asyncio.run(
        service.create_indicator(
            profile_from_env(),
            name=name,
            short_name=short_name,
            indicator_type_uid=indicator_type_uid,
            numerator=numerator,
            denominator=denominator,
            numerator_description=numerator_description,
            denominator_description=denominator_description,
            legend_set_uids=legend_set_uid,
            annualized=annualized,
            decimals=decimals,
            code=code,
            description=description,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(ind.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] indicator [cyan]{ind.id}[/cyan]  name={ind.name!r}")


@indicators_app.command("rename")
def indicators_rename_command(
    uid: Annotated[str, typer.Argument(help="Indicator UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update label fields on an Indicator."""
    ind = asyncio.run(
        service.rename_indicator(profile_from_env(), uid, name=name, short_name=short_name, description=description),
    )
    if is_json_output():
        typer.echo(ind.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] indicator [cyan]{ind.id}[/cyan]  name={ind.name!r}")


@indicators_app.command("validate-expression")
def indicators_validate_expression_command(
    expression: Annotated[str, typer.Argument(help="Numerator / denominator expression to validate.")],
) -> None:
    """Parse-check one indicator expression — fast pre-flight before create."""
    desc = asyncio.run(service.validate_indicator_expression(profile_from_env(), expression))
    if is_json_output():
        typer.echo(desc.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"status:      {desc.status}")
    typer.echo(f"description: {desc.description}")
    if desc.message:
        typer.echo(f"message:     {desc.message}")


@indicators_app.command("set-legend-sets")
def indicators_set_legend_sets_command(
    uid: Annotated[str, typer.Argument(help="Indicator UID.")],
    legend_set_uids: Annotated[
        list[str],
        typer.Option("--legend-set", help="LegendSet UID to attach. Empty list clears."),
    ],
) -> None:
    """Replace the legend-set refs on one Indicator."""
    ind = asyncio.run(
        service.set_indicator_legend_sets(profile_from_env(), uid, legend_set_uids=legend_set_uids),
    )
    _console.print(
        f"[green]legend sets[/green] on [cyan]{uid}[/cyan]: {[getattr(ls, 'id', ls) for ls in ind.legendSets or []]}",
    )


@indicators_app.command("delete")
def indicators_delete_command(
    uid: Annotated[str, typer.Argument(help="Indicator UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete an Indicator — DHIS2 rejects deletes on indicators used in viz/dashboards."""
    if not yes:
        typer.confirm(f"really delete indicator {uid}?", abort=True)
    asyncio.run(service.delete_indicator(profile_from_env(), uid))
    _emit_mutation(f"deleted indicator {uid}")


# ---------------------------------------------------------------------------
# IndicatorGroup — `dhis2 metadata indicator-groups ...`
# ---------------------------------------------------------------------------


@indicator_groups_app.command("get")
def indicator_groups_get_command(
    uid: Annotated[str, typer.Argument(help="IndicatorGroup UID.")],
) -> None:
    """Show one group with its member refs."""
    group = asyncio.run(service.show_indicator_group(profile_from_env(), uid))
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{group.name} ({group.id}) code={group.code or '-'}")
    if group.description:
        typer.echo(f"  description: {group.description}")
    typer.echo(f"  members:     {len(group.indicators or [])}")
    typer.echo(f"  group sets:  {len(group.groupSets or [])}")


@indicator_groups_app.command("members")
def indicator_groups_members_command(
    uid: Annotated[str, typer.Argument(help="IndicatorGroup UID.")],
    page: Annotated[int, typer.Option("--page", help="1-based page number.")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="Rows per page.")] = 50,
) -> None:
    """Page through Indicators inside one group."""
    members = asyncio.run(
        service.list_indicator_group_members(profile_from_env(), uid, page=page, page_size=page_size),
    )
    if is_json_output():
        typer.echo(
            json.dumps([m.model_dump(by_alias=True, exclude_none=True, mode="json") for m in members], indent=2),
        )
        return
    if not members:
        typer.echo(f"no indicators in group {uid} on page {page}")
        return
    table = Table(title=f"members of {uid} (page {page})")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("code", style="dim")
    table.add_column("type", style="magenta")
    for row in members:
        itype = getattr(row.indicatorType, "id", None) if row.indicatorType else None
        table.add_row(
            str(row.id or "-"),
            str(row.name or "-"),
            str(row.code or "-"),
            str(itype or "-"),
        )
    _console.print(table)


@indicator_groups_app.command("create")
def indicator_groups_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name.")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name.")],
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
) -> None:
    """Create an empty IndicatorGroup."""
    group = asyncio.run(
        service.create_indicator_group(
            profile_from_env(),
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] indicatorGroup [cyan]{group.id}[/cyan]  name={group.name!r}")


@indicator_groups_app.command("add-members")
def indicator_groups_add_members_command(
    uid: Annotated[str, typer.Argument(help="IndicatorGroup UID.")],
    indicator_uids: Annotated[
        list[str],
        typer.Option("--indicator", "-i", help="Indicator UID to add. Repeat for multiple."),
    ],
) -> None:
    """Add `--indicator` members via the per-item POST shortcut."""
    group = asyncio.run(
        service.add_indicator_group_members(profile_from_env(), uid, indicator_uids=indicator_uids),
    )
    total = len(group.indicators or [])
    _emit_mutation(f"[green]added[/green] {len(indicator_uids)} indicator(s) to {uid}  total={total}")


@indicator_groups_app.command("remove-members")
def indicator_groups_remove_members_command(
    uid: Annotated[str, typer.Argument(help="IndicatorGroup UID.")],
    indicator_uids: Annotated[
        list[str],
        typer.Option("--indicator", "-i", help="Indicator UID to drop. Repeat for multiple."),
    ],
) -> None:
    """Drop `--indicator` members via the per-item DELETE shortcut."""
    group = asyncio.run(
        service.remove_indicator_group_members(profile_from_env(), uid, indicator_uids=indicator_uids),
    )
    total = len(group.indicators or [])
    _emit_mutation(f"[green]removed[/green] {len(indicator_uids)} indicator(s) from {uid}  total={total}")


@indicator_groups_app.command("delete")
def indicator_groups_delete_command(
    uid: Annotated[str, typer.Argument(help="IndicatorGroup UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete the grouping row — member indicators stay."""
    if not yes:
        typer.confirm(f"really delete indicatorGroup {uid}?", abort=True)
    asyncio.run(service.delete_indicator_group(profile_from_env(), uid))
    _emit_mutation(f"deleted indicatorGroup {uid}")


# ---------------------------------------------------------------------------
# IndicatorGroupSet — `dhis2 metadata indicator-group-sets ...`
# ---------------------------------------------------------------------------


@indicator_group_sets_app.command("get")
def indicator_group_sets_get_command(
    uid: Annotated[str, typer.Argument(help="IndicatorGroupSet UID.")],
) -> None:
    """Show one group set with its groups."""
    group_set = asyncio.run(service.show_indicator_group_set(profile_from_env(), uid))
    if is_json_output():
        typer.echo(group_set.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{group_set.name} ({group_set.id}) code={group_set.code or '-'}")
    if group_set.description:
        typer.echo(f"  description: {group_set.description}")
    typer.echo(f"  compulsory:  {'yes' if group_set.compulsory else 'no'}")
    groups = list(group_set.indicatorGroups or [])
    if not groups:
        typer.echo("  (no groups)")
        return
    table = Table(title=f"groups in {group_set.name}")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("code", style="dim")
    for group in groups:
        if not isinstance(group, dict):
            continue
        table.add_row(
            str(group.get("id") or "-"),
            str(group.get("name") or "-"),
            str(group.get("code") or "-"),
        )
    _console.print(table)


@indicator_group_sets_app.command("create")
def indicator_group_sets_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name.")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name.")],
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    compulsory: Annotated[
        bool,
        typer.Option("--compulsory/--not-compulsory", help="Require indicators to land in exactly one member group."),
    ] = False,
) -> None:
    """Create an empty IndicatorGroupSet."""
    gs = asyncio.run(
        service.create_indicator_group_set(
            profile_from_env(),
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
            compulsory=compulsory,
        ),
    )
    if is_json_output():
        typer.echo(gs.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] indicatorGroupSet [cyan]{gs.id}[/cyan]  name={gs.name!r}")


@indicator_group_sets_app.command("add-groups")
def indicator_group_sets_add_groups_command(
    uid: Annotated[str, typer.Argument(help="IndicatorGroupSet UID.")],
    group_uids: Annotated[list[str], typer.Option("--group", help="IndicatorGroup UID to add. Repeat for multiple.")],
) -> None:
    """Add `--group` members to a group set."""
    gs = asyncio.run(service.add_indicator_group_set_groups(profile_from_env(), uid, group_uids=group_uids))
    total = len(gs.indicatorGroups or [])
    _emit_mutation(f"[green]added[/green] {len(group_uids)} group(s) to {uid}  total={total}")


@indicator_group_sets_app.command("remove-groups")
def indicator_group_sets_remove_groups_command(
    uid: Annotated[str, typer.Argument(help="IndicatorGroupSet UID.")],
    group_uids: Annotated[list[str], typer.Option("--group", help="IndicatorGroup UID to drop. Repeat for multiple.")],
) -> None:
    """Drop `--group` members from a group set."""
    gs = asyncio.run(service.remove_indicator_group_set_groups(profile_from_env(), uid, group_uids=group_uids))
    total = len(gs.indicatorGroups or [])
    _emit_mutation(f"[green]removed[/green] {len(group_uids)} group(s) from {uid}  total={total}")


@indicator_group_sets_app.command("delete")
def indicator_group_sets_delete_command(
    uid: Annotated[str, typer.Argument(help="IndicatorGroupSet UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete an IndicatorGroupSet — member groups stay."""
    if not yes:
        typer.confirm(f"really delete indicatorGroupSet {uid}?", abort=True)
    asyncio.run(service.delete_indicator_group_set(profile_from_env(), uid))
    _emit_mutation(f"deleted indicatorGroupSet {uid}")


# ---------------------------------------------------------------------------
# ProgramIndicator workflows — `dhis2 metadata program-indicators ...`
# ---------------------------------------------------------------------------


@program_indicators_app.command("get")
def program_indicators_get_command(
    uid: Annotated[str, typer.Argument(help="ProgramIndicator UID.")],
) -> None:
    """Show one ProgramIndicator with its expression + filter resolved inline."""
    pi = asyncio.run(service.show_program_indicator(profile_from_env(), uid))
    if is_json_output():
        typer.echo(pi.model_dump_json(indent=2, exclude_none=True))
        return
    program_id = getattr(pi.program, "id", None) if pi.program else None
    typer.echo(f"{pi.name} ({pi.id}) code={pi.code or '-'}")
    typer.echo(f"  program:        {program_id or '-'}")
    typer.echo(f"  analyticsType:  {pi.analyticsType.value if pi.analyticsType else '-'}")
    typer.echo(f"  expression:     {pi.expression or '-'}")
    typer.echo(f"  filter:         {pi.filter or '-'}")
    typer.echo(f"  decimals:       {pi.decimals if pi.decimals is not None else '-'}")
    typer.echo(f"  legendSets:     {len(pi.legendSets or [])}")
    if pi.description:
        typer.echo(f"  description:    {pi.description}")


@program_indicators_app.command("create")
def program_indicators_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    program_uid: Annotated[str, typer.Option("--program", help="Program UID — required.")],
    expression: Annotated[str, typer.Option("--expression", help="DHIS2 expression (e.g. '#{deUid}').")],
    analytics_type: Annotated[
        str,
        typer.Option("--analytics-type", help="EVENT (default) or ENROLLMENT."),
    ] = "EVENT",
    filter_expression: Annotated[
        str | None,
        typer.Option("--filter", help="Boolean filter expression narrowing the rows."),
    ] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    aggregation_type: Annotated[
        str | None, typer.Option("--aggregation-type", help="Override the default SUM.")
    ] = None,
    decimals: Annotated[int | None, typer.Option("--decimals", help="Rendered decimal places.")] = None,
    legend_set_uid: Annotated[
        list[str] | None, typer.Option("--legend-set", help="LegendSet UID. Repeat for multiple.")
    ] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a ProgramIndicator for a given program."""
    pi = asyncio.run(
        service.create_program_indicator(
            profile_from_env(),
            name=name,
            short_name=short_name,
            program_uid=program_uid,
            expression=expression,
            analytics_type=analytics_type,
            filter_expression=filter_expression,
            description=description,
            aggregation_type=aggregation_type,
            decimals=decimals,
            legend_set_uids=legend_set_uid,
            code=code,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(pi.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] programIndicator [cyan]{pi.id}[/cyan]  name={pi.name!r}")


@program_indicators_app.command("rename")
def program_indicators_rename_command(
    uid: Annotated[str, typer.Argument(help="ProgramIndicator UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update label fields on a ProgramIndicator."""
    pi = asyncio.run(
        service.rename_program_indicator(
            profile_from_env(), uid, name=name, short_name=short_name, description=description
        ),
    )
    if is_json_output():
        typer.echo(pi.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] programIndicator [cyan]{pi.id}[/cyan]  name={pi.name!r}")


@program_indicators_app.command("validate-expression")
def program_indicators_validate_expression_command(
    expression: Annotated[str, typer.Argument(help="Program-indicator expression to validate.")],
) -> None:
    """Parse-check one program-indicator expression — fast pre-flight before create."""
    desc = asyncio.run(service.validate_program_indicator_expression(profile_from_env(), expression))
    if is_json_output():
        typer.echo(desc.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"status:      {desc.status}")
    typer.echo(f"description: {desc.description}")
    if desc.message:
        typer.echo(f"message:     {desc.message}")


@program_indicators_app.command("set-legend-sets")
def program_indicators_set_legend_sets_command(
    uid: Annotated[str, typer.Argument(help="ProgramIndicator UID.")],
    legend_set_uids: Annotated[
        list[str],
        typer.Option("--legend-set", help="LegendSet UID to attach. Empty list clears."),
    ],
) -> None:
    """Replace the legend-set refs on one ProgramIndicator."""
    pi = asyncio.run(
        service.set_program_indicator_legend_sets(profile_from_env(), uid, legend_set_uids=legend_set_uids),
    )
    _console.print(
        f"[green]legend sets[/green] on [cyan]{uid}[/cyan]: {[getattr(ls, 'id', ls) for ls in pi.legendSets or []]}",
    )


@program_indicators_app.command("delete")
def program_indicators_delete_command(
    uid: Annotated[str, typer.Argument(help="ProgramIndicator UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a ProgramIndicator — DHIS2 rejects deletes on PIs used in viz / dashboards."""
    if not yes:
        typer.confirm(f"really delete programIndicator {uid}?", abort=True)
    asyncio.run(service.delete_program_indicator(profile_from_env(), uid))
    _emit_mutation(f"deleted programIndicator {uid}")


# ---------------------------------------------------------------------------
# ProgramIndicatorGroup — `dhis2 metadata program-indicator-groups ...`
# ---------------------------------------------------------------------------


@program_indicator_groups_app.command("get")
def program_indicator_groups_get_command(
    uid: Annotated[str, typer.Argument(help="ProgramIndicatorGroup UID.")],
) -> None:
    """Show one group with its member refs."""
    group = asyncio.run(service.show_program_indicator_group(profile_from_env(), uid))
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{group.name} ({group.id}) code={group.code or '-'}")
    if group.description:
        typer.echo(f"  description: {group.description}")
    typer.echo(f"  members:     {len(group.programIndicators or [])}")


@program_indicator_groups_app.command("members")
def program_indicator_groups_members_command(
    uid: Annotated[str, typer.Argument(help="ProgramIndicatorGroup UID.")],
    page: Annotated[int, typer.Option("--page", help="1-based page number.")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="Rows per page.")] = 50,
) -> None:
    """Page through ProgramIndicators inside one group."""
    members = asyncio.run(
        service.list_program_indicator_group_members(profile_from_env(), uid, page=page, page_size=page_size),
    )
    if is_json_output():
        typer.echo(
            json.dumps([m.model_dump(by_alias=True, exclude_none=True, mode="json") for m in members], indent=2),
        )
        return
    if not members:
        typer.echo(f"no programIndicators in group {uid} on page {page}")
        return
    table = Table(title=f"members of {uid} (page {page})")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("code", style="dim")
    table.add_column("program", style="dim")
    for row in members:
        program_id = getattr(row.program, "id", None) if row.program else None
        table.add_row(
            str(row.id or "-"),
            str(row.name or "-"),
            str(row.code or "-"),
            str(program_id or "-"),
        )
    _console.print(table)


@program_indicator_groups_app.command("create")
def program_indicator_groups_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name.")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name.")],
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
) -> None:
    """Create an empty ProgramIndicatorGroup."""
    group = asyncio.run(
        service.create_program_indicator_group(
            profile_from_env(),
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] programIndicatorGroup [cyan]{group.id}[/cyan]  name={group.name!r}")


@program_indicator_groups_app.command("add-members")
def program_indicator_groups_add_members_command(
    uid: Annotated[str, typer.Argument(help="ProgramIndicatorGroup UID.")],
    program_indicator_uids: Annotated[
        list[str],
        typer.Option("--program-indicator", "-i", help="ProgramIndicator UID to add. Repeat for multiple."),
    ],
) -> None:
    """Add `--program-indicator` members via the per-item POST shortcut."""
    group = asyncio.run(
        service.add_program_indicator_group_members(
            profile_from_env(), uid, program_indicator_uids=program_indicator_uids
        ),
    )
    total = len(group.programIndicators or [])
    _emit_mutation(f"[green]added[/green] {len(program_indicator_uids)} PI(s) to {uid}  total={total}")


@program_indicator_groups_app.command("remove-members")
def program_indicator_groups_remove_members_command(
    uid: Annotated[str, typer.Argument(help="ProgramIndicatorGroup UID.")],
    program_indicator_uids: Annotated[
        list[str],
        typer.Option("--program-indicator", "-i", help="ProgramIndicator UID to drop. Repeat for multiple."),
    ],
) -> None:
    """Drop `--program-indicator` members via the per-item DELETE shortcut."""
    group = asyncio.run(
        service.remove_program_indicator_group_members(
            profile_from_env(), uid, program_indicator_uids=program_indicator_uids
        ),
    )
    total = len(group.programIndicators or [])
    _emit_mutation(f"[green]removed[/green] {len(program_indicator_uids)} PI(s) from {uid}  total={total}")


@program_indicator_groups_app.command("delete")
def program_indicator_groups_delete_command(
    uid: Annotated[str, typer.Argument(help="ProgramIndicatorGroup UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete the grouping row — member program indicators stay."""
    if not yes:
        typer.confirm(f"really delete programIndicatorGroup {uid}?", abort=True)
    asyncio.run(service.delete_program_indicator_group(profile_from_env(), uid))
    _emit_mutation(f"deleted programIndicatorGroup {uid}")


# ---------------------------------------------------------------------------
# CategoryOption workflows — `dhis2 metadata category-options ...`
# ---------------------------------------------------------------------------


@category_options_app.command("get")
def category_options_get_command(
    uid: Annotated[str, typer.Argument(help="CategoryOption UID.")],
) -> None:
    """Show one CategoryOption with its categories + groups inline."""
    co = asyncio.run(service.show_category_option(profile_from_env(), uid))
    if is_json_output():
        typer.echo(co.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{co.name} ({co.id}) code={co.code or '-'}")
    typer.echo(f"  shortName:   {co.shortName or '-'}")
    typer.echo(f"  startDate:   {co.startDate.date() if co.startDate else '-'}")
    typer.echo(f"  endDate:     {co.endDate.date() if co.endDate else '-'}")
    typer.echo(f"  categories:  {len(co.categories or [])}")
    typer.echo(f"  groups:      {len(co.categoryOptionGroups or [])}")
    if co.description:
        typer.echo(f"  description: {co.description}")


@category_options_app.command("create")
def category_options_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="Form name override.")] = None,
    start_date: Annotated[
        str | None,
        typer.Option("--start-date", help="ISO-8601 date — beginning of validity window."),
    ] = None,
    end_date: Annotated[
        str | None,
        typer.Option("--end-date", help="ISO-8601 date — end of validity window."),
    ] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a CategoryOption. Omit `--start-date`/`--end-date` for an always-valid option."""
    co = asyncio.run(
        service.create_category_option(
            profile_from_env(),
            name=name,
            short_name=short_name,
            code=code,
            description=description,
            form_name=form_name,
            start_date=start_date,
            end_date=end_date,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(co.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] categoryOption [cyan]{co.id}[/cyan]  name={co.name!r}")


@category_options_app.command("rename")
def category_options_rename_command(
    uid: Annotated[str, typer.Argument(help="CategoryOption UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="New form name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update the label fields on a CategoryOption."""
    co = asyncio.run(
        service.rename_category_option(
            profile_from_env(),
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(co.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] categoryOption [cyan]{co.id}[/cyan]  name={co.name!r}")


@category_options_app.command("set-validity")
def category_options_set_validity_command(
    uid: Annotated[str, typer.Argument(help="CategoryOption UID.")],
    start_date: Annotated[
        str | None,
        typer.Option("--start-date", help="ISO-8601 date (empty to clear)."),
    ] = None,
    end_date: Annotated[
        str | None,
        typer.Option("--end-date", help="ISO-8601 date (empty to clear)."),
    ] = None,
) -> None:
    """Set the `startDate` / `endDate` validity window on a CategoryOption."""
    co = asyncio.run(
        service.set_category_option_validity(
            profile_from_env(),
            uid,
            start_date=start_date,
            end_date=end_date,
        ),
    )
    _console.print(
        f"[green]validity[/green] on [cyan]{co.id}[/cyan]: "
        f"{co.startDate.date() if co.startDate else '-'} … {co.endDate.date() if co.endDate else '-'}",
    )


@category_options_app.command("delete")
def category_options_delete_command(
    uid: Annotated[str, typer.Argument(help="CategoryOption UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a CategoryOption — DHIS2 rejects deletes on options in use."""
    if not yes:
        typer.confirm(f"really delete categoryOption {uid}?", abort=True)
    asyncio.run(service.delete_category_option(profile_from_env(), uid))
    _emit_mutation(f"deleted categoryOption {uid}")


# ---------------------------------------------------------------------------
# Category workflows — `dhis2 metadata categories ...`
# ---------------------------------------------------------------------------


@categories_app.command("get")
def categories_get_command(
    uid: Annotated[str, typer.Argument(help="Category UID.")],
) -> None:
    """Show one Category with its options inline."""
    cat = asyncio.run(service.show_category(profile_from_env(), uid))
    if is_json_output():
        typer.echo(cat.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{cat.name} ({cat.id}) code={cat.code or '-'}")
    typer.echo(f"  shortName:    {cat.shortName or '-'}")
    typer.echo(f"  type:         {cat.dataDimensionType or '-'}")
    typer.echo(f"  options:      {len(cat.categoryOptions or [])}")
    if cat.description:
        typer.echo(f"  description:  {cat.description}")


@categories_app.command("create")
def categories_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    data_dimension_type: Annotated[
        str,
        typer.Option(
            "--type",
            help="DISAGGREGATION (default) or ATTRIBUTE.",
        ),
    ] = "DISAGGREGATION",
    options: Annotated[
        list[str] | None,
        typer.Option(
            "--option",
            help="CategoryOption UID to wire on create. Repeatable; order is preserved on save.",
        ),
    ] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a Category, optionally wiring CategoryOption members on create."""
    cat = asyncio.run(
        service.create_category(
            profile_from_env(),
            name=name,
            short_name=short_name,
            code=code,
            description=description,
            data_dimension_type=data_dimension_type,
            options=options,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(cat.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[green]created[/green] category [cyan]{cat.id}[/cyan]  name={cat.name!r}  "
        f"options={len(cat.categoryOptions or [])}",
    )


@categories_app.command("rename")
def categories_rename_command(
    uid: Annotated[str, typer.Argument(help="Category UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update the label fields on a Category."""
    cat = asyncio.run(
        service.rename_category(
            profile_from_env(),
            uid,
            name=name,
            short_name=short_name,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(cat.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] category [cyan]{cat.id}[/cyan]  name={cat.name!r}")


@categories_app.command("add-option")
def categories_add_option_command(
    uid: Annotated[str, typer.Argument(help="Category UID.")],
    option_uid: Annotated[str, typer.Argument(help="CategoryOption UID to append.")],
) -> None:
    """Append a CategoryOption to this Category's ordered membership."""
    asyncio.run(service.add_category_option(profile_from_env(), uid, option_uid))
    _emit_mutation(f"[green]added[/green] option [cyan]{option_uid}[/cyan] to category [cyan]{uid}[/cyan]")


@categories_app.command("remove-option")
def categories_remove_option_command(
    uid: Annotated[str, typer.Argument(help="Category UID.")],
    option_uid: Annotated[str, typer.Argument(help="CategoryOption UID to remove.")],
) -> None:
    """Remove a CategoryOption from this Category's membership."""
    asyncio.run(service.remove_category_option(profile_from_env(), uid, option_uid))
    _emit_mutation(f"[green]removed[/green] option [cyan]{option_uid}[/cyan] from category [cyan]{uid}[/cyan]")


@categories_app.command("delete")
def categories_delete_command(
    uid: Annotated[str, typer.Argument(help="Category UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a Category — DHIS2 rejects deletes on categories referenced by a CategoryCombo."""
    if not yes:
        typer.confirm(f"really delete category {uid}?", abort=True)
    asyncio.run(service.delete_category(profile_from_env(), uid))
    _emit_mutation(f"deleted category {uid}")


# ---------------------------------------------------------------------------
# CategoryCombo workflows — `dhis2 metadata category-combos ...`
# ---------------------------------------------------------------------------


@category_combos_app.command("get")
def category_combos_get_command(
    uid: Annotated[str, typer.Argument(help="CategoryCombo UID.")],
) -> None:
    """Show one CategoryCombo with its category + COC refs inline."""
    cc = asyncio.run(service.show_category_combo(profile_from_env(), uid))
    if is_json_output():
        typer.echo(cc.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{cc.name} ({cc.id}) code={cc.code or '-'}")
    typer.echo(f"  type:         {cc.dataDimensionType or '-'}")
    typer.echo(f"  default:      {cc.isDefault!r}")
    typer.echo(f"  skipTotal:    {cc.skipTotal!r}")
    typer.echo(f"  categories:   {len(cc.categories or [])}")
    typer.echo(f"  COCs:         {len(cc.categoryOptionCombos or [])}")


@category_combos_app.command("create")
def category_combos_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name (<=230 chars).")],
    categories: Annotated[
        list[str],
        typer.Option(
            "--category",
            help="Category UID. Repeatable; order is preserved on save and shapes the COC matrix.",
        ),
    ],
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    data_dimension_type: Annotated[
        str,
        typer.Option("--type", help="DISAGGREGATION (default) or ATTRIBUTE."),
    ] = "DISAGGREGATION",
    skip_total: Annotated[
        bool,
        typer.Option(
            "--skip-total/--with-total",
            help="Omit the total aggregation row downstream tables draw from this combo.",
        ),
    ] = False,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a CategoryCombo with an ordered list of Category UIDs."""
    if not categories:
        raise typer.BadParameter("pass at least one --category UID")
    cc = asyncio.run(
        service.create_category_combo(
            profile_from_env(),
            name=name,
            categories=list(categories),
            code=code,
            data_dimension_type=data_dimension_type,
            skip_total=skip_total,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(cc.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[green]created[/green] categoryCombo [cyan]{cc.id}[/cyan]  name={cc.name!r}  "
        f"categories={len(cc.categories or [])}",
    )
    _console.print(
        "[yellow]note[/yellow] DHIS2 regenerates the categoryOptionCombo matrix in the background — "
        "use `category-combos wait-for-cocs` to block until it lands.",
    )


@category_combos_app.command("rename")
def category_combos_rename_command(
    uid: Annotated[str, typer.Argument(help="CategoryCombo UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="New code.")] = None,
) -> None:
    """Partial-update label fields on a CategoryCombo."""
    cc = asyncio.run(service.rename_category_combo(profile_from_env(), uid, name=name, code=code))
    if is_json_output():
        typer.echo(cc.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] categoryCombo [cyan]{cc.id}[/cyan]  name={cc.name!r}")


@category_combos_app.command("add-category")
def category_combos_add_category_command(
    uid: Annotated[str, typer.Argument(help="CategoryCombo UID.")],
    category_uid: Annotated[str, typer.Argument(help="Category UID to append.")],
) -> None:
    """Append a Category to this combo's ordered membership.

    DHIS2 regenerates the COC matrix server-side. Re-fetch the combo + use
    `wait-for-cocs` if you need to block until the new matrix lands.
    """
    asyncio.run(service.add_category_to_combo(profile_from_env(), uid, category_uid))
    _emit_mutation(f"[green]added[/green] category [cyan]{category_uid}[/cyan] to combo [cyan]{uid}[/cyan]")


@category_combos_app.command("remove-category")
def category_combos_remove_category_command(
    uid: Annotated[str, typer.Argument(help="CategoryCombo UID.")],
    category_uid: Annotated[str, typer.Argument(help="Category UID to remove.")],
) -> None:
    """Remove a Category from this combo's membership."""
    asyncio.run(service.remove_category_from_combo(profile_from_env(), uid, category_uid))
    _emit_mutation(
        f"[green]removed[/green] category [cyan]{category_uid}[/cyan] from combo [cyan]{uid}[/cyan]",
    )


@category_combos_app.command("wait-for-cocs")
def category_combos_wait_for_cocs_command(
    uid: Annotated[str, typer.Argument(help="CategoryCombo UID.")],
    expected: Annotated[
        int,
        typer.Option("--expected", help="Expected total of CategoryOptionCombos materialised by this combo."),
    ],
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Seconds to wait before giving up (default 60)."),
    ] = 60.0,
    poll: Annotated[
        float,
        typer.Option("--poll", help="Seconds between polls (default 1)."),
    ] = 1.0,
) -> None:
    """Block until the COC matrix on this combo reaches `--expected`.

    Cold-start regen of a large combo can take tens of seconds, especially
    under arm64 emulation. Use after `create` or `add-category` when the
    next step depends on the matrix being ready.
    """
    landed = asyncio.run(
        service.wait_for_coc_generation(
            profile_from_env(),
            uid,
            expected_count=expected,
            timeout_seconds=timeout,
            poll_interval_seconds=poll,
        ),
    )
    _console.print(
        f"[green]matrix ready[/green] on [cyan]{uid}[/cyan]: {landed} categoryOptionCombo(s) (expected {expected})",
    )


@category_combos_app.command("delete")
def category_combos_delete_command(
    uid: Annotated[str, typer.Argument(help="CategoryCombo UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a CategoryCombo — DHIS2 rejects the default combo + combos in use."""
    if not yes:
        typer.confirm(f"really delete categoryCombo {uid}?", abort=True)
    asyncio.run(service.delete_category_combo(profile_from_env(), uid))
    _emit_mutation(f"deleted categoryCombo {uid}")


@category_combos_app.command("build")
def category_combos_build_command(
    spec_file: Annotated[
        str,
        typer.Option(
            "--spec",
            help=(
                "Path to a JSON CategoryComboBuildSpec, or `-` to read from stdin. "
                "Shape: `{name, categories: [{name, options: [{name, ...}, ...]}, ...]}`."
            ),
        ),
    ],
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Seconds to wait for the COC matrix to settle (default 120)."),
    ] = 120.0,
    poll: Annotated[
        float,
        typer.Option("--poll", help="Seconds between matrix polls (default 1)."),
    ] = 1.0,
) -> None:
    """One-pass create-or-reuse for the full Category dimension stack.

    Walks a declarative `CategoryComboBuildSpec`, ensuring every
    `CategoryOption` -> `Category` -> `CategoryCombo` referenced exists
    on the target. Idempotent — re-running the same spec is a no-op
    modulo new options getting wired into existing categories. Polls
    the COC matrix until the cross-product count lands.

    Lookup is by `name` (DHIS2 enforces unique names on each layer).
    Existing entries are reused; only missing entries get created.
    """
    spec_text = sys.stdin.read() if spec_file == "-" else Path(spec_file).read_text(encoding="utf-8")
    try:
        from dhis2w_client.v43 import CategoryComboBuildSpec

        spec = CategoryComboBuildSpec.model_validate_json(spec_text)
    except ValueError as exc:
        raise typer.BadParameter(f"invalid spec: {exc}") from exc
    result = asyncio.run(
        service.build_category_combo_spec(
            profile_from_env(), spec, timeout_seconds=timeout, poll_interval_seconds=poll
        ),
    )
    if is_json_output():
        typer.echo(result.model_dump_json(indent=2))
        return

    _console.print(
        f"[green]combo[/green] [cyan]{result.combo_uid}[/cyan]  "
        f"({'created' if result.combo_created else 'reused'})  "
        f"COCs={result.coc_count}/{result.expected_coc_count}",
    )
    if result.combo_appended_category_uids:
        _console.print(
            "  appended categories: " + ", ".join(f"[cyan]{uid}[/cyan]" for uid in result.combo_appended_category_uids),
        )
    table = Table(title=f"categories ({len(result.categories)})")
    table.add_column("name", overflow="fold")
    table.add_column("uid", style="cyan", no_wrap=True)
    table.add_column("status", justify="center")
    table.add_column("options", justify="right")
    table.add_column("created options", justify="right")
    table.add_column("appended options", justify="right")
    for entry in result.categories:
        table.add_row(
            entry.name,
            entry.uid,
            "[green]created[/green]" if entry.created else "[dim]reused[/dim]",
            str(len(entry.option_uids)),
            str(len(entry.created_option_uids)),
            str(len(entry.appended_option_uids)),
        )
    _console.print(table)


# ---------------------------------------------------------------------------
# CategoryOptionCombo read-only — `dhis2 metadata category-option-combos ...`
# ---------------------------------------------------------------------------


@category_option_combos_app.command("get")
def category_option_combos_get_command(
    uid: Annotated[str, typer.Argument(help="CategoryOptionCombo UID.")],
) -> None:
    """Show one CategoryOptionCombo with its parent combo + option refs."""
    coc = asyncio.run(service.show_category_option_combo(profile_from_env(), uid))
    if is_json_output():
        typer.echo(coc.model_dump_json(indent=2, exclude_none=True))
        return
    combo_id = coc.categoryCombo.id if coc.categoryCombo else "-"
    typer.echo(f"{coc.name} ({coc.id}) code={coc.code or '-'}")
    typer.echo(f"  combo:   {combo_id}")
    typer.echo(f"  options: {len(coc.categoryOptions or [])}")


@category_option_combos_app.command("list-for-combo")
def category_option_combos_list_for_combo_command(
    combo_uid: Annotated[str, typer.Argument(help="CategoryCombo UID.")],
) -> None:
    """List every CategoryOptionCombo materialised by one CategoryCombo."""
    rows = asyncio.run(service.list_category_option_combos_for_combo(profile_from_env(), combo_uid))
    if is_json_output():
        typer.echo(
            json.dumps([row.model_dump(by_alias=True, exclude_none=True, mode="json") for row in rows], indent=2)
        )
        return
    if not rows:
        typer.echo(f"no categoryOptionCombos for combo {combo_uid} yet (matrix may still be regenerating)")
        return
    table = Table(title=f"COCs for combo {combo_uid} ({len(rows)} rows)")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("code", style="dim")
    for row in rows:
        table.add_row(str(row.id or "-"), str(row.name or "-"), str(row.code or "-"))
    _console.print(table)


# ---------------------------------------------------------------------------
# CategoryOptionGroup — `dhis2 metadata category-option-groups ...`
# ---------------------------------------------------------------------------


@category_option_groups_app.command("get")
def category_option_groups_get_command(
    uid: Annotated[str, typer.Argument(help="CategoryOptionGroup UID.")],
) -> None:
    """Show one group with its member + group-set refs."""
    group = asyncio.run(service.show_category_option_group(profile_from_env(), uid))
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{group.name} ({group.id}) code={group.code or '-'}")
    if group.description:
        typer.echo(f"  description: {group.description}")
    typer.echo(f"  members:     {len(group.categoryOptions or [])}")
    typer.echo(f"  group sets:  {len(group.groupSets or [])}")


@category_option_groups_app.command("members")
def category_option_groups_members_command(
    uid: Annotated[str, typer.Argument(help="CategoryOptionGroup UID.")],
    page: Annotated[int, typer.Option("--page", help="1-based page number.")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="Rows per page.")] = 50,
) -> None:
    """Page through CategoryOptions inside one group."""
    members = asyncio.run(
        service.list_category_option_group_members(profile_from_env(), uid, page=page, page_size=page_size),
    )
    if is_json_output():
        typer.echo(
            json.dumps([m.model_dump(by_alias=True, exclude_none=True, mode="json") for m in members], indent=2),
        )
        return
    if not members:
        typer.echo(f"no categoryOptions in group {uid} on page {page}")
        return
    table = Table(title=f"members of {uid} (page {page})")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("code", style="dim")
    for row in members:
        table.add_row(
            str(row.id or "-"),
            str(row.name or "-"),
            str(row.code or "-"),
        )
    _console.print(table)


@category_option_groups_app.command("create")
def category_option_groups_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name.")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name.")],
    data_dimension_type: Annotated[
        str,
        typer.Option("--data-dimension-type", help="DISAGGREGATION (default) or ATTRIBUTE."),
    ] = "DISAGGREGATION",
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
) -> None:
    """Create an empty CategoryOptionGroup."""
    group = asyncio.run(
        service.create_category_option_group(
            profile_from_env(),
            name=name,
            short_name=short_name,
            data_dimension_type=data_dimension_type,
            uid=uid,
            code=code,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] categoryOptionGroup [cyan]{group.id}[/cyan]  name={group.name!r}")


@category_option_groups_app.command("add-members")
def category_option_groups_add_members_command(
    uid: Annotated[str, typer.Argument(help="CategoryOptionGroup UID.")],
    category_option_uids: Annotated[
        list[str],
        typer.Option("--category-option", "-c", help="CategoryOption UID to add. Repeat for multiple."),
    ],
) -> None:
    """Add `--category-option` members via the per-item POST shortcut."""
    group = asyncio.run(
        service.add_category_option_group_members(
            profile_from_env(),
            uid,
            category_option_uids=category_option_uids,
        ),
    )
    total = len(group.categoryOptions or [])
    _emit_mutation(f"[green]added[/green] {len(category_option_uids)} CO(s) to {uid}  total={total}")


@category_option_groups_app.command("remove-members")
def category_option_groups_remove_members_command(
    uid: Annotated[str, typer.Argument(help="CategoryOptionGroup UID.")],
    category_option_uids: Annotated[
        list[str],
        typer.Option("--category-option", "-c", help="CategoryOption UID to drop. Repeat for multiple."),
    ],
) -> None:
    """Drop `--category-option` members via the per-item DELETE shortcut."""
    group = asyncio.run(
        service.remove_category_option_group_members(
            profile_from_env(),
            uid,
            category_option_uids=category_option_uids,
        ),
    )
    total = len(group.categoryOptions or [])
    _emit_mutation(f"[green]removed[/green] {len(category_option_uids)} CO(s) from {uid}  total={total}")


@category_option_groups_app.command("delete")
def category_option_groups_delete_command(
    uid: Annotated[str, typer.Argument(help="CategoryOptionGroup UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete the grouping row — member category options stay."""
    if not yes:
        typer.confirm(f"really delete categoryOptionGroup {uid}?", abort=True)
    asyncio.run(service.delete_category_option_group(profile_from_env(), uid))
    _emit_mutation(f"deleted categoryOptionGroup {uid}")


# ---------------------------------------------------------------------------
# CategoryOptionGroupSet — `dhis2 metadata category-option-group-sets ...`
# ---------------------------------------------------------------------------


@category_option_group_sets_app.command("get")
def category_option_group_sets_get_command(
    uid: Annotated[str, typer.Argument(help="CategoryOptionGroupSet UID.")],
) -> None:
    """Show one group set with its groups."""
    gs = asyncio.run(service.show_category_option_group_set(profile_from_env(), uid))
    if is_json_output():
        typer.echo(gs.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{gs.name} ({gs.id}) code={gs.code or '-'}")
    if gs.description:
        typer.echo(f"  description:    {gs.description}")
    typer.echo(f"  dimensionType:  {gs.dataDimensionType.value if gs.dataDimensionType else '-'}")
    typer.echo(f"  dataDimension:  {'yes' if gs.dataDimension else 'no'}")
    groups = list(gs.categoryOptionGroups or [])
    if not groups:
        typer.echo("  (no groups)")
        return
    table = Table(title=f"groups in {gs.name}")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("code", style="dim")
    for group in groups:
        if not isinstance(group, dict):
            continue
        table.add_row(
            str(group.get("id") or "-"),
            str(group.get("name") or "-"),
            str(group.get("code") or "-"),
        )
    _console.print(table)


@category_option_group_sets_app.command("create")
def category_option_group_sets_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name.")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name.")],
    data_dimension_type: Annotated[
        str,
        typer.Option("--data-dimension-type", help="DISAGGREGATION (default) or ATTRIBUTE."),
    ] = "DISAGGREGATION",
    data_dimension: Annotated[
        bool,
        typer.Option("--data-dimension/--no-data-dimension", help="Expose as analytics axis."),
    ] = True,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
) -> None:
    """Create an empty CategoryOptionGroupSet."""
    gs = asyncio.run(
        service.create_category_option_group_set(
            profile_from_env(),
            name=name,
            short_name=short_name,
            data_dimension_type=data_dimension_type,
            data_dimension=data_dimension,
            uid=uid,
            code=code,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(gs.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] categoryOptionGroupSet [cyan]{gs.id}[/cyan]  name={gs.name!r}")


@category_option_group_sets_app.command("add-groups")
def category_option_group_sets_add_groups_command(
    uid: Annotated[str, typer.Argument(help="CategoryOptionGroupSet UID.")],
    group_uids: Annotated[
        list[str],
        typer.Option("--group", help="CategoryOptionGroup UID to add. Repeat for multiple."),
    ],
) -> None:
    """Add `--group` members to a group set."""
    gs = asyncio.run(service.add_category_option_group_set_groups(profile_from_env(), uid, group_uids=group_uids))
    total = len(gs.categoryOptionGroups or [])
    _emit_mutation(f"[green]added[/green] {len(group_uids)} group(s) to {uid}  total={total}")


@category_option_group_sets_app.command("remove-groups")
def category_option_group_sets_remove_groups_command(
    uid: Annotated[str, typer.Argument(help="CategoryOptionGroupSet UID.")],
    group_uids: Annotated[
        list[str],
        typer.Option("--group", help="CategoryOptionGroup UID to drop. Repeat for multiple."),
    ],
) -> None:
    """Drop `--group` members from a group set."""
    gs = asyncio.run(service.remove_category_option_group_set_groups(profile_from_env(), uid, group_uids=group_uids))
    total = len(gs.categoryOptionGroups or [])
    _emit_mutation(f"[green]removed[/green] {len(group_uids)} group(s) from {uid}  total={total}")


@category_option_group_sets_app.command("delete")
def category_option_group_sets_delete_command(
    uid: Annotated[str, typer.Argument(help="CategoryOptionGroupSet UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a CategoryOptionGroupSet — member groups stay."""
    if not yes:
        typer.confirm(f"really delete categoryOptionGroupSet {uid}?", abort=True)
    asyncio.run(service.delete_category_option_group_set(profile_from_env(), uid))
    _emit_mutation(f"deleted categoryOptionGroupSet {uid}")


# ---------------------------------------------------------------------------
# OrganisationUnit workflows — `dhis2 metadata organisation-units ...`
# ---------------------------------------------------------------------------


def _unit_level(unit: Any) -> int | None:
    """Return the OU's depth.

    DHIS2 emits `level` on `/api/organisationUnits` responses but the
    generated model field is `hierarchyLevel`; `level` lands in
    `model_extra` via the `extra="allow"` config. Prefer the extra
    (what the server returned), fall back to `hierarchyLevel`.
    """
    extra_level = getattr(unit, "level", None)
    if isinstance(extra_level, int):
        return extra_level
    return unit.hierarchyLevel  # type: ignore[no-any-return]


@organisation_units_app.command("get")
def organisation_units_get_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnit UID.")],
) -> None:
    """Show one OU with parent + core hierarchy fields."""
    unit = asyncio.run(service.show_organisation_unit(profile_from_env(), uid))
    if is_json_output():
        typer.echo(unit.model_dump_json(indent=2, exclude_none=True))
        return
    parent_ref = unit.parent
    parent_label = "-"
    if parent_ref is not None:
        parent_id = getattr(parent_ref, "id", None)
        if parent_id:
            parent_label = str(parent_id)
    typer.echo(f"{unit.name} ({unit.id}) code={unit.code or '-'}")
    typer.echo(f"  level:  {_unit_level(unit) or '-'}")
    typer.echo(f"  parent: {parent_label}")
    typer.echo(f"  path:   {unit.path or '-'}")
    if unit.description:
        typer.echo(f"  description: {unit.description}")


@organisation_units_app.command("tree")
def organisation_units_tree_command(
    root_uid: Annotated[str, typer.Argument(help="Root OU UID — render this + descendants.")],
    max_depth: Annotated[
        int, typer.Option("--max-depth", help="Depth of descendants to include (0 = just the root).")
    ] = 3,
) -> None:
    """Render a bounded-depth subtree indented by hierarchy level."""
    units = asyncio.run(
        service.tree_organisation_units(profile_from_env(), root_uid=root_uid, max_depth=max_depth),
    )
    if is_json_output():
        typer.echo(json.dumps([u.model_dump(by_alias=True, exclude_none=True, mode="json") for u in units], indent=2))
        return
    if not units:
        typer.echo(f"no subtree rooted at {root_uid}")
        return
    # DHIS2's materialised `path` field gives tree order for free (a
    # pre-order walk): sorting alphabetically groups every child under
    # its parent. Breadth-first would instead dump every L2 first, then
    # every L3, breaking the visual hierarchy.
    sorted_units = sorted(units, key=lambda u: u.path or "")
    root_level = _unit_level(sorted_units[0]) or 1
    for unit in sorted_units:
        unit_level = _unit_level(unit) or root_level
        indent = "  " * max(unit_level - root_level, 0)
        typer.echo(f"{indent}- {unit.name} ({unit.id}) [L{unit_level}]")


@organisation_units_app.command("create")
def organisation_units_create_command(
    parent_uid: Annotated[str, typer.Argument(help="Parent OU UID to create under.")],
    name: Annotated[str, typer.Option("--name", help="Full name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    opening_date: Annotated[str, typer.Option("--opening-date", help="ISO-8601 date, e.g. 2024-01-01.")],
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID (generated when omitted).")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free-text description.")] = None,
) -> None:
    """Create a child OU under `parent_uid`."""
    unit = asyncio.run(
        service.create_organisation_unit(
            profile_from_env(),
            parent_uid=parent_uid,
            name=name,
            short_name=short_name,
            opening_date=opening_date,
            uid=uid,
            code=code,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(unit.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[green]created[/green] OU [cyan]{unit.id}[/cyan]  name={unit.name!r}  path={unit.path}",
    )


@organisation_units_app.command("move")
def organisation_units_move_command(
    uid: Annotated[str, typer.Argument(help="OU UID to reparent.")],
    new_parent_uid: Annotated[str, typer.Argument(help="New parent OU UID.")],
) -> None:
    """Reparent an OU. DHIS2 recomputes `path` + `hierarchyLevel`."""
    unit = asyncio.run(
        service.move_organisation_unit(profile_from_env(), uid=uid, new_parent_uid=new_parent_uid),
    )
    if is_json_output():
        typer.echo(unit.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[green]moved[/green] [cyan]{unit.id}[/cyan]  new parent={new_parent_uid}  path={unit.path}",
    )


@organisation_units_app.command("delete")
def organisation_units_delete_command(
    uid: Annotated[str, typer.Argument(help="OU UID to delete.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Delete an OU. DHIS2 rejects deletes on units with children or data."""
    if not yes:
        typer.confirm(f"really delete organisationUnit {uid}?", abort=True)
    asyncio.run(service.delete_organisation_unit(profile_from_env(), uid))
    _emit_mutation(f"deleted organisationUnit {uid}")


# ---------------------------------------------------------------------------
# OrganisationUnitGroup — `dhis2 metadata organisation-unit-groups ...`
# ---------------------------------------------------------------------------


@organisation_unit_groups_app.command("get")
def organisation_unit_groups_get_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitGroup UID.")],
) -> None:
    """Show one group with its member refs and the group-sets it belongs to."""
    group = asyncio.run(service.show_organisation_unit_group(profile_from_env(), uid))
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{group.name} ({group.id}) code={group.code or '-'}")
    if group.description:
        typer.echo(f"  description: {group.description}")
    members = list(group.organisationUnits or [])
    group_sets = list(group.groupSets or [])
    typer.echo(f"  members: {len(members)}")
    typer.echo(f"  group sets: {len(group_sets)}")
    if group_sets:
        for gs in group_sets:
            if isinstance(gs, dict):
                typer.echo(f"    - {gs.get('name')} ({gs.get('id')})")


@organisation_unit_groups_app.command("members")
def organisation_unit_groups_members_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitGroup UID.")],
    page: Annotated[int, typer.Option("--page", help="1-based page number.")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="Rows per page.")] = 50,
) -> None:
    """Page through the OUs inside one group."""
    members = asyncio.run(
        service.list_organisation_unit_group_members(
            profile_from_env(),
            uid,
            page=page,
            page_size=page_size,
        ),
    )
    if is_json_output():
        typer.echo(json.dumps([m.model_dump(by_alias=True, exclude_none=True, mode="json") for m in members], indent=2))
        return
    if not members:
        typer.echo(f"no OUs in group {uid} on page {page}")
        return
    table = Table(title=f"members of {uid} (page {page})")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("code", style="dim")
    table.add_column("level", justify="right")
    for row in members:
        table.add_row(
            str(row.id or "-"),
            str(row.name or "-"),
            str(row.code or "-"),
            str(_unit_level(row) or "-"),
        )
    _console.print(table)


@organisation_unit_groups_app.command("create")
def organisation_unit_groups_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name (<=230 chars, unique).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars, unique).")],
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID (generated when omitted).")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free-text description.")] = None,
    color: Annotated[str | None, typer.Option("--color", help="Hex colour (#RRGGBB).")] = None,
) -> None:
    """Create an empty OrganisationUnitGroup."""
    group = asyncio.run(
        service.create_organisation_unit_group(
            profile_from_env(),
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
            color=color,
        ),
    )
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] organisationUnitGroup [cyan]{group.id}[/cyan]  name={group.name!r}")


@organisation_unit_groups_app.command("add-members")
def organisation_unit_groups_add_members_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitGroup UID.")],
    ou_uids: Annotated[list[str], typer.Option("--ou", help="OU UID to add. Repeat for multiple.")],
) -> None:
    """Add `--ou` members to a group via the per-item POST shortcut."""
    group = asyncio.run(
        service.add_organisation_unit_group_members(profile_from_env(), uid, ou_uids=ou_uids),
    )
    member_count = len(group.organisationUnits or [])
    _emit_mutation(
        f"[green]added[/green] {len(ou_uids)} OU(s) to {uid}  total members={member_count}",
    )


@organisation_unit_groups_app.command("remove-members")
def organisation_unit_groups_remove_members_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitGroup UID.")],
    ou_uids: Annotated[list[str], typer.Option("--ou", help="OU UID to remove. Repeat for multiple.")],
) -> None:
    """Drop `--ou` members from a group via the per-item DELETE shortcut."""
    group = asyncio.run(
        service.remove_organisation_unit_group_members(profile_from_env(), uid, ou_uids=ou_uids),
    )
    member_count = len(group.organisationUnits or [])
    _emit_mutation(
        f"[green]removed[/green] {len(ou_uids)} OU(s) from {uid}  total members={member_count}",
    )


@organisation_unit_groups_app.command("delete")
def organisation_unit_groups_delete_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitGroup UID to delete.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Delete an OrganisationUnitGroup — members stay."""
    if not yes:
        typer.confirm(f"really delete organisationUnitGroup {uid}?", abort=True)
    asyncio.run(service.delete_organisation_unit_group(profile_from_env(), uid))
    _emit_mutation(f"deleted organisationUnitGroup {uid}")


# ---------------------------------------------------------------------------
# OrganisationUnitGroupSet — `dhis2 metadata organisation-unit-group-sets ...`
# ---------------------------------------------------------------------------


@organisation_unit_group_sets_app.command("get")
def organisation_unit_group_sets_get_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitGroupSet UID.")],
) -> None:
    """Show one group set with its groups + per-group member counts."""
    group_set, group_member_counts = asyncio.run(
        service.show_organisation_unit_group_set(profile_from_env(), uid),
    )
    if is_json_output():
        typer.echo(group_set.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{group_set.name} ({group_set.id}) code={group_set.code or '-'}")
    if group_set.description:
        typer.echo(f"  description: {group_set.description}")
    typer.echo(f"  compulsory: {'yes' if group_set.compulsory else 'no'}")
    typer.echo(f"  data dimension: {'yes' if group_set.dataDimension else 'no'}")
    groups = list(group_set.organisationUnitGroups or [])
    if not groups:
        typer.echo("  (no groups)")
        return
    table = Table(title=f"groups in {group_set.name}")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("code", style="dim")
    table.add_column("members", justify="right")
    for group in groups:
        if not isinstance(group, dict):
            continue
        gid = str(group.get("id") or "-")
        table.add_row(
            gid,
            str(group.get("name") or "-"),
            str(group.get("code") or "-"),
            str(group_member_counts.get(gid, 0)),
        )
    _console.print(table)


@organisation_unit_group_sets_app.command("create")
def organisation_unit_group_sets_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name (<=230 chars, unique).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars, unique).")],
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID (generated when omitted).")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free-text description.")] = None,
    compulsory: Annotated[
        bool,
        typer.Option("--compulsory/--not-compulsory", help="Require OUs to land in exactly one group of this set."),
    ] = False,
    data_dimension: Annotated[
        bool, typer.Option("--data-dimension/--no-data-dimension", help="Expose as a pivot/visualisation axis.")
    ] = True,
) -> None:
    """Create an empty OrganisationUnitGroupSet."""
    group_set = asyncio.run(
        service.create_organisation_unit_group_set(
            profile_from_env(),
            name=name,
            short_name=short_name,
            uid=uid,
            code=code,
            description=description,
            compulsory=compulsory,
            data_dimension=data_dimension,
        ),
    )
    if is_json_output():
        typer.echo(group_set.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[green]created[/green] organisationUnitGroupSet [cyan]{group_set.id}[/cyan]  name={group_set.name!r}",
    )


@organisation_unit_group_sets_app.command("add-groups")
def organisation_unit_group_sets_add_groups_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitGroupSet UID.")],
    group_uids: Annotated[
        list[str], typer.Option("--group", help="OrganisationUnitGroup UID to add. Repeat for multiple.")
    ],
) -> None:
    """Add `--group` members to a group set."""
    group_set = asyncio.run(
        service.add_organisation_unit_group_set_groups(profile_from_env(), uid, group_uids=group_uids),
    )
    total = len(group_set.organisationUnitGroups or [])
    _emit_mutation(f"[green]added[/green] {len(group_uids)} group(s) to {uid}  total groups={total}")


@organisation_unit_group_sets_app.command("remove-groups")
def organisation_unit_group_sets_remove_groups_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitGroupSet UID.")],
    group_uids: Annotated[
        list[str], typer.Option("--group", help="OrganisationUnitGroup UID to drop. Repeat for multiple.")
    ],
) -> None:
    """Drop `--group` members from a group set."""
    group_set = asyncio.run(
        service.remove_organisation_unit_group_set_groups(profile_from_env(), uid, group_uids=group_uids),
    )
    total = len(group_set.organisationUnitGroups or [])
    _emit_mutation(f"[green]removed[/green] {len(group_uids)} group(s) from {uid}  total groups={total}")


@organisation_unit_group_sets_app.command("delete")
def organisation_unit_group_sets_delete_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitGroupSet UID to delete.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Delete an OrganisationUnitGroupSet — groups stay."""
    if not yes:
        typer.confirm(f"really delete organisationUnitGroupSet {uid}?", abort=True)
    asyncio.run(service.delete_organisation_unit_group_set(profile_from_env(), uid))
    _emit_mutation(f"deleted organisationUnitGroupSet {uid}")


# ---------------------------------------------------------------------------
# OrganisationUnitLevel — `dhis2 metadata organisation-unit-levels ...`
# ---------------------------------------------------------------------------


@organisation_unit_levels_app.command("get")
def organisation_unit_levels_get_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitLevel UID (or pass --by-level).")],
    by_level: Annotated[bool, typer.Option("--by-level", help="Treat UID as the numeric level (1 = roots).")] = False,
) -> None:
    """Show one level row — by UID (default) or by numeric depth."""
    if by_level:
        try:
            numeric = int(uid)
        except ValueError:
            typer.echo(f"--by-level requires an integer, got {uid!r}", err=True)
            raise typer.Exit(code=1) from None
        row = asyncio.run(service.show_organisation_unit_level_by_level(profile_from_env(), numeric))
    else:
        row = asyncio.run(service.show_organisation_unit_level(profile_from_env(), uid))
    if row is None:
        typer.echo("no matching OrganisationUnitLevel")
        raise typer.Exit(code=1)
    if is_json_output():
        typer.echo(row.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"level {row.level}: {row.name} ({row.id}) code={row.code or '-'}")
    typer.echo(f"  offlineLevels: {row.offlineLevels or '-'}")


@organisation_unit_levels_app.command("rename")
def organisation_unit_levels_rename_command(
    uid: Annotated[str, typer.Argument(help="OrganisationUnitLevel UID (or the numeric level with --by-level).")],
    name: Annotated[str, typer.Option("--name", help="New human label (e.g. 'Country', 'District', 'Facility').")],
    by_level: Annotated[bool, typer.Option("--by-level", help="Treat UID as the numeric level (1 = roots).")] = False,
    code: Annotated[str | None, typer.Option("--code", help="Optionally update the business code.")] = None,
    offline_levels: Annotated[
        int | None, typer.Option("--offline-levels", help="How many levels to cache offline from this one.")
    ] = None,
) -> None:
    """Give a level a human label — turns 'level 2' into 'Province'."""
    if by_level:
        try:
            numeric = int(uid)
        except ValueError:
            typer.echo(f"--by-level requires an integer, got {uid!r}", err=True)
            raise typer.Exit(code=1) from None
        row = asyncio.run(
            service.rename_organisation_unit_level_by_level(
                profile_from_env(),
                numeric,
                name=name,
                code=code,
                offline_levels=offline_levels,
            ),
        )
    else:
        row = asyncio.run(
            service.rename_organisation_unit_level(
                profile_from_env(),
                uid,
                name=name,
                code=code,
                offline_levels=offline_levels,
            ),
        )
    if is_json_output():
        typer.echo(row.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[green]renamed[/green] level {row.level} -> {row.name!r}  ({row.id})",
    )


# ---------------------------------------------------------------------------
# DataSet workflows — `dhis2 metadata data-sets ...`
# ---------------------------------------------------------------------------


@data_sets_app.command("get")
def data_sets_get_command(
    uid: Annotated[str, typer.Argument(help="DataSet UID.")],
) -> None:
    """Show one DataSet with its DSE + section + OU counts inline."""
    ds = asyncio.run(service.show_data_set(profile_from_env(), uid))
    if is_json_output():
        typer.echo(ds.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{ds.name} ({ds.id}) code={ds.code or '-'}")
    typer.echo(f"  periodType:   {ds.periodType.value if ds.periodType else '-'}")
    typer.echo(f"  elements:     {len(ds.dataSetElements or [])}")
    typer.echo(f"  sections:     {len(ds.sections or [])}")
    typer.echo(f"  organisation units: {len(ds.organisationUnits or [])}")
    if ds.openFuturePeriods is not None:
        typer.echo(f"  openFuturePeriods: {ds.openFuturePeriods}")
    if ds.expiryDays is not None:
        typer.echo(f"  expiryDays:   {ds.expiryDays}")
    if ds.description:
        typer.echo(f"  description:  {ds.description}")


@data_sets_app.command("create")
def data_sets_create_command(
    name: Annotated[str, typer.Option("--name", help="Full name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    period_type: Annotated[
        str,
        typer.Option("--period-type", help="Period type (Monthly, Weekly, Daily, Quarterly, Yearly, …)."),
    ],
    category_combo: Annotated[
        str | None,
        typer.Option("--category-combo", "-cc", help="CategoryCombo UID (defaults to the instance default)."),
    ] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="Form-name override.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    open_future_periods: Annotated[
        int | None,
        typer.Option("--open-future-periods", help="Number of future periods open for entry."),
    ] = None,
    expiry_days: Annotated[
        int | None,
        typer.Option("--expiry-days", help="Days after period-end that entry remains open."),
    ] = None,
    timely_days: Annotated[
        int | None,
        typer.Option("--timely-days", help="Days after period-start considered on-time."),
    ] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a DataSet."""
    ds = asyncio.run(
        service.create_data_set(
            profile_from_env(),
            name=name,
            short_name=short_name,
            period_type=period_type,
            category_combo_uid=category_combo,
            code=code,
            form_name=form_name,
            description=description,
            open_future_periods=open_future_periods,
            expiry_days=expiry_days,
            timely_days=timely_days,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(ds.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] dataSet [cyan]{ds.id}[/cyan]  name={ds.name!r}")


@data_sets_app.command("rename")
def data_sets_rename_command(
    uid: Annotated[str, typer.Argument(help="DataSet UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="New form name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update the label fields on a DataSet."""
    ds = asyncio.run(
        service.rename_data_set(
            profile_from_env(),
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(ds.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] dataSet [cyan]{ds.id}[/cyan]  name={ds.name!r}")


@data_sets_app.command("add-element")
def data_sets_add_element_command(
    data_set_uid: Annotated[str, typer.Argument(help="DataSet UID.")],
    data_element_uid: Annotated[str, typer.Argument(help="DataElement UID to attach.")],
    category_combo: Annotated[
        str | None,
        typer.Option("--category-combo", "-cc", help="CategoryCombo UID override for this DSE."),
    ] = None,
) -> None:
    """Attach a DataElement to the DataSet (optionally with a per-set CategoryCombo override)."""
    ds = asyncio.run(
        service.add_data_set_element(
            profile_from_env(),
            data_set_uid,
            data_element_uid,
            category_combo_uid=category_combo,
        ),
    )
    _emit_mutation(
        f"[green]+ element[/green] dataSet [cyan]{ds.id}[/cyan]  "
        f"de={data_element_uid}  total={len(ds.dataSetElements or [])}",
    )


@data_sets_app.command("remove-element")
def data_sets_remove_element_command(
    data_set_uid: Annotated[str, typer.Argument(help="DataSet UID.")],
    data_element_uid: Annotated[str, typer.Argument(help="DataElement UID to detach.")],
) -> None:
    """Detach a DataElement from the DataSet."""
    ds = asyncio.run(
        service.remove_data_set_element(
            profile_from_env(),
            data_set_uid,
            data_element_uid,
        ),
    )
    _console.print(
        f"[yellow]- element[/yellow] dataSet [cyan]{ds.id}[/cyan]  "
        f"de={data_element_uid}  total={len(ds.dataSetElements or [])}",
    )


@data_sets_app.command("delete")
def data_sets_delete_command(
    uid: Annotated[str, typer.Argument(help="DataSet UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a DataSet — DHIS2 rejects deletes on DataSets with saved values."""
    if not yes:
        typer.confirm(f"really delete dataSet {uid}?", abort=True)
    asyncio.run(service.delete_data_set(profile_from_env(), uid))
    _emit_mutation(f"deleted dataSet {uid}")


# ---------------------------------------------------------------------------
# Section workflows — `dhis2 metadata sections ...`
# ---------------------------------------------------------------------------


@sections_app.command("get")
def sections_get_command(
    uid: Annotated[str, typer.Argument(help="Section UID.")],
) -> None:
    """Show one Section with its ordered DE list inline."""
    section = asyncio.run(service.show_section(profile_from_env(), uid))
    if is_json_output():
        typer.echo(section.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{section.name} ({section.id})")
    typer.echo(f"  dataSet:    {section.dataSet.id if section.dataSet else '-'}")
    typer.echo(f"  sortOrder:  {section.sortOrder if section.sortOrder is not None else '-'}")
    typer.echo(f"  elements:   {len(section.dataElements or [])}")
    typer.echo(f"  indicators: {len(section.indicators or [])}")
    if section.description:
        typer.echo(f"  description: {section.description}")


@sections_app.command("create")
def sections_create_command(
    name: Annotated[str, typer.Option("--name", help="Section name (<=230 chars).")],
    data_set: Annotated[str, typer.Option("--data-set", "-ds", help="Parent DataSet UID.")],
    sort_order: Annotated[
        int | None,
        typer.Option("--sort-order", help="Ordering within the DataSet (ascending)."),
    ] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    data_element: Annotated[
        list[str] | None,
        typer.Option("--data-element", "-de", help="DataElement UID (repeatable, order preserved)."),
    ] = None,
    indicator: Annotated[
        list[str] | None,
        typer.Option("--indicator", "-i", help="Indicator UID to show in the side pane (repeatable)."),
    ] = None,
    show_column_totals: Annotated[
        bool | None,
        typer.Option("--show-column-totals/--no-show-column-totals", help="Render column totals."),
    ] = None,
    show_row_totals: Annotated[
        bool | None,
        typer.Option("--show-row-totals/--no-show-row-totals", help="Render row totals."),
    ] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a Section attached to a DataSet. Repeat `--data-element` to seed the ordered DE list."""
    section = asyncio.run(
        service.create_section(
            profile_from_env(),
            name=name,
            data_set_uid=data_set,
            sort_order=sort_order,
            description=description,
            code=code,
            data_element_uids=data_element,
            indicator_uids=indicator,
            show_column_totals=show_column_totals,
            show_row_totals=show_row_totals,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(section.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(
        f"[green]created[/green] section [cyan]{section.id}[/cyan]  name={section.name!r}  dataSet={data_set}",
    )


@sections_app.command("rename")
def sections_rename_command(
    uid: Annotated[str, typer.Argument(help="Section UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
    sort_order: Annotated[int | None, typer.Option("--sort-order", help="New sort order.")] = None,
) -> None:
    """Partial-update the label / sort-order fields on a Section."""
    section = asyncio.run(
        service.rename_section(
            profile_from_env(),
            uid,
            name=name,
            description=description,
            sort_order=sort_order,
        ),
    )
    if is_json_output():
        typer.echo(section.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] section [cyan]{section.id}[/cyan]  name={section.name!r}")


@sections_app.command("add-element")
def sections_add_element_command(
    section_uid: Annotated[str, typer.Argument(help="Section UID.")],
    data_element_uid: Annotated[str, typer.Argument(help="DataElement UID.")],
    position: Annotated[
        int | None,
        typer.Option("--position", help="0-indexed insertion position. Omit to append."),
    ] = None,
) -> None:
    """Append (or insert at `--position`) a DataElement to the Section."""
    section = asyncio.run(
        service.add_section_element(
            profile_from_env(),
            section_uid,
            data_element_uid,
            position=position,
        ),
    )
    _emit_mutation(
        f"[green]+ element[/green] section [cyan]{section.id}[/cyan]  "
        f"de={data_element_uid}  total={len(section.dataElements or [])}",
    )


@sections_app.command("remove-element")
def sections_remove_element_command(
    section_uid: Annotated[str, typer.Argument(help="Section UID.")],
    data_element_uid: Annotated[str, typer.Argument(help="DataElement UID.")],
) -> None:
    """Remove a DataElement from the Section (stays on the parent DataSet)."""
    section = asyncio.run(
        service.remove_section_element(
            profile_from_env(),
            section_uid,
            data_element_uid,
        ),
    )
    _console.print(
        f"[yellow]- element[/yellow] section [cyan]{section.id}[/cyan]  "
        f"de={data_element_uid}  total={len(section.dataElements or [])}",
    )


@sections_app.command("reorder")
def sections_reorder_command(
    section_uid: Annotated[str, typer.Argument(help="Section UID.")],
    data_element_uids: Annotated[
        list[str],
        typer.Argument(help="DataElement UIDs in the desired order."),
    ],
) -> None:
    """Replace the Section's `dataElements` with exactly the given UIDs in order."""
    section = asyncio.run(
        service.reorder_section_elements(
            profile_from_env(),
            section_uid,
            data_element_uids=data_element_uids,
        ),
    )
    _console.print(
        f"[green]reordered[/green] section [cyan]{section.id}[/cyan]  elements={len(section.dataElements or [])}",
    )


@sections_app.command("delete")
def sections_delete_command(
    uid: Annotated[str, typer.Argument(help="Section UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a Section — DEs stay on the parent DataSet."""
    if not yes:
        typer.confirm(f"really delete section {uid}?", abort=True)
    asyncio.run(service.delete_section(profile_from_env(), uid))
    _emit_mutation(f"deleted section {uid}")


# ---------------------------------------------------------------------------
# ValidationRule workflows — `dhis2 metadata validation-rules ...`
# ---------------------------------------------------------------------------


@validation_rules_app.command("get")
def validation_rules_get_command(
    uid: Annotated[str, typer.Argument(help="ValidationRule UID.")],
) -> None:
    """Show one ValidationRule with both expression sides inline."""
    rule = asyncio.run(service.show_validation_rule(profile_from_env(), uid))
    if is_json_output():
        typer.echo(rule.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{rule.name} ({rule.id}) code={rule.code or '-'}")
    typer.echo(f"  periodType:  {rule.periodType.value if rule.periodType else '-'}")
    typer.echo(f"  operator:    {rule.operator.value if rule.operator else '-'}")
    typer.echo(f"  importance:  {rule.importance.value if rule.importance else '-'}")
    left = rule.leftSide if isinstance(rule.leftSide, dict) else {}
    right = rule.rightSide if isinstance(rule.rightSide, dict) else {}
    typer.echo(f"  leftSide:    {left.get('expression') or '-'}")
    typer.echo(f"  rightSide:   {right.get('expression') or '-'}")
    if rule.description:
        typer.echo(f"  description: {rule.description}")


@validation_rules_app.command("create")
def validation_rules_create_command(
    name: Annotated[str, typer.Option("--name", help="Rule name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    left_expression: Annotated[str, typer.Option("--left", help="Left-side expression (e.g. #{deUid}).")],
    operator: Annotated[str, typer.Option("--operator", help="Comparison operator.")],
    right_expression: Annotated[str, typer.Option("--right", help="Right-side expression.")],
    period_type: Annotated[str, typer.Option("--period-type", help="Period type.")] = "Monthly",
    importance: Annotated[str, typer.Option("--importance", help="LOW / MEDIUM / HIGH.")] = "MEDIUM",
    missing_value_strategy: Annotated[
        str,
        typer.Option("--missing-value-strategy", help="How to treat absent operands."),
    ] = "SKIP_IF_ALL_VALUES_MISSING",
    description: Annotated[str | None, typer.Option("--description", help="Free-text description.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    ou_level: Annotated[
        list[int] | None,
        typer.Option("--ou-level", help="OU depth (repeatable). E.g. `--ou-level 4` for facilities."),
    ] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a ValidationRule."""
    rule = asyncio.run(
        service.create_validation_rule(
            profile_from_env(),
            name=name,
            short_name=short_name,
            left_expression=left_expression,
            operator=operator,
            right_expression=right_expression,
            period_type=period_type,
            importance=importance,
            missing_value_strategy=missing_value_strategy,
            description=description,
            code=code,
            organisation_unit_levels=ou_level,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(rule.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] validationRule [cyan]{rule.id}[/cyan]  name={rule.name!r}")


@validation_rules_app.command("rename")
def validation_rules_rename_command(
    uid: Annotated[str, typer.Argument(help="ValidationRule UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update the label fields on a ValidationRule."""
    rule = asyncio.run(
        service.rename_validation_rule(
            profile_from_env(),
            uid,
            name=name,
            short_name=short_name,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(rule.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] validationRule [cyan]{rule.id}[/cyan]  name={rule.name!r}")


@validation_rules_app.command("delete")
def validation_rules_delete_command(
    uid: Annotated[str, typer.Argument(help="ValidationRule UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a ValidationRule — any outstanding results are purged."""
    if not yes:
        typer.confirm(f"really delete validationRule {uid}?", abort=True)
    asyncio.run(service.delete_validation_rule(profile_from_env(), uid))
    _emit_mutation(f"deleted validationRule {uid}")


# ---------------------------------------------------------------------------
# ValidationRuleGroup workflows — `dhis2 metadata validation-rule-groups ...`
# ---------------------------------------------------------------------------


@validation_rule_groups_app.command("get")
def validation_rule_groups_get_command(
    uid: Annotated[str, typer.Argument(help="ValidationRuleGroup UID.")],
) -> None:
    """Show one group with its rule refs."""
    group = asyncio.run(service.show_validation_rule_group(profile_from_env(), uid))
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{group.name} ({group.id})")
    typer.echo(f"  code:       {group.code or '-'}")
    typer.echo(f"  members:    {len(group.validationRules or [])}")
    if group.description:
        typer.echo(f"  description: {group.description}")


@validation_rule_groups_app.command("members")
def validation_rule_groups_members_command(
    uid: Annotated[str, typer.Argument(help="ValidationRuleGroup UID.")],
    page: Annotated[int, typer.Option("--page", help="1-based page.")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="Rows per page.")] = 50,
) -> None:
    """Page through ValidationRules inside a group."""
    rows = asyncio.run(
        service.list_validation_rule_group_members(
            profile_from_env(),
            uid,
            page=page,
            page_size=page_size,
        ),
    )
    if is_json_output():
        typer.echo(json.dumps([r.model_dump(by_alias=True, exclude_none=True, mode="json") for r in rows], indent=2))
        return
    if not rows:
        typer.echo(f"no rules in group {uid} on page {page}")
        return
    table = Table(title=f"group {uid} — page {page}, {len(rows)} rule(s)")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("operator", style="dim")
    for rule in rows:
        table.add_row(
            str(rule.id or "-"),
            str(rule.name or "-"),
            str(rule.operator.value if rule.operator else "-"),
        )
    _console.print(table)


@validation_rule_groups_app.command("create")
def validation_rule_groups_create_command(
    name: Annotated[str, typer.Option("--name", help="Group name.")],
    short_name: Annotated[str | None, typer.Option("--short-name", help="Short name.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create an empty ValidationRuleGroup."""
    group = asyncio.run(
        service.create_validation_rule_group(
            profile_from_env(),
            name=name,
            short_name=short_name,
            code=code,
            description=description,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] validationRuleGroup [cyan]{group.id}[/cyan]  name={group.name!r}")


@validation_rule_groups_app.command("add-members")
def validation_rule_groups_add_members_command(
    uid: Annotated[str, typer.Argument(help="ValidationRuleGroup UID.")],
    rule: Annotated[
        list[str],
        typer.Option("--rule", "-r", help="ValidationRule UID (repeatable)."),
    ],
) -> None:
    """Attach ValidationRules to a group."""
    group = asyncio.run(
        service.add_validation_rule_group_members(
            profile_from_env(),
            uid,
            validation_rule_uids=rule,
        ),
    )
    _console.print(
        f"[green]+ members[/green] validationRuleGroup [cyan]{group.id}[/cyan]  "
        f"total={len(group.validationRules or [])}",
    )


@validation_rule_groups_app.command("remove-members")
def validation_rule_groups_remove_members_command(
    uid: Annotated[str, typer.Argument(help="ValidationRuleGroup UID.")],
    rule: Annotated[
        list[str],
        typer.Option("--rule", "-r", help="ValidationRule UID (repeatable)."),
    ],
) -> None:
    """Detach ValidationRules from a group."""
    group = asyncio.run(
        service.remove_validation_rule_group_members(
            profile_from_env(),
            uid,
            validation_rule_uids=rule,
        ),
    )
    _console.print(
        f"[yellow]- members[/yellow] validationRuleGroup [cyan]{group.id}[/cyan]  "
        f"total={len(group.validationRules or [])}",
    )


@validation_rule_groups_app.command("delete")
def validation_rule_groups_delete_command(
    uid: Annotated[str, typer.Argument(help="ValidationRuleGroup UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a ValidationRuleGroup — member rules stay."""
    if not yes:
        typer.confirm(f"really delete validationRuleGroup {uid}?", abort=True)
    asyncio.run(service.delete_validation_rule_group(profile_from_env(), uid))
    _emit_mutation(f"deleted validationRuleGroup {uid}")


# ---------------------------------------------------------------------------
# Predictor workflows — `dhis2 metadata predictors ...`
# ---------------------------------------------------------------------------


@predictors_app.command("get")
def predictors_get_command(
    uid: Annotated[str, typer.Argument(help="Predictor UID.")],
) -> None:
    """Show one Predictor with generator + output inline."""
    predictor = asyncio.run(service.show_predictor(profile_from_env(), uid))
    if is_json_output():
        typer.echo(predictor.model_dump_json(indent=2, exclude_none=True))
        return
    gen = predictor.generator if isinstance(predictor.generator, dict) else {}
    typer.echo(f"{predictor.name} ({predictor.id}) code={predictor.code or '-'}")
    typer.echo(f"  periodType:  {predictor.periodType.value if predictor.periodType else '-'}")
    typer.echo(f"  expression:  {gen.get('expression') or '-'}")
    typer.echo(f"  output DE:   {predictor.output.id if predictor.output else '-'}")
    typer.echo(f"  samples:     sequential={predictor.sequentialSampleCount} annual={predictor.annualSampleCount}")
    if predictor.description:
        typer.echo(f"  description: {predictor.description}")


@predictors_app.command("create")
def predictors_create_command(
    name: Annotated[str, typer.Option("--name", help="Predictor name.")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name.")],
    expression: Annotated[str, typer.Option("--expression", help="Generator expression (e.g. #{deUid}).")],
    output: Annotated[str, typer.Option("--output", "-o", help="Output DataElement UID.")],
    period_type: Annotated[str, typer.Option("--period-type", help="Period type.")] = "Monthly",
    sequential: Annotated[
        int,
        typer.Option("--sequential", help="Sequential sample count (e.g. 3 for 3-month rolling)."),
    ] = 3,
    annual: Annotated[int, typer.Option("--annual", help="Annual sample count.")] = 0,
    ou_level: Annotated[
        list[str] | None,
        typer.Option("--ou-level", help="OrganisationUnitLevel UID (repeatable)."),
    ] = None,
    output_combo: Annotated[
        str | None,
        typer.Option("--output-combo", help="Output CategoryOptionCombo UID."),
    ] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a Predictor."""
    predictor = asyncio.run(
        service.create_predictor(
            profile_from_env(),
            name=name,
            short_name=short_name,
            expression=expression,
            output_data_element_uid=output,
            period_type=period_type,
            sequential_sample_count=sequential,
            annual_sample_count=annual,
            organisation_unit_level_uids=ou_level,
            output_combo_uid=output_combo,
            description=description,
            code=code,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(predictor.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] predictor [cyan]{predictor.id}[/cyan]  name={predictor.name!r}")


@predictors_app.command("rename")
def predictors_rename_command(
    uid: Annotated[str, typer.Argument(help="Predictor UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update the label fields on a Predictor."""
    predictor = asyncio.run(
        service.rename_predictor(
            profile_from_env(),
            uid,
            name=name,
            short_name=short_name,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(predictor.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] predictor [cyan]{predictor.id}[/cyan]  name={predictor.name!r}")


@predictors_app.command("delete")
def predictors_delete_command(
    uid: Annotated[str, typer.Argument(help="Predictor UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a Predictor. DHIS2 keeps any data values it has already written."""
    if not yes:
        typer.confirm(f"really delete predictor {uid}?", abort=True)
    asyncio.run(service.delete_predictor(profile_from_env(), uid))
    _emit_mutation(f"deleted predictor {uid}")


# ---------------------------------------------------------------------------
# PredictorGroup workflows — `dhis2 metadata predictor-groups ...`
# ---------------------------------------------------------------------------


@predictor_groups_app.command("get")
def predictor_groups_get_command(
    uid: Annotated[str, typer.Argument(help="PredictorGroup UID.")],
) -> None:
    """Show one group with its predictor refs."""
    group = asyncio.run(service.show_predictor_group(profile_from_env(), uid))
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{group.name} ({group.id})")
    typer.echo(f"  code:       {group.code or '-'}")
    typer.echo(f"  members:    {len(group.predictors or [])}")
    if group.description:
        typer.echo(f"  description: {group.description}")


@predictor_groups_app.command("members")
def predictor_groups_members_command(
    uid: Annotated[str, typer.Argument(help="PredictorGroup UID.")],
    page: Annotated[int, typer.Option("--page", help="1-based page.")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="Rows per page.")] = 50,
) -> None:
    """Page through Predictors in a group."""
    rows = asyncio.run(
        service.list_predictor_group_members(
            profile_from_env(),
            uid,
            page=page,
            page_size=page_size,
        ),
    )
    if is_json_output():
        typer.echo(json.dumps([p.model_dump(by_alias=True, exclude_none=True, mode="json") for p in rows], indent=2))
        return
    if not rows:
        typer.echo(f"no predictors in group {uid} on page {page}")
        return
    table = Table(title=f"group {uid} — page {page}, {len(rows)} predictor(s)")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name", overflow="fold")
    table.add_column("output DE", style="dim")
    for predictor in rows:
        table.add_row(
            str(predictor.id or "-"),
            str(predictor.name or "-"),
            str(predictor.output.id if predictor.output else "-"),
        )
    _console.print(table)


@predictor_groups_app.command("create")
def predictor_groups_create_command(
    name: Annotated[str, typer.Option("--name", help="Group name.")],
    short_name: Annotated[str | None, typer.Option("--short-name", help="Short name.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create an empty PredictorGroup."""
    group = asyncio.run(
        service.create_predictor_group(
            profile_from_env(),
            name=name,
            short_name=short_name,
            code=code,
            description=description,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(group.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] predictorGroup [cyan]{group.id}[/cyan]  name={group.name!r}")


@predictor_groups_app.command("add-members")
def predictor_groups_add_members_command(
    uid: Annotated[str, typer.Argument(help="PredictorGroup UID.")],
    predictor: Annotated[
        list[str],
        typer.Option("--predictor", "-p", help="Predictor UID (repeatable)."),
    ],
) -> None:
    """Attach Predictors to a group."""
    group = asyncio.run(
        service.add_predictor_group_members(
            profile_from_env(),
            uid,
            predictor_uids=predictor,
        ),
    )
    _console.print(
        f"[green]+ members[/green] predictorGroup [cyan]{group.id}[/cyan]  total={len(group.predictors or [])}",
    )


@predictor_groups_app.command("remove-members")
def predictor_groups_remove_members_command(
    uid: Annotated[str, typer.Argument(help="PredictorGroup UID.")],
    predictor: Annotated[
        list[str],
        typer.Option("--predictor", "-p", help="Predictor UID (repeatable)."),
    ],
) -> None:
    """Detach Predictors from a group."""
    group = asyncio.run(
        service.remove_predictor_group_members(
            profile_from_env(),
            uid,
            predictor_uids=predictor,
        ),
    )
    _console.print(
        f"[yellow]- members[/yellow] predictorGroup [cyan]{group.id}[/cyan]  total={len(group.predictors or [])}",
    )


@predictor_groups_app.command("delete")
def predictor_groups_delete_command(
    uid: Annotated[str, typer.Argument(help="PredictorGroup UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a PredictorGroup — member predictors stay."""
    if not yes:
        typer.confirm(f"really delete predictorGroup {uid}?", abort=True)
    asyncio.run(service.delete_predictor_group(profile_from_env(), uid))
    _emit_mutation(f"deleted predictorGroup {uid}")


# ---------------------------------------------------------------------------
# TrackedEntityAttribute workflows — `dhis2 metadata tracked-entity-attributes ...`
# ---------------------------------------------------------------------------


@tracked_entity_attributes_app.command("get")
def tracked_entity_attributes_get_command(
    uid: Annotated[str, typer.Argument(help="TrackedEntityAttribute UID.")],
) -> None:
    """Show one TrackedEntityAttribute with its toggles inline."""
    tea = asyncio.run(service.show_tracked_entity_attribute(profile_from_env(), uid))
    if is_json_output():
        typer.echo(tea.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{tea.name} ({tea.id}) code={tea.code or '-'}")
    typer.echo(f"  valueType:   {tea.valueType.value if tea.valueType else '-'}")
    typer.echo(f"  optionSet:   {tea.optionSet.id if tea.optionSet else '-'}")
    typer.echo(
        f"  unique={tea.unique}  generated={tea.generated}  confidential={tea.confidential}  inherit={tea.inherit}",
    )
    typer.echo(f"  displayInListNoProgram: {tea.displayInListNoProgram}")
    if tea.pattern:
        typer.echo(f"  pattern:     {tea.pattern}")
    if tea.description:
        typer.echo(f"  description: {tea.description}")


@tracked_entity_attributes_app.command("create")
def tracked_entity_attributes_create_command(
    name: Annotated[str, typer.Option("--name", help="Attribute name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    value_type: Annotated[str, typer.Option("--value-type", help="TEXT / NUMBER / DATE / …")] = "TEXT",
    aggregation_type: Annotated[str, typer.Option("--aggregation-type", help="DHIS2 aggregation type.")] = "NONE",
    option_set: Annotated[str | None, typer.Option("--option-set", help="Constraining OptionSet UID.")] = None,
    legend_set: Annotated[
        list[str] | None,
        typer.Option("--legend-set", help="LegendSet UID (repeatable)."),
    ] = None,
    unique: Annotated[bool, typer.Option("--unique/--no-unique", help="Unique across the instance.")] = False,
    generated: Annotated[
        bool,
        typer.Option("--generated/--no-generated", help="Auto-generate via --pattern on TEI register."),
    ] = False,
    confidential: Annotated[bool, typer.Option("--confidential/--no-confidential", help="Sensitive.")] = False,
    inherit: Annotated[bool, typer.Option("--inherit/--no-inherit", help="Inherit on parent/child TEI link.")] = False,
    display_in_list_no_program: Annotated[
        bool,
        typer.Option(
            "--display-in-list-no-program/--no-display-in-list-no-program",
            help="Show in the list when no program is selected.",
        ),
    ] = False,
    orgunit_scope: Annotated[
        bool,
        typer.Option("--orgunit-scope/--no-orgunit-scope", help="Scope values to the capturing OU."),
    ] = False,
    pattern: Annotated[str | None, typer.Option("--pattern", help="Generator pattern (with --generated).")] = None,
    field_mask: Annotated[str | None, typer.Option("--field-mask", help="Input mask for the data-entry field.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="Form-name override.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a TrackedEntityAttribute."""
    tea = asyncio.run(
        service.create_tracked_entity_attribute(
            profile_from_env(),
            name=name,
            short_name=short_name,
            value_type=value_type,
            aggregation_type=aggregation_type,
            option_set_uid=option_set,
            legend_set_uids=legend_set,
            unique=unique,
            generated=generated,
            confidential=confidential,
            inherit=inherit,
            display_in_list_no_program=display_in_list_no_program,
            orgunit_scope=orgunit_scope,
            pattern=pattern,
            field_mask=field_mask,
            code=code,
            form_name=form_name,
            description=description,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(tea.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] trackedEntityAttribute [cyan]{tea.id}[/cyan]  name={tea.name!r}")


@tracked_entity_attributes_app.command("rename")
def tracked_entity_attributes_rename_command(
    uid: Annotated[str, typer.Argument(help="TrackedEntityAttribute UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="New form name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update the label fields on a TrackedEntityAttribute."""
    tea = asyncio.run(
        service.rename_tracked_entity_attribute(
            profile_from_env(),
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(tea.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] trackedEntityAttribute [cyan]{tea.id}[/cyan]  name={tea.name!r}")


@tracked_entity_attributes_app.command("delete")
def tracked_entity_attributes_delete_command(
    uid: Annotated[str, typer.Argument(help="TrackedEntityAttribute UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a TrackedEntityAttribute — DHIS2 rejects deletes on TEAs wired into a TET or program."""
    if not yes:
        typer.confirm(f"really delete trackedEntityAttribute {uid}?", abort=True)
    asyncio.run(service.delete_tracked_entity_attribute(profile_from_env(), uid))
    _emit_mutation(f"deleted trackedEntityAttribute {uid}")


# ---------------------------------------------------------------------------
# TrackedEntityType workflows — `dhis2 metadata tracked-entity-types ...`
# ---------------------------------------------------------------------------


@tracked_entity_types_app.command("get")
def tracked_entity_types_get_command(
    uid: Annotated[str, typer.Argument(help="TrackedEntityType UID.")],
) -> None:
    """Show one TrackedEntityType with its attribute link-table counts."""
    tet = asyncio.run(service.show_tracked_entity_type(profile_from_env(), uid))
    if is_json_output():
        typer.echo(tet.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{tet.name} ({tet.id}) code={tet.code or '-'}")
    typer.echo(f"  shortName:   {tet.shortName or '-'}")
    typer.echo(f"  featureType: {tet.featureType.value if tet.featureType else '-'}")
    typer.echo(f"  allowAuditLog: {tet.allowAuditLog}")
    typer.echo(f"  attributes:   {len(tet.trackedEntityTypeAttributes or [])}")
    if tet.description:
        typer.echo(f"  description: {tet.description}")


@tracked_entity_types_app.command("create")
def tracked_entity_types_create_command(
    name: Annotated[str, typer.Option("--name", help="TET name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="Form-name override.")] = None,
    allow_audit_log: Annotated[
        bool | None,
        typer.Option("--allow-audit-log/--no-allow-audit-log", help="Enable the per-TEI audit trail."),
    ] = None,
    feature_type: Annotated[
        str | None,
        typer.Option("--feature-type", help="NONE / POINT / POLYGON — geometry captured per TEI."),
    ] = None,
    min_attrs: Annotated[
        int | None,
        typer.Option("--min-attrs", help="Min attributes required to search TEIs."),
    ] = None,
    max_tei: Annotated[
        int | None,
        typer.Option("--max-tei", help="Max TEI count to return per search."),
    ] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a TrackedEntityType."""
    tet = asyncio.run(
        service.create_tracked_entity_type(
            profile_from_env(),
            name=name,
            short_name=short_name,
            description=description,
            code=code,
            form_name=form_name,
            allow_audit_log=allow_audit_log,
            feature_type=feature_type,
            min_attributes_required_to_search=min_attrs,
            max_tei_count_to_return=max_tei,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(tet.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] trackedEntityType [cyan]{tet.id}[/cyan]  name={tet.name!r}")


@tracked_entity_types_app.command("rename")
def tracked_entity_types_rename_command(
    uid: Annotated[str, typer.Argument(help="TrackedEntityType UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="New form name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update the label fields on a TrackedEntityType."""
    tet = asyncio.run(
        service.rename_tracked_entity_type(
            profile_from_env(),
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(tet.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] trackedEntityType [cyan]{tet.id}[/cyan]  name={tet.name!r}")


@tracked_entity_types_app.command("add-attribute")
def tracked_entity_types_add_attribute_command(
    tet_uid: Annotated[str, typer.Argument(help="TrackedEntityType UID.")],
    attribute_uid: Annotated[str, typer.Argument(help="TrackedEntityAttribute UID to wire in.")],
    mandatory: Annotated[bool, typer.Option("--mandatory/--no-mandatory", help="Require on enrollment.")] = False,
    searchable: Annotated[bool, typer.Option("--searchable/--no-searchable", help="Include in TEI search.")] = False,
    display_in_list: Annotated[
        bool,
        typer.Option("--display-in-list/--no-display-in-list", help="Show in the enrolled-TEI list."),
    ] = True,
) -> None:
    """Attach a TrackedEntityAttribute to a TrackedEntityType."""
    tet = asyncio.run(
        service.add_tracked_entity_type_attribute(
            profile_from_env(),
            tet_uid,
            attribute_uid,
            mandatory=mandatory,
            searchable=searchable,
            display_in_list=display_in_list,
        ),
    )
    _console.print(
        f"[green]+ attribute[/green] trackedEntityType [cyan]{tet.id}[/cyan]  "
        f"tea={attribute_uid}  total={len(tet.trackedEntityTypeAttributes or [])}",
    )


@tracked_entity_types_app.command("remove-attribute")
def tracked_entity_types_remove_attribute_command(
    tet_uid: Annotated[str, typer.Argument(help="TrackedEntityType UID.")],
    attribute_uid: Annotated[str, typer.Argument(help="TrackedEntityAttribute UID to detach.")],
) -> None:
    """Detach a TrackedEntityAttribute from a TrackedEntityType."""
    tet = asyncio.run(
        service.remove_tracked_entity_type_attribute(
            profile_from_env(),
            tet_uid,
            attribute_uid,
        ),
    )
    _console.print(
        f"[yellow]- attribute[/yellow] trackedEntityType [cyan]{tet.id}[/cyan]  "
        f"tea={attribute_uid}  total={len(tet.trackedEntityTypeAttributes or [])}",
    )


@tracked_entity_types_app.command("delete")
def tracked_entity_types_delete_command(
    uid: Annotated[str, typer.Argument(help="TrackedEntityType UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a TrackedEntityType — DHIS2 rejects deletes on TETs in use by enrolled TEIs."""
    if not yes:
        typer.confirm(f"really delete trackedEntityType {uid}?", abort=True)
    asyncio.run(service.delete_tracked_entity_type(profile_from_env(), uid))
    _emit_mutation(f"deleted trackedEntityType {uid}")


# ---------------------------------------------------------------------------
# Program workflows — `dhis2 metadata programs ...`
# ---------------------------------------------------------------------------


@programs_app.command("get")
def programs_get_command(
    uid: Annotated[str, typer.Argument(help="Program UID.")],
) -> None:
    """Show one Program with counts inline."""
    program = asyncio.run(service.show_program(profile_from_env(), uid))
    if is_json_output():
        typer.echo(program.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{program.name} ({program.id}) code={program.code or '-'}")
    typer.echo(f"  type:         {program.programType.value if program.programType else '-'}")
    typer.echo(f"  TET:          {program.trackedEntityType.id if program.trackedEntityType else '-'}")
    typer.echo(f"  TEAs on enrollment form: {len(program.programTrackedEntityAttributes or [])}")
    typer.echo(f"  stages:       {len(program.programStages or [])}")
    typer.echo(f"  organisation units: {len(program.organisationUnits or [])}")
    if program.description:
        typer.echo(f"  description:  {program.description}")


@programs_app.command("create")
def programs_create_command(
    name: Annotated[str, typer.Option("--name", help="Program name (<=230 chars).")],
    short_name: Annotated[str, typer.Option("--short-name", help="Short name (<=50 chars).")],
    program_type: Annotated[
        str,
        typer.Option("--program-type", help="WITH_REGISTRATION (tracker) or WITHOUT_REGISTRATION (event)."),
    ] = "WITH_REGISTRATION",
    tracked_entity_type: Annotated[
        str | None,
        typer.Option("--tracked-entity-type", "-tet", help="TET UID. Required for WITH_REGISTRATION."),
    ] = None,
    category_combo: Annotated[
        str | None,
        typer.Option("--category-combo", "-cc", help="CategoryCombo UID (defaults to the instance default)."),
    ] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="Form-name override.")] = None,
    display_incident_date: Annotated[
        bool | None,
        typer.Option("--display-incident-date/--no-display-incident-date", help="Capture an incident date."),
    ] = None,
    enrollment_date_label: Annotated[
        str | None,
        typer.Option("--enrollment-date-label", help="Custom enrollment-date label."),
    ] = None,
    incident_date_label: Annotated[
        str | None,
        typer.Option("--incident-date-label", help="Custom incident-date label."),
    ] = None,
    feature_type: Annotated[
        str | None,
        typer.Option("--feature-type", help="Geometry captured per enrollment (NONE / POINT / POLYGON)."),
    ] = None,
    only_enroll_once: Annotated[
        bool | None,
        typer.Option("--only-enroll-once/--no-only-enroll-once", help="Block re-enrollment of the same TEI."),
    ] = None,
    expiry_days: Annotated[
        int | None,
        typer.Option("--expiry-days", help="Days after which enrollments expire for edit."),
    ] = None,
    min_attrs: Annotated[
        int | None,
        typer.Option("--min-attrs", help="Min attributes required for TEI search."),
    ] = None,
    max_tei: Annotated[
        int | None,
        typer.Option("--max-tei", help="Max TEI count per search."),
    ] = None,
    use_first_stage_during_registration: Annotated[
        bool | None,
        typer.Option(
            "--use-first-stage-during-registration/--no-use-first-stage-during-registration",
            help="Run the first ProgramStage inside the enrollment flow.",
        ),
    ] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a Program. `--program-type WITH_REGISTRATION` requires `--tracked-entity-type`."""
    program = asyncio.run(
        service.create_program(
            profile_from_env(),
            name=name,
            short_name=short_name,
            program_type=program_type,
            tracked_entity_type_uid=tracked_entity_type,
            category_combo_uid=category_combo,
            description=description,
            code=code,
            form_name=form_name,
            display_incident_date=display_incident_date,
            enrollment_date_label=enrollment_date_label,
            incident_date_label=incident_date_label,
            feature_type=feature_type,
            only_enroll_once=only_enroll_once,
            expiry_days=expiry_days,
            min_attributes_required_to_search=min_attrs,
            max_tei_count_to_return=max_tei,
            use_first_stage_during_registration=use_first_stage_during_registration,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(program.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] program [cyan]{program.id}[/cyan]  name={program.name!r}")


@programs_app.command("rename")
def programs_rename_command(
    uid: Annotated[str, typer.Argument(help="Program UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="New form name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update the label fields on a Program."""
    program = asyncio.run(
        service.rename_program(
            profile_from_env(),
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(program.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] program [cyan]{program.id}[/cyan]  name={program.name!r}")


@programs_app.command("add-attribute")
def programs_add_attribute_command(
    program_uid: Annotated[str, typer.Argument(help="Program UID.")],
    attribute_uid: Annotated[str, typer.Argument(help="TrackedEntityAttribute UID.")],
    mandatory: Annotated[bool, typer.Option("--mandatory/--no-mandatory", help="Require on enrollment.")] = False,
    searchable: Annotated[bool, typer.Option("--searchable/--no-searchable", help="Include in search.")] = False,
    display_in_list: Annotated[
        bool,
        typer.Option("--display-in-list/--no-display-in-list", help="Show in enrolled-TEI list."),
    ] = True,
    sort_order: Annotated[int | None, typer.Option("--sort-order", help="Position on enrollment form.")] = None,
    allow_future_date: Annotated[
        bool,
        typer.Option("--allow-future-date/--no-allow-future-date", help="Permit dates past today."),
    ] = False,
    render_options_as_radio: Annotated[
        bool,
        typer.Option(
            "--render-options-as-radio/--no-render-options-as-radio",
            help="Render option-set choices as radios instead of a dropdown.",
        ),
    ] = False,
) -> None:
    """Attach a TrackedEntityAttribute to the Program's enrollment form."""
    program = asyncio.run(
        service.add_program_attribute(
            profile_from_env(),
            program_uid,
            attribute_uid,
            mandatory=mandatory,
            searchable=searchable,
            display_in_list=display_in_list,
            sort_order=sort_order,
            allow_future_date=allow_future_date,
            render_options_as_radio=render_options_as_radio,
        ),
    )
    _console.print(
        f"[green]+ PTEA[/green] program [cyan]{program.id}[/cyan]  "
        f"tea={attribute_uid}  total={len(program.programTrackedEntityAttributes or [])}",
    )


@programs_app.command("remove-attribute")
def programs_remove_attribute_command(
    program_uid: Annotated[str, typer.Argument(help="Program UID.")],
    attribute_uid: Annotated[str, typer.Argument(help="TrackedEntityAttribute UID.")],
) -> None:
    """Detach a TrackedEntityAttribute from the Program's enrollment form."""
    program = asyncio.run(
        service.remove_program_attribute(profile_from_env(), program_uid, attribute_uid),
    )
    _console.print(
        f"[yellow]- PTEA[/yellow] program [cyan]{program.id}[/cyan]  "
        f"tea={attribute_uid}  total={len(program.programTrackedEntityAttributes or [])}",
    )


@programs_app.command("add-to-ou")
def programs_add_to_ou_command(
    program_uid: Annotated[str, typer.Argument(help="Program UID.")],
    organisation_unit_uid: Annotated[str, typer.Argument(help="OrganisationUnit UID.")],
) -> None:
    """Scope the Program to another OrganisationUnit."""
    program = asyncio.run(
        service.add_program_organisation_unit(profile_from_env(), program_uid, organisation_unit_uid),
    )
    _console.print(
        f"[green]+ OU[/green] program [cyan]{program.id}[/cyan]  "
        f"ou={organisation_unit_uid}  total={len(program.organisationUnits or [])}",
    )


@programs_app.command("remove-from-ou")
def programs_remove_from_ou_command(
    program_uid: Annotated[str, typer.Argument(help="Program UID.")],
    organisation_unit_uid: Annotated[str, typer.Argument(help="OrganisationUnit UID.")],
) -> None:
    """Drop an OrganisationUnit from the Program's scope."""
    program = asyncio.run(
        service.remove_program_organisation_unit(profile_from_env(), program_uid, organisation_unit_uid),
    )
    _console.print(
        f"[yellow]- OU[/yellow] program [cyan]{program.id}[/cyan]  "
        f"ou={organisation_unit_uid}  total={len(program.organisationUnits or [])}",
    )


@programs_app.command("delete")
def programs_delete_command(
    uid: Annotated[str, typer.Argument(help="Program UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a Program — DHIS2 rejects deletes on programs with enrollments or events."""
    if not yes:
        typer.confirm(f"really delete program {uid}?", abort=True)
    asyncio.run(service.delete_program(profile_from_env(), uid))
    _emit_mutation(f"deleted program {uid}")


# ---------------------------------------------------------------------------
# ProgramStage workflows — `dhis2 metadata program-stages ...`
# ---------------------------------------------------------------------------


@program_stages_app.command("get")
def program_stages_get_command(
    uid: Annotated[str, typer.Argument(help="ProgramStage UID.")],
) -> None:
    """Show one ProgramStage with its PSDE list summary inline."""
    stage = asyncio.run(service.show_program_stage(profile_from_env(), uid))
    if is_json_output():
        typer.echo(stage.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{stage.name} ({stage.id}) code={stage.code or '-'}")
    typer.echo(f"  program:      {stage.program.id if stage.program else '-'}")
    typer.echo(f"  sortOrder:    {stage.sortOrder if stage.sortOrder is not None else '-'}")
    typer.echo(f"  repeatable:   {stage.repeatable}")
    typer.echo(f"  autoGenerateEvent: {stage.autoGenerateEvent}")
    typer.echo(f"  data elements: {len(stage.programStageDataElements or [])}")
    if stage.description:
        typer.echo(f"  description:  {stage.description}")


@program_stages_app.command("create")
def program_stages_create_command(
    name: Annotated[str, typer.Option("--name", help="ProgramStage name (<=230 chars).")],
    program: Annotated[str, typer.Option("--program", "-p", help="Parent Program UID.")],
    short_name: Annotated[str | None, typer.Option("--short-name", help="Short name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Free text.")] = None,
    code: Annotated[str | None, typer.Option("--code", help="Business code.")] = None,
    sort_order: Annotated[int | None, typer.Option("--sort-order", help="Stage order inside the Program.")] = None,
    repeatable: Annotated[
        bool | None,
        typer.Option("--repeatable/--no-repeatable", help="Allow the stage to reoccur within one enrollment."),
    ] = None,
    auto_generate_event: Annotated[
        bool | None,
        typer.Option(
            "--auto-generate-event/--no-auto-generate-event",
            help="Auto-create an event when the enrollment starts.",
        ),
    ] = None,
    generated_by_enrollment_date: Annotated[
        bool | None,
        typer.Option(
            "--generated-by-enrollment-date/--no-generated-by-enrollment-date",
            help="Base due-date math on enrollment date (vs incident date).",
        ),
    ] = None,
    feature_type: Annotated[
        str | None,
        typer.Option("--feature-type", help="Geometry captured per event (NONE / POINT / POLYGON)."),
    ] = None,
    period_type: Annotated[str | None, typer.Option("--period-type", help="Period type for scheduled events.")] = None,
    validation_strategy: Annotated[
        str | None,
        typer.Option("--validation-strategy", help="ON_COMPLETE / ON_UPDATE_AND_INSERT."),
    ] = None,
    min_days_from_start: Annotated[
        int | None,
        typer.Option("--min-days", help="Minimum days from enrollment start before the stage opens."),
    ] = None,
    standard_interval: Annotated[
        int | None,
        typer.Option("--standard-interval", help="Default days between scheduled repeats."),
    ] = None,
    uid: Annotated[str | None, typer.Option("--uid", help="Explicit 11-char UID.")] = None,
) -> None:
    """Create a ProgramStage under `--program`."""
    stage = asyncio.run(
        service.create_program_stage(
            profile_from_env(),
            name=name,
            program_uid=program,
            short_name=short_name,
            description=description,
            code=code,
            sort_order=sort_order,
            repeatable=repeatable,
            auto_generate_event=auto_generate_event,
            generated_by_enrollment_date=generated_by_enrollment_date,
            feature_type=feature_type,
            period_type=period_type,
            validation_strategy=validation_strategy,
            min_days_from_start=min_days_from_start,
            standard_interval=standard_interval,
            uid=uid,
        ),
    )
    if is_json_output():
        typer.echo(stage.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]created[/green] programStage [cyan]{stage.id}[/cyan]  name={stage.name!r}")


@program_stages_app.command("rename")
def program_stages_rename_command(
    uid: Annotated[str, typer.Argument(help="ProgramStage UID.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    short_name: Annotated[str | None, typer.Option("--short-name", help="New short name.")] = None,
    form_name: Annotated[str | None, typer.Option("--form-name", help="New form name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description.")] = None,
) -> None:
    """Partial-update the label fields on a ProgramStage."""
    stage = asyncio.run(
        service.rename_program_stage(
            profile_from_env(),
            uid,
            name=name,
            short_name=short_name,
            form_name=form_name,
            description=description,
        ),
    )
    if is_json_output():
        typer.echo(stage.model_dump_json(indent=2, exclude_none=True))
        return
    _console.print(f"[green]renamed[/green] programStage [cyan]{stage.id}[/cyan]  name={stage.name!r}")


@program_stages_app.command("add-element")
def program_stages_add_element_command(
    stage_uid: Annotated[str, typer.Argument(help="ProgramStage UID.")],
    data_element_uid: Annotated[str, typer.Argument(help="DataElement UID to attach.")],
    compulsory: Annotated[bool, typer.Option("--compulsory/--no-compulsory", help="Required on save.")] = False,
    allow_future_date: Annotated[
        bool,
        typer.Option("--allow-future-date/--no-allow-future-date", help="Permit dates past today."),
    ] = False,
    display_in_reports: Annotated[
        bool,
        typer.Option("--display-in-reports/--no-display-in-reports", help="Show in event reports."),
    ] = True,
    allow_provided_elsewhere: Annotated[
        bool,
        typer.Option(
            "--allow-provided-elsewhere/--no-allow-provided-elsewhere",
            help="Mark the value as provided by a different OU.",
        ),
    ] = False,
    render_options_as_radio: Annotated[
        bool,
        typer.Option(
            "--render-options-as-radio/--no-render-options-as-radio",
            help="Render option-set picklists as radios.",
        ),
    ] = False,
    sort_order: Annotated[
        int | None,
        typer.Option("--sort-order", help="Position inside the stage data-entry form."),
    ] = None,
) -> None:
    """Attach a DataElement to the ProgramStage."""
    stage = asyncio.run(
        service.add_program_stage_element(
            profile_from_env(),
            stage_uid,
            data_element_uid,
            compulsory=compulsory,
            allow_future_date=allow_future_date,
            display_in_reports=display_in_reports,
            allow_provided_elsewhere=allow_provided_elsewhere,
            render_options_as_radio=render_options_as_radio,
            sort_order=sort_order,
        ),
    )
    _console.print(
        f"[green]+ PSDE[/green] programStage [cyan]{stage.id}[/cyan]  "
        f"de={data_element_uid}  total={len(stage.programStageDataElements or [])}",
    )


@program_stages_app.command("remove-element")
def program_stages_remove_element_command(
    stage_uid: Annotated[str, typer.Argument(help="ProgramStage UID.")],
    data_element_uid: Annotated[str, typer.Argument(help="DataElement UID.")],
) -> None:
    """Detach a DataElement from the ProgramStage."""
    stage = asyncio.run(
        service.remove_program_stage_element(profile_from_env(), stage_uid, data_element_uid),
    )
    _console.print(
        f"[yellow]- PSDE[/yellow] programStage [cyan]{stage.id}[/cyan]  "
        f"de={data_element_uid}  total={len(stage.programStageDataElements or [])}",
    )


@program_stages_app.command("reorder")
def program_stages_reorder_command(
    stage_uid: Annotated[str, typer.Argument(help="ProgramStage UID.")],
    data_element_uids: Annotated[list[str], typer.Argument(help="DataElement UIDs in the desired order.")],
) -> None:
    """Replace the ProgramStage's PSDE list with exactly the given DE UIDs in order."""
    stage = asyncio.run(
        service.reorder_program_stage_elements(
            profile_from_env(),
            stage_uid,
            data_element_uids=data_element_uids,
        ),
    )
    _console.print(
        f"[green]reordered[/green] programStage [cyan]{stage.id}[/cyan]  "
        f"total={len(stage.programStageDataElements or [])}",
    )


@program_stages_app.command("delete")
def program_stages_delete_command(
    uid: Annotated[str, typer.Argument(help="ProgramStage UID.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a ProgramStage — DHIS2 rejects deletes on stages with recorded events."""
    if not yes:
        typer.confirm(f"really delete programStage {uid}?", abort=True)
    asyncio.run(service.delete_program_stage(profile_from_env(), uid))
    _emit_mutation(f"deleted programStage {uid}")
