"""Plugin descriptor - mounts `d2w fhir` and the `fhir_*` MCP tools via the `dhis2.plugins` entry point.

The package is version-neutral: the wire client auto-detects the DHIS2 major
on connect, and FSH emission only consumes the reduced source models, so one
plugin serves v41/v42/v43 without per-tree copies.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _FhirPlugin(BaseModel):
    """Plugin descriptor for FHIR IG generation."""

    model_config = ConfigDict(frozen=True)

    name: str = "fhir"
    description: str = (
        "FHIR Implementation Guide generation: scaffold a SUSHI project (`d2w fhir init`), generate FSH from "
        "DHIS2 option sets and organisation units (`d2w fhir generate`), and check a DHIS2 instance's codes "
        "for FHIR-safety (`d2w fhir validate`)."
    )

    def register_cli(self, app: Any) -> None:
        """Mount the fhir sub-app under `d2w fhir`."""
        from dhis2w_fhir import cli as cli_module

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register the `fhir_*` tools on the MCP server."""
        from dhis2w_fhir import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _FhirPlugin()
