"""FastMCP tool registration for the `fhir` plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.types import ToolAnnotations

from dhis2w_fhir import (
    FhirProject,
    FhirValidationReport,
    GenerateReport,
    InitOptions,
    ScaffoldReport,
    load_project,
    service,
)
from dhis2w_fhir.names import pascal

_READ = ToolAnnotations(readOnlyHint=True)


def _load_tool_project(project_directory: str | None) -> FhirProject:
    """Load the FHIR project for one tool call, starting from `project_directory` when given."""
    return load_project(Path(project_directory) if project_directory else None)


def register(mcp: Any) -> None:
    """Register the `fhir_*` tools on `mcp`."""

    @mcp.tool()
    async def fhir_init(
        directory: str,
        ig_id: str = "dhis2.fhir.example",
        canonical: str = "http://example.org/fhir",
        name: str | None = None,
        title: str | None = None,
        publisher: str = "Example Organisation",
        force: bool = False,
    ) -> ScaffoldReport:
        """Scaffold a dockerized SUSHI FHIR IG project (fhir.toml, sushi-config, Makefile) into `directory`."""
        resolved_name = name or pascal(ig_id)
        options = InitOptions(
            ig_id=ig_id,
            canonical=canonical,
            name=resolved_name,
            title=title or f"{resolved_name} Implementation Guide",
            publisher=publisher,
        )
        return await service.init_project(Path(directory), options, force=force)

    @mcp.tool()
    async def fhir_generate_option_sets(
        project_directory: str | None = None, profile: str | None = None
    ) -> GenerateReport:
        """Generate CodeSystem/ValueSet FSH from DHIS2 option sets into the FHIR project at `project_directory`."""
        project = _load_tool_project(project_directory)
        generation = service.resolve_generation_profile(project, profile)
        return await service.generate_option_sets(generation.profile, project)

    @mcp.tool()
    async def fhir_generate_org_units(
        project_directory: str | None = None, profile: str | None = None
    ) -> GenerateReport:
        """Generate Organization/Location FSH from DHIS2 organisation units into the FHIR project."""
        project = _load_tool_project(project_directory)
        generation = service.resolve_generation_profile(project, profile)
        return await service.generate_org_units(generation.profile, project)

    @mcp.tool(annotations=_READ)
    async def fhir_validate(profile: str | None = None, project_directory: str | None = None) -> FhirValidationReport:
        """Check a DHIS2 instance's option-set codes and names for FHIR-safety (read-only, writes nothing)."""
        if project_directory:
            project = _load_tool_project(project_directory)
            generation = service.resolve_generation_profile(project, profile)
            return await service.validate_codes(generation.profile, project.config.generate)
        context = service.resolve_validation_context(profile)
        return await service.validate_codes(context.generation.profile, context.config)
