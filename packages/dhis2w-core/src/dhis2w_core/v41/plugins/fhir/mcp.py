"""FastMCP tool registration for the `fhir` plugin."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dhis2w_core.fhir_core import FhirProject, GenerateReport, InitOptions, ScaffoldReport, load_project
from dhis2w_core.fhir_core.names import pascal
from dhis2w_core.profile import Profile, resolve_profile
from dhis2w_core.v41.plugins.fhir import service


def _load_tool_project(project_directory: str | None) -> FhirProject:
    """Load the FHIR project for one tool call, starting from `project_directory` when given."""
    return load_project(Path(project_directory) if project_directory else None)


def _tool_profile(project: FhirProject, profile: str | None) -> Profile:
    """Resolve the DHIS2 profile: explicit argument wins, then `DHIS2_PROFILE`, then fhir.toml."""
    return resolve_profile(profile or os.environ.get("DHIS2_PROFILE") or project.config.profile)


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
        return await service.generate_option_sets(_tool_profile(project, profile), project)

    @mcp.tool()
    async def fhir_generate_org_units(
        project_directory: str | None = None, profile: str | None = None
    ) -> GenerateReport:
        """Generate Organization/Location FSH from DHIS2 organisation units into the FHIR project."""
        project = _load_tool_project(project_directory)
        return await service.generate_org_units(_tool_profile(project, profile), project)
