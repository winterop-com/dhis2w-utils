"""FastMCP tool registration for the `fhir` plugin - the read surface only.

Scaffolding and generation are CLI-only by design: they write a file tree
onto the machine the MCP server happens to run on, which is the wrong shape
for an agent protocol (the same judgment as the browser plugin and the
security audit runner). The one data-shaped question - "are this instance's
codes FHIR-safe?" - is exposed as the read-only `fhir_validate`.
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
    async def fhir_validate(profile: str | None = None, project_directory: str | None = None) -> FhirValidationReport:
        """Check a DHIS2 instance's codes for FHIR-safety - instance-wide sweep plus a deep option-set pass."""
        if project_directory:
            project = load_project(Path(project_directory))
            generation = service.resolve_generation_profile(project, profile)
            return await service.validate_codes(generation.profile, project.config.generate)
        context = service.resolve_validation_context(profile)
        return await service.validate_codes(context.generation.profile, context.config)
