"""The settings the FHIR facade app factory is built from."""

from __future__ import annotations

from pathlib import Path

from dhis2w_fhir.config import DEFAULT_BASEMAP_TEMPLATE
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.capture.validate import DEFAULT_STRICT_CODES


class ServeSettings(BaseModel):
    """Everything the app factory needs to build the FHIR facade for one project.

    Host and port stay uvicorn-side: they describe where the process listens, not what
    it serves, so the factory never sees them. `live` selects a store built from a live
    DHIS2 instance over the compiled IG on disk, `profile` names the DHIS2 profile that
    store connects with, and `strict_codes` rejects a received answer whose code is not
    in the served terminology instead of recording a warning.

    `strict_codes` is the runtime source every capture is validated against; the default it
    starts from lives with the capture path, in `capture.validate.DEFAULT_STRICT_CODES`.

    `ui` serves the built capture UI at `/`, same-origin with the FHIR routes it talks to. It is
    off by default: a facade is an endpoint first, and a process answering `/metadata` for a
    scripted client has no reason to also hold a React bundle open.

    `basemap` is the raster tile template the UI's organisation-unit map draws under the
    boundaries, and `"none"` turns it off. It lives here rather than being read from the project
    at request time for the same reason `strict_codes` does: a flag may override the table, so the
    resolved value is a property of this run.
    """

    model_config = ConfigDict(frozen=True)

    project_dir: Path
    live: bool = False
    profile: str | None = None
    strict_codes: bool = DEFAULT_STRICT_CODES
    ui: bool = False
    basemap: str = DEFAULT_BASEMAP_TEMPLATE
