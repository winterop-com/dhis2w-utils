"""Generate a whole FHIR IG from Python and read the report back as a model.

`d2w fhir generate` is a thin shell over three calls, and this is the same three:
`load_project` finds the nearest `fhir.toml` and parses it into a `FhirProject`,
`resolve_generation_profile` says which DHIS2 instance the run reads, and
`generate_full` reads that instance once and writes every target off the one pass.

What comes back is a `GenerateFullReport` - one `GenerateReport` per target, each
carrying the files it wrote, the files it deleted, its own counts, and its own notes.
Nothing here parses text: the counts printed below are fields on a pydantic model,
which is what makes them safe to gate a pipeline on.

Give it a project directory to generate that project. With no argument it scaffolds a
throwaway one under a temporary directory, generates it, and removes it again.

Usage:
    uv run python examples/fhir/client/generate_ig.py [PROJECT_DIRECTORY]

Requires a DHIS2 profile (`d2w profile list`), and a compile is NOT part of this -
generation writes IG source, `make sushi` inside the project turns it into resources.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from _runner import run_example
from dhis2w_fhir import FhirProject, GenerateReport, InitOptions, load_project, service

# One data set and a shallow registry keep a demonstration run to a few seconds.
_DEMO_OPTIONS = InitOptions(
    ig_id="dhis2.fhir.generatedemo",
    canonical="http://example.org/fhir/generate-demo",
    name="GenerateDemo",
    title="Generate Demo Implementation Guide",
    publisher="Demo Org",
    data_set_ids=["BfMAe6Itzgt"],
    max_level=2,
)


async def _open_project(directory: Path | None) -> FhirProject:
    """Load the named project, or scaffold a throwaway one and load that."""
    if directory is not None:
        return load_project(directory)
    scratch = Path(tempfile.mkdtemp(prefix="d2w-fhir-generate-"))
    scaffold = await service.init_project(scratch, _DEMO_OPTIONS)
    print(f"scaffolded {len(scaffold.created_files)} files into {scaffold.directory}")
    return load_project(scratch)


def _print_target(label: str, report: GenerateReport) -> None:
    """Print one target's row: what it wrote, what it swept, and what it counted."""
    counts = ", ".join(
        f"{value} {name}"
        for name, value in (
            ("option sets", report.option_set_count),
            ("categories", report.category_count),
            ("questionnaires", report.questionnaire_count),
            ("examples", report.example_count),
            ("organisation units", report.organisation_unit_count),
            ("pages", report.page_count),
        )
        if value
    )
    print(
        f"  {label:20} {len(report.written_files):4} written  {len(report.deleted_files):4} deleted  "
        f"{report.unchanged_count:4} unchanged  {counts or '-'}"
    )


async def main() -> None:
    """Generate every target of a FHIR project and print the typed report."""
    argument = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    project = await _open_project(argument)
    generation = service.resolve_generation_profile(project)
    print(f"project: {project.project_root}")
    print(f"instance: {generation.profile.base_url} (profile {generation.name}, from {generation.origin})")

    full = await service.generate_full(generation.profile, project)

    targets: tuple[tuple[str, GenerateReport], ...] = (
        ("foundation", full.foundation),
        ("option sets", full.option_sets),
        ("categories", full.categories),
        ("questionnaires", full.questionnaires),
        ("examples", full.examples),
        ("organisation units", full.organisation_units),
        ("pages", full.pages),
    )
    for label, report in targets:
        _print_target(label, report)

    # Notes are the run telling you what it decided that you did not ask for - a program shape it
    # could not map, a name it had to escape, a registry it capped. Each is a model, not a string.
    notes = [note for _, report in targets for note in report.notes]
    print(f"{len(notes)} note(s) across the run")
    for note in notes[:5]:
        print(f"  {note.category}: {note.message}")

    if argument is None:
        shutil.rmtree(project.project_root, ignore_errors=True)
        print(f"removed the throwaway project at {project.project_root}")


if __name__ == "__main__":
    run_example(main)
