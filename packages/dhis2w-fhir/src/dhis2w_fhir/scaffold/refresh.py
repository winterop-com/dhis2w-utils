"""Bring an existing project's scaffold-managed files up to date without dropping anything the user wrote.

The scaffold grows: a `path-resource` declaration lands in `ig/sushi-config.yaml`, an entry lands in
`.gitignore`, and a project scaffolded before that carries neither. `refresh_project` re-renders the
scaffold for that project - identity read back off disk, not defaults - and writes a file only when
the render reproduces every line already there, so a refresh can add what the scaffold gained and can
never take away what the user added. A file holding a line the scaffold would not produce is left
exactly as it is and reported. `fhir.toml` is the user's configuration and is never written at all.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from dhis2w_fhir.config import FHIR_CONFIG_FILENAME, NoFhirProjectError, load_fhir_config
from dhis2w_fhir.scaffold import FSH_INI_RELATIVE_PATH, SUSHI_CONFIG_RELATIVE_PATH, build_scaffold_files
from dhis2w_fhir.scaffold.schemas import (
    DEFAULT_SUSHI_TIMEOUT_SECONDS,
    InitOptions,
    ProjectScaffoldState,
    ScaffoldReport,
)

__all__ = ["preserves_every_line", "read_project_scaffold_state", "refresh_project"]

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
    """Re-render the scaffold for the project in `directory`, writing only where nothing on disk is lost."""
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
            report.edited_files.append(relative_path)
        elif current == scaffold_file.content:
            report.unchanged_files.append(relative_path)
        elif preserves_every_line(current, scaffold_file.content):
            destination.write_text(scaffold_file.content, encoding="utf-8")
            report.refreshed_files.append(relative_path)
        else:
            report.edited_files.append(relative_path)
    return report


def _read_file(path: Path) -> str | None:
    """Read a project file, returning None when it cannot be read as text - unreadable content is never replaced."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_text(path: Path) -> str:
    """Read a project file for value recovery, treating an absent or unreadable one as empty."""
    return _read_file(path) or ""
