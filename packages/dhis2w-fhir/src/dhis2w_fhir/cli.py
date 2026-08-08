"""Typer sub-app for the `fhir` plugin (mounted under `d2w fhir`)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from dhis2w_core.cli_output import DetailRow, is_json_output, render_detail

from dhis2w_fhir import DEFAULT_LOAD_SET_PER_TARGET, DEFAULT_SUSHI_TIMEOUT_SECONDS, GenerateReport, load_project

if TYPE_CHECKING:
    from dhis2w_fhir.service import GenerationProfile, LoadSetReport
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
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="DHIS2 profile to seed the `profile` key of the scaffolded fhir.toml with, so "
            "`d2w fhir generate` reads that instance without a flag. Offline: the name is written as "
            "given, never resolved against profiles.toml.",
        ),
    ] = None,
    sushi_timeout: Annotated[
        int,
        typer.Option(
            "--sushi-timeout",
            help="Seconds the IG publisher gives its internal SUSHI run, written to `\\[FSH] timeout` of "
            "ig/fsh.ini. The registry ships as pre-built JSON and never reaches SUSHI, so this bounds the "
            "FSH targets: an IG whose SUSHI run overruns the ceiling fails the build with exit 143.",
        ),
    ] = DEFAULT_SUSHI_TIMEOUT_SECONDS,
    max_level: Annotated[
        int | None,
        typer.Option(
            "--max-level",
            help="Deepest organisation-unit level to generate, seeding `\\[generate.organisation_units]` "
            "max_level. Every unit emits two instances and a hierarchy fans out at the bottom, so this is "
            "the dial that bounds how many resources the IG publisher renders. Offline: the level is "
            "written to fhir.toml as given, never checked against an instance.",
        ),
    ] = None,
    data_set_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--data-set",
            help="Data set UID to seed `\\[generate.data_sets]` include_ids with (repeatable). Offline: the UID is "
            "written to fhir.toml as given, never checked against an instance.",
        ),
    ] = None,
    event_program_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--event",
            help="Event program UID to seed `\\[generate.event_programs]` include_ids with (repeatable). Offline: "
            "the UID is written to fhir.toml as given, never checked against an instance.",
        ),
    ] = None,
    tracker_program_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--tracker-program",
            help="Tracker program UID to seed `\\[generate.tracker_programs]` include_ids with (repeatable); the "
            "program emits one Questionnaire per program stage. Offline: the UID is written to fhir.toml as "
            "given, never checked against an instance.",
        ),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite scaffold files that already exist.")] = False,
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh",
            help="Bring an existing project's scaffold-managed files up to date. Identity comes from the "
            "project's own fhir.toml, which a refresh never writes, and a file carrying a line the scaffold "
            "would not produce is left alone and reported, so your edits survive. Rejects --force.",
        ),
    ] = False,
) -> None:
    """Scaffold a dockerized SUSHI IG project with a fhir.toml for `d2w fhir generate`."""
    from dhis2w_fhir import InitOptions, service
    from dhis2w_fhir.names import pascal

    if refresh and force:
        raise typer.BadParameter(
            "--refresh and --force are mutually exclusive: --force rewrites every scaffold file including "
            "the ones you edited, --refresh rewrites only what it can rewrite without losing your edits"
        )
    if refresh:
        _refresh_project(directory)
        return
    if status not in {"draft", "active"}:
        raise typer.BadParameter("status must be 'draft' or 'active'")
    if max_level is not None and max_level < 1:
        raise typer.BadParameter("max-level must be 1 or greater")
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
        profile=profile,
        sushi_timeout=sushi_timeout,
        max_level=max_level,
        data_set_ids=data_set_ids or [],
        event_program_ids=event_program_ids or [],
        tracker_program_ids=tracker_program_ids or [],
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
    if profile:
        typer.secho(f"next: run `d2w fhir generate all` (profile `{profile}`)", err=True)
    else:
        typer.secho("next: set `profile` in fhir.toml, then run `d2w fhir generate all`", err=True)


def _refresh_project(directory: Path) -> None:
    """Refresh an existing project's scaffold-managed files and render what each one did."""
    from dhis2w_fhir.config import FHIR_CONFIG_FILENAME, NoFhirProjectError
    from dhis2w_fhir.scaffold.refresh import refresh_project

    try:
        report = refresh_project(directory)
    except NoFhirProjectError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from error
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    render_detail(
        "fhir init --refresh",
        [
            DetailRow("directory", str(report.directory)),
            DetailRow("created", str(len(report.created_files))),
            DetailRow("refreshed", str(len(report.refreshed_files))),
            DetailRow("unchanged", str(len(report.unchanged_files))),
            DetailRow("skipped", str(len(report.edited_files))),
        ],
    )
    for relative_path in report.created_files:
        typer.echo(f"  created {relative_path}")
    for relative_path in report.refreshed_files:
        typer.echo(f"  refreshed {relative_path}")
    for relative_path in report.unchanged_files:
        typer.echo(f"  unchanged {relative_path}")
    for relative_path in report.edited_files:
        typer.echo(f"  skipped {relative_path} (you edited it; your version stays)")
    typer.secho(f"note: {FHIR_CONFIG_FILENAME} is yours - a refresh never writes it", err=True)
    if report.edited_files:
        typer.secho(
            "note: to take the scaffold's version of a skipped file, delete it and refresh again",
            err=True,
            fg=typer.colors.YELLOW,
        )


def _render_generate_report(title: str, report: GenerateReport, generation: GenerationProfile) -> None:
    """Render one generation report as a Rich detail table plus note lines on stderr."""
    rows = [
        DetailRow("profile", f"{generation.name} ({generation.origin})"),
        DetailRow("project", str(report.project_root)),
        DetailRow("target", f"{report.target_base}/{report.target_directory}"),
        DetailRow("files written", str(len(report.written_files))),
        DetailRow("unchanged", str(report.unchanged_count)),
        DetailRow("files deleted", str(len(report.deleted_files))),
    ]
    if report.option_set_count:
        rows.append(DetailRow("option sets", str(report.option_set_count)))
    if report.category_count:
        rows.append(DetailRow("categories", str(report.category_count)))
    if report.questionnaire_count:
        rows.append(DetailRow("questionnaires", str(report.questionnaire_count)))
    if report.example_count:
        rows.append(DetailRow("examples", str(report.example_count)))
    if report.organisation_unit_count:
        rows.append(DetailRow("org units", str(report.organisation_unit_count)))
    if report.position_count:
        rows.append(DetailRow("positions", str(report.position_count)))
    if report.boundary_count:
        rows.append(DetailRow("boundaries", str(report.boundary_count)))
    if report.page_count:
        rows.append(DetailRow("pages", str(report.page_count)))
    if report.intro_count:
        rows.append(DetailRow("intros", str(report.intro_count)))
    render_detail(title, rows)
    for note in report.notes:
        typer.secho(f"note: {note}", err=True, fg=typer.colors.YELLOW)


@generate_app.command("foundation")
def generate_foundation_command() -> None:
    """Generate the DHIS2 identifier aliases, the extensions, and the capture contract into the FHIR project."""
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
    """Generate CodeSystem/ValueSet JSON from DHIS2 option sets into the nearest FHIR project."""
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_option_sets(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate option-sets", report, generation)


@generate_app.command("categories")
def generate_categories_command() -> None:
    """Generate CodeSystem/ValueSet JSON from DHIS2 categories into the nearest FHIR project."""
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_categories(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate categories", report, generation)


@generate_app.command("questionnaires")
def generate_questionnaires_command() -> None:
    """Generate Questionnaire FSH into data-sets/, event-programs/, tracker-programs/, and data-dictionary/.

    A data set and an event program are one Questionnaire each; a tracker program is one
    Questionnaire per program stage, filed under the UID of the program it belongs to.
    """
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_questionnaires(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate questionnaires", report, generation)


@generate_app.command("examples")
def generate_examples_command() -> None:
    """Generate example QuestionnaireResponses for every configured data set, event program, and tracker stage."""
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_examples(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate examples", report, generation)


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


@generate_app.command("pages")
def generate_pages_command() -> None:
    """Generate the narrative site pages and the per-artifact intros into ig/input/pagecontent/."""
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_pages(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate pages", report, generation)


@generate_app.command("all")
def generate_all_command() -> None:
    """Generate the foundation, terminology, questionnaires, examples, org-unit instances, and the pages.

    The questionnaire pass covers all four directories: data-sets/, event-programs/,
    tracker-programs/ (one file per stage, under its program's UID), and data-dictionary/.
    """
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(service.generate_full(generation.profile, project))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report("fhir generate foundation", report.foundation, generation)
    _render_generate_report("fhir generate option-sets", report.option_sets, generation)
    _render_generate_report("fhir generate categories", report.categories, generation)
    _render_generate_report("fhir generate questionnaires", report.questionnaires, generation)
    _render_generate_report("fhir generate examples", report.examples, generation)
    _render_generate_report("fhir generate org-units", report.organisation_units, generation)
    _render_generate_report("fhir generate pages", report.pages, generation)


@generate_app.command("load")
def generate_load_command(
    per_target: Annotated[
        int,
        typer.Option(
            "--per-target",
            min=1,
            help="How many synthetic responses each questionnaire target contributes.",
        ),
    ] = DEFAULT_LOAD_SET_PER_TARGET,
    directory: Annotated[
        Path | None,
        typer.Option(
            "--directory",
            file_okay=False,
            help="Where to write the `load/` corpus (default: the project root).",
        ),
    ] = None,
) -> None:
    """Write a synthetic QuestionnaireResponse corpus into load/ for posting at a running `d2w fhir serve`.

    A load set is test data, not IG source: it lands beside `ig/` rather than inside it, the
    scaffold gitignores it, and `d2w fhir generate all` does not write it.
    """
    from dhis2w_fhir import service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(
        service.generate_load_set(generation.profile, project, per_target=per_target, output_directory=directory)
    )
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_load_set_report(report, generation)


def _render_load_set_report(report: LoadSetReport, generation: GenerationProfile) -> None:
    """Render one load-set run the way the generate targets render theirs."""
    render_detail(
        "fhir generate load",
        [
            DetailRow("profile", f"{generation.name} ({generation.origin})"),
            DetailRow("project", str(report.project_root)),
            DetailRow("target", report.target_directory),
            DetailRow("files written", str(len(report.written_files))),
            DetailRow("unchanged", str(report.unchanged_count)),
            DetailRow("files deleted", str(len(report.deleted_files))),
            DetailRow("responses", str(report.response_count)),
            DetailRow("questionnaires", str(report.questionnaire_count)),
        ],
    )
    for note in report.notes:
        typer.secho(f"note: {note}", err=True, fg=typer.colors.YELLOW)


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
            "(default: reports/fhir-validate-report under the project root or current directory).",
        ),
    ] = None,
    formats: Annotated[
        str, typer.Option("--format", help="Comma-separated report formats to write: md, csv, pdf.")
    ] = "md,csv,pdf",
    code_source: Annotated[
        str | None,
        typer.Option(
            "--code-source",
            help="Override `\\[generate]` concept_code_source for this run: id or code. In id mode the option "
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

    from dhis2w_fhir import REPORTS_DIRECTORY, find_project_fhir_config, service
    from dhis2w_fhir.validation.pdf import render_validation_pdf
    from dhis2w_fhir.validation.report import display_code, render_validation_csv, render_validation_markdown

    selected_formats = _parse_report_formats(formats)
    if code_source is not None and code_source not in {"id", "code"}:
        raise typer.BadParameter("code_source must be 'id' or 'code'")
    context = service.resolve_validation_context()
    report = asyncio.run(service.validate_codes(context.generation.profile, context.config, code_source))
    project_config = find_project_fhir_config()
    default_directory = project_config.parent if project_config else Path.cwd()
    stem = report_stem or default_directory / REPORTS_DIRECTORY / "fhir-validate-report"
    stem.parent.mkdir(parents=True, exist_ok=True)
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
                DetailRow("attributes", str(report.attribute_count)),
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


#: What a caller is told when the serve extra is not installed. `LookupError` renders through the
#: CLI error funnel as a one-line message, which is what an install instruction wants to be.
_SERVE_PACKAGE_MISSING = (
    "`d2w fhir serve` needs the dhis2w-fhir-serve package. Install it with "
    "`uv add dhis2w-fhir-serve` or `pip install 'dhis2w-cli[serve]'`."
)


@app.command("serve")
def serve_command(
    directory: Annotated[
        Path, typer.Argument(file_okay=False, help="Project directory (default: current directory).")
    ] = Path("."),
    live: Annotated[
        bool,
        typer.Option(
            "--live",
            help="Build the served resources from a DHIS2 instance at startup instead of reading the "
            "compiled IG off disk. One client is opened during startup and closed before the first "
            "request, so the store is a snapshot of the instance the server started against.",
        ),
    ] = False,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Interface to bind. The default is loopback: the facade has no authentication, so "
            "reaching it from another host is a deliberate act.",
        ),
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Port to listen on.")] = 8080,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="DHIS2 profile the --live store reads from. Ignored without --live."),
    ] = None,
    strict_codes: Annotated[
        bool,
        typer.Option(
            "--strict-codes",
            help="Refuse a received answer whose code is outside the served terminology. The default "
            "records the drift as a warning and stores the submission, because an option added to the "
            "instance since the IG was built is a fact about the instance, not a client mistake.",
        ),
    ] = False,
) -> None:
    """Serve the project's IG as a FHIR read and capture facade over HTTP.

    Reads answer from what the IG publishes. Received QuestionnaireResponses are stored as
    receipts - submissions as they arrived - so reading one back says what was submitted, not
    what DHIS2 holds. `--live` builds the served resources from the instance at startup.
    """
    try:
        from dhis2w_fhir_serve import (
            COMPILED_RESOURCES_RELATIVE_PATH,
            CompiledIgMissingError,
            ServeSettings,
            configure_logging,
            create_app,
        )
    except ImportError as error:
        raise LookupError(_SERVE_PACKAGE_MISSING) from error

    project = load_project(directory)
    if not live and not any((project.ig_directory / COMPILED_RESOURCES_RELATIVE_PATH).glob("*.json")):
        raise CompiledIgMissingError
    settings = ServeSettings(project_dir=directory, live=live, profile=profile, strict_codes=strict_codes)
    configure_logging()
    typer.secho(f"serving {project.project_root} on http://{host}:{port} (ctrl-c to stop)", err=True)
    _run_server(create_app(settings), host=host, port=port)


def _run_server(application: Any, *, host: str, port: int) -> None:
    """Run one built facade under uvicorn until the process is interrupted.

    The server's own logging is switched off - `configure_logging` already put one line per
    request on stderr, and uvicorn's access log would double every one of them.
    """
    import uvicorn

    try:
        uvicorn.run(application, host=host, port=port, log_config=None, access_log=False)
    except KeyboardInterrupt as interrupt:
        raise typer.Exit(0) from interrupt


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `d2w fhir`."""
    root_app.add_typer(app, name="fhir", help="FHIR Implementation Guide generation from DHIS2 metadata.")
