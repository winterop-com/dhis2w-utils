"""Drain the spool from inside your own process: one connection you own, every dial stated in code.

The other half of the headless loop. `capture_headless.py` writes receipts into a project's spool
without a server; this drains them into DHIS2 without a command line - no `d2w fhir forward`
subprocess, no `[forward]` table consulted for anything this program has an opinion about.

Two things make it the embedder's path rather than `forward_spool.py`'s:

**The client belongs to the caller.** A drain given `client=` reads the value types and posts every
payload through that connection and leaves it open, so a process that already holds a DHIS2 client -
a worker, a scheduler, a service with a lifespan - spends no new connection on the drain. Given
none, the drain opens one for its own length and closes it.

**The dials are arguments.** Every one of the six is `None` for "the caller stated nothing", which
falls to `fhir.toml` and then to the key's own default. An embedder that decides these in its own
configuration states them here instead, and the report says which run it was.

A DRY RUN IS THE DEFAULT, and it is what this example runs. Every payload still goes to the real
endpoint on the real instance under that endpoint's own validate-only mode - `dryRun=true` on
`/api/dataValueSets`, `importMode=VALIDATE` on `/api/tracker` - so DHIS2's own rules decide each
answer while nothing is written and no receipt moves. `import_responses=True` is the committing run.

Usage:
    uv run python examples/fhir/client/forward_headless.py [PROJECT_DIRECTORY]

With no argument it drains the shared example project's spool (see `_fixture.py`). An empty spool
reports a run of zero, which is an answer rather than an error.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _fixture import example_project
from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_fhir import CodedAnswerMode, OverwritePosture, load_project, service

RECEIPTS_LISTED = 10
"""How many per-receipt rows this example prints, so a hundred-receipt spool stays readable."""


async def main() -> None:
    """Drain one project's spool through a connection this program owns, with the dials named here."""
    directory = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else example_project()
    project = load_project(directory)
    generation = service.resolve_generation_profile(project)
    print(f"project: {project.project_root}")
    print(f"instance: {generation.profile.base_url} (profile {generation.name})")

    # The connection is opened here and closed here. The drain reads and posts through it, and never
    # closes a client it did not open - which is what lets a long-lived process hand in its own.
    async with open_client(generation.profile) as client:
        report = await service.forward_responses(
            generation.profile,
            project,
            client=client,
            import_responses=False,
            coded_answer_mode=CodedAnswerMode.LENIENT,
            register_completeness=False,
            overwrites=OverwritePosture.ALLOW,
        )

    print(f"{'dry run' if report.dry_run else 'import'}, {report.coded_answer_mode} coded answers")
    print(f"  {report.counts_line}")

    # One row per receipt: what it answered, and what this run made of it.
    for outcome in report.outcomes[:RECEIPTS_LISTED]:
        print(f"  {outcome.kind:13} {outcome.response_id:34} {outcome.target_kind or '-'}")

    # A rejection is DHIS2 stating the payload is wrong, rolled up by cause rather than by receipt.
    for reason in report.rejection_reasons:
        print(f"  rejected x{reason.responses} [{reason.error_code or 'no code'}] {reason.reason}")

    # A refusal is the translator declining to read a response whole. The receipt stays queued, so
    # the next drain is the retry - which is why an embedder can run this on a timer and act on the
    # report rather than on a queue it has to reconcile itself.
    for outcome in report.translator_refused:
        for refusal in outcome.refusals:
            print(f"  refused {outcome.response_id}: {refusal.reason}")


if __name__ == "__main__":
    run_example(main)
