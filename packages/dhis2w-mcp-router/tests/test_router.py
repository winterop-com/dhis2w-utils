"""Unit tests for the domain-neutral router core (no live MCP servers)."""

from __future__ import annotations

import pytest
from dhis2w_mcp_router.core import Registry, ToolEntry, UpstreamServer


def _entry(name: str, server: str, bare: str, description: str) -> ToolEntry:
    """Build a ToolEntry with an empty schema for search/dispatch tests."""
    return ToolEntry(name=name, server=server, bare=bare, description=description, input_schema={})


def _registry_with(*entries: ToolEntry) -> Registry:
    """A registry pre-seeded with entries, bypassing live upstream connection."""
    registry = Registry([])
    for entry in entries:
        registry._entries[entry.name] = entry  # noqa: SLF001 — test seam for the domain-neutral search
    return registry


def test_upstream_client_config_merges_parent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The upstream config keeps the parent environment and layers the per-server overrides on top."""
    monkeypatch.setenv("PATH", "/usr/bin")
    server = UpstreamServer(name="dhis2", command="uv", args=["run", "dhis2w-mcp"], env={"DHIS2_PROFILE": "play42"})
    cfg = server.client_config()["mcpServers"]["dhis2"]
    assert cfg["command"] == "uv"
    assert cfg["args"] == ["run", "dhis2w-mcp"]
    assert cfg["env"]["DHIS2_PROFILE"] == "play42"
    assert cfg["env"]["PATH"] == "/usr/bin"  # parent env merged, not replaced


async def test_search_ranks_by_term_hits_and_excludes_misses() -> None:
    """Search ranks tools by how many query terms hit, and drops tools with zero hits."""
    registry = _registry_with(
        _entry("dhis2__metadata_data_set_create", "dhis2", "metadata_data_set_create", "Create a data set"),
        _entry("dhis2__metadata_data_element_create", "dhis2", "metadata_data_element_create", "Create a data element"),
        _entry("dhis2__system_info", "dhis2", "system_info", "System information"),
    )
    hits = await registry.search("data set", limit=5)
    assert hits[0].name == "dhis2__metadata_data_set_create"  # matches both 'data' and 'set'
    assert all(hit.name != "dhis2__system_info" for hit in hits)  # no term hit -> excluded


async def test_search_empty_query_lists_alphabetically() -> None:
    """An empty query is a browse: every tool, name-sorted for determinism."""
    registry = _registry_with(_entry("b__t", "b", "t", "x"), _entry("a__t", "a", "t", "x"))
    assert [hit.name for hit in await registry.search("", limit=10)] == ["a__t", "b__t"]


async def test_search_honours_limit() -> None:
    """Search returns at most `limit` results."""
    registry = _registry_with(*[_entry(f"s__t{i}", "s", f"t{i}", "a tool") for i in range(5)])
    assert len(await registry.search("tool", limit=2)) == 2


async def test_call_unknown_tool_raises() -> None:
    """Dispatching an unregistered name is a clear KeyError pointing at search_tools."""
    registry = _registry_with(_entry("s__t", "s", "t", "x"))
    with pytest.raises(KeyError, match="unknown tool"):
        await registry.call("s__missing", {})


def test_tool_entry_summary_is_the_agent_facing_shape() -> None:
    """summary() returns exactly the name/description/schema the agent needs to call the tool."""
    entry = _entry("dhis2__system_info", "dhis2", "system_info", "System information")
    assert entry.summary() == {
        "name": "dhis2__system_info",
        "description": "System information",
        "input_schema": {},
    }


async def test_readonly_registry_hides_and_refuses_writes() -> None:
    """A read-only registry drops write tools from search and refuses them at dispatch."""
    registry = Registry([], readonly=True)
    registry._entries["dhis2__metadata_count"] = _entry("dhis2__metadata_count", "dhis2", "metadata_count", "Count")  # noqa: SLF001
    registry._entries["dhis2__data_set_create"] = _entry("dhis2__data_set_create", "dhis2", "data_set_create", "Create")  # noqa: SLF001
    names = [hit.name for hit in await registry.search("", limit=10)]
    assert "dhis2__metadata_count" in names  # read survives
    assert "dhis2__data_set_create" not in names  # write hidden


async def test_readonly_call_refuses_write_with_permission_error() -> None:
    """Dispatching a write tool through a read-only registry raises PermissionError."""
    registry = Registry([], readonly=True)
    registry._entries["dhis2__data_set_create"] = _entry("dhis2__data_set_create", "dhis2", "data_set_create", "Create")  # noqa: SLF001
    with pytest.raises(PermissionError, match="read-only"):
        await registry.call("dhis2__data_set_create", {})


def test_is_read_honours_annotation_then_falls_back_to_verb() -> None:
    """is_read uses the readOnlyHint annotation when present, else the bare-name verb."""
    from dhis2w_mcp_router.core import DEFAULT_READ_VERBS, ToolEntry

    by_verb_read = ToolEntry(name="s__system_info", server="s", bare="system_info", description="", input_schema={})
    by_verb_write = _entry("s__data_set_create", "s", "data_set_create", "")
    annotated_write = ToolEntry(
        name="s__looks_get", server="s", bare="looks_get", description="", input_schema={}, read_only_hint=False
    )
    assert by_verb_read.is_read(DEFAULT_READ_VERBS) is True
    assert by_verb_write.is_read(DEFAULT_READ_VERBS) is False
    assert annotated_write.is_read(DEFAULT_READ_VERBS) is False  # annotation overrides the read-looking verb


async def test_per_server_readonly_denies_only_that_server() -> None:
    """A server flagged readonly denies its writes; a non-flagged server still permits writes."""
    from dhis2w_mcp_router.core import UpstreamServer

    servers = [UpstreamServer(name="play", command="x", readonly=True), UpstreamServer(name="local", command="x")]
    registry = Registry(servers)
    registry._entries["play__data_set_create"] = _entry("play__data_set_create", "play", "data_set_create", "Create")  # noqa: SLF001
    registry._entries["local__data_set_create"] = _entry("local__data_set_create", "local", "data_set_create", "Create")  # noqa: SLF001
    names = [hit.name for hit in await registry.search("create", limit=10)]
    assert "local__data_set_create" in names  # writable server
    assert "play__data_set_create" not in names  # read-only server's write hidden


def test_cosine_similarity() -> None:
    """Cosine is 1 for identical vectors, 0 for orthogonal, and 0 for a degenerate (zero) vector."""
    from dhis2w_mcp_router.ranking import _cosine

    assert _cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


async def test_embedding_ranker_orders_by_cosine() -> None:
    """The embedding ranker ranks the tool whose vector is closest to the query first (mocked embeddings)."""
    from dhis2w_mcp_router.core import ToolEntry
    from dhis2w_mcp_router.ranking import EmbeddingRanker

    table = {
        "dhis2__metadata_count Count data elements": [1.0, 0.0],
        "dhis2__analytics_query Query analytics data": [0.0, 1.0],
        "how many data elements": [0.9, 0.1],  # closest to the count tool
    }

    class _FakeRanker(EmbeddingRanker):
        async def _embed(self, inputs: list[str]) -> list[list[float]]:  # noqa: D102 — test override of the HTTP call
            return [table[text] for text in inputs]

    entries = [
        ToolEntry(
            name="dhis2__metadata_count",
            server="dhis2",
            bare="metadata_count",
            description="Count data elements",
            input_schema={},
        ),  # noqa: E501
        ToolEntry(
            name="dhis2__analytics_query",
            server="dhis2",
            bare="analytics_query",
            description="Query analytics data",
            input_schema={},
        ),  # noqa: E501
    ]
    ranker = _FakeRanker("http://x/v1/embeddings", "m")
    await ranker.prepare(entries)
    hits = await ranker.rank("how many data elements", entries, limit=2)
    assert hits[0].name == "dhis2__metadata_count"  # cosine beats the keyword mis-rank


def test_router_config_parses_optional_embeddings() -> None:
    """The router config accepts an optional embeddings block; absent means keyword ranking."""
    from dhis2w_mcp_router.config import RouterConfig

    with_embed = RouterConfig.model_validate(
        {"servers": [{"name": "d", "command": "x"}], "embeddings": {"url": "http://x", "model": "m"}}
    )
    assert with_embed.embeddings is not None
    assert with_embed.embeddings.model == "m"
    assert RouterConfig.model_validate({"servers": []}).embeddings is None


# --- Registry build: concurrency + partial-failure retry ------------------------------------


class _FakeUpstreamTool:
    """Bare tool shape (`name` only) — the registry reads the rest via getattr defaults."""

    def __init__(self, name: str) -> None:
        """Carry just the tool name."""
        self.name = name


class _FakeUpstreamClient:
    """Stands in for `fastmcp.Client`: counts spawns per server and lists one canned tool."""

    spawn_counts: dict[str, int] = {}
    fail_first_connect: set[str] = set()

    def __init__(self, config: dict[str, dict[str, object]]) -> None:
        """Record which upstream this client was spawned for."""
        self.server_name = next(iter(config["mcpServers"]))
        counts = type(self).spawn_counts
        counts[self.server_name] = counts.get(self.server_name, 0) + 1

    async def __aenter__(self) -> _FakeUpstreamClient:
        """Yield to the loop (so concurrent builders interleave); fail the first marked connect."""
        import asyncio

        await asyncio.sleep(0)
        if self.server_name in type(self).fail_first_connect and type(self).spawn_counts[self.server_name] == 1:
            raise RuntimeError(f"upstream {self.server_name!r} refused the first connect")
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Nothing to close."""
        return None

    async def list_tools(self) -> list[_FakeUpstreamTool]:
        """One canned read tool per upstream."""
        return [_FakeUpstreamTool(f"{self.server_name}_info")]


@pytest.fixture
def fake_upstreams(monkeypatch: pytest.MonkeyPatch) -> type[_FakeUpstreamClient]:
    """Patch the registry's `Client` with the counting fake and reset its class state."""
    from dhis2w_mcp_router import core as core_module

    _FakeUpstreamClient.spawn_counts = {}
    _FakeUpstreamClient.fail_first_connect = set()
    monkeypatch.setattr(core_module, "Client", _FakeUpstreamClient)
    return _FakeUpstreamClient


async def test_ensure_built_concurrent_calls_spawn_each_upstream_once(
    fake_upstreams: type[_FakeUpstreamClient],
) -> None:
    """Concurrent first calls serialise on the build lock — every upstream spawns exactly once."""
    import asyncio

    registry = Registry([UpstreamServer(name="alpha", command="x"), UpstreamServer(name="beta", command="x")])

    await asyncio.gather(*(registry.ensure_built() for _ in range(3)))

    assert fake_upstreams.spawn_counts == {"alpha": 1, "beta": 1}
    assert registry.built
    assert registry.tool_count() == 2


async def test_ensure_built_retry_after_partial_failure_reconnects_only_the_missing_upstream(
    fake_upstreams: type[_FakeUpstreamClient],
) -> None:
    """A failing upstream on attempt 1 doesn't make attempt 2 respawn the healthy upstreams."""
    fake_upstreams.fail_first_connect = {"flaky"}
    registry = Registry([UpstreamServer(name="steady", command="x"), UpstreamServer(name="flaky", command="x")])

    with pytest.raises(RuntimeError, match="refused the first connect"):
        await registry.ensure_built()
    assert not registry.built

    await registry.ensure_built()

    assert fake_upstreams.spawn_counts == {"steady": 1, "flaky": 2}
    assert registry.built
    assert registry.tool_count() == 2
    assert "steady__steady_info" in {entry.name for entry in await registry.search("", limit=10)}


# --- Ranking strictness ----------------------------------------------------------------------


def test_cosine_dimension_mismatch_raises() -> None:
    """Mismatched vector dimensions are an error, not a silent truncation."""
    from dhis2w_mcp_router.ranking import _cosine

    with pytest.raises(ValueError, match="dimension mismatch"):
        _cosine([1.0, 0.0], [1.0])


async def test_embedding_prepare_rejects_vector_count_mismatch() -> None:
    """Fewer vectors than inputs is an error, not silently dropped tools."""
    from dhis2w_mcp_router.ranking import EmbeddingRanker

    class _ShortRanker(EmbeddingRanker):
        async def _embed(self, inputs: list[str]) -> list[list[float]]:  # noqa: D102 — test override of the HTTP call
            return [[1.0, 0.0]]

    entries = [_entry("s__a_get", "s", "a_get", "a"), _entry("s__b_get", "s", "b_get", "b")]
    with pytest.raises(RuntimeError, match="returned 1 vectors for 2 inputs"):
        await _ShortRanker("http://x/v1/embeddings", "m").prepare(entries)
