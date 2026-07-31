"""Typer sub-app for the `fhir` plugin (mounted under `d2w fhir`)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from dhis2w_core.fhir_core import FhirProject, GenerateReport, load_project
from dhis2w_core.profile import Profile, resolve_profile
from dhis2w_core.v41.cli_output import DetailRow, is_json_output, render_detail

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
    from dhis2w_core.fhir_core import InitOptions
    from dhis2w_core.fhir_core.names import pascal
    from dhis2w_core.v41.plugins.fhir import service

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


def _generation_profile(project: FhirProject) -> Profile:
    """Resolve the DHIS2 profile: explicit `-p`/`DHIS2_PROFILE` wins, then fhir.toml, then the normal chain."""
    return resolve_profile(os.environ.get("DHIS2_PROFILE") or project.config.profile)


def _render_generate_report(title: str, report: GenerateReport) -> None:
    """Render one generation report as a Rich detail table plus note lines on stderr."""
    rows = [
        DetailRow("project", str(report.project_root)),
        DetailRow("target", f"ig/input/fsh/{report.target_directory}"),
        DetailRow("files written", str(len(report.written_files))),
        DetailRow("files deleted", str(len(report.deleted_files))),
    ]
    if report.option_set_count:
        rows.append(DetailRow("option sets", str(report.option_set_count)))
    if report.org_unit_count:
        rows.append(DetailRow("org units", str(report.org_unit_count)))
    if report.location_count:
        rows.append(DetailRow("locations", str(report.location_count)))
    render_detail(title, rows)
    for note in report.notes:
        typer.secho(f"note: {note}", err=True, fg=typer.colors.YELLOW)


@generate_app.command("option-sets")
def generate_option_sets_command() -> None:
    """Generate CodeSystem/ValueSet FSH from DHIS2 option sets into the nearest FHIR project."""
    from dhis2w_core.v41.plugins.fhir import service

    project = load_project()
    report = asyncio.run(service.generate_option_sets(_generation_profile(project), project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate option-sets", report)


@generate_app.command("org-units")
def generate_org_units_command() -> None:
    """Generate Organization/Location FSH from DHIS2 organisation units into the nearest FHIR project."""
    from dhis2w_core.v41.plugins.fhir import service

    project = load_project()
    report = asyncio.run(service.generate_org_units(_generation_profile(project), project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate org-units", report)


@generate_app.command("all")
def generate_all_command() -> None:
    """Generate option-set terminology and organisation-unit instances in one run."""
    from dhis2w_core.v41.plugins.fhir import service

    project = load_project()
    report = asyncio.run(service.generate_all(_generation_profile(project), project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate option-sets", report.option_sets)
    _render_generate_report("fhir generate org-units", report.org_units)


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `d2w fhir`."""
    root_app.add_typer(app, name="fhir", help="FHIR Implementation Guide generation from DHIS2 metadata.")
