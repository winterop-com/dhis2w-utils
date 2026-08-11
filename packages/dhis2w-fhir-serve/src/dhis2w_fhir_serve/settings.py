"""The settings the FHIR facade app factory is built from."""

from __future__ import annotations

from pathlib import Path

from dhis2w_fhir.config import DEFAULT_BASEMAPS, BasemapSource
from pydantic import BaseModel, ConfigDict, Field

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

    `basemaps` are the raster tile layers the UI's organisation-unit map offers under the
    boundaries, first one first, and an empty list offers none. They live here rather than being
    read from the project at request time for the same reason `strict_codes` does: a flag may
    override the table, so the resolved value is a property of this run.

    `dhis2_base_url` is the address of the instance this run resolved a profile for, and None when
    it resolved none - a compiled guide served on a machine that names no profile is a whole,
    supported posture. It is what the UI links an organisation unit, a form, or a data element out
    to; with no address there are no links, which is the honest rendering of not knowing which of a
    hundred DHIS2 instances a guide was generated from. The profile's NAME and its credentials stay
    here and never reach a browser - see `dhis2w_fhir_serve.routes.uiconfig`.
    """

    model_config = ConfigDict(frozen=True)

    project_dir: Path
    live: bool = False
    profile: str | None = None
    strict_codes: bool = DEFAULT_STRICT_CODES
    ui: bool = False
    basemaps: list[BasemapSource] = Field(default_factory=lambda: list(DEFAULT_BASEMAPS))
    dhis2_base_url: str | None = None
