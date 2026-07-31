"""FHIR plugin - scaffold a SUSHI IG project and generate FSH from DHIS2 metadata.

Heavy lifting (fhir.toml config, FSH emission, scaffolding) lives in the
version-neutral `dhis2w_core.fhir_core`; this plugin binds it to the v42
client tree and the CLI/MCP surfaces.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _FhirPlugin(BaseModel):
    """Plugin descriptor for FHIR IG generation."""

    model_config = ConfigDict(frozen=True)

    name: str = "fhir"
    description: str = (
        "FHIR Implementation Guide generation: scaffold a SUSHI project (`d2w fhir init`) and generate "
        "FSH from DHIS2 option sets and organisation units (`d2w fhir generate`)."
    )

    def register_cli(self, app: Any) -> None:
        """Mount the fhir sub-app under `d2w fhir`."""
        from dhis2w_core.v42.plugins.fhir import cli as cli_module

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register the `fhir_*` tools on the MCP server."""
        from dhis2w_core.v42.plugins.fhir import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _FhirPlugin()
