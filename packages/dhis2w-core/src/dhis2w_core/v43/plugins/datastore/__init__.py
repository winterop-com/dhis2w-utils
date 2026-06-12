"""Datastore plugin — DHIS2 key-value store (/api/dataStore + /api/userDataStore) as CLI + MCP."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_core.v43.plugins.datastore import cli as cli_module
from dhis2w_core.v43.plugins.datastore import mcp as mcp_module


class _DatastorePlugin(BaseModel):
    """Plugin descriptor for the DHIS2 key-value data store."""

    model_config = ConfigDict(frozen=True)

    name: str = "datastore"
    description: str = (
        "DHIS2 key-value data store: namespaced get/set/delete over /api/dataStore (shared) and "
        "/api/userDataStore (per-user, --user)."
    )

    def register_cli(self, app: Any) -> None:
        """Mount the datastore sub-app under `d2w datastore`."""
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register the `datastore_*` MCP tools."""
        mcp_module.register(mcp)


plugin = _DatastorePlugin()
