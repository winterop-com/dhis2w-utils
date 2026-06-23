"""View-models for the `query` plugin: explain output exposed by the CLI and MCP."""

from __future__ import annotations

from typing import Literal

from dhis2w_ql import NativeQuery
from pydantic import BaseModel, ConfigDict


class QueryExplain(BaseModel):
    """How a pipeline splits between DHIS2-native pushdown and local d2ql evaluation."""

    model_config = ConfigDict(frozen=True)

    source: str
    source_kind: Literal["resource", "read", "expression", "call"]
    pushed_down: NativeQuery | None = None
    residual_stages: list[str] = []
    note: str | None = None
