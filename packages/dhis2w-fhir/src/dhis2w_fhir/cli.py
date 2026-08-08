"""Typer sub-app for the `fhir` plugin (mounted under `d2w fhir`).

Two output channels, one rule: every table, note, and progress line goes to
stderr through `STDERR_CONSOLE`, and stdout carries the `--json` payload alone.
A caller pipes stdout into `jq` without filtering anything out, and a human
reads the narration on the terminal either way.
"""

from __future__ import annotations

import asyncio
import errno
import socket
from collections import Counter
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from dhis2w_core.cli_output import ColumnSpec, DetailRow, is_json_output, render_detail, render_list
from dhis2w_core.progress import animated_progress, make_reporter
from dhis2w_core.rich_console import STDERR_CONSOLE
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir import DEFAULT_LOAD_SET_PER_TARGET, DEFAULT_SUSHI_TIMEOUT_SECONDS, GenerateReport, load_project

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from dhis2w_core.progress import ProgressReporter

    from dhis2w_fhir.notes import GenerateNote
    from dhis2w_fhir.service import GenerateFullReport, GenerationProfile, LoadSetReport
    from dhis2w_fhir.validation.schemas import FhirValidationReport

app = typer.Typer(help="FHIR Implementation Guide generation from DHIS2 metadata.", no_args_is_help=True)
generate_app = typer.Typer()
app.add_typer(generate_app, name="generate")


class IgStatusChoice(StrEnum):
    """The IG life-cycle values `--status` accepts, mirroring the `IgStatus` literal."""

    DRAFT = "draft"
    ACTIVE = "active"


class CodeSourceChoice(StrEnum):
    """The concept code sources `--code-source` accepts, mirroring `[generate] concept_code_source`."""

    ID = "id"
    CODE = "code"


#: The detail-table title every generate target renders under, keyed by its command name.
_TARGET_TITLES = {
    "foundation": "fhir generate foundation",
    "option-sets": "fhir generate option-sets",
    "categories": "fhir generate categories",
    "questionnaires": "fhir generate questionnaires",
    "examples": "fhir generate examples",
    "org-units": "fhir generate org-units",
    "pages": "fhir generate pages",
    "load-set": "fhir generate load-set",
}

#: The Rich style each hint prefix carries, so a note reads as a note wherever it is printed.
_HINT_STYLES = {"note": "yellow", "ok": "green"}

#: The basename every validation report file is written under, inside `--output-dir`.
_VALIDATION_REPORT_STEM = "fhir-validate-report"

#: The report formats `--format` accepts, in the order they are written.
_REPORT_FORMATS = ("md", "csv", "pdf")

#: The scaffold defaults `--refresh` compares against to tell an untouched flag from a given one.
_DEFAULT_IG_ID = "dhis2.fhir.example"
_DEFAULT_CANONICAL = "http://example.org/fhir"
_DEFAULT_PUBLISHER = "Example Organisation"

#: The flag every long-running command narrates through, declared once and reused by each of them.
ProgressOption = Annotated[
    bool,
    typer.Option("--progress/--no-progress", help="Narrate each step on stderr as it completes."),
]


def _line(text: str) -> None:
    """Print one plain narration line on stderr, unwrapped so a path in it stays one selectable string."""
    STDERR_CONSOLE.print(text, markup=False, highlight=False, soft_wrap=True)


def _hint(prefix: str, text: str, *, style: str | None = None) -> None:
    """Print one `prefix: text` line on stderr, in the style that prefix carries unless one is given."""
    STDERR_CONSOLE.print(
        f"{prefix}: {text}",
        style=style or _HINT_STYLES.get(prefix),
        markup=False,
        highlight=False,
        soft_wrap=True,
    )


@contextmanager
def _progress(total: int, *, enabled: bool) -> Generator[ProgressReporter | None]:
    """Yield the reporter a run narrates its `total` steps through, torn down on every exit path.

    None when the run stays quiet - `--no-progress`, or `--json`, where stderr carries nothing
    so a caller reads the payload off stdout without filtering. The service treats a missing
    reporter as "announce to nothing", so the same call works either way.
    """
    if not enabled or is_json_output():
        yield None
        return
    reporter = make_reporter(STDERR_CONSOLE, animated=animated_progress(enabled))
    reporter.start(total, activity="step")
    try:
        yield reporter
    finally:
        reporter.stop()


@app.command("init")
def init_command(
    directory: Annotated[
        Path, typer.Argument(file_okay=False, help="Project directory (default: current directory).")
    ] = Path("."),
    ig_id: Annotated[str, typer.Option("--id", help="IG package id.")] = _DEFAULT_IG_ID,
    canonical: Annotated[
        str, typer.Option("--canonical", help="Canonical base URL for the IG (no trailing slash).")
    ] = _DEFAULT_CANONICAL,
    name: Annotated[str | None, typer.Option("--name", help="SUSHI name (default: derived from --id).")] = None,
    title: Annotated[str | None, typer.Option("--title", help="IG title (default: derived from --name).")] = None,
    publisher: Annotated[str, typer.Option("--publisher", help="Publisher name.")] = _DEFAULT_PUBLISHER,
    status: Annotated[
        IgStatusChoice,
        typer.Option(
            "--status",
            help="IG life cycle. Drives the sushi-config status, and the status and experimental flag "
            "on every generated definitional resource.",
        ),
    ] = IgStatusChoice.DRAFT,
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
            "ig/fsh.ini. It bounds the FSH targets alone - the registry and the terminology ship as "
            "pre-built JSON - and an overrun fails the build with exit 143.",
        ),
    ] = DEFAULT_SUSHI_TIMEOUT_SECONDS,
    max_level: Annotated[
        int | None,
        typer.Option(
            "--max-level",
            help="Deepest organisation-unit level to generate, seeding `\\[generate.organisation_units]` "
            "max_level. A hierarchy fans out at the bottom and every unit emits two instances, so this "
            "is the dial that bounds how much the IG publisher renders. Offline: written as given.",
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
            "--event-program",
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
        _reject_scaffold_flags(
            ig_id=ig_id,
            canonical=canonical,
            name=name,
            title=title,
            publisher=publisher,
            status=status,
            publisher_url=publisher_url,
            profile=profile,
            sushi_timeout=sushi_timeout,
            max_level=max_level,
            data_set_ids=data_set_ids,
            event_program_ids=event_program_ids,
            tracker_program_ids=tracker_program_ids,
        )
        _refresh_project(directory)
        return
    if max_level is not None and max_level < 1:
        raise typer.BadParameter("--max-level must be 1 or greater")
    resolved_name = name or pascal(ig_id)
    options = InitOptions(
        ig_id=ig_id,
        canonical=canonical,
        name=resolved_name,
        title=title or f"{resolved_name} Implementation Guide",
        publisher=publisher,
        status="active" if status is IgStatusChoice.ACTIVE else "draft",
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
        console=STDERR_CONSOLE,
    )
    for relative_path in report.created_files:
        _line(f"  created {relative_path}")
    for relative_path in report.skipped_files:
        _line(f"  skipped {relative_path} (exists; use --force to overwrite)")
    if profile:
        _hint("next", f"run `d2w fhir generate` (profile `{profile}`)")
    else:
        _hint("next", "set `profile` in fhir.toml, then run `d2w fhir generate`")


def _reject_scaffold_flags(
    *,
    ig_id: str,
    canonical: str,
    name: str | None,
    title: str | None,
    publisher: str,
    status: IgStatusChoice,
    publisher_url: str | None,
    profile: str | None,
    sushi_timeout: int,
    max_level: int | None,
    data_set_ids: list[str] | None,
    event_program_ids: list[str] | None,
    tracker_program_ids: list[str] | None,
) -> None:
    """Refuse a refresh that carries scaffold content, naming the flags a refresh would ignore.

    A refresh reads the IG identity and the generation tables back off the project's own
    fhir.toml, and never writes that file, so a flag seeding either of them cannot land. Silently
    dropping it would leave a caller believing they changed something they did not.
    """
    given = {
        "--id": ig_id != _DEFAULT_IG_ID,
        "--canonical": canonical != _DEFAULT_CANONICAL,
        "--name": name is not None,
        "--title": title is not None,
        "--publisher": publisher != _DEFAULT_PUBLISHER,
        "--status": status is not IgStatusChoice.DRAFT,
        "--publisher-url": publisher_url is not None,
        "--profile": profile is not None,
        "--sushi-timeout": sushi_timeout != DEFAULT_SUSHI_TIMEOUT_SECONDS,
        "--max-level": max_level is not None,
        "--data-set": bool(data_set_ids),
        "--event-program": bool(event_program_ids),
        "--tracker-program": bool(tracker_program_ids),
    }
    named = [flag for flag, was_given in given.items() if was_given]
    if not named:
        return
    raise typer.BadParameter(
        f"--refresh takes the project's identity and generation tables from its own fhir.toml, "
        f"so {', '.join(named)} would be ignored: drop the flag, or edit fhir.toml and refresh"
    )


def _refresh_project(directory: Path) -> None:
    """Refresh an existing project's scaffold-managed files and render what each one did."""
    from dhis2w_fhir.config import FHIR_CONFIG_FILENAME
    from dhis2w_fhir.scaffold.refresh import refresh_project

    report = refresh_project(directory)
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
            DetailRow("edited (kept)", str(len(report.edited_files))),
        ],
        console=STDERR_CONSOLE,
    )
    for relative_path in report.created_files:
        _line(f"  created {relative_path}")
    for relative_path in report.refreshed_files:
        _line(f"  refreshed {relative_path}")
    for relative_path in report.unchanged_files:
        _line(f"  unchanged {relative_path}")
    for relative_path in report.edited_files:
        _line(f"  skipped {relative_path} (you edited it; your version stays)")
    _hint("note", f"{FHIR_CONFIG_FILENAME} is yours - a refresh never writes it")
    if report.edited_files:
        _hint("note", "to take the scaffold's version of a skipped file, delete it and refresh again")


class _TargetOutcome(BaseModel):
    """One target of a full run, paired with the command name its summary row is labelled by."""

    model_config = ConfigDict(frozen=True)

    target: str
    report: GenerateReport


def _target_label(report: GenerateReport | LoadSetReport) -> str:
    """Where a run wrote, as one path: a generate target carries its base, a load set is the corpus directory."""
    if isinstance(report, GenerateReport):
        return f"{report.target_base}/{report.target_directory}"
    return report.target_directory


def _render_generate_report(
    title: str,
    report: GenerateReport | LoadSetReport,
    generation: GenerationProfile,
    *,
    extra_rows: Iterable[DetailRow] = (),
) -> None:
    """Render one run's outcome as a detail table on stderr, followed by every note it raised.

    The common rows - profile, project, target, and the written / unchanged / deleted counts -
    are the same whichever run wrote them; `extra_rows` carries the counts that belong to this
    target alone. Every row renders at zero too, so a table's shape says what a target counts
    rather than what it happened to find.
    """
    rows = [
        DetailRow("profile", f"{generation.name} ({generation.origin})"),
        DetailRow("project", str(report.project_root)),
        DetailRow("target", _target_label(report)),
        DetailRow("files written", str(len(report.written_files))),
        DetailRow("unchanged", str(report.unchanged_count)),
        DetailRow("files deleted", str(len(report.deleted_files))),
        *extra_rows,
    ]
    render_detail(title, rows, console=STDERR_CONSOLE)
    for note in report.notes:
        _hint("note", note.message)


def _full_outcomes(report: GenerateFullReport) -> list[_TargetOutcome]:
    """Every target of a full run, in the order the run wrote them."""
    return [
        _TargetOutcome(target="foundation", report=report.foundation),
        _TargetOutcome(target="option-sets", report=report.option_sets),
        _TargetOutcome(target="categories", report=report.categories),
        _TargetOutcome(target="questionnaires", report=report.questionnaires),
        _TargetOutcome(target="examples", report=report.examples),
        _TargetOutcome(target="org-units", report=report.organisation_units),
        _TargetOutcome(target="pages", report=report.pages),
    ]


def _full_run_summary(report: GenerateFullReport) -> str:
    """The closing line of a full run: how much it wrote, across how many targets."""
    outcomes = _full_outcomes(report)
    written = sum(len(outcome.report.written_files) for outcome in outcomes)
    return f"full pipeline: {written:,} file(s) written across {len(outcomes)} target(s)"


#: The basename the notes of one full run are written under, inside the reports directory.
_GENERATE_NOTES_STEM = "fhir-generate-notes"

#: The heading the notes that only restate a `d2w fhir validate` finding are filed under, per target.
_ECHO_SECTION_HEADING = "Restatements of validate findings"


def _plain_notes(outcome: _TargetOutcome) -> list[GenerateNote]:
    """The notes of one target that say something `d2w fhir validate` does not already say better."""
    return [note for note in outcome.report.notes if not note.echoes_validate]


def _echo_notes(outcome: _TargetOutcome) -> list[GenerateNote]:
    """The notes of one target that only restate a finding the validate report carries in full."""
    return [note for note in outcome.report.notes if note.echoes_validate]


def _write_generate_notes(
    outcomes: Iterable[_TargetOutcome], generation: GenerationProfile, project_root: Path
) -> Path:
    """Write every note of one full run to `reports/fhir-generate-notes.md`, grouped by target.

    A target's own notes come first; the ones that only restate a `d2w fhir validate` finding follow
    in a trailing subsection, so the file still holds everything the run raised while reading as what
    generation alone has to say.
    """
    from datetime import UTC, datetime

    from dhis2w_fhir import REPORTS_DIRECTORY

    directory = project_root / REPORTS_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "# fhir generate notes",
        "",
        f"- Profile: {generation.name} ({generation.profile.base_url})",
        f"- Generated: {datetime.now(tz=UTC).isoformat(timespec='seconds')}",
        "",
    ]
    for outcome in outcomes:
        if not outcome.report.notes:
            continue
        lines.append(f"## {outcome.target}")
        lines.append("")
        lines.extend(f"- {note.message}" for note in _plain_notes(outcome))
        lines.append("")
        echoes = _echo_notes(outcome)
        if echoes:
            lines.append(f"### {_ECHO_SECTION_HEADING}")
            lines.append("")
            lines.extend(f"- {note.message}" for note in echoes)
            lines.append("")
    destination = directory / f"{_GENERATE_NOTES_STEM}.md"
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def _generate_notes_hint(outcomes: list[_TargetOutcome], destination: Path) -> str:
    """The one line a bare run carries its notes on: what generation raised, then the validate echoes."""
    plain_targets = [outcome for outcome in outcomes if _plain_notes(outcome)]
    plain_total = sum(len(_plain_notes(outcome)) for outcome in plain_targets)
    echo_total = sum(len(_echo_notes(outcome)) for outcome in outcomes)
    tail = f"; full list in {destination} (--details to print)"
    if not plain_total:
        echo_targets = sum(1 for outcome in outcomes if _echo_notes(outcome))
        return f"{echo_total} validate echo(es) across {echo_targets} target(s){tail}"
    echoes = f" (+{echo_total} validate echoes)" if echo_total else ""
    return f"{plain_total} note(s) across {len(plain_targets)} target(s){echoes}{tail}"


def _render_full_notes(outcomes: list[_TargetOutcome], generation: GenerationProfile, *, details: bool) -> None:
    """Say where the run's notes are, or print them all when the caller asked to read them here.

    A national instance raises several aggregate notes per target, and eight targets of them bury
    the summary table the run is actually read from. The count and the file are what the terminal
    carries; `--details` is the firehose.

    The count is of what generation alone found. A note that only restates a `d2w fhir validate`
    finding - a code fall-back, a code collision, a stem fall-back - is counted separately at the end
    of the line, because the validate report says the same thing about the same objects at length.
    """
    noted = [outcome for outcome in outcomes if outcome.report.notes]
    if not noted:
        return
    if details:
        for outcome in noted:
            for note in outcome.report.notes:
                _hint("note", f"{outcome.target}: {note.message}")
        return
    destination = _write_generate_notes(noted, generation, outcomes[0].report.project_root)
    _hint("note", _generate_notes_hint(noted, destination))


def _render_full_report(report: GenerateFullReport, generation: GenerationProfile, *, details: bool = False) -> None:
    """Render a full run as one row per target, then say where the notes each target raised are."""
    outcomes = _full_outcomes(report)
    _hint("info", f"{generation.name} ({generation.origin}) -> {report.foundation.project_root}")
    render_list(
        "fhir generate",
        [
            {
                "target": outcome.target,
                "directory": _target_label(outcome.report),
                "written": str(len(outcome.report.written_files)),
                "unchanged": str(outcome.report.unchanged_count),
                "deleted": str(len(outcome.report.deleted_files)),
                "notes": str(len(outcome.report.notes)),
            }
            for outcome in outcomes
        ],
        [
            ColumnSpec("Target", "target", no_wrap=True),
            ColumnSpec("Directory", "directory"),
            ColumnSpec("Written", "written", no_wrap=True),
            ColumnSpec("Unchanged", "unchanged", no_wrap=True),
            ColumnSpec("Deleted", "deleted", no_wrap=True),
            ColumnSpec("Notes", "notes", no_wrap=True),
        ],
        console=STDERR_CONSOLE,
    )
    _render_full_notes(outcomes, generation, details=details)


@generate_app.callback(invoke_without_command=True)
def generate_callback(
    ctx: typer.Context,
    details: Annotated[
        bool,
        typer.Option("--details", help="Print every note inline instead of writing them to the notes report."),
    ] = False,
    progress: ProgressOption = True,
) -> None:
    """Generate the whole IG source from DHIS2 metadata, or one named target of it.

    Bare `d2w fhir generate` runs every target off a single pass over the instance.

    The foundation runs first because it reads nothing, the pages last because they narrate the rest.

    Notes land in reports/fhir-generate-notes.md; `--details` prints them here instead.

    Name a target to run that one alone; the flags here belong to the bare run.
    """
    if ctx.invoked_subcommand is not None:
        return
    from dhis2w_fhir import GENERATE_FULL_STEPS, service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    with _progress(GENERATE_FULL_STEPS, enabled=progress) as reporter:
        report = asyncio.run(service.generate_full(generation.profile, project, reporter=reporter))
        if reporter is not None:
            reporter.finish(_full_run_summary(report))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_full_report(report, generation, details=details)


@generate_app.command("foundation")
def generate_foundation_command(progress: ProgressOption = True) -> None:
    """Generate the DHIS2 identifier aliases, the extensions, and the capture contract into the FHIR project."""
    from dhis2w_fhir import GENERATE_FOUNDATION_STEPS, service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    with _progress(GENERATE_FOUNDATION_STEPS, enabled=progress) as reporter:
        report = asyncio.run(service.generate_foundation(project, reporter=reporter))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report(_TARGET_TITLES["foundation"], report, generation)


@generate_app.command("option-sets")
def generate_option_sets_command(progress: ProgressOption = True) -> None:
    """Generate CodeSystem/ValueSet JSON from DHIS2 option sets into the nearest FHIR project."""
    from dhis2w_fhir import GENERATE_TARGET_STEPS, service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    with _progress(GENERATE_TARGET_STEPS, enabled=progress) as reporter:
        report = asyncio.run(service.generate_option_sets(generation.profile, project, reporter=reporter))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report(
        _TARGET_TITLES["option-sets"],
        report,
        generation,
        extra_rows=[DetailRow("option sets", str(report.option_set_count))],
    )


@generate_app.command("categories")
def generate_categories_command(progress: ProgressOption = True) -> None:
    """Generate CodeSystem/ValueSet JSON from DHIS2 categories into the nearest FHIR project."""
    from dhis2w_fhir import GENERATE_TARGET_STEPS, service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    with _progress(GENERATE_TARGET_STEPS, enabled=progress) as reporter:
        report = asyncio.run(service.generate_categories(generation.profile, project, reporter=reporter))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report(
        _TARGET_TITLES["categories"],
        report,
        generation,
        extra_rows=[DetailRow("categories", str(report.category_count))],
    )


@generate_app.command("questionnaires")
def generate_questionnaires_command(progress: ProgressOption = True) -> None:
    """Generate Questionnaire FSH into data-sets/, event-programs/, tracker-programs/, and data-dictionary/.

    A data set and an event program are one Questionnaire each.

    A tracker program is one Questionnaire per program stage, filed under its program's UID.
    """
    from dhis2w_fhir import GENERATE_TARGET_STEPS, service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    with _progress(GENERATE_TARGET_STEPS, enabled=progress) as reporter:
        report = asyncio.run(service.generate_questionnaires(generation.profile, project, reporter=reporter))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report(
        _TARGET_TITLES["questionnaires"],
        report,
        generation,
        extra_rows=[DetailRow("questionnaires", str(report.questionnaire_count))],
    )


@generate_app.command("examples")
def generate_examples_command(progress: ProgressOption = True) -> None:
    """Generate example QuestionnaireResponses for every configured data set, event program, and tracker stage."""
    from dhis2w_fhir import GENERATE_TARGET_STEPS, service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    with _progress(GENERATE_TARGET_STEPS, enabled=progress) as reporter:
        report = asyncio.run(service.generate_examples(generation.profile, project, reporter=reporter))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report(
        _TARGET_TITLES["examples"],
        report,
        generation,
        extra_rows=[DetailRow("examples", str(report.example_count))],
    )


@generate_app.command("org-units")
def generate_organisation_units_command(progress: ProgressOption = True) -> None:
    """Generate Organization/Location FSH from DHIS2 organisation units into the nearest FHIR project."""
    from dhis2w_fhir import GENERATE_TARGET_STEPS, service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    with _progress(GENERATE_TARGET_STEPS, enabled=progress) as reporter:
        report = asyncio.run(service.generate_organisation_units(generation.profile, project, reporter=reporter))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report(
        _TARGET_TITLES["org-units"],
        report,
        generation,
        extra_rows=[
            DetailRow("org units", str(report.organisation_unit_count)),
            DetailRow("positions", str(report.position_count)),
            DetailRow("boundaries", str(report.boundary_count)),
        ],
    )


@generate_app.command("pages")
def generate_pages_command(progress: ProgressOption = True) -> None:
    """Generate the narrative site pages and the per-artifact intros into ig/input/pagecontent/."""
    from dhis2w_fhir import GENERATE_TARGET_STEPS, service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    with _progress(GENERATE_TARGET_STEPS, enabled=progress) as reporter:
        report = asyncio.run(service.generate_pages(generation.profile, project, reporter=reporter))
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report(
        _TARGET_TITLES["pages"],
        report,
        generation,
        extra_rows=[DetailRow("pages", str(report.page_count)), DetailRow("intros", str(report.intro_count))],
    )


@generate_app.command("load-set")
def generate_load_set_command(
    per_target: Annotated[
        int,
        typer.Option(
            "--per-target",
            min=1,
            help="How many synthetic responses each questionnaire target contributes.",
        ),
    ] = DEFAULT_LOAD_SET_PER_TARGET,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            file_okay=False,
            help="Directory to write the `load/` corpus into (default: the project root).",
        ),
    ] = None,
    progress: ProgressOption = True,
) -> None:
    """Write a synthetic QuestionnaireResponse corpus into load/ for posting at a running `d2w fhir serve`.

    A load set is test data, not IG source: it lands beside `ig/` rather than inside it.

    The scaffold gitignores it, and `d2w fhir generate` never writes it.
    """
    from dhis2w_fhir import GENERATE_TARGET_STEPS, service

    project = load_project()
    generation = service.resolve_generation_profile(project)
    with _progress(GENERATE_TARGET_STEPS, enabled=progress) as reporter:
        report = asyncio.run(
            service.generate_load_set(
                generation.profile,
                project,
                per_target=per_target,
                output_directory=output_dir,
                reporter=reporter,
            )
        )
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_generate_report(
        _TARGET_TITLES["load-set"],
        report,
        generation,
        extra_rows=[
            DetailRow("responses", str(report.response_count)),
            DetailRow("questionnaires", str(report.questionnaire_count)),
        ],
    )


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
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            file_okay=False,
            help="Directory to write the report files into, one per format, all named "
            "fhir-validate-report (default: reports/ under the project root, else the working directory).",
        ),
    ] = None,
    formats: Annotated[
        str, typer.Option("--format", help="Comma-separated report formats to write: md, csv, pdf.")
    ] = "md,csv,pdf",
    code_source: Annotated[
        CodeSourceChoice | None,
        typer.Option(
            "--code-source",
            help="Override `\\[generate]` concept_code_source for this run. In id mode the option code "
            "findings are informational; run with code to see what switching would cost.",
        ),
    ] = None,
    details: Annotated[
        bool,
        typer.Option("--details", help="List every finding individually instead of the rolled-up category counts."),
    ] = False,
    fail: Annotated[bool, typer.Option("--fail/--no-fail", help="Exit 1 when errors are found.")] = True,
    progress: ProgressOption = True,
) -> None:
    """Check the instance's codes for FHIR-safety, writing md/csv/pdf reports grouped by type.

    Severity means build impact on the configured IG: an error aborts your build (generate refuses
    the same codes), a warning degrades an emitted resource, and an info is instance hygiene on
    objects the build never reads. Each finding carries that verdict as its scope - `selection`
    for objects the configured selection emits, `instance` for the rest.

    The terminal says what the state is: a summary, a count per severity, scope, and category, and
    every error by name, because an error is what gates the build and the user has to know which
    object holds it. The written report is where a warning is read one row at a time; `--details`
    puts every row on the terminal too.
    """
    from datetime import UTC, datetime

    from dhis2w_fhir import REPORTS_DIRECTORY, VALIDATE_CODES_STEPS, find_project_fhir_config, service
    from dhis2w_fhir.validation.pdf import render_validation_pdf
    from dhis2w_fhir.validation.report import display_code, render_validation_csv, render_validation_markdown
    from dhis2w_fhir.validation.schemas import pluralize

    selected_formats = _parse_report_formats(formats)
    requested_source = code_source.value if code_source is not None else None
    context = service.resolve_validation_context()
    with _progress(VALIDATE_CODES_STEPS, enabled=progress) as reporter:
        report = asyncio.run(
            service.validate_codes(context.generation.profile, context.config, requested_source, reporter=reporter)
        )
    project_config = find_project_fhir_config()
    default_root = project_config.parent if project_config else Path.cwd()
    directory = output_dir or default_root / REPORTS_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    target = f"{context.generation.name} ({context.generation.profile.base_url})"
    generated_at = datetime.now(tz=UTC)
    for report_format in selected_formats:
        destination = directory / f"{_VALIDATION_REPORT_STEM}.{report_format}"
        if report_format == "md":
            destination.write_text(render_validation_markdown(report, target, generated_at), encoding="utf-8")
        elif report_format == "csv":
            destination.write_text(render_validation_csv(report), encoding="utf-8")
        else:
            destination.write_bytes(render_validation_pdf(report, target, generated_at))
        _line(f"wrote {destination}")
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
    else:
        summary_rows = [
            DetailRow("profile", f"{context.generation.name} ({context.generation.origin})"),
            DetailRow("resource types", str(report.resource_type_count)),
            DetailRow("objects swept", str(report.object_count)),
            DetailRow("option sets", str(report.option_set_count)),
            DetailRow("options", str(report.option_count)),
            DetailRow("attributes", str(report.attribute_count)),
            DetailRow("errors", str(report.error_count)),
            DetailRow("warnings", str(report.warning_count)),
            DetailRow("infos", str(report.info_count)),
        ]
        if report.code_coverage is not None:
            summary_rows.extend(
                [
                    DetailRow(
                        "selection findings",
                        f"{pluralize(report.selection_error_count, 'error')}, "
                        f"{pluralize(report.selection_warning_count, 'warning')}, "
                        f"{pluralize(report.selection_info_count, 'info')}",
                    ),
                    DetailRow(
                        "code coverage",
                        f"{report.code_coverage.line} (selection objects whose code can serve as an identity stem)",
                    ),
                ]
            )
        summary_rows.append(DetailRow("code source", service.resolve_code_source(context.config, requested_source)))
        render_detail("fhir validate", summary_rows, console=STDERR_CONSOLE)
        _render_finding_rollup(report)
        listed = [finding for finding in report.findings if details or finding.severity == "error"]
        if listed:
            render_list(
                "findings",
                [
                    {
                        "severity": finding.severity,
                        "scope": _scope_cell(finding.scope),
                        "category": finding.category,
                        "type": finding.resource_type,
                        "object": f"{finding.name} ({finding.uid})",
                        "code": display_code(finding.code),
                        "message": finding.message,
                    }
                    for finding in listed
                ],
                [
                    ColumnSpec("Severity", "severity", formatter=_severity_cell, no_wrap=True),
                    ColumnSpec("Scope", "scope", no_wrap=True),
                    ColumnSpec("Category", "category", no_wrap=True),
                    ColumnSpec("Type", "type", no_wrap=True),
                    ColumnSpec("Object", "object"),
                    ColumnSpec("Code", "code"),
                    ColumnSpec("Why it matters", "message"),
                ],
                console=STDERR_CONSOLE,
            )
        if not report.error_count:
            _hint("ok", f"{_passed_summary(report)}; full findings in {directory / f'{_VALIDATION_REPORT_STEM}.md'}")
    if report.error_count and fail:
        _hint("error", f"{report.error_count} error(s) found; exiting 1 (--no-fail to suppress)", style="red")
        raise typer.Exit(code=1)


#: The severity order the rollup reads in - what blocks a build first, what only reads badly last.
_SEVERITY_ORDER = ("error", "warning", "info")

#: The scope order within one severity - the build path before the instance hygiene.
_SCOPE_ORDER = ("selection", "instance")

#: The style each severity carries in the rollup, so a glance separates a blocker from a note.
_SEVERITY_STYLES = {"error": "red", "warning": "yellow", "info": "dim"}


def _severity_cell(value: Any) -> str:
    """Render one severity in the style it carries, so the blockers read as blockers."""
    severity = str(value)
    return f"[{_SEVERITY_STYLES.get(severity, 'default')}]{severity}[/]"


def _scope_cell(scope: str) -> str:
    """Render one scope: selection full-strength, instance dimmed, so the build path carries the weight."""
    return f"[dim]{scope}[/]" if scope == "instance" else scope


def _instance_dimmed(text: str, scope: str) -> str:
    """Dim one rollup cell on an instance row, so out-of-scope hygiene reads as background."""
    return f"[dim]{text}[/]" if scope == "instance" else text


def _passed_summary(report: FhirValidationReport) -> str:
    """The passing line's counts: split by scope when one was resolved, plain totals otherwise."""
    if report.code_coverage is None:
        return f"passed: {report.warning_count} warning(s), {report.info_count} info(s)"
    instance_count = sum(1 for finding in report.findings if finding.scope == "instance")
    return (
        f"passed: {report.selection_warning_count} selection warning(s), "
        f"{report.selection_info_count} selection info(s), {instance_count} instance finding(s)"
    )


def _render_finding_rollup(report: FhirValidationReport) -> None:
    """Render one row per (severity, scope, category) with its count - the whole report at a glance."""
    counts = Counter((finding.severity, finding.scope, finding.category) for finding in report.findings)
    if not counts:
        return
    ordered = sorted(counts, key=lambda key: (_SEVERITY_ORDER.index(key[0]), _SCOPE_ORDER.index(key[1]), key[2]))
    render_list(
        "findings by category",
        [
            {
                "severity": severity,
                "scope": _scope_cell(scope),
                "category": _instance_dimmed(category, scope),
                "count": _instance_dimmed(str(counts[severity, scope, category]), scope),
            }
            for severity, scope, category in ordered
        ],
        [
            ColumnSpec("Severity", "severity", formatter=_severity_cell, no_wrap=True),
            ColumnSpec("Scope", "scope", no_wrap=True),
            ColumnSpec("Category", "category", no_wrap=True),
            ColumnSpec("Count", "count", no_wrap=True),
        ],
        console=STDERR_CONSOLE,
    )


#: What a caller is told when the serve extra is not installed. `LookupError` renders through the
#: CLI error funnel as a one-line message, which is what an install instruction wants to be.
_SERVE_PACKAGE_MISSING = (
    "`d2w fhir serve` needs the dhis2w-fhir-serve package. Install it with "
    "`uv add dhis2w-fhir-serve` or `pip install 'dhis2w-cli[serve]'`."
)


class PortInUseError(LookupError):
    """A serve address something else already holds, rendered by the CLI error funnel as one line."""

    def __init__(self, *, host: str, port: int) -> None:
        """Carry the refusal naming the port, its usual holder, and both ways to move off it."""
        super().__init__(
            f"port {port} on {host} is already in use "
            "(usually the local DHIS2 instance; set [serve] port in fhir.toml or pass --port)"
        )


def _bind_probe(host: str, port: int) -> None:
    """Bind (host, port) once with SO_REUSEADDR - the option uvicorn sets - and release it."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    probe = socket.socket(family, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, port))
    finally:
        probe.close()


def _address_already_in_use(host: str, port: int) -> bool:
    """Whether binding (host, port) fails with EADDRINUSE right now."""
    try:
        _bind_probe(host, port)
    except OSError as error:
        return error.errno == errno.EADDRINUSE
    return False


def _preflight_bind(host: str, port: int) -> None:
    """Refuse a taken port before anything says the server is starting.

    The probe claims the address once and releases it, so a port held by something else -
    typically 8080, where a local DHIS2 stack lives - fails as one line before the banner
    and before the app's lifespan loads a store. The port can still be taken between this
    probe and uvicorn's own bind; that race is accepted, and `_run_server` renders the same
    one-line refusal when it loses, so the window narrows without reopening the traceback.
    """
    try:
        _bind_probe(host, port)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            raise PortInUseError(host=host, port=port) from error
        raise


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
        str | None,
        typer.Option(
            "--host",
            help="Interface to bind, overriding `[serve] host`. The default is loopback: the facade has "
            "no authentication, so reaching it from another host is a deliberate act.",
        ),
    ] = None,
    port: Annotated[
        int | None, typer.Option("--port", help="Port to listen on, overriding `[serve] port` (default 8080).")
    ] = None,
    strict_codes: Annotated[
        bool | None,
        typer.Option(
            "--strict-codes/--no-strict-codes",
            help="Refuse a received answer whose code is outside the served terminology, overriding "
            "`[serve] strict_codes`. The default records the drift as a warning and stores the "
            "submission, because an option added to the instance since the IG was built is a fact about "
            "the instance, not a client mistake.",
        ),
    ] = None,
) -> None:
    """Serve the project's IG as a FHIR read and capture facade over HTTP.

    Reads answer from what the IG publishes.

    Received QuestionnaireResponses are stored as receipts, so reading one back says what was submitted.

    `--live` builds the store from the instance at startup, as the profile `d2w -p` names.

    Host, port, and strict codes come from `[serve]` in fhir.toml unless a flag overrides them.
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

    from dhis2w_fhir import service

    project = load_project(directory)
    serve_config = project.config.serve
    resolved_host = host if host is not None else serve_config.host
    resolved_port = port if port is not None else serve_config.port
    resolved_strict_codes = strict_codes if strict_codes is not None else serve_config.strict_codes
    if live:
        # Resolve the profile the live store will connect with before anything says the server is
        # starting, so an unknown profile fails as a failure rather than under a success banner.
        service.resolve_generation_profile(project)
    elif not any((project.ig_directory / COMPILED_RESOURCES_RELATIVE_PATH).glob("*.json")):
        raise CompiledIgMissingError
    settings = ServeSettings(project_dir=directory, live=live, profile=None, strict_codes=resolved_strict_codes)
    _preflight_bind(resolved_host, resolved_port)
    configure_logging()
    _line(f"starting {project.project_root} on http://{resolved_host}:{resolved_port} (ctrl-c to stop)")
    _run_server(create_app(settings), host=resolved_host, port=resolved_port)


def _run_server(application: Any, *, host: str, port: int) -> None:
    """Run one built facade under uvicorn until the process is interrupted.

    The server's own logging is switched off - `configure_logging` already put one line per
    request on stderr, and uvicorn's access log would double every one of them.

    A taken port normally fails in `_preflight_bind`, before the banner. When the port is
    taken inside the race window instead, uvicorn refuses it at its own bind - by raising
    the `OSError`, or by logging one line and calling `sys.exit(1)` - and both shapes are
    mapped to the same `PortInUseError` one-liner here, so neither can reach the terminal
    as a traceback. The `SystemExit` mapping re-probes the address first, because exit 1
    is also how uvicorn reports failures that are not about the port.
    """
    import uvicorn

    try:
        uvicorn.run(application, host=host, port=port, log_config=None, access_log=False)
    except KeyboardInterrupt as interrupt:
        raise typer.Exit(0) from interrupt
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            raise PortInUseError(host=host, port=port) from error
        raise
    except SystemExit as system_exit:
        if system_exit.code not in (0, None) and _address_already_in_use(host, port):
            raise PortInUseError(host=host, port=port) from system_exit
        raise


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `d2w fhir`."""
    root_app.add_typer(app, name="fhir", help="FHIR Implementation Guide generation from DHIS2 metadata.")
