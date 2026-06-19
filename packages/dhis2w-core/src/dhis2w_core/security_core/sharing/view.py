"""Project a SharingGraph into the window.__SHARING__ payload the explorer runtime reads.

Mirrors `security_core/report/view.py`: a view model that serializes to an assignable JavaScript
statement written into `sharing-data.js`. The whole graph is the payload (the explorer is a pure
function of it), wrapped with the run identity the header shows but the graph itself does not carry.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.sharing.model import SharingGraph


class SharingExplorerMeta(BaseModel):
    """Run identity shown in the explorer header (fields the graph does not carry itself)."""

    model_config = ConfigDict(frozen=True)

    target: str
    profile: str
    version: str
    scanner: str
    generated: str


class SharingView(BaseModel):
    """The full window.__SHARING__ object: the run meta plus the complete access graph."""

    model_config = ConfigDict(frozen=True)

    meta: SharingExplorerMeta
    graph: SharingGraph

    def to_sharing_data_js(self) -> str:
        """Render the assignable JavaScript payload written to sharing-data.js."""
        return f"window.__SHARING__ = {self.model_dump_json()};\n"


def build_sharing_view(graph: SharingGraph, *, profile: str, version: str, scanner: str) -> SharingView:
    """Project a graph plus the run identity into the explorer payload view."""
    meta = SharingExplorerMeta(
        target=graph.target,
        profile=profile,
        version=version,
        scanner=scanner,
        generated=graph.generated_at,
    )
    return SharingView(meta=meta, graph=graph)
