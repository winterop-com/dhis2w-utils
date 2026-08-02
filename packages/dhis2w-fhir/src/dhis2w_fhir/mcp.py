"""FastMCP tool registration for the `fhir` plugin - the read surface only.

Scaffolding and generation are CLI-only by design: they write a file tree
onto the machine the MCP server happens to run on, which is the wrong shape
for an agent protocol (the same judgment as the browser plugin and the
security audit runner). `fhir generate pages` is no exception - it writes
markdown into `ig/input/pagecontent/`, so it ships as a CLI command with no
MCP tool. The one data-shaped question - "are this instance's codes
FHIR-safe?" - is exposed as the read-only `fhir_validate`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.types import ToolAnnotations

from dhis2w_fhir import FhirValidationReport, load_project, service

_READ = ToolAnnotations(readOnlyHint=True)


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
