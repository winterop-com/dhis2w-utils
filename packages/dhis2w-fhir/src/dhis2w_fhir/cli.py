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
    from dhis2w_fhir.status import IgStatus

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
    status: Annotated[
        str,
        typer.Option(
            "--status",
            help="IG life cycle, draft or active. Drives the sushi-config status and the status and "
            "experimental flag on every generated definitional resource.",
        ),
    ] = "draft",
    publisher_url: Annotated[
        str | None,
        typer.Option(
            "--publisher-url",
            help="Publisher home page. Omit it unless you have a real site: the IG publisher links it from "
            "every generated page, and pointing it at the canonical yields one broken link per page.",
        ),
    ] = None,
    data_set_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--data-set",
            help="Data set UID to seed [generate.data_sets] include_ids with (repeatable). Offline: the UID is "
            "written to fhir.toml as given, never checked against an instance.",
        ),
    ] = None,
    event_program_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--event",
            help="Event program UID to seed [generate.event_programs] include_ids with (repeatable). Offline: "
            "the UID is written to fhir.toml as given, never checked against an instance.",
        ),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite scaffold files that already exist.")] = False,
) -> None:
    """Scaffold a dockerized SUSHI IG project with a fhir.toml for `d2w fhir generate`."""
    from dhis2w_fhir import InitOptions, service
    from dhis2w_fhir.names import pascal

    if status not in {"draft", "active"}:
        raise typer.BadParameter("status must be 'draft' or 'active'")
    ig_status: IgStatus = "active" if status == "active" else "draft"
    resolved_name = name or pascal(ig_id)
    options = InitOptions(
        ig_id=ig_id,
        canonical=canonical,
        name=resolved_name,
        title=title or f"{resolved_name} Implementation Guide",
        publisher=publisher,
        status=ig_status,
        publisher_url=publisher_url,
        data_set_ids=data_set_ids or [],
        event_program_ids=event_program_ids or [],
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
    if report.questionnaire_count:
        rows.append(DetailRow("questionnaires", str(report.questionnaire_count)))
    if report.organisation_unit_count:
        rows.append(DetailRow("org units", str(report.organisation_unit_count)))
    if report.position_count:
        rows.append(DetailRow("positions", str(report.position_count)))
    if report.boundary_count:
        rows.append(DetailRow("boundaries", str(report.boundary_count)))
    render_detail(title, rows)
    for note in report.notes:
        typer.secho(f"note: {note}", err=True, fg=typer.colors.YELLOW)


@generate_app.command("foundation")
def generate_foundation_command() -> None:
    """Generate the DHIS2 identifier aliases and the D2Period extension into the nearest FHIR project."""
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_foundation(project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate foundation", report, generation)


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


@generate_app.command("questionnaires")
def generate_questionnaires_command() -> None:
    """Generate Questionnaire FSH from the configured DHIS2 data sets and event programs."""
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_questionnaires(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate questionnaires", report, generation)


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
    """Generate the foundation, option-set terminology, questionnaires, and organisation-unit instances in one run."""
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_all(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate foundation", report.foundation, generation)
    _render_generate_report("fhir generate option-sets", report.option_sets, generation)
    _render_generate_report("fhir generate questionnaires", report.questionnaires, generation)
    _render_generate_report("fhir generate org-units", report.organisation_units, generation)


#: The report formats `--format` accepts, in the order they are written.
_REPORT_FORMATS = ("md", "csv", "pdf")


def _parse_report_formats(value: str) -> list[str]:
    """Parse the `--format` comma list into the canonical write order, rejecting unknown names."""
    requested = {item.strip().lower() for item in value.split(",") if item.strip()}
    unknown = sorted(requested - set(_REPORT_FORMATS))
    if unknown:
        raise typer.BadParameter(f"unknown format(s): {', '.join(unknown)} (choose from md, csv, pdf)")
    if not requested:
        raise typer.BadParameter("at least one format is required (choose from md, csv, pdf)")
    return [name for name in _REPORT_FORMATS if name in requested]


@app.command("validate")
def validate_command(
    report_stem: Annotated[
        Path | None,
        typer.Option(
            "--report",
            dir_okay=False,
            help="Report path stem, without extension "
            "(default: fhir-validate-report in the project root or current directory).",
        ),
    ] = None,
    formats: Annotated[
        str, typer.Option("--format", help="Comma-separated report formats to write: md, csv, pdf.")
    ] = "md,csv,pdf",
    code_source: Annotated[
        str | None,
        typer.Option(
            "--code-source",
            help="Override [generate] concept_code_source for this run: id or code. In id mode the option "
            "code findings are informational; run with code to see what switching would cost.",
        ),
    ] = None,
    show_all: Annotated[
        bool, typer.Option("--all", help="List info-level findings individually instead of rolled up.")
    ] = False,
    no_fail: Annotated[bool, typer.Option("--no-fail", help="Exit 0 even when errors are found.")] = False,
) -> None:
    """Check the instance's codes for FHIR-safety; writes md/csv/pdf reports grouped by type. Exits 1 on errors."""
    from collections import Counter
    from datetime import UTC, datetime

    from dhis2w_core.cli_output import ColumnSpec, render_list

    from dhis2w_fhir import find_project_fhir_config, service
    from dhis2w_fhir.validation.pdf import render_validation_pdf
    from dhis2w_fhir.validation.report import display_code, render_validation_csv, render_validation_markdown

    selected_formats = _parse_report_formats(formats)
    if code_source is not None and code_source not in {"id", "code"}:
        raise typer.BadParameter("code_source must be 'id' or 'code'")
    context = service.resolve_validation_context()
    report = asyncio.run(service.validate_codes(context.generation.profile, context.config, code_source))
    project_config = find_project_fhir_config()
    default_directory = project_config.parent if project_config else Path.cwd()
    stem = report_stem or default_directory / "fhir-validate-report"
    target = f"{context.generation.name} ({context.generation.profile.base_url})"
    generated_at = datetime.now(tz=UTC)
    for report_format in selected_formats:
        destination = stem.with_name(f"{stem.name}.{report_format}")
        if report_format == "md":
            destination.write_text(render_validation_markdown(report, target, generated_at), encoding="utf-8")
        elif report_format == "csv":
            destination.write_text(render_validation_csv(report), encoding="utf-8")
        else:
            destination.write_bytes(render_validation_pdf(report, target, generated_at))
        typer.secho(f"wrote {destination}", err=True)
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
                DetailRow("code source", service.resolve_code_source(context.config, code_source)),
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
                        "code": display_code(finding.code),
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
