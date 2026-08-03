"""Generated Access model for DHIS2 v41. Do not edit by hand."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Access(BaseModel):
    """Generated model for DHIS2 `Access`.

    DHIS2 Access - DHIS2 resource (generated from /api/schemas at DHIS2 v41).

    Transient — not stored in the DHIS2 database (computed / projection).

    Field `Field(description=...)` entries flag DHIS2 semantics the bare
    type can't capture: which side of a relationship owns the link
    (writable) vs the inverse side (ignored by the API), uniqueness
    constraints, and length bounds.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    data: Any | None = Field(default=None, description="Reference to AccessData. Read-only (inverse side).")
    delete: bool | None = None
    manage: bool | None = None
    read: bool | None = None
    update: bool | None = None
    write: bool | None = None
