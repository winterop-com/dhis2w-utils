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


class EmbeddingsConfig(BaseModel):
    """Optional embedding-ranker config: an OpenAI-compatible `/v1/embeddings` endpoint + model."""

    model_config = ConfigDict(frozen=True)

    url: str
    model: str


class RouterConfig(BaseModel):
    """The router config file: upstream MCP servers to front, plus an optional embedding ranker."""

    model_config = ConfigDict(frozen=True)

    servers: list[UpstreamServer]
    embeddings: EmbeddingsConfig | None = None


def config_path() -> Path:
    """Return the configured router config path (env override, else the default file)."""
    return Path(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG))


def load_config() -> RouterConfig:
    """Read the full router config; raise if the config file is missing."""
    path = config_path()
    if not path.is_file():
        raise FileNotFoundError(f"router config not found at {path} (set {CONFIG_ENV} to point at one)")
    return RouterConfig.model_validate_json(path.read_text())


def load_servers() -> list[UpstreamServer]:
    """Read the configured upstream MCP servers."""
    return load_config().servers
