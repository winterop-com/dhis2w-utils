"""Drain a capture spool into DHIS2 from Python and read the `ForwardReport` back as a model.

`forward_responses` is what `d2w fhir forward` calls, and a **dry run is the default**:
every payload still goes to the real endpoint on the real instance under that endpoint's
own validate-only mode - `dryRun=true` on `/api/dataValueSets`, `importMode=VALIDATE` on
`/api/tracker` - so DHIS2's own rules decide each answer while nothing is written and no
receipt moves. Pass `import_responses=True` to commit.

The report is where the value is. `ForwardReport` carries every receipt's outcome plus
derived views a caller would otherwise have to compute: `accepted` / `rejected` /
`refused` / `unverifiable` partition the run, `counts_line` states it in one sentence, and
`rejection_reasons` rolls a wall of DHIS2 errors up by cause so a hundred rejections read
as the three things that are actually wrong.

Usage:
    uv run python examples/fhir/client/forward_spool.py [PROJECT_DIRECTORY]

Fill the spool first - see examples/fhir/cli/serve.sh, or any `d2w fhir serve` that has
been POSTed a QuestionnaireResponse. An empty spool reports a run of zero, which is a
valid answer rather than an error.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _runner import run_example
from dhis2w_fhir import load_project, service


async def main() -> None:
    """Dry-run the nearest project's spool and print what each receipt became."""
    directory = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    project = load_project(directory)
    generation = service.resolve_generation_profile(project)
    print(f"project: {project.project_root}")
    print(f"instance: {generation.profile.base_url} (profile {generation.name})")

    report = await service.forward_responses(generation.profile, project, import_responses=False)

    print(f"{'dry run' if report.dry_run else 'import'}, {report.coded_answer_mode} coded answers")
    print(f"  {report.counts_line}")

    # One row per receipt: what it answered, where in DHIS2 it was headed, and what became of it.
    for outcome in report.outcomes[:10]:
        print(f"  {outcome.kind:13} {outcome.response_id:24} {outcome.target_kind or '-'}")

    # A refusal is the translator declining to read a response whole - the fix is in the guide or
    # in the data, and the receipt stays queued so the next drain is the retry.
    for outcome in report.refused:
        for refusal in outcome.refusals:
            print(f"  refused {outcome.response_id}: {refusal.reason}")

    # A rejection is DHIS2 stating the payload is wrong. Rolled up by cause, commonest first.
    for reason in report.rejection_reasons:
        print(f"  rejected x{reason.responses} [{reason.error_code or 'no code'}] {reason.reason}")

    # A dry run cannot check a stage event whose enrollment this very run would create.
    for unverifiable in report.unverifiable_reasons:
        print(f"  unverifiable x{unverifiable.responses}: {unverifiable.reason}")

    if report.stopped is not None:
        print(f"  stopped short at {report.stopped.response_id}: {report.stopped.reason}")


if __name__ == "__main__":
    run_example(main)
