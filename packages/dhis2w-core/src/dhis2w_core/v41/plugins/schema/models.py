"""View-models for the `schema` plugin."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SchemaField(BaseModel):
    """One field of a generated type: name, rendered type, requiredness, and description."""

    model_config = ConfigDict(frozen=True)

    name: str
    type: str
    required: bool
    description: str | None = None


class TypeSchema(BaseModel):
    """The introspected shape of one generated type (metadata or instance-side)."""

    model_config = ConfigDict(frozen=True)

    name: str
    source: str
    version: str
    field_count: int
    fields: list[SchemaField]
