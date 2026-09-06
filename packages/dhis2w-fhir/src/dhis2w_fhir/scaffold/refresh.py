"""Bring an existing project's scaffold-managed files up to date without dropping anything the user wrote.

The scaffold grows: a `path-resource` declaration lands in `ig/sushi-config.yaml`, an entry lands in
`.gitignore`, a recipe in the `Makefile` takes a new shape, and a project scaffolded before any of
that carries none of it. `refresh_project` re-renders the scaffold for that project - identity read
back off disk, not defaults - and lands the current render wherever nothing of the project's own is
at stake.

The files at `OWNED_WHOLE_RELATIVE_PATHS` are the scaffold's outright: nobody edits the `Makefile`,
the `Dockerfile`, `.python-version`, `ig/ig.ini` or `ig/fsh.ini`, because every value in them is
either a `?=` default taken from the command line or the environment, or a value the project states
elsewhere and the render carries back in. A refresh writes each of those from the current render
whenever it differs, so a revision that replaces a line lands whole.

Every other file goes through the line ladder. It is rewritten only when the render reproduces every
line already there, so a refresh adds what the scaffold gained and never takes away what the user
added. A file holding a line the scaffold would not produce stays exactly as it is and is reported -
as carrying the user's additions when it still holds every current scaffold line, and as diverged
when lines are missing in both directions, since the user's edits and a scaffold line that has since
changed read identically from disk. `fhir.toml` is the user's configuration and is never written at
all.

The identity lines are the exception to line preservation, because `fhir.toml` declares them. Five
files carry the identity - `ig/sushi-config.yaml`, `fhir.example.toml`, the front page at
`ig/input/pagecontent/index.md`, `ig/ig.ini`, and `pyproject.toml` - and each owns the lines listed in
`dhis2w_fhir.scaffold.identity`, so a refresh substitutes each of them into the file and reports it
refreshed. Every other line of every one of those files is the project's and survives
byte-identical.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from dhis2w_fhir.config import FHIR_CONFIG_FILENAME, NoFhirProjectError, load_fhir_config
from dhis2w_fhir.scaffold import (
    CONFIG_EXAMPLE_RELATIVE_PATH,
    FSH_INI_RELATIVE_PATH,
    OWNED_WHOLE_RELATIVE_PATHS,
    SUSHI_CONFIG_RELATIVE_PATH,
    build_scaffold_files,
)
from dhis2w_fhir.scaffold.identity import adopt_scaffold_owned_lines
from dhis2w_fhir.scaffold.schemas import (
    DEFAULT_SUSHI_TIMEOUT_SECONDS,
    InitOptions,
    ProjectScaffoldState,
    ScaffoldReport,
)

__all__ = ["preserves_every_line", "read_project_scaffold_state", "refresh_project"]

#: What a project may carry from an older scaffold, and the file that writes that content today.
_SUPERSEDED_FILES = {"fhir.toml.example": CONFIG_EXAMPLE_RELATIVE_PATH}

#: `copyrightYear: 2026+` of sushi-config - the scaffold stamps the year it ran and nothing else records it.
_COPYRIGHT_YEAR_PATTERN = re.compile(r"^copyrightYear:\s*(\d{4})\+?\s*$", re.MULTILINE)

#: The publisher home page of sushi-config, the scaffold's only two-space `url:` key.
_PUBLISHER_URL_PATTERN = re.compile(r"^  url:\s*(\S+)\s*$", re.MULTILINE)

#: The `[FSH] timeout` of fsh.ini, the ceiling the IG publisher gives its internal SUSHI run.
_SUSHI_TIMEOUT_PATTERN = re.compile(r"^timeout\s*=\s*(\d+)\s*$", re.MULTILINE)


def read_project_scaffold_state(directory: Path) -> ProjectScaffoldState:
    """Recover the scaffold inputs of the project in `directory` from its fhir.toml, sushi-config, and fsh.ini."""
    config_path = directory / FHIR_CONFIG_FILENAME
    if not config_path.is_file():
        raise NoFhirProjectError(
            f"no {FHIR_CONFIG_FILENAME} in {directory} - there is no project to refresh. "
            f"Run `d2w fhir init {directory}` to scaffold one."
        )
    config = load_fhir_config(config_path)
    sushi_config = _read_text(directory / SUSHI_CONFIG_RELATIVE_PATH)
    fsh_ini = _read_text(directory / FSH_INI_RELATIVE_PATH)
    copyright_year = _COPYRIGHT_YEAR_PATTERN.search(sushi_config)
    publisher_url = _PUBLISHER_URL_PATTERN.search(sushi_config)
    sushi_timeout = _SUSHI_TIMEOUT_PATTERN.search(fsh_ini)
    options = InitOptions(
        ig_id=config.ig.id,
        canonical=config.ig.canonical,
        name=config.ig.name,
        title=config.ig.title,
        publisher=config.ig.publisher,
        status=config.ig.status,
        publisher_url=publisher_url.group(1) if publisher_url else None,
        profile=config.profile,
        sushi_timeout=int(sushi_timeout.group(1)) if sushi_timeout else DEFAULT_SUSHI_TIMEOUT_SECONDS,
        identifier_system_base=config.generate.identifier_system_base,
        max_level=config.generate.organisation_units.max_level,
        data_set_ids=list(config.generate.data_sets.include_ids),
        event_program_ids=list(config.generate.event_programs.include_ids),
        tracker_program_ids=list(config.generate.tracker_programs.include_ids),
    )
    year = int(copyright_year.group(1)) if copyright_year else datetime.now(tz=UTC).year
    return ProjectScaffoldState(options=options, copyright_year=year)


def preserves_every_line(current: str, rendered: str) -> bool:
    """Report whether `rendered` carries every line of `current`, in order - rewriting loses nothing."""
    remaining = iter(rendered.splitlines())
    return all(any(candidate == line for candidate in remaining) for line in current.splitlines())


def refresh_project(directory: Path) -> ScaffoldReport:
    """Re-render the scaffold for the project in `directory`, landing every file nothing of the project's is in."""
    state = read_project_scaffold_state(directory)
    report = ScaffoldReport(directory=directory.resolve())
    for scaffold_file in build_scaffold_files(state.options, copyright_year=state.copyright_year):
        relative_path = scaffold_file.relative_path
        if relative_path == FHIR_CONFIG_FILENAME:
            continue
        destination = directory / relative_path
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(scaffold_file.content, encoding="utf-8")
            report.created_files.append(relative_path)
            continue
        current = _read_file(destination)
        if current is None:
            report.diverged_files.append(relative_path)
            continue
        if current == scaffold_file.content:
            report.unchanged_files.append(relative_path)
            continue
        if relative_path in OWNED_WHOLE_RELATIVE_PATHS:
            destination.write_text(scaffold_file.content, encoding="utf-8")
            report.refreshed_files.append(relative_path)
            continue
        comparable = adopt_scaffold_owned_lines(relative_path, current, scaffold_file.content)
        if preserves_every_line(comparable, scaffold_file.content):
            destination.write_text(scaffold_file.content, encoding="utf-8")
            report.refreshed_files.append(relative_path)
        elif comparable != current:
            # The identity fhir.toml declares lands on its own lines, and every other line the
            # project wrote - its own additions included - stays exactly where it is.
            destination.write_text(comparable, encoding="utf-8")
            report.refreshed_files.append(relative_path)
        elif preserves_every_line(scaffold_file.content, comparable):
            # The file holds every line the current render produces, plus lines of its own:
            # user additions on a current scaffold, with nothing for a refresh to add.
            report.extended_files.append(relative_path)
        else:
            # Lines missing in both directions. The user's edits and a scaffold line that has
            # since changed read identically here, so the verdict claims neither author.
            report.diverged_files.append(relative_path)
    report.notes.extend(_files_the_scaffold_no_longer_writes(directory))
    return report


def _files_the_scaffold_no_longer_writes(directory: Path) -> list[str]:
    """Name each file a project carries that the scaffold does not write, so the person can delete it."""
    return [
        f"{superseded} is not a scaffold file; delete it, {replacement} has replaced it"
        for superseded, replacement in _SUPERSEDED_FILES.items()
        if (directory / superseded).exists()
    ]


def _read_file(path: Path) -> str | None:
    """Read a project file, returning None when it cannot be read as text - unreadable content is never replaced."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_text(path: Path) -> str:
    """Read a project file for value recovery, treating an absent or unreadable one as empty."""
    return _read_file(path) or ""
