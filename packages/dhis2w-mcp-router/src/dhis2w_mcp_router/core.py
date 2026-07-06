"""Domain-neutral MCP router core: a registry over upstream MCP servers with search + dispatch.

No DHIS2 (or any domain) imports — it fronts whatever MCP servers the config names. The two operations
an agent needs are `search` (find tools by keyword over name + description) and `call` (dispatch a tool
by its namespaced `server__tool` name). Upstream connections are opened once and reused. This is the
portable, MCP-native equivalent of the Claude SDK's ToolSearch: it gives ANY client lazy, searchable
tool discovery instead of a huge up-front tool payload.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Any

from fastmcp import Client
from pydantic import BaseModel, ConfigDict

#: Separator between an upstream server's name and a tool's bare name in the namespaced id.
_NS = "__"

#: Default read-verb suffixes for classifying a tool read-only when it carries no `readOnlyHint`
#: annotation (its bare name ends in one of these). Fail-closed: anything else counts as a write.
DEFAULT_READ_VERBS: frozenset[str] = frozenset(
    {
        "get", "list", "ls", "count", "find", "search", "show", "info", "whoami", "me", "tree",
        "members", "query", "namespaces", "keys", "usage", "diff", "verify", "status", "result", "outstanding",
    }
)  # fmt: skip


class UpstreamServer(BaseModel):
    """A stdio MCP server the router fronts."""

    model_config = ConfigDict(frozen=True)

    name: str
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    #: When true, only this upstream's read tools are dispatchable (e.g. front a shared host read-only).
    readonly: bool = False

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
    #: The upstream tool's MCP `readOnlyHint` annotation when it set one; None when unknown.
    read_only_hint: bool | None = None

    def summary(self) -> dict[str, Any]:
        """The shape returned to the agent from `search_tools`."""
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}

    def is_read(self, read_verbs: frozenset[str]) -> bool:
        """True when this tool is read-only — by its `readOnlyHint` annotation, else its bare-name verb."""
        if self.read_only_hint is not None:
            return self.read_only_hint
        return self.bare.rsplit("_", 1)[-1] in read_verbs


class Registry:
    """Holds upstream tool metadata + open clients; lazily built, then searched and dispatched against."""

    def __init__(
        self,
        servers: list[UpstreamServer],
        *,
        readonly: bool = False,
        read_verbs: frozenset[str] = DEFAULT_READ_VERBS,
        ranker: object | None = None,
    ) -> None:
        """Take the upstream servers to front; `readonly` denies writes, `ranker` decides search order."""
        from dhis2w_mcp_router.ranking import KeywordRanker, Ranker

        self._servers = list(servers)
        self._entries: dict[str, ToolEntry] = {}
        self._clients: dict[str, Client] = {}
        self._stack = AsyncExitStack()
        self._build_lock = asyncio.Lock()
        self._built = False
        self._readonly = readonly
        self._read_verbs = read_verbs
        self._readonly_servers = {server.name for server in servers if server.readonly}
        self._ranker: Ranker = ranker if isinstance(ranker, Ranker) else KeywordRanker()

    def _permits(self, entry: ToolEntry) -> bool:
        """Whether the entry is dispatchable: always for reads; for writes only when not in a read-only context."""
        writable = not self._readonly and entry.server not in self._readonly_servers
        return writable or entry.is_read(self._read_verbs)

    @property
    def built(self) -> bool:
        """True once every upstream has been connected and its tools registered."""
        return self._built

    def tool_count(self) -> int:
        """Number of registered upstream tools."""
        return len(self._entries)

    async def ensure_built(self) -> None:
        """Connect to every upstream once, list + namespace its tools (idempotent, concurrency-safe).

        A lock serialises concurrent first calls so upstream servers spawn once, not once per
        caller. On a partial failure (one upstream refusing to connect) the successfully opened
        clients stay registered in `_clients`; a retry connects only the missing upstreams and
        re-lists tools from the surviving ones, so nothing is spawned twice or leaked.
        """
        if self._built:
            return
        async with self._build_lock:
            if self._built:
                return
            for server in self._servers:
                if server.name not in self._clients:
                    client = await self._stack.enter_async_context(Client(server.client_config()))
                    self._clients[server.name] = client
                for tool in await self._clients[server.name].list_tools():
                    name = f"{server.name}{_NS}{tool.name}"
                    annotations = getattr(tool, "annotations", None)
                    self._entries[name] = ToolEntry(
                        name=name,
                        server=server.name,
                        bare=tool.name,
                        description=getattr(tool, "description", "") or "",
                        input_schema=getattr(tool, "inputSchema", {}) or {},
                        read_only_hint=getattr(annotations, "readOnlyHint", None) if annotations else None,
                    )
            await self._ranker.prepare(list(self._entries.values()))
            self._built = True

    async def search(self, query: str, limit: int = 10) -> list[ToolEntry]:
        """Rank the permitted tools (read-only context hides write tools) via the configured ranker."""
        candidates = [entry for entry in self._entries.values() if self._permits(entry)]
        return await self._ranker.rank(query, candidates, limit)

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Dispatch a namespaced tool to its upstream and return the result text; refuse writes when read-only."""
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError(f"unknown tool {name!r}; call search_tools to discover names")
        if not self._permits(entry):
            raise PermissionError(f"read-only router: tool {name!r} is a write and is refused")
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
