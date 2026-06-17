"""Load the router's upstream-server list from a JSON config file (env `MCP_ROUTER_CONFIG`).

The config is domain-neutral — it names whatever MCP servers to front. Example (`mcp-router.json`):

    {
      "servers": [
        {"name": "dhis2", "command": "uv", "args": ["run", "--directory", "/repo", "dhis2w-mcp"],
         "env": {"DHIS2_PROFILE": "play42"}}
      ]
    }
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from dhis2w_mcp_router.core import UpstreamServer

#: Env var pointing at the router config file; falls back to `mcp-router.json` in the working directory.
CONFIG_ENV = "MCP_ROUTER_CONFIG"
DEFAULT_CONFIG = "mcp-router.json"


class RouterConfig(BaseModel):
    """The router config file: the list of upstream MCP servers to front."""

    model_config = ConfigDict(frozen=True)

    servers: list[UpstreamServer]


def config_path() -> Path:
    """Return the configured router config path (env override, else the default file)."""
    return Path(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG))


def load_servers() -> list[UpstreamServer]:
    """Read the configured upstream MCP servers; raise if the config file is missing."""
    path = config_path()
    if not path.is_file():
        raise FileNotFoundError(f"router config not found at {path} (set {CONFIG_ENV} to point at one)")
    return RouterConfig.model_validate_json(path.read_text()).servers
