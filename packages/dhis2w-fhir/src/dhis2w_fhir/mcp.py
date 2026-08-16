"""FastMCP tool registration for the `fhir` plugin - the two data-shaped questions, and nothing else.

Scaffolding and generation are CLI-only by design: they write a file tree
onto the machine the MCP server happens to run on, which is the wrong shape
for an agent protocol (the same judgment as the browser plugin and the
security audit runner). `fhir generate pages` is no exception - it writes
markdown into `ig/input/pagecontent/`, so it ships as a CLI command with no
MCP tool.

What is exposed is what an agent really asks. `fhir_validate` answers "are
this instance's codes FHIR-safe?" and reads nothing but metadata.
`fhir_forward` answers "would the captured responses import, and did they?" -
it drains an existing spool rather than writing a tree, and it runs the
posture the project states in `[forward]`, which is a dry run until a project
says otherwise.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.types import ToolAnnotations

from dhis2w_fhir import FhirValidationReport, ForwardReport, load_project, service
from dhis2w_fhir.conversion import CodedAnswerMode

_READ = ToolAnnotations(readOnlyHint=True)

#: A forward run writes to DHIS2 only when the caller asks it to, and it never removes anything.
_IMPORT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)


def register(mcp: Any) -> None:
    """Register the `fhir_*` tools on `mcp`."""

    @mcp.tool(annotations=_READ)
    async def fhir_validate(
        profile: str | None = None,
        project_directory: str | None = None,
        code_source: str | None = None,
    ) -> FhirValidationReport:
        """Check a DHIS2 instance's codes for FHIR-safety - instance-wide sweep plus a deep option-set pass.

        `code_source` ("id" or "code") overrides the project's `concept_code_source` for this run:
        in id mode the option code findings are informational, in code mode they are defects.
        """
        if project_directory:
            project = load_project(Path(project_directory))
            generation = service.resolve_generation_profile(project, profile)
            return await service.validate_codes(generation.profile, project.config.generate, code_source)
        context = service.resolve_validation_context(profile)
        return await service.validate_codes(context.generation.profile, context.config, code_source)

    @mcp.tool(annotations=_IMPORT)
    async def fhir_forward(
        profile: str | None = None,
        project_directory: str | None = None,
        dry_run: bool | None = None,
        strict_codes: bool | None = None,
        register_completeness: bool | None = None,
    ) -> ForwardReport:
        """Drain a FHIR project's capture spool into DHIS2 - translate every received response and post it.

        `dry_run` unstated is what the project says in `[forward] import`, which itself defaults to a
        dry run - the safe answer: every payload still goes to the real endpoint under its own
        validate-only mode (`dryRun=true` for `/api/dataValueSets`, `importMode=VALIDATE` for
        `/api/tracker`), so DHIS2's rules decide the outcome while nothing is written and no receipt
        moves. Pass `dry_run=False` to commit whatever the project says, which also moves an accepted
        receipt to the spool's `forwarded/` and a rejected one to `rejected/` beside its report.

        A response the translator refuses never reaches DHIS2 and stays in the spool, so fixing the
        guide or the data and forwarding again is the retry.

        A dry run counts a stage event whose enrollment a registration of the same run creates as
        `unverifiable` rather than `rejected`: the run writes nothing, so there is no enrollment for
        DHIS2 to check the event against, and an import posts registrations first. A stage event
        naming an enrollment no registration of the run creates is a rejection in either mode.

        An aggregate response whose status is `completed` also registers the data set complete for the
        tuple its values landed under, as a second write made only after DHIS2 has taken the values.
        An `in-progress` response imports its values and registers nothing, and
        `register_completeness=False` turns the second write off for the whole run. Unstated, it is
        what `[forward] register_completeness` says, which defaults to on. A refused registration
        does not un-import the values.

        `strict_codes` overrides `[serve] strict_codes`: strict refuses a coded answer outside the
        served terminology, lenient resolves the DHIS2 option UID and code too and notes what it did.
        """
        project = load_project(Path(project_directory) if project_directory else None)
        generation = service.resolve_generation_profile(project, profile)
        mode = None if strict_codes is None else (CodedAnswerMode.STRICT if strict_codes else CodedAnswerMode.LENIENT)
        return await service.forward_responses(
            generation.profile,
            project,
            import_responses=None if dry_run is None else not dry_run,
            coded_answer_mode=mode,
            register_completeness=register_completeness,
        )
