"""Domain-neutral MCP router core: a registry over upstream MCP servers with search + dispatch.

No DHIS2 (or any domain) imports — it fronts whatever MCP servers the config names. The two operations
an agent needs are `search` (find tools by keyword over name + description) and `call` (dispatch a tool
by its namespaced `server__tool` name). Upstream connections are opened once and reused. This is the
portable, MCP-native equivalent of the Claude SDK's ToolSearch: it gives ANY client lazy, searchable
tool discovery instead of a huge up-front tool payload.
"""

from __future__ import annotations

import os
from contextlib import AsyncExitStack
from typing import Any

from fastmcp import Client
from pydantic import BaseModel, ConfigDict

#: Separator between an upstream server's name and a tool's bare name in the namespaced id.
_NS = "__"


class UpstreamServer(BaseModel):
    """A stdio MCP server the router fronts."""

    model_config = ConfigDict(frozen=True)

    name: str
    command: str
    args: list[str] = []
    env: dict[str, str] = {}

    def client_config(self) -> dict[str, Any]:
        """FastMCP client config spawning just this upstream (env merges the parent environment)."""
        return {
            "mcpServers": {
                self.name: {"command": self.command, "args": list(self.args), "env": {**os.environ, **self.env}}
            }
        }


class ToolEntry(BaseModel):
    """One upstream tool, namespaced and carrying its schema so an agent can call it."""

    model_config = ConfigDict(frozen=True)

    name: str
    server: str
    bare: str
    description: str
    input_schema: dict[str, Any]

    def summary(self) -> dict[str, Any]:
        """The shape returned to the agent from `search_tools`."""
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def _score(entry: ToolEntry, terms: list[str]) -> int:
    """Keyword score: how many query terms appear in the tool's name or description (case-insensitive)."""
    haystack = f"{entry.name} {entry.description}".lower()
    return sum(1 for term in terms if term in haystack)


class Registry:
    """Holds upstream tool metadata + open clients; lazily built, then searched and dispatched against."""

    def __init__(self, servers: list[UpstreamServer]) -> None:
        """Take the upstream servers to front; nothing connects until `ensure_built`."""
        self._servers = list(servers)
        self._entries: dict[str, ToolEntry] = {}
        self._clients: dict[str, Client] = {}
        self._stack = AsyncExitStack()
        self._built = False

    @property
    def built(self) -> bool:
        """True once every upstream has been connected and its tools registered."""
        return self._built

    def tool_count(self) -> int:
        """Number of registered upstream tools."""
        return len(self._entries)

    async def ensure_built(self) -> None:
        """Connect to every upstream once, list + namespace its tools (idempotent)."""
        if self._built:
            return
        for server in self._servers:
            client = await self._stack.enter_async_context(Client(server.client_config()))
            self._clients[server.name] = client
            for tool in await client.list_tools():
                name = f"{server.name}{_NS}{tool.name}"
                self._entries[name] = ToolEntry(
                    name=name,
                    server=server.name,
                    bare=tool.name,
                    description=getattr(tool, "description", "") or "",
                    input_schema=getattr(tool, "inputSchema", {}) or {},
                )
        self._built = True

    def search(self, query: str, limit: int = 10) -> list[ToolEntry]:
        """Rank tools by how many query terms hit name + description; an empty query lists alphabetically."""
        terms = [term for term in query.lower().split() if term]
        if not terms:
            return sorted(self._entries.values(), key=lambda entry: entry.name)[:limit]
        scored = [(score, entry) for entry in self._entries.values() if (score := _score(entry, terms)) > 0]
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        return [entry for _, entry in scored[:limit]]

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Dispatch a namespaced tool to its upstream and return the result text."""
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError(f"unknown tool {name!r}; call search_tools to discover names")
        result = await self._clients[entry.server].call_tool(entry.bare, arguments)
        return _result_text(result)

    async def aclose(self) -> None:
        """Close every upstream connection."""
        await self._stack.aclose()
        self._clients.clear()
        self._built = False


def _result_text(result: object) -> str:
    """Extract text from a FastMCP `call_tool` result (its `.data`, else its content blocks)."""
    data = getattr(result, "data", None)
    if data is not None:
        return data if isinstance(data, str) else str(data)
    content = getattr(result, "content", None) or []
    texts = [getattr(block, "text", "") for block in content]
    return "\n".join(text for text in texts if text)
