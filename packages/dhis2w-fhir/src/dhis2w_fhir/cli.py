"""Typer sub-app for the `fhir` plugin (mounted under `d2w fhir`)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from dhis2w_core.cli_output import DetailRow, is_json_output, render_detail

from dhis2w_fhir import GenerateReport, load_project

if TYPE_CHECKING:
    from dhis2w_fhir.service import GenerationProfile

app = typer.Typer(help="FHIR Implementation Guide generation from DHIS2 metadata.", no_args_is_help=True)
generate_app = typer.Typer(
    help="Generate FSH files from DHIS2 metadata into the nearest FHIR project.", no_args_is_help=True
)
app.add_typer(generate_app, name="generate")


@app.command("init")
def init_command(
    directory: Annotated[
        Path, typer.Argument(file_okay=False, help="Project directory (default: current directory).")
    ] = Path("."),
    ig_id: Annotated[str, typer.Option("--id", help="IG package id.")] = "dhis2.fhir.example",
    canonical: Annotated[
        str, typer.Option("--canonical", help="Canonical base URL for the IG (no trailing slash).")
    ] = "http://example.org/fhir",
    name: Annotated[str | None, typer.Option("--name", help="SUSHI name (default: derived from --id).")] = None,
    title: Annotated[str | None, typer.Option("--title", help="IG title (default: derived from --name).")] = None,
    publisher: Annotated[str, typer.Option("--publisher", help="Publisher name.")] = "Example Organisation",
    force: Annotated[bool, typer.Option("--force", help="Overwrite scaffold files that already exist.")] = False,
) -> None:
    """Scaffold a dockerized SUSHI IG project with a fhir.toml for `d2w fhir generate`."""
    from dhis2w_fhir import InitOptions, service
    from dhis2w_fhir.names import pascal

    resolved_name = name or pascal(ig_id)
    options = InitOptions(
        ig_id=ig_id,
        canonical=canonical,
        name=resolved_name,
        title=title or f"{resolved_name} Implementation Guide",
        publisher=publisher,
    )
    report = asyncio.run(service.init_project(directory, options, force=force))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    render_detail(
        "fhir init",
        [
            DetailRow("directory", str(report.directory)),
            DetailRow("created", str(len(report.created_files))),
            DetailRow("skipped", str(len(report.skipped_files))),
        ],
    )
    for relative_path in report.created_files:
        typer.echo(f"  created {relative_path}")
    for relative_path in report.skipped_files:
        typer.echo(f"  skipped {relative_path} (exists; use --force to overwrite)")
    typer.secho("next: set `profile` in fhir.toml, then run `d2w fhir generate all`", err=True)


def _render_generate_report(title: str, report: GenerateReport, generation: GenerationProfile) -> None:
    """Render one generation report as a Rich detail table plus note lines on stderr."""
    rows = [
        DetailRow("profile", f"{generation.name} ({generation.origin})"),
        DetailRow("project", str(report.project_root)),
        DetailRow("target", f"ig/input/fsh/{report.target_directory}"),
        DetailRow("files written", str(len(report.written_files))),
        DetailRow("unchanged", str(report.unchanged_count)),
        DetailRow("files deleted", str(len(report.deleted_files))),
    ]
    if report.option_set_count:
        rows.append(DetailRow("option sets", str(report.option_set_count)))
    if report.organisation_unit_count:
        rows.append(DetailRow("org units", str(report.organisation_unit_count)))
    if report.position_count:
        rows.append(DetailRow("positions", str(report.position_count)))
    if report.boundary_count:
        rows.append(DetailRow("boundaries", str(report.boundary_count)))
    render_detail(title, rows)
    for note in report.notes:
        typer.secho(f"note: {note}", err=True, fg=typer.colors.YELLOW)


@generate_app.command("option-sets")
def generate_option_sets_command() -> None:
    """Generate CodeSystem/ValueSet FSH from DHIS2 option sets into the nearest FHIR project."""
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_option_sets(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate option-sets", report, generation)


@generate_app.command("org-units")
def generate_organisation_units_command() -> None:
    """Generate Organization/Location FSH from DHIS2 organisation units into the nearest FHIR project."""
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_organisation_units(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate org-units", report, generation)


@generate_app.command("all")
def generate_all_command() -> None:
    """Generate option-set terminology and organisation-unit instances in one run."""
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_all(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate option-sets", report.option_sets, generation)
    _render_generate_report("fhir generate org-units", report.organisation_units, generation)


@app.command("validate")
def validate_command(
    report_path: Annotated[
        Path | None,
        typer.Option(
            "--report",
            dir_okay=False,
            help="Markdown report path (default: fhir-validate-report.md in the project root or current directory).",
        ),
    ] = None,
    show_all: Annotated[
        bool, typer.Option("--all", help="List info-level findings individually instead of rolled up.")
    ] = False,
    no_fail: Annotated[bool, typer.Option("--no-fail", help="Exit 0 even when errors are found.")] = False,
) -> None:
    """Check the instance's codes for FHIR-safety; writes a Markdown report grouped by type. Exits 1 on errors."""
    from collections import Counter

    from dhis2w_core.cli_output import ColumnSpec, render_list

    from dhis2w_fhir import find_project_fhir_config, render_validation_markdown, service

    context = service.resolve_validation_context()
    report = asyncio.run(service.validate_codes(context.generation.profile, context.config))
    project_config = find_project_fhir_config()
    default_directory = project_config.parent if project_config else Path.cwd()
    destination = report_path or default_directory / "fhir-validate-report.md"
    target = f"{context.generation.name} ({context.generation.profile.base_url})"
    destination.write_text(render_validation_markdown(report, target), encoding="utf-8")
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
    else:
        render_detail(
            "fhir validate",
            [
                DetailRow("profile", f"{context.generation.name} ({context.generation.origin})"),
                DetailRow("resource types", str(report.resource_type_count)),
                DetailRow("objects swept", str(report.object_count)),
                DetailRow("option sets", str(report.option_set_count)),
                DetailRow("options", str(report.option_count)),
                DetailRow("errors", str(report.error_count)),
                DetailRow("warnings", str(report.warning_count)),
                DetailRow("infos", str(report.info_count)),
                DetailRow("report", str(destination)),
            ],
        )
        detailed = [finding for finding in report.findings if show_all or finding.severity in {"error", "warning"}]
        if detailed:
            render_list(
                "findings",
                [
                    {
                        "severity": finding.severity,
                        "category": finding.category,
                        "type": finding.resource_type,
                        "object": f"{finding.name} ({finding.uid})",
                        "code": finding.code or "-",
                        "message": finding.message,
                    }
                    for finding in detailed
                ],
                [
                    ColumnSpec("Severity", "severity", style="red", no_wrap=True),
                    ColumnSpec("Category", "category", no_wrap=True),
                    ColumnSpec("Type", "type", no_wrap=True),
                    ColumnSpec("Object", "object"),
                    ColumnSpec("Code", "code"),
                    ColumnSpec("Why it matters", "message"),
                ],
            )
        if not show_all:
            rollup = Counter(finding.category for finding in report.findings if finding.severity == "info")
            for category, count in sorted(rollup.items()):
                typer.secho(f"info: {category} x{count} (details in the report; --all to list)", err=True)
    if report.error_count and not no_fail:
        typer.secho(
            f"{report.error_count} error(s) found; exiting 1 (--no-fail to suppress)", err=True, fg=typer.colors.RED
        )
        raise typer.Exit(code=1)


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `d2w fhir`."""
    root_app.add_typer(app, name="fhir", help="FHIR Implementation Guide generation from DHIS2 metadata.")
