"""Pluggable rankers for `search_tools`: keyword (default, no deps) and embedding (optional).

A `Ranker` decides which upstream tools best match a query. `KeywordRanker` scores by query-term hits
over name + description — fast, dependency-free, but crude (a term can hit the wrong tool's
description). `EmbeddingRanker` ranks by cosine similarity against an OpenAI-compatible `/v1/embeddings`
endpoint (e.g. a local embedder served by LM Studio / Ollama), which understands meaning rather than
substrings. Both are async so a ranker may do IO (the embedding one does).
"""

from __future__ import annotations

import math
from typing import Protocol, runtime_checkable

import httpx

from dhis2w_mcp_router.core import ToolEntry


@runtime_checkable
class Ranker(Protocol):
    """Ranks tool entries against a query; `prepare` is called once after the registry is built."""

    async def prepare(self, entries: list[ToolEntry]) -> None:
        """Precompute whatever the ranker needs from the full entry set (a no-op for keyword)."""
        ...

    async def rank(self, query: str, entries: list[ToolEntry], limit: int) -> list[ToolEntry]:
        """Return up to `limit` entries best matching `query` (an empty query lists alphabetically)."""
        ...


def _keyword_score(entry: ToolEntry, terms: list[str]) -> int:
    """How many query terms appear in the tool's name or description (case-insensitive)."""
    haystack = f"{entry.name} {entry.description}".lower()
    return sum(1 for term in terms if term in haystack)


class KeywordRanker:
    """Default ranker: substring term-hit scoring over name + description. No dependencies, no IO."""

    async def prepare(self, entries: list[ToolEntry]) -> None:
        """Nothing to precompute."""
        return

    async def rank(self, query: str, entries: list[ToolEntry], limit: int) -> list[ToolEntry]:
        """Rank by query-term hits; ties broken by name; empty query lists alphabetically."""
        terms = [term for term in query.lower().split() if term]
        if not terms:
            return sorted(entries, key=lambda entry: entry.name)[:limit]
        scored = [(score, entry) for entry in entries if (score := _keyword_score(entry, terms)) > 0]
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        return [entry for _, entry in scored[:limit]]


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors (0.0 if either is degenerate)."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class EmbeddingRanker:
    """Ranker that scores tools by cosine similarity against an OpenAI-compatible embeddings endpoint."""

    def __init__(self, url: str, model: str) -> None:
        """Embed against `url` (an OpenAI `/v1/embeddings` endpoint) using `model`."""
        self._url = url
        self._model = model
        self._vectors: dict[str, list[float]] = {}

    async def prepare(self, entries: list[ToolEntry]) -> None:
        """Embed every tool's `name + description` once and cache the vectors by tool name."""
        if not entries:
            return
        texts = [f"{entry.name} {entry.description}" for entry in entries]
        vectors = await self._embed(texts)
        self._vectors = {entry.name: vector for entry, vector in zip(entries, vectors, strict=False)}

    async def rank(self, query: str, entries: list[ToolEntry], limit: int) -> list[ToolEntry]:
        """Rank permitted entries by cosine similarity to the embedded query; empty query lists alphabetically."""
        if not query.strip():
            return sorted(entries, key=lambda entry: entry.name)[:limit]
        (query_vector,) = await self._embed([query])
        scored = [
            (_cosine(query_vector, self._vectors[entry.name]), entry)
            for entry in entries
            if entry.name in self._vectors
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        return [entry for _, entry in scored[:limit]]

    async def _embed(self, inputs: list[str]) -> list[list[float]]:
        """POST `inputs` to the embeddings endpoint and return their vectors in input order."""
        async with httpx.AsyncClient() as http:
            response = await http.post(self._url, json={"model": self._model, "input": inputs}, timeout=120.0)
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in data]
