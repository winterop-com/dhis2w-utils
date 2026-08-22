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
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from dhis2w_core.cli_errors import CliUserError
from dhis2w_core.cli_output import ColumnSpec, DetailRow, is_json_output, render_detail, render_list
from dhis2w_core.progress import animated_progress, make_reporter
from dhis2w_core.rich_console import STDERR_CONSOLE
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir import (
    DEFAULT_LOAD_SET_PER_TARGET,
    DEFAULT_SUSHI_TIMEOUT_SECONDS,
    MALFORMED_RESPONSES_RELATIVE_PATH,
    CorrectionPosture,
    GenerateReport,
    OverwritePosture,
    ServeAuth,
    ServeAuthScope,
    WithdrawalPosture,
    load_project,
)
from dhis2w_fhir.doctor import DEFAULT_ORACLE_SAMPLES

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from dhis2w_core.progress import ProgressReporter

    # Type-only, exactly as `d2w fhir serve` and `d2w fhir sync` import the package itself: the serve
    # extra may not be installed, and a name used in an annotation costs no import at runtime.
    from dhis2w_fhir_serve import ServeSettings, SyncReport

    from dhis2w_fhir.config import FhirProject, ProjectionConfig
    from dhis2w_fhir.doctor import DoctorReport
    from dhis2w_fhir.notes import GenerateNote
    from dhis2w_fhir.service import (
        ForwardOutcome,
        ForwardReport,
        GenerateFullReport,
        GenerationProfile,
        LoadSetReport,
        SpoolStateReport,
        WithdrawReport,
    )
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
            DetailRow("with your additions", str(len(report.extended_files))),
            DetailRow("diverged (kept)", str(len(report.diverged_files))),
        ],
        console=STDERR_CONSOLE,
    )
    for relative_path in report.created_files:
        _line(f"  created {relative_path}")
    for relative_path in report.refreshed_files:
        _line(f"  refreshed {relative_path}")
    for relative_path in report.unchanged_files:
        _line(f"  unchanged {relative_path}")
    for relative_path in report.extended_files:
        _line(f"  kept {relative_path} (already carries the current scaffold, plus lines of your own)")
    for relative_path in report.diverged_files:
        _line(f"  kept {relative_path} (holds lines the current scaffold does not write)")
    _hint("note", f"{FHIR_CONFIG_FILENAME} is yours - a refresh never writes it")
    if report.diverged_files:
        _hint(
            "note",
            "a diverged file holds your edits, or scaffold lines that have since changed - this refresh "
            "cannot tell which. To take the scaffold's version, delete the file and refresh again; lines "
            "of your own in it go with it.",
        )


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

    Each note appears once, under the first target that raised it - the outcomes arrive on the
    run's distinct-notes view. A target's own notes come first; the ones that only restate a
    `d2w fhir validate` finding follow in a trailing subsection, so the file still holds
    everything the run raised while reading as what generation alone has to say.
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
    """Render a full run as one row per target, then say where the notes the run raised are.

    Rendering reads the distinct-notes view of the run, so a note several targets share is
    counted and printed once, on the first target that raised it; the `--json` dump keeps the
    full per-target lists, which read exactly as the solo commands' do.
    """
    outcomes = _full_outcomes(report.with_distinct_notes())
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

    A form whose DHIS2 organisation-unit assignment narrows the published registry also gets one
    List of the Locations it admits, into resources/assignments/.
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
        extra_rows=[
            DetailRow("questionnaires", str(report.questionnaire_count)),
            DetailRow("assignments", str(report.assignment_count)),
        ],
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
    salt: Annotated[
        str,
        typer.Option(
            "--salt",
            help="Mint a different corpus from the same metadata - name any string to move every drawn value.",
        ),
    ] = "",
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

    A corpus mints the DHIS2 identities it names, so it imports once: DHIS2 refuses a second import
    of the same corpus with E1002 and E1080 because those UIDs already exist. Pass `--salt` to mint
    a fresh corpus for a second import; the same salt reproduces the same corpus.
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
                salt=salt,
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
    from dhis2w_fhir.notes import pluralize
    from dhis2w_fhir.validation.pdf import render_validation_pdf
    from dhis2w_fhir.validation.report import display_code, render_validation_csv, render_validation_markdown

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


#: How many characters of an offending value the terminal carries before it is cut. A DHIS2 name is
#: short; a narrative-bound string is not, and one runaway row must not push the remedy off screen.
_ARTIFACT_VALUE_WIDTH = 60


@app.command("check-artifacts")
def check_artifacts_command(
    directory: Annotated[
        Path | None,
        typer.Argument(
            file_okay=False,
            help="Project to scan (default: the nearest fhir.toml, walking up from the working directory).",
        ),
    ] = None,
    fail: Annotated[bool, typer.Option("--fail/--no-fail", help="Exit 1 when findings are found.")] = True,
) -> None:
    """Refuse the build before it begins: scan the artifacts on disk for what aborts the IG publisher.

    `d2w fhir generate` refuses a run whose selected DHIS2 names or codes carry a `<`. A build reads
    no such gate - it publishes whatever `ig/fsh-generated/` and `ig/input/` hold - so output written
    before the gate existed, output from an older pinned toolchain, and hand-authored FSH all reach
    the publisher, and cost its full run before failing in its final pass.

    This is that refusal applied to the files themselves, through the very predicates the generate
    gate uses. It names the file, the resource, the element, and the value, so what comes back is the
    object rather than the page the publisher happened to die on.

    No connection, no profile, no compile - the artifacts are the whole input, so it answers in
    seconds. Exit 1 when anything is found, which is what `make build` runs it for.
    """
    from dhis2w_fhir.validation.artifacts import check_publishable_artifacts

    project = load_project(directory)
    report = check_publishable_artifacts(project)
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        if report.finding_count and fail:
            raise typer.Exit(code=1)
        return
    render_detail(
        "fhir check-artifacts",
        [
            DetailRow("project", str(project.project_root)),
            DetailRow("json files", str(report.json_file_count)),
            DetailRow("fsh files", str(report.fsh_file_count)),
            DetailRow("findings", str(report.finding_count)),
        ],
        console=STDERR_CONSOLE,
    )
    for unreadable in report.unreadable_files:
        _hint("note", f"{unreadable} is not readable as a JSON object; nothing in it was checked")
    if report.findings:
        render_list(
            "build-aborting artifacts",
            [
                {
                    "file": finding.file,
                    "resource": finding.resource_id,
                    "field": finding.field,
                    "value": _truncate(finding.value, _ARTIFACT_VALUE_WIDTH),
                    "remedy": finding.remedy,
                }
                for finding in report.findings
            ],
            [
                ColumnSpec("File", "file"),
                ColumnSpec("Resource", "resource", no_wrap=True),
                ColumnSpec("Field", "field", no_wrap=True),
                ColumnSpec("Value", "value"),
                ColumnSpec("What to do", "remedy"),
            ],
            console=STDERR_CONSOLE,
        )
        for message in report.messages:
            _hint("note", f"what it costs: {message}")
    else:
        _hint("ok", f"{report.file_count} publishable file(s) scanned; nothing the IG publisher aborts on")
    if report.finding_count and fail:
        _hint(
            "error",
            f"{report.finding_count} build-aborting artifact(s) found; exiting 1 before the publisher runs "
            "(--no-fail to suppress)",
            style="red",
        )
        raise typer.Exit(code=1)


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


#: The wildcard of each IP stack, probed for every host. A server published to all interfaces -
#: which is what a Docker port mapping does, and how the local DHIS2 stack holds 8080 - listens on
#: one of these, and SO_REUSEADDR then lets a *loopback-specific* bind succeed underneath it. So a
#: probe of `127.0.0.1` alone reports a held port as free, uvicorn binds it just as happily, and
#: this server quietly takes the localhost traffic meant for the instance. Only the wildcard bind
#: collides with the wildcard listener, which is what makes the port's real holder visible.
_WILDCARD_ADDRESSES = (
    (socket.AF_INET, "0.0.0.0"),  # noqa: S104 - probed and released, never an address this serves on
    (socket.AF_INET6, "::"),
)

#: The other stack's loopback, for a host naming one. A listener can hold `::1` alone while nothing
#: holds `127.0.0.1`, and a browser asking this machine for `localhost` may still be routed to it.
_SIBLING_LOOPBACK_ADDRESSES = {
    "127.0.0.1": (socket.AF_INET6, "::1"),
    "::1": (socket.AF_INET, "127.0.0.1"),
    "localhost": (socket.AF_INET6, "::1"),
}

#: Bind failures that say this machine cannot offer the address at all - no IPv6 stack, or an
#: address belonging to some other host. Neither is the port being held by anything, so neither
#: refuses a run.
_ADDRESS_UNAVAILABLE_ERRNOS = frozenset({errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT})


def _probe_addresses(host: str, port: int) -> list[tuple[int, str]]:
    """Every (family, address) whose holder would contend for `host:port`, deduped in probe order."""
    candidates: list[tuple[int, str]] = []
    try:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        # An unresolvable host is uvicorn's failure to report, not the preflight's: probe the
        # literal it was given and let the bind say what is wrong with it.
        resolved = []
    for family, _type, _protocol, _canonical_name, address in resolved:
        if family in (socket.AF_INET, socket.AF_INET6):
            candidates.append((family, str(address[0])))
    if not candidates:
        candidates.append((socket.AF_INET6 if ":" in host else socket.AF_INET, host))
    sibling = _SIBLING_LOOPBACK_ADDRESSES.get(host)
    if sibling is not None:
        candidates.append(sibling)
    candidates.extend(_WILDCARD_ADDRESSES)
    return list(dict.fromkeys(candidates))


def _bind_probe(host: str, port: int) -> None:
    """Bind the port on every address whose holder would contend for it, and release each one.

    SO_REUSEADDR is set because uvicorn sets it, so the probe fails exactly where uvicorn's own
    bind would - except for the case that option creates: a specific address binds happily under
    a wildcard listener, so the wildcards are probed too and a port already spoken for on this
    machine is refused rather than quietly shared. An address this machine cannot offer is
    skipped rather than raised: a host with no IPv6 stack has no IPv6 listener either, so its
    absence says nothing about whether the port is free.
    """
    for family, address in _probe_addresses(host, port):
        probe = socket.socket(family, socket.SOCK_STREAM)
        try:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((address, port))
        except OSError as error:
            if error.errno in _ADDRESS_UNAVAILABLE_ERRNOS:
                continue
            raise
        finally:
            probe.close()


def _address_already_in_use(host: str, port: int) -> bool:
    """Whether binding (host, port) fails with EADDRINUSE on either stack right now."""
    try:
        _bind_probe(host, port)
    except OSError as error:
        return error.errno == errno.EADDRINUSE
    return False


def _preflight_bind(host: str, port: int) -> None:
    """Refuse a taken port before anything says the server is starting.

    The probe claims the address on every stack the host names and releases it, so a port held
    by something else - typically 8080, where a local DHIS2 stack lives - fails as one line
    before the banner and before the app's lifespan loads a store. A holder on either stack
    refuses the run, because a browser asking this machine for that port may be routed to
    either one. The port can still be taken between this probe and uvicorn's own bind; that
    race is accepted, and `_run_server` renders the same one-line refusal when it loses, so
    the window narrows without reopening the traceback.
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
            "compiled IG off disk. The store is a snapshot of the instance the server started against, "
            "and the one client that built it stays open for the life of the process, because the "
            "register routes read the instance per request.",
        ),
    ] = False,
    host: Annotated[
        str | None,
        typer.Option(
            "--host",
            help="Interface to bind, overriding `\\[serve] host`. The default is loopback. Binding "
            "anything else while neither --auth nor `\\[serve] auth` states a posture is refused: who "
            "reaches this facade and who it answers are one decision.",
        ),
    ] = None,
    port: Annotated[
        int | None, typer.Option("--port", help="Port to listen on, overriding `\\[serve] port` (default 8080).")
    ] = None,
    auth: Annotated[
        ServeAuth | None,
        typer.Option(
            "--auth",
            help="Who this facade serves, overriding `\\[serve] auth`. `none` serves every caller; "
            "`token` takes a static bearer token out of D2W_FHIR_SERVE_TOKENS; `dhis2` takes the "
            "caller's own DHIS2 credentials and checks them against the instance this run reads, "
            "which needs --live; `jwt` takes a token from the OpenID Connect issuer named in "
            "`\\[serve.jwt] issuer`, verified against that issuer's published keys. Binding an "
            "interface other than loopback while neither this flag nor fhir.toml states a posture "
            "is refused.",
        ),
    ] = None,
    auth_scope: Annotated[
        ServeAuthScope | None,
        typer.Option(
            "--auth-scope",
            help="How much of the surface the posture covers, overriding `\\[serve] auth_scope`. "
            "`write` asks for credentials on `POST /QuestionnaireResponse` and leaves every read "
            "open; `all` asks for them everywhere except `/metadata`, which stays open so a client "
            "can read the posture it has to meet.",
        ),
    ] = None,
    strict_codes: Annotated[
        bool | None,
        typer.Option(
            "--strict-codes/--no-strict-codes",
            help="Refuse a received answer whose code is outside the served terminology, overriding "
            "`\\[serve] strict_codes`. The default records the drift as a warning and stores the "
            "submission, because an option added to the instance since the IG was built is a fact about "
            "the instance, not a client mistake.",
        ),
    ] = None,
    ui: Annotated[
        bool | None,
        typer.Option(
            "--ui/--no-ui",
            help="Serve the capture UI at `/` alongside the FHIR routes, overriding `\\[serve] ui`. "
            "The bundle is mounted around them and shadows none of them; a checkout that has never "
            "run `make build-frontend` is refused rather than served blank.",
        ),
    ] = None,
    basemap: Annotated[
        list[str] | None,
        typer.Option(
            "--basemap",
            help="Raster tile layer the capture UI's organisation-unit map offers under the "
            "boundaries, overriding `\\[serve.basemaps]` (default: OpenStreetMap's standard tiles). "
            "Repeat it to offer several: `Name=https://.../{z}/{x}/{y}.png`, or a bare template "
            "named after its host. The map's layer control always carries a None entry beside them, "
            "and `--basemap none` offers nothing else - which is what an air-gapped deployment "
            "wants, the tiles being the only thing in the UI that reaches an origin other than "
            "this server.",
        ),
    ] = None,
) -> None:
    r"""Serve the project's IG as a FHIR read and capture facade over HTTP.

    Reads answer from what the IG publishes.

    Received QuestionnaireResponses are stored as receipts, so reading one back says what was submitted.

    `--live` builds the store from the instance at startup, as the profile `d2w -p` names.

    `--ui` also serves the capture UI at `/`, same-origin with the FHIR routes it reads.

    `--basemap` offers another tile layer on the organisation-unit map, and `--basemap none` offers none.

    `--auth` says who is served: `none`, `token` (D2W_FHIR_SERVE_TOKENS), `dhis2` (the caller's own
    credentials), or `jwt` (a token from the OpenID Connect issuer named in `\[serve.jwt] issuer`,
    verified against that issuer's published keys).

    Host, port, authentication, strict codes, the UI, and basemaps come from `\[serve]` unless a flag beats them.

    Two more `\[serve]` keys have no flag: `capture = false` serves the guide and receives nothing, and
    `spool_dir` says where the receipts live - the same directory `d2w fhir forward` drains.
    """
    try:
        from dhis2w_fhir_serve import ServeAuthConfigurationError, ServeSettings, configure_logging, create_app
    except ImportError as error:
        raise LookupError(_SERVE_PACKAGE_MISSING) from error

    project = load_project(directory)
    # The precedence, the profile, and the preflight on the compiled guide belong to
    # `ServeSettings.resolve`, in `dhis2w-fhir-serve`, so an embedded facade asks for the posture
    # this command has by name and the two cannot disagree about what a flag beats or when an
    # unknown profile refuses a run. The one `ValueError` it raises is a `--basemap` value that
    # names nothing servable, which is this command's to render against the flag it came from.
    try:
        invocation = ServeSettings.resolve(
            project,
            live=live,
            host=host,
            port=port,
            strict_codes=strict_codes,
            ui=ui,
            basemaps=basemap,
            auth=auth,
            auth_scope=auth_scope,
        )
    except ServeAuthConfigurationError as error:
        raise typer.BadParameter(str(error), param_hint="--auth") from error
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="--basemap") from error
    settings = invocation.settings
    generation = invocation.generation
    _preflight_bind(invocation.host, invocation.port)
    configure_logging()
    # The app is built before the banner so a missing UI bundle refuses as one line here, the way
    # a taken port does, rather than under a message saying the server is starting.
    application = create_app(settings)
    surface = _serve_surface(capture=settings.capture, ui=settings.ui)
    _line(
        f"starting {project.project_root} on http://{invocation.host}:{invocation.port} as a {surface} (ctrl-c to stop)"
    )
    if settings.ui:
        _hint(
            "links",
            f"the screens link identities into {generation.profile.base_url} ({generation.name}, "
            f"from {generation.origin})"
            if generation is not None
            else "no profile resolved, so the screens link no identity to a DHIS2 instance",
        )
    _run_server(application, host=invocation.host, port=invocation.port)


def _serve_surface(*, capture: bool, ui: bool) -> str:
    """What one run is, as the starting line names it: what it serves, and whether it receives.

    A run that receives nothing says so on the line that starts it, because every other sign of it
    is a refusal somebody meets later - a 405 on a submission, a Submit the screens will not offer.
    """
    surface = ("FHIR endpoint + capture UI" if capture else "FHIR endpoint + screens") if ui else "FHIR endpoint"
    return surface if capture else f"{surface}, receiving no submissions"


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


#: The basename the per-response outcomes of one forward run are written under, inside the reports directory.
_FORWARD_REPORT_STEM = "fhir-forward-report"

#: The banner a dry run opens and closes with. It says the mode, what it did instead, and how to commit -
#: a run that reads as an import and was not one is the single worst thing this command could do.
_DRY_RUN_BANNER = (
    "DRY RUN - every payload was posted to DHIS2 under its own validate-only mode "
    "(dataValueSets dryRun=true, tracker importMode=VALIDATE). Nothing was written to the instance and "
    "no receipt moved. Re-run with --import to commit."
)

#: The Rich style each outcome kind renders in, so a glance separates what landed from what did not.
_OUTCOME_STYLES = {
    "accepted": "green",
    "rejected": "red",
    "refused": "yellow",
    "unverifiable": "cyan",
    "not-posted": "yellow",
}


def _outcome_cell(value: Any) -> str:
    """Render one outcome kind in the style it carries."""
    kind = str(value)
    return f"[{_OUTCOME_STYLES.get(kind, 'default')}]{kind}[/]"


#: How many of a rejection's reasons the terminal cell shows before it counts the rest. DHIS2 names one
#: row per broken rule, and a response breaking six of them would otherwise own the whole table width.
_TERMINAL_REASON_SAMPLE = 1

#: How many of a rejection's reasons the written report lists per response before it counts the rest.
_REPORT_REASON_SAMPLE = 5

#: The width one reason is truncated to in the terminal cell. The outcomes table has six columns, so
#: what a cell may claim is what the other five leave: a reason wide enough to squeeze a neighbour to
#: nothing costs more than it carries, and the written report is where a whole reason is read.
_REASON_CELL_WIDTH = 60

#: The width one spool path is truncated to in the terminal cell, for the same reason. A path is
#: truncated from its front rather than its end, because the receipt's own file name is the half that
#: says which response the row is - and the directory above it repeats what the Outcome column states.
_SPOOL_CELL_WIDTH = 30


def _truncate(text: str, width: int) -> str:
    """One reason cut to the width a table cell has for it, with the cut marked rather than hidden."""
    return text if len(text) <= width else f"{text[: width - 1]}..."


def _truncate_path(path: str, width: int) -> str:
    """One path cut to the width a table cell has for it, keeping the end - which is what names the file."""
    return path if len(path) <= width else f"...{path[-(width - 3) :]}"


def _outcome_reasons(outcome: ForwardOutcome, sample: int, width: int | None = None) -> str:
    """Why this response ended where it did: DHIS2's rows for a rejection, the translator's for a refusal.

    A rejection that DHIS2 named no row for still says something - the message off the envelope - because
    "rejected" with nothing beside it is the one thing a reader cannot act on. A response refused as an
    overwrite reads its covered values, which are the whole of why it stayed in the queue.
    """
    if outcome.overwrite_refused:
        lines = [value.line for value in outcome.overwritten_values]
    elif outcome.refusals:
        lines = [f"{refusal.category}: {refusal.reason}" for refusal in outcome.refusals]
    else:
        imported = outcome.import_outcome
        if imported is None:
            return ""
        lines = [issue.line for issue in imported.issues]
        if not lines:
            lines = [imported.message] if imported.message else []
        if not lines:
            return imported.counts_line
    shown = [_truncate(line, width) if width else line for line in lines[:sample]]
    remaining = len(lines) - len(shown)
    return "; ".join(shown) + (f" (+{remaining} more)" if remaining else "")


def _render_rejection_reasons(report: ForwardReport) -> None:
    """Roll every rejection up by cause, so two hundred of them read as the handful of rules they broke."""
    reasons = report.rejection_reasons
    if not reasons:
        return
    render_list(
        "rejection reasons",
        [
            {
                "code": reason.error_code or "",
                "reason": reason.reason,
                "responses": str(reason.responses),
            }
            for reason in reasons
        ],
        [
            ColumnSpec("Code", "code", no_wrap=True),
            ColumnSpec("What DHIS2 said", "reason"),
            ColumnSpec("Responses", "responses", no_wrap=True),
        ],
        console=STDERR_CONSOLE,
    )


def _render_unverifiable_reasons(report: ForwardReport) -> None:
    """State what this dry run could not check and why, so nobody reads it as data DHIS2 turned down."""
    reasons = report.unverifiable_reasons
    if not reasons:
        return
    render_list(
        "unverifiable",
        [{"reason": reason.reason, "responses": str(reason.responses)} for reason in reasons],
        [
            ColumnSpec("What a dry run cannot check", "reason"),
            ColumnSpec("Responses", "responses", no_wrap=True),
        ],
        console=STDERR_CONSOLE,
    )


#: The Rich style each completeness outcome renders in, matching the outcome palette a row above it.
_COMPLETENESS_STYLES = {
    "registered": "green",
    "would-register": "cyan",
    "not-claimed": "dim",
    "not-registered": "dim",
    "refused": "red",
}


def _completeness_cell(value: Any) -> str:
    """Render one completeness outcome kind in the style it carries."""
    kind = str(value)
    return f"[{_COMPLETENESS_STYLES.get(kind, 'default')}]{kind}[/]"


def _render_completeness(report: ForwardReport) -> None:
    """State what every aggregate response of the run claimed about completeness, and what came of it."""
    from dhis2w_fhir.service import ForwardCompletenessKind

    outcomes = report.completeness_outcomes
    if not outcomes:
        return
    render_list(
        "data set completeness",
        [
            {
                "outcome": outcome.kind,
                "tuple": outcome.tuple_line,
                "date": outcome.date or "",
                "reason": outcome.reason if outcome.kind == ForwardCompletenessKind.REFUSED else "",
            }
            for outcome in outcomes
        ],
        [
            ColumnSpec("Completeness", "outcome", formatter=_completeness_cell, no_wrap=True),
            ColumnSpec("Data set / period / organisation unit / attribute option combo", "tuple"),
            ColumnSpec("Completed on", "date", no_wrap=True),
            ColumnSpec("Why", "reason"),
        ],
        console=STDERR_CONSOLE,
    )


def _render_overwritten_values(report: ForwardReport) -> None:
    """Name every value the run met that an earlier submission had already sent, and which one sent it."""
    overwrites = report.overwrites
    if not overwrites:
        return
    render_list(
        "values a previous submission already sent",
        [
            {
                "response": overwrite.response_id,
                "value": value.cell.line,
                "previous": value.previous_response_id,
                "received": value.previous_received_at,
            }
            for overwrite in overwrites
            for value in overwrite.values
        ],
        [
            ColumnSpec("Response", "response"),
            ColumnSpec(
                "Data element / category option combo / period / organisation unit / attribute option combo", "value"
            ),
            ColumnSpec("Sent before by", "previous"),
            ColumnSpec("Received", "received", no_wrap=True),
        ],
        console=STDERR_CONSOLE,
    )


def _render_forward_outcomes(report: ForwardReport) -> None:
    """List every response the run drained, with what became of it and why."""
    if not report.outcomes:
        return
    render_list(
        "responses",
        [
            {
                "response": outcome.response_id,
                "target": outcome.target_kind or "",
                "outcome": outcome.kind,
                "notes": str(len(outcome.notes)),
                "reason": _outcome_reasons(outcome, _TERMINAL_REASON_SAMPLE, _REASON_CELL_WIDTH),
                "spool": _truncate_path(outcome.spool_path, _SPOOL_CELL_WIDTH),
            }
            for outcome in report.outcomes
        ],
        [
            # A receipt id is thirty-two characters and every row carries one, so holding it on a
            # single line claims most of an eighty-column fall-back and leaves the two columns that
            # explain the row a character apiece. It folds; the four short columns do not.
            ColumnSpec("Response", "response"),
            ColumnSpec("Target", "target", no_wrap=True),
            ColumnSpec("Outcome", "outcome", formatter=_outcome_cell, no_wrap=True),
            ColumnSpec("Notes", "notes", no_wrap=True),
            ColumnSpec("Why", "reason"),
            ColumnSpec("Spool", "spool"),
        ],
        console=STDERR_CONSOLE,
    )


def _completeness_report_lines(report: ForwardReport) -> list[str]:
    """The written report's completeness section: the tuple every aggregate response claimed, and its answer."""
    from dhis2w_fhir.service import ForwardCompletenessKind

    outcomes = report.completeness_outcomes
    if not outcomes:
        return []
    lines = [
        "## Data set completeness",
        "",
        "An aggregate response whose status is `completed` registers the data set complete for the",
        "tuple its values landed under. The registration is a second write, made only once DHIS2 has",
        "taken the values; a response reporting itself `in-progress` imports its values and claims",
        "nothing. A refused registration does not un-import the values - they are imported and stay",
        "imported, and forwarding the same tuple again registers it.",
        "",
        "| Completeness | Data set | Period | Organisation unit | Attribute option combo | Completed on | Why |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {outcome.kind} | {outcome.data_set or ''} | {outcome.period or ''} | "
        f"{outcome.organisation_unit or ''} | {outcome.attribute_option_combo or ''} | {outcome.date or ''} | "
        f"{outcome.reason if outcome.kind == ForwardCompletenessKind.REFUSED else ''} |"
        for outcome in outcomes
    )
    lines.append("")
    reason = report.completeness_dry_run_reason
    if reason:
        lines.extend([reason, ""])
    return lines


#: What the written report says about the values an import replaced, above the table naming them. The
#: fact a reader needs first is that DHIS2 counted the write the same way it counts a first entry, so
#: this section is the only place the run can state which is which.
_OVERWRITE_IMPORT_PREAMBLE = (
    "Each value below was sent to DHIS2 by a receipt this spool has already forwarded, and this run",
    "sent it again. The instance now holds the number this run's response carried.",
    "",
    "DHIS2 keeps the newest number for a value and counts writing it exactly as it counts a first",
    "entry, so no import summary separates a correction from a first entry, and this run states it",
    "here instead.",
)

#: The same section on a dry run, where nothing has been written and the whole point is that there is
#: still time to act on it.
_OVERWRITE_DRY_RUN_PREAMBLE = (
    "Each value below was sent to DHIS2 by a receipt this spool has already forwarded, and this run",
    "would send it again. Nothing has changed in the instance: this run wrote nothing.",
    "",
    "An import replaces each number below with the one this run's response carries. DHIS2 counts that",
    "write exactly as it counts a first entry, so no import summary would separate the two afterwards.",
)

#: The same section under `[forward] overwrites = "refuse"`, where the values below are what the run
#: refused over rather than what it replaced. The response is what is refused, never the value: a
#: payload posted in part would tear one submission across two postures.
_OVERWRITE_REFUSED_PREAMBLE = (
    "Each value below was sent to DHIS2 by a receipt this spool has already forwarded, and this run",
    'carries it again. `[forward] overwrites = "refuse"` is set, so none of it was sent: a response',
    "holding any of these values is refused whole and stays in `.serve/responses/received/`.",
    "",
    "Nothing in the instance changed, and nothing about these responses is decided. `overwrites =",
    '"allow"` - or `--overwrites allow` for one run - posts them and names each replaced value',
    "instead.",
)


def _overwrite_preamble(report: ForwardReport) -> tuple[str, ...]:
    """Which of the three things the written report's overwrite section is about, for this run's posture."""
    if report.overwrite_posture is OverwritePosture.REFUSE:
        return _OVERWRITE_REFUSED_PREAMBLE
    return _OVERWRITE_DRY_RUN_PREAMBLE if report.dry_run else _OVERWRITE_IMPORT_PREAMBLE


def _overwritten_value_report_lines(report: ForwardReport) -> list[str]:
    """The written report's section for the values this run sent that an earlier submission had sent."""
    overwrites = report.overwrites
    if not overwrites and not report.forwarded_without_values:
        return []
    lines = ["## Values a previous submission already sent", ""]
    if overwrites:
        lines.extend(
            [
                *_overwrite_preamble(report),
                "",
                "The earlier receipt is named so the submission it came from can be read: it is",
                "`.serve/responses/forwarded/<id>.json`, with what DHIS2 did with it in `<id>.report.json`",
                "beside it.",
                "",
                "| Response | Data element | Category option combo | Period | Organisation unit "
                "| Attribute option combo | Sent before by | Received |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| {overwrite.response_id} | {value.cell.data_element} | {value.cell.category_option_combo or ''} | "
            f"{value.cell.period or ''} | {value.cell.organisation_unit or ''} | "
            f"{value.cell.attribute_option_combo or ''} | {value.previous_response_id} | "
            f"{value.previous_received_at} |"
            for overwrite in overwrites
            for value in overwrite.values
        )
        lines.append("")
    if report.forwarded_without_values:
        lines.extend(
            [
                f"{report.forwarded_without_values} receipt(s) DHIS2 has already accepted record no values, so "
                "this run cannot say whether any of them sent these values first. Every receipt a drain files "
                "records what it sent, so a receipt that records nothing is one something else put in "
                "`.serve/responses/forwarded/`.",
                "",
            ]
        )
    return lines


def _write_forward_report(report: ForwardReport, generation: GenerationProfile) -> Path:
    """Write every response's outcome to `reports/fhir-forward-report.md`, grouped by what became of it."""
    from datetime import UTC, datetime

    from dhis2w_fhir import REPORTS_DIRECTORY

    directory = report.project_root / REPORTS_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "# fhir forward report",
        "",
        f"- Profile: {generation.name} ({generation.profile.base_url})",
        f"- Mode: {'dry run (validate only)' if report.dry_run else 'import'}",
        f"- Coded answers: {report.coded_answer_mode}",
        f"- Data set completeness: {report.completeness_line or 'no aggregate response claimed any'}",
        f"- Values a previous submission already sent: {report.overwrite_line or 'none'}",
        f"- Overwrites: {report.overwrite_posture}",
        f"- Forwarded: {datetime.now(tz=UTC).isoformat(timespec='seconds')}",
        f"- Counts: {report.counts_line}",
        "",
    ]
    if report.stopped is not None:
        lines.extend(
            [
                "## The drain stopped early",
                "",
                f"It stopped at `{report.stopped.response_id}`: {report.stopped.reason}",
                "",
                f"{len(report.not_posted)} response(s) were never posted. They are untouched in the queue, "
                "as is the receipt that met the failure, so forwarding again once the instance is healthy "
                "is the retry.",
                "",
            ]
        )
    if report.quarantined:
        lines.extend(
            [
                "## Files that do not read as receipts",
                "",
                "Each was moved to `.serve/responses/malformed/` with its reason written beside it, and this",
                "run carried on with everything else. Nothing in that directory is a receipt.",
                "",
                "| File | What stopped it |",
                "| --- | --- |",
            ]
        )
        lines.extend(f"| `{entry.file_name}` | {entry.reason} |" for entry in report.quarantined)
        lines.append("")
    if report.filing_issues:
        lines.extend(
            [
                "## Receipts whose file had already moved",
                "",
                "DHIS2 answered about each of these, and the answer is in this report - but the file was gone",
                "when the run went to file it, so it is wherever whatever moved it put it.",
                "",
            ]
        )
        lines.extend(f"- `{issue.response_id}` - {issue.reason}" for issue in report.filing_issues)
        lines.append("")
    reasons = report.rejection_reasons
    if reasons:
        lines.extend(
            [
                "## Rejection reasons",
                "",
                "Every rejection of this run rolled up by cause, commonest first. A response counts once",
                "per distinct cause it met, and the identifiers DHIS2 quotes in a message are generalised",
                "away, so one broken rule reads as one row however many responses met it.",
                "",
                "| Responses | Code | What DHIS2 said |",
                "| --- | --- | --- |",
            ]
        )
        lines.extend(f"| {reason.responses} | {reason.error_code or ''} | {reason.reason} |" for reason in reasons)
        lines.append("")
    unverifiable_reasons = report.unverifiable_reasons
    if unverifiable_reasons:
        lines.extend(["## What a dry run could not check", ""])
        for reason in unverifiable_reasons:
            lines.extend([f"{reason.reason} ({reason.responses} response(s))", ""])
    lines.extend(_overwritten_value_report_lines(report))
    lines.extend(_completeness_report_lines(report))
    for heading, outcomes in (
        ("Rejected by DHIS2", report.rejected),
        ("Unverifiable in a dry run", report.unverifiable),
        ("Refused by the translator", report.translator_refused),
        ("Refused as an overwrite", report.overwrite_refused),
        ("Not yet sent to DHIS2", report.not_posted),
        ("Accepted", report.accepted),
    ):
        if not outcomes:
            continue
        lines.extend([f"## {heading}", ""])
        for outcome in outcomes:
            target = outcome.target_kind or "no payload"
            lines.append(
                f"- `{outcome.response_id}` ({outcome.questionnaire or 'no form'}) - {target} - {outcome.spool_path}"
            )
            if outcome.submitted_by:
                lines.append(f"    - captured by {outcome.submitted_by}")
            imported = outcome.import_outcome
            if imported is not None and imported.issues:
                lines.extend(f"    - {issue.line}" for issue in imported.issues[:_REPORT_REASON_SAMPLE])
                remaining = len(imported.issues) - _REPORT_REASON_SAMPLE
                if remaining > 0:
                    lines.append(f"    - (+{remaining} more reason(s))")
            else:
                detail = _outcome_reasons(outcome, _REPORT_REASON_SAMPLE)
                if detail:
                    lines.append(f"    - {detail}")
            lines.extend(f"    - note: {note.category}: {note.message}" for note in outcome.notes)
        lines.append("")
    destination = directory / f"{_FORWARD_REPORT_STEM}.md"
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def _render_overwrite_hints(report: ForwardReport) -> None:
    """State that this run met values an earlier submission had sent, which DHIS2's own answer cannot."""
    overwrites = report.overwrites
    if overwrites and report.overwrite_posture is OverwritePosture.REFUSE:
        refused = len(report.overwrite_refused)
        values = report.overwritten_value_count
        _hint(
            "note",
            f"{refused} response(s) were not sent: each carries {values} value(s) in all that a receipt this "
            "spool has already forwarded sent, and `[forward] overwrites` is `refuse`. They are still in the "
            "queue"
            + (
                ", each with the covered values written down beside it, and `--overwrites allow` posts them"
                if not report.dry_run
                else " - this run wrote nothing at all, and `--overwrites allow` posts them"
            ),
            style="yellow",
        )
    elif overwrites:
        values = report.overwritten_value_count
        _hint(
            "note",
            (
                f"{len(overwrites)} response(s) sent {values} value(s) an earlier submission had already sent, "
                "and the instance now holds the numbers these responses carried. DHIS2 counts that write "
                "exactly as it counts a first entry, so nothing in the import summary says it happened - the "
                "report names each value and the receipt that sent it before"
                if not report.dry_run
                else f"{len(overwrites)} response(s) carry {values} value(s) an earlier submission has already "
                "sent. Nothing has changed in the instance yet, and an import replaces those numbers with the "
                "ones these responses carry - the report names each value and the receipt that sent it before"
            ),
            style="yellow",
        )
    if report.forwarded_without_values:
        _hint(
            "note",
            f"{report.forwarded_without_values} receipt(s) DHIS2 has already accepted record no values, so this "
            "run cannot say whether they sent any of these values first",
        )


def _render_completeness_hints(report: ForwardReport) -> None:
    """Say what a completeness refusal means for the values, which is the one thing a reader must not guess."""
    from dhis2w_fhir.service import ForwardCompletenessKind

    refused = report.completeness_of(ForwardCompletenessKind.REFUSED)
    if refused:
        _hint(
            "note",
            f"{len(refused)} report(s) imported and DHIS2 refused the completeness registration. The values "
            "are imported and stay imported - only the completeness claim failed. Forwarding the same tuple "
            "again registers it; a tuple registered twice is an update, not a conflict.",
            style="yellow",
        )
    reason = report.completeness_dry_run_reason
    if reason:
        _hint("note", reason)


def _render_forward_report(report: ForwardReport, generation: GenerationProfile, *, details: bool) -> None:
    """Render one forward run: the mode first, the counts, then either every response or where they are."""
    if report.dry_run:
        _hint("dry run", _DRY_RUN_BANNER, style="bold yellow")
    render_detail(
        "fhir forward",
        [
            DetailRow("profile", f"{generation.name} ({generation.origin})"),
            DetailRow("project", str(report.project_root)),
            DetailRow("mode", "DRY RUN (validate only)" if report.dry_run else "import"),
            DetailRow("coded answers", str(report.coded_answer_mode)),
            DetailRow("spooled", str(report.spooled)),
            DetailRow("translated", str(report.translated_count)),
            DetailRow("refused", str(len(report.refused))),
            DetailRow("posted", str(report.posted_count)),
            DetailRow("accepted", str(len(report.accepted))),
            DetailRow("rejected", str(len(report.rejected))),
            *([DetailRow("unverifiable", str(len(report.unverifiable)))] if report.dry_run else []),
            *([DetailRow("data set completeness", report.completeness_line)] if report.completeness_line else []),
            *(
                [DetailRow("values a previous submission already sent", report.overwrite_line)]
                if report.overwrite_line
                else []
            ),
            *(
                [DetailRow("overwrites", str(report.overwrite_posture))]
                if report.overwrite_posture is OverwritePosture.REFUSE or report.overwrite_line
                else []
            ),
            *(
                [DetailRow("corrections", str(report.correction_posture))]
                if report.correction_posture is not CorrectionPosture.OFF
                else []
            ),
            *(
                [DetailRow("withdrawals", str(report.withdrawal_posture))]
                if report.withdrawal_posture is not WithdrawalPosture.OFF
                else []
            ),
            *([DetailRow("not posted", str(len(report.not_posted)))] if report.stopped is not None else []),
        ],
        console=STDERR_CONSOLE,
    )
    for unreadable in report.unreadable_artifacts:
        _hint("note", f"published resource left out of the translation context: {unreadable}")
    for quarantined in report.quarantined:
        _hint(
            "note",
            f"{quarantined.file_name} does not read as a receipt and was moved to "
            f"{MALFORMED_RESPONSES_RELATIVE_PATH}: {quarantined.reason}",
        )
    for issue in report.filing_issues:
        _hint("note", f"{issue.response_id}: {issue.reason}")
    if not report.spooled:
        _hint("note", "the spool is empty - `d2w fhir serve` is what fills it")
        return
    _render_rejection_reasons(report)
    _render_unverifiable_reasons(report)
    if details:
        _render_overwritten_values(report)
        _render_completeness(report)
        _render_forward_outcomes(report)
    else:
        destination = _write_forward_report(report, generation)
        noted = sum(len(outcome.notes) for outcome in report.outcomes)
        _hint(
            "note",
            f"{len(report.outcomes)} response(s), {noted} note(s); full outcomes in {destination} (--details to print)",
        )
    if report.stopped is not None:
        _hint(
            "error",
            f"the drain stopped at `{report.stopped.response_id}` - {report.stopped.reason}. "
            f"{len(report.not_posted)} response(s) were never posted and are untouched in the queue; "
            "forwarding again once the instance is healthy is the retry",
            style="red",
        )
    if report.rejected:
        _hint(
            "error",
            f"{len(report.rejected)} response(s) rejected by DHIS2; exiting 1 - read the import summary, fix "
            "the instance or the data, and forward again",
            style="red",
        )
    if report.translator_refused:
        _hint(
            "note",
            f"{len(report.translator_refused)} response(s) refused by the translator - they stay in the spool, "
            "so fixing the guide or the data and forwarding again is the retry",
        )
    if report.unverifiable:
        _hint(
            "note",
            f"{len(report.unverifiable)} response(s) this dry run could not check - each is a stage event whose "
            "enrollment a registration of the same run creates, and only an import creates it",
        )
    _render_overwrite_hints(report)
    _render_completeness_hints(report)
    if report.dry_run:
        _hint("dry run", _DRY_RUN_BANNER, style="bold yellow")


@app.command("forward")
def forward_command(
    directory: Annotated[
        Path, typer.Argument(file_okay=False, help="Project directory (default: current directory).")
    ] = Path("."),
    import_responses: Annotated[
        bool | None,
        typer.Option(
            "--import/--dry-run",
            help="Commit the payloads to DHIS2 and move the receipts, overriding `\\[forward] import`. "
            "The default is a dry run: every payload still goes to the real endpoint under its own "
            "validate-only mode, and nothing is written and nothing moves.",
        ),
    ] = None,
    strict_codes: Annotated[
        bool | None,
        typer.Option(
            "--strict-codes/--no-strict-codes",
            help="Refuse a coded answer whose code is outside the served terminology, overriding "
            "`\\[serve] strict_codes`. Lenient resolves the DHIS2 option UID and code too, and notes it.",
        ),
    ] = None,
    register_completeness: Annotated[
        bool | None,
        typer.Option(
            "--register-completeness/--no-register-completeness",
            help="Register the data set complete for every aggregate response whose status is `completed`, "
            "once DHIS2 has taken its values, overriding `\\[forward] register_completeness`. On by "
            "default - the response said it was finished.",
        ),
    ] = None,
    overwrites: Annotated[
        OverwritePosture | None,
        typer.Option(
            "--overwrites",
            help="What to do with an aggregate value a forwarded receipt already sent, overriding "
            "`\\[forward] overwrites`. `allow` - the default - posts it and names it; `refuse` leaves "
            "the whole response in the queue with the covered values written down beside it.",
        ),
    ] = None,
    corrections: Annotated[
        CorrectionPosture | None,
        typer.Option(
            "--corrections",
            help="Whether this deployment accepts a submission that names the receipt it corrects, "
            "overriding `\\[forward] corrections`. Off by default. Stated by the run rather than acted "
            "on by it - a drain imports, and a correction lands on the corrected receipt's identity.",
        ),
    ] = None,
    withdrawals: Annotated[
        WithdrawalPosture | None,
        typer.Option(
            "--withdrawals",
            help="Whether this deployment retracts what it forwarded, overriding "
            "`\\[forward] withdrawals`. Off by default, and read by `d2w fhir withdraw` rather than by "
            "the drain, which never deletes anything.",
        ),
    ] = None,
    details: Annotated[
        bool,
        typer.Option("--details", help="Print every response's outcome instead of writing them to the report."),
    ] = False,
    progress: ProgressOption = True,
) -> None:
    r"""Drain the capture spool into DHIS2 - translate every received response and post it.

    DRY RUN IS THE DEFAULT. Every payload is posted to the real instance under the endpoint's own
    validate-only mode, so DHIS2's rules decide the answer and nothing is written; `--import` commits.

    The posture comes from `\[forward]` in fhir.toml - `import`, `register_completeness`,
    `overwrites`, `corrections`, and `withdrawals` - unless a flag here overrides it for this run,
    and from the defaults above when the file states none. Which spool is drained is
    `\[serve] spool_dir`, the same key the server writes receipts under.

    `corrections` and `withdrawals` are the deployment's posture towards a submission that names what
    it amends or retracts, and the run states them rather than acting on them: a drain imports, and
    `d2w fhir withdraw` is what reads `withdrawals`.

    An imported response moves from the spool's received/ to forwarded/, a DHIS2-rejected one to
    rejected/ beside a report, and a translator-refused one stays put - fix and forward again.

    Every payload names its own DHIS2 object - an event's UID is derived from the receipt's logical id -
    so one receipt forwarded twice is refused as an object the instance holds, never imported twice.

    An aggregate response whose status is `completed` also registers the data set complete for the
    period, organisation unit, and attribute option combo its values landed under - a second write,
    made only after DHIS2 has taken the values. `in-progress` imports the values and registers
    nothing, and `--no-register-completeness` turns the second write off for the whole run.

    A value an earlier submission already sent is named in the run, with the receipt that sent it and
    when that receipt arrived. DHIS2 replaces such a value in place and counts the write exactly as it
    counts a first entry, so no import summary can say it happened; a dry run says it too, while there
    is still time to act on it. `--overwrites refuse` leaves any response holding one in the queue,
    with each covered value written down beside it, instead of posting it.

    A DHIS2 rejection exits 1. A dry run counts a stage event whose enrollment a registration of the
    same run creates as unverifiable rather than rejected - a dry run writes nothing, so there is no
    enrollment to check it against - and a run whose only failures are those exits 0.

    Outcomes land in reports/fhir-forward-report.md; `--details` prints them here instead.
    """
    from dhis2w_fhir import FORWARD_STEPS, service
    from dhis2w_fhir.conversion import CodedAnswerMode

    project = load_project(directory)
    generation = service.resolve_generation_profile(project)
    mode = None if strict_codes is None else (CodedAnswerMode.STRICT if strict_codes else CodedAnswerMode.LENIENT)
    with _progress(FORWARD_STEPS, enabled=progress) as reporter:
        report = asyncio.run(
            service.forward_responses(
                generation.profile,
                project,
                import_responses=import_responses,
                coded_answer_mode=mode,
                register_completeness=register_completeness,
                overwrites=overwrites,
                corrections=corrections,
                withdrawals=withdrawals,
                reporter=reporter,
            )
        )
        if reporter is not None:
            reporter.finish(report.counts_line)
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
    else:
        _render_forward_report(report, generation, details=details)
    if report.rejected or report.stopped is not None:
        raise typer.Exit(code=1)


def _render_spool_state(report: SpoolStateReport, *, details: bool) -> None:
    """Render one spool listing: the count in each state, then a row per receipt under `--details`."""
    render_detail(
        "fhir spool",
        [
            DetailRow("project", str(report.project_root)),
            DetailRow("not yet sent to DHIS2", str(report.counts.received)),
            DetailRow("refused by a drain, still queued", str(report.counts.refused_in_queue)),
            DetailRow("accepted by DHIS2", str(report.counts.forwarded)),
            DetailRow("refused by DHIS2", str(report.counts.rejected)),
            DetailRow("withdrawn from DHIS2", str(report.counts.withdrawn)),
            DetailRow("unreadable files", str(report.counts.malformed)),
        ],
        console=STDERR_CONSOLE,
    )
    if details and report.receipts:
        # The capture identity is a column only where there is one to show. Every receipt a
        # no-authentication facade wrote carries none, and a column of empty cells in a table that
        # already folds would cost the two columns that explain a row their width.
        attributed = any(row.submitted_by for row in report.receipts)
        render_list(
            "receipts",
            [
                {
                    "id": row.response_id,
                    "state": row.state.value,
                    "form": row.questionnaire.rsplit("/", 1)[-1] or row.questionnaire,
                    "received": row.received_at,
                    "captured_by": row.submitted_by or "",
                    "reason": row.reason or "",
                }
                for row in report.receipts
            ],
            [
                ColumnSpec("Receipt", "id", no_wrap=True),
                ColumnSpec("State", "state", no_wrap=True),
                ColumnSpec("Form", "form"),
                ColumnSpec("Received", "received", no_wrap=True),
                *([ColumnSpec("Captured by", "captured_by", no_wrap=True)] if attributed else []),
                ColumnSpec("Why it is there", "reason"),
            ],
            console=STDERR_CONSOLE,
        )
    if details and report.quarantined:
        render_list(
            "unreadable files",
            [{"file": entry.file_name, "reason": entry.reason} for entry in report.quarantined],
            [ColumnSpec("File", "file", no_wrap=True), ColumnSpec("What stopped it", "reason")],
            console=STDERR_CONSOLE,
        )
    if not report.receipts:
        _hint("note", "the spool holds no receipts - `d2w fhir serve` is what fills it")
        return
    if report.counts.malformed:
        _hint(
            "note",
            f"{report.counts.malformed} file(s) in {MALFORMED_RESPONSES_RELATIVE_PATH} do not read as receipts; "
            "each has its reason written beside it",
        )
    if report.counts.rejected:
        _hint(
            "note",
            f"{report.counts.rejected} receipt(s) were refused by DHIS2; fix the instance or the data and "
            "`d2w fhir requeue` puts them back in the queue",
        )
    if report.counts.refused_in_queue:
        _hint(
            "note",
            f"{report.counts.refused_in_queue} queued receipt(s) were refused on the last run that posted; the "
            "reason sits beside each receipt and the next `d2w fhir forward` retries them",
        )
    if not details:
        _hint("note", "--details lists every receipt")


@app.command("spool")
def spool_command(
    directory: Annotated[
        Path, typer.Argument(file_okay=False, help="Project directory (default: current directory).")
    ] = Path("."),
    details: Annotated[
        bool, typer.Option("--details", help="List every receipt, not just how many are in each state.")
    ] = False,
) -> None:
    """List the capture spool - how many receipts wait for DHIS2, and what became of the rest.

    Reads the project's own .serve/responses/ directory and nothing else: no DHIS2 connection, no
    profile, no network. Which directory a receipt's file is in is its state, and the report DHIS2's
    answer was written into says why a drained one is where it is.

    A file that does not read as a receipt is moved to .serve/responses/malformed/ with its reason
    beside it and counted there, so one unreadable file costs one row rather than the listing.
    """
    from dhis2w_fhir import service

    project = load_project(directory)
    report = service.read_spool_state(project)
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    _render_spool_state(report, details=details)


def _render_sync_report(report: SyncReport, generation: GenerationProfile) -> None:
    """Render one sync: what it read, what it changed per resource type, and where the cursor now stands."""
    render_detail(
        "fhir sync",
        [
            DetailRow("project", str(report.project_root)),
            DetailRow("instance", f"{generation.profile.base_url} ({generation.name}, from {generation.origin})"),
            DetailRow("projection", str(report.store_path)),
            DetailRow("run", report.mode.value + (" (dry run)" if report.dry_run else "")),
            DetailRow("tracked entity types", str(len(report.tracked_entity_types))),
            DetailRow("programs polled for enrollments", str(len(report.programs))),
            DetailRow("pages read", str(report.pages_read)),
        ],
        console=STDERR_CONSOLE,
    )
    if report.counts:
        render_list(
            "resources",
            [
                {
                    "type": row.resource_type,
                    "created": str(row.created),
                    "updated": str(row.updated),
                    "removed": str(row.removed),
                }
                for row in report.counts
            ],
            [
                ColumnSpec("Resource", "type", no_wrap=True),
                ColumnSpec("Created", "created", no_wrap=True),
                ColumnSpec("Updated", "updated", no_wrap=True),
                ColumnSpec("Removed", "removed", no_wrap=True),
            ],
            console=STDERR_CONSOLE,
        )
    render_list(
        "how far each collection has been read",
        [
            {
                "collection": move.endpoint.value,
                "was": "never" if move.moved_from is None else move.moved_from.isoformat(),
                "now": "never" if move.moved_to is None else move.moved_to.isoformat(),
            }
            for move in report.cursors
        ],
        [
            ColumnSpec("Collection", "collection", no_wrap=True),
            ColumnSpec("Read up to, before", "was", no_wrap=True),
            ColumnSpec("Read up to, now", "now", no_wrap=True),
        ],
        console=STDERR_CONSOLE,
    )
    if report.dry_run:
        _line(_SYNC_DRY_RUN_BANNER)
    _hint("ok", report.counts_line())
    if report.cursor.updated_at is None:
        _hint(
            "note",
            "the projection states no cursor yet: both collections have to have been read before an "
            "answer can say what instant it is as of",
        )
    else:
        _hint("ok", f"answers served from this projection are as of {report.cursor.updated_at.isoformat()}")


#: What a sync's dry run says, so nobody reads its counts as a description of what is on disk.
_SYNC_DRY_RUN_BANNER = (
    "DRY RUN - the instance was read exactly as a committing run reads it and the counts above are "
    "what a committing run would do. Nothing was written to the projection and no cursor moved. "
    "Re-run without --dry-run to commit."
)


@app.command("sync")
def sync_command(
    directory: Annotated[
        Path, typer.Argument(file_okay=False, help="Project directory (default: current directory).")
    ] = Path("."),
    rebuild: Annotated[
        bool,
        typer.Option(
            "--rebuild",
            help="Empty the projection first, then fill it from zero. How a mapping change reaches it.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Read the instance and count what would change, writing nothing and moving no cursor.",
        ),
    ] = False,
    progress: ProgressOption = True,
) -> None:
    r"""Fill this project's materialized projection from DHIS2 - the register, as FHIR, on disk.

    A projection is a durable copy of the mapped scope of a DHIS2 instance, held as the FHIR resources
    this project's map publishes. It is what `\[serve.search] backend = "projection"` answers a register
    search from: one indexed query instead of one tracker query per key per tracked entity type, and a
    search across every value a person holds rather than an exact match on one.

    The first run reads the whole mapped scope. Every run after it reads what moved since the last one,
    which on an unchanged instance is one request and 56 bytes. `--rebuild` drops the projection and
    fills it from zero, which is routine rather than a recovery step - it is how a change to
    `\[serve.tracked_entities]` or to the published map reaches what is already stored.

    DHIS2 STAYS THE RECORD. Nothing here writes to the instance, and nothing but this command writes
    to the projection. A projection row that disagrees with DHIS2 is a defect of this command, and the
    fix for one is `--rebuild` rather than an edit.

    A deletion is followed. Every poll carries `includeDeleted=true`, which is not a flag here because
    its absence is silent: a sync without it never learns that anybody left. A tombstone removes the
    row rather than archiving a last state, because DHIS2 will not answer a read of a deleted entity.

    WHAT A SYNCED SERVER DOES NOT CHANGE. A record is still read from the instance under the
    credentials of whoever asks, so DHIS2 authorizes every disclosure exactly as it does today; the
    projection decides who is on the page. Which is why a synced answer states the instant it is as of
    and a live one does not.

    Where the projection lives is `\[serve.projection] path`, and which store holds it is
    `\[serve.projection] store` - a project that names none is refused here, naming the key.
    """
    try:
        from dhis2w_fhir_serve import SYNC_STEPS, ServeSettings
    except ImportError as error:
        raise LookupError(_SERVE_PACKAGE_MISSING) from error

    from dhis2w_fhir import service

    project = load_project(directory)
    configured = project.config.serve.projection
    if not configured.enabled():
        raise CliUserError(_SYNC_NO_PROJECTION)
    generation = service.resolve_generation_profile(project)
    settings = ServeSettings(
        project_dir=project.project_root,
        live=True,
        tracked_entities=project.config.serve.tracked_entities,
        search=project.config.serve.search,
        projection=configured,
        dhis2_base_url=generation.profile.base_url,
    )
    with _progress(SYNC_STEPS, enabled=progress) as reporter:
        report = asyncio.run(_sync(settings, project, configured, rebuild=rebuild, dry_run=dry_run, reporter=reporter))
        if reporter is not None:
            reporter.finish(report.counts_line())
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
    else:
        _render_sync_report(report, generation)


#: What a project that configured no projection is told, naming the key and the two commands it pairs.
_SYNC_NO_PROJECTION = (
    'this project holds no materialized projection to fill: state `[serve.projection] store = "sqlite"` '
    'in fhir.toml, and `[serve.search] backend = "projection"` beside it if you want `d2w fhir serve` '
    "to answer register searches from it"
)


async def _sync(
    settings: ServeSettings,
    project: FhirProject,
    configured: ProjectionConfig,
    *,
    rebuild: bool,
    dry_run: bool,
    reporter: ProgressReporter | None,
) -> SyncReport:
    """Open the instance and the projection, run one sync over both, and close them again.

    The register surface comes from a live store build - the same one `d2w fhir serve --live` starts
    with - because a sync maps exactly what a live run serves, through exactly the same published map.
    A second way of deciding what a tracked entity is in FHIR would be a second answer to that
    question, and the two would disagree on the first mapping change.
    """
    from dhis2w_fhir_serve import (
        RegisterSurface,
        TrackedEntityIndex,
        build_store,
        open_live_client,
        open_projection_store,
        projection_path,
        run_sync,
    )

    async with open_live_client(project, settings) as client:
        store = await build_store(settings, project, client)
        surface = RegisterSurface.resolve(TrackedEntityIndex.from_store(project, store), settings.tracked_entities)
        async with open_projection_store(configured, project_root=project.project_root) as projection:
            if projection is None:
                raise CliUserError(_SYNC_NO_PROJECTION)
            return await run_sync(
                client,
                surface=surface,
                store=projection,
                project_root=project.project_root,
                store_path=projection_path(configured, project_root=project.project_root),
                overlap=timedelta(seconds=configured.overlap_seconds),
                rebuild=rebuild,
                dry_run=dry_run,
                narrator=reporter,
            )


@app.command("requeue")
def requeue_command(
    response_ids: Annotated[list[str] | None, typer.Argument(help="Receipt ids to move back into the queue.")] = None,
    directory: Annotated[
        Path, typer.Option("--directory", file_okay=False, help="Project directory (default: current directory).")
    ] = Path("."),
    all_rejected: Annotated[
        bool, typer.Option("--all-rejected", help="Move every receipt DHIS2 refused back into the queue.")
    ] = False,
) -> None:
    """Move receipts DHIS2 refused back into the queue, so the next forward posts them again.

    The one reverse move the spool has, and it is a decision rather than a repair: a rejection is
    DHIS2 stating that this payload is wrong, so nothing moves it back until a person who has changed
    the instance, the guide, or their mind says so.

    The import report stays in rejected/ as the record of what DHIS2 last answered about the payload.
    The next drain writes a fresh one wherever the receipt lands.

    Needs no DHIS2 connection and no profile - it is a rename inside the project directory.
    """
    from dhis2w_fhir import service

    named = list(response_ids or [])
    if not named and not all_rejected:
        raise CliUserError("name the receipt(s) to requeue, or pass --all-rejected to move every refused one")
    if named and all_rejected:
        raise CliUserError("--all-rejected moves every refused receipt, so it takes no ids of its own")
    project = load_project(directory)
    report = service.requeue_rejected_responses(project, named, all_rejected=all_rejected)
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
        return
    for receipt in report.requeued:
        _line(f"{receipt.response_id} -> {receipt.spool_path}")
    _hint("ok", report.counts_line)
    if report.requeued:
        _hint("note", "`d2w fhir forward --import` posts them again")


#: What a withdrawal's dry run says at both ends of its output. The delete reaches the real tracker
#: endpoint under that endpoint's own validate-only mode, which for a terminal act is the one
#: rehearsal worth having.
_WITHDRAW_DRY_RUN_BANNER = (
    "DRY RUN - every delete was posted to DHIS2 under the tracker endpoint's own validate-only mode "
    "(importMode=VALIDATE). Nothing was deleted from the instance and no receipt moved. Re-run with "
    "--import to commit."
)

#: The Rich style each withdrawal outcome renders in, so a glance separates a refusal from a retraction.
_WITHDRAWAL_KIND_STYLES = {
    "retracted": "green",
    "would-retract": "yellow",
    "refused": "red",
}


def _withdrawal_kind_cell(value: Any) -> str:
    """Render one withdrawal outcome in the style it carries."""
    kind = str(value)
    return f"[{_WITHDRAWAL_KIND_STYLES.get(kind, 'default')}]{kind}[/]"


def _render_withdraw_report(report: WithdrawReport, generation: GenerationProfile) -> None:
    """Render one withdrawal run: the mode first, then a row per receipt, then what remains in DHIS2."""
    if report.dry_run:
        _hint("dry run", _WITHDRAW_DRY_RUN_BANNER, style="bold yellow")
    render_detail(
        "fhir withdraw",
        [
            DetailRow("profile", f"{generation.name} ({generation.origin})"),
            DetailRow("project", str(report.project_root)),
            DetailRow("mode", "DRY RUN (validate only)" if report.dry_run else "withdraw"),
            DetailRow("named", str(len(report.receipts))),
            DetailRow("refused by DHIS2", str(len(report.refused))),
        ],
        console=STDERR_CONSOLE,
    )
    render_list(
        "receipts",
        [
            {
                "id": receipt.response_id,
                "kind": receipt.kind.value,
                "event": receipt.event_uid,
                "form": receipt.questionnaire.rsplit("/", 1)[-1] or receipt.questionnaire,
                "answer": receipt.line,
            }
            for receipt in report.receipts
        ],
        [
            ColumnSpec("Receipt", "id", no_wrap=True),
            ColumnSpec("Outcome", "kind", formatter=_withdrawal_kind_cell, no_wrap=True),
            ColumnSpec("Event", "event", no_wrap=True),
            ColumnSpec("Form", "form"),
            ColumnSpec("DHIS2 said", "answer"),
        ],
    )
    if report.retracted:
        _hint(
            "note",
            "This DHIS2 instance keeps a hidden copy of each withdrawn event; none of them appears in "
            "reports any more. The UIDs are burned, so those receipts can never be forwarded again",
        )
    if report.refused:
        _hint(
            "error",
            f"{len(report.refused)} receipt(s) DHIS2 would not delete; exiting 1 - each stays in forwarded/ "
            "with the import report that says what it landed",
            style="red",
        )
    _hint("ok", report.counts_line)
    if report.dry_run:
        _hint("dry run", _WITHDRAW_DRY_RUN_BANNER, style="bold yellow")


@app.command("withdraw")
def withdraw_command(
    response_ids: Annotated[list[str], typer.Argument(help="Forwarded receipt ids to retract from DHIS2.")],
    directory: Annotated[
        Path, typer.Option("--directory", file_okay=False, help="Project directory (default: current directory).")
    ] = Path("."),
    import_responses: Annotated[
        bool,
        typer.Option(
            "--import/--dry-run",
            help="Delete the events in DHIS2 and file the receipts under withdrawn/. The default is a dry "
            "run: the delete goes to the real endpoint under its own validate-only mode, and nothing is "
            "written and nothing moves.",
        ),
    ] = False,
    withdrawals: Annotated[
        WithdrawalPosture | None,
        typer.Option(
            "--withdrawals",
            help="Whether this project retracts what it forwarded, overriding `\\[forward] withdrawals`. "
            "Off by default, and `retract` is what this command requires.",
        ),
    ] = None,
) -> None:
    r"""Retract from DHIS2 the events named forwarded receipts landed, and file each receipt as withdrawn.

    WITHDRAWAL IS TERMINAL. DHIS2 burns the UID of a tracker object it deletes and refuses it under
    every import strategy afterwards, so a withdrawn receipt can never be forwarded again. What
    remains in the instance is a hidden copy of the event carrying its values, which no ordinary read
    returns - not the nothing that the word "deleted" implies.

    DRY RUN IS THE DEFAULT. The delete goes to the real instance under the tracker endpoint's own
    validate-only mode, so DHIS2 answers whether it would take it while nothing is written; `--import`
    commits.

    `\[forward] withdrawals` gates the whole command and is off unless this project says otherwise -
    a project that publishes forms and forwards them is not thereby one that reaches back into what
    DHIS2 already holds. `--withdrawals retract` states it for one run.

    The receipt is never rewritten. Its file moves from forwarded/ to withdrawn/ with a sidecar
    holding what DHIS2 answered the delete, and the import report that recorded what it landed stays
    in forwarded/, because that document is still true of that import.

    Only a receipt in forwarded/ that landed a single event can be withdrawn, and every id is checked
    before anything is posted. `d2w data aggregate delete` and `d2w data tracker delete` are the raw
    escape hatches for the other kinds, outside the FHIR path.
    """
    from dhis2w_fhir import service

    project = load_project(directory)
    generation = service.resolve_generation_profile(project)
    report = asyncio.run(
        service.withdraw_responses(
            generation.profile,
            project,
            response_ids,
            import_responses=import_responses,
            withdrawals=withdrawals,
        )
    )
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
    else:
        _render_withdraw_report(report, generation)
    if report.refused:
        raise typer.Exit(code=1)


#: The Rich style each doctor outcome renders in, so a glance separates a break from a note.
_DOCTOR_OUTCOME_STYLES = {
    "pass": "green",
    "warn": "yellow",
    "fail": "red",
    "skipped": "dim",
    "blocked": "dim",
}


def _doctor_outcome_cell(value: Any) -> str:
    """Render one phase outcome in the style it carries."""
    outcome = str(value)
    return f"[{_DOCTOR_OUTCOME_STYLES.get(outcome, 'default')}]{outcome}[/]"


def _render_doctor_report(report: DoctorReport) -> None:
    """Render one doctor run: what it ran against, one row per phase, then every finding."""
    from dhis2w_fhir.doctor import DoctorOutcome, phase_evidence

    render_detail(
        "fhir doctor",
        [
            DetailRow("profile", f"{report.profile_name} ({report.profile_origin})"),
            DetailRow("instance", report.base_url),
            DetailRow(
                "DHIS2 version",
                f"{report.dhis2_version or 'not detected'} (plugin tree {report.version_tree or 'not bound'})",
            ),
            DetailRow(
                "workspace",
                f"{report.workspace}{'' if report.workspace_kept else ' (removed when the run ended)'}",
            ),
        ],
        console=STDERR_CONSOLE,
    )
    render_list(
        "phases",
        [
            {
                "phase": phase.phase.value,
                "outcome": phase.outcome.value,
                "seconds": f"{phase.elapsed_seconds:.1f}",
                "evidence": phase_evidence(phase),
            }
            for phase in report.phases
        ],
        [
            ColumnSpec("Phase", "phase", no_wrap=True),
            ColumnSpec("Outcome", "outcome", formatter=_doctor_outcome_cell, no_wrap=True),
            ColumnSpec("Seconds", "seconds", no_wrap=True),
            ColumnSpec("What it found", "evidence"),
        ],
        console=STDERR_CONSOLE,
    )
    findings = report.findings
    if findings:
        render_list(
            "findings",
            [
                {
                    "phase": finding.phase.value,
                    "severity": finding.severity,
                    "subject": finding.subject,
                    "where": finding.field_path or "",
                    "detail": finding.detail,
                }
                for finding in findings
            ],
            [
                ColumnSpec("Phase", "phase", no_wrap=True),
                ColumnSpec("Severity", "severity", formatter=_severity_cell, no_wrap=True),
                ColumnSpec("Subject", "subject"),
                ColumnSpec("Where", "where", no_wrap=True),
                ColumnSpec("What", "detail"),
            ],
            console=STDERR_CONSOLE,
        )
    failed = report.failed_phases
    if failed:
        _hint(
            "verdict",
            f"{report.verdict_line}; {', '.join(phase.phase.value for phase in failed)} failed - "
            "this instance breaks the toolchain as configured",
            style="bold red",
        )
    elif any(phase.outcome is DoctorOutcome.WARNED for phase in report.phases):
        _hint("verdict", f"{report.verdict_line}; the toolchain runs, with notes", style="yellow")
    else:
        _hint("verdict", f"{report.verdict_line}; the toolchain runs clean against this instance", style="green")


def _write_doctor_report(report: DoctorReport) -> Path:
    """Write one run's markdown report where a handover reads it, and say where that is."""
    from dhis2w_fhir import REPORTS_DIRECTORY
    from dhis2w_fhir.doctor import DOCTOR_REPORT_STEM, render_doctor_markdown

    root = report.workspace if report.options.workspace is not None else Path.cwd()
    directory = root / REPORTS_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{DOCTOR_REPORT_STEM}.md"
    destination.write_text(render_doctor_markdown(report), encoding="utf-8")
    return destination


@app.command("doctor")
def doctor_command(
    workspace: Annotated[
        Path | None,
        typer.Option(
            "--workspace",
            file_okay=False,
            help="Directory to run in, kept after the run. The default is a temporary directory, "
            "removed when the run ends unless --keep says otherwise.",
        ),
    ] = None,
    keep: Annotated[
        bool,
        typer.Option("--keep", help="Keep the temporary workspace, so the generated project can be read afterwards."),
    ] = False,
    all_targets: Annotated[
        bool,
        typer.Option(
            "--all-targets",
            help="Scaffold empty selection tables, which takes every data set, every program, and every "
            "organisation-unit level. The default is a small representative probe.",
        ),
    ] = False,
    live: Annotated[
        bool,
        typer.Option(
            "--live",
            help="Run the oracle phase: fetch the DHIS2 objects behind a sample of the served resources "
            "and let the instance judge whether each one still derives from current instance state.",
        ),
    ] = False,
    samples: Annotated[
        int,
        typer.Option("--samples", min=0, help="How many resources per family the oracle deep-compares."),
    ] = DEFAULT_ORACLE_SAMPLES,
    progress: ProgressOption = True,
) -> None:
    """Run the whole FHIR toolchain against this profile's instance and report what the instance breaks.

    Nine phases in a throwaway workspace: connect, scaffold, generate, compile, validate, serve,
    capture, forward, oracle. Each reports pass, warn, fail, skipped, or blocked with its reason.

    The instance comes from `d2w -p <name>` and the ambient profile resolution, as `d2w fhir serve` does.

    A phase that fails never stops one that does not depend on it, and only a failure exits 1.

    Compiling needs a FSH compiler on the machine; without one the phase is skipped and the served
    store is built by the live builders instead, so every later phase still runs.

    `--live` adds the oracle: the DHIS2 objects behind a seeded sample of the served resources are
    fetched back and the instance decides whether the served output still derives from them.

    The run writes reports/fhir-doctor-report.md, into the workspace when one was named and into the
    working directory otherwise.
    """
    from dhis2w_fhir.doctor import DOCTOR_STEPS, DoctorOptions, resolve_doctor_profile, run_doctor

    generation = resolve_doctor_profile()
    options = DoctorOptions(
        workspace=workspace,
        keep=keep,
        all_targets=all_targets,
        live=live,
        samples=samples,
    )
    with _progress(DOCTOR_STEPS, enabled=progress) as reporter:
        report = asyncio.run(run_doctor(generation, options, reporter=reporter))
        if reporter is not None:
            reporter.finish(report.verdict_line)
    destination = _write_doctor_report(report)
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2))
    else:
        _line(f"wrote {destination}")
        _render_doctor_report(report)
    if report.failed_phases:
        raise typer.Exit(code=1)


def register(root_app: Any) -> None:
    """Mount this plugin's Typer sub-app under `d2w fhir`."""
    root_app.add_typer(app, name="fhir", help="FHIR Implementation Guide generation from DHIS2 metadata.")
