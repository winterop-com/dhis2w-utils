"""The settings the FHIR facade app factory is built from."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ServeSettings(BaseModel):
    """Everything the app factory needs to build the FHIR facade for one project.

    Host and port stay uvicorn-side: they describe where the process listens, not what
    it serves, so the factory never sees them. `live` selects a store built from a live
    DHIS2 instance over the compiled IG on disk, `profile` names the DHIS2 profile that
    store connects with, and `strict_codes` rejects a received answer whose code is not
    in the served terminology instead of recording a warning.
    """

    model_config = ConfigDict(frozen=True)

    project_dir: Path
    live: bool = False
    profile: str | None = None
    strict_codes: bool = False
