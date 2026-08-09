"""`GET /uiconfig` - the handful of run-time settings the capture UI is allowed to know.

WHY THIS EXISTS AT ALL. Everything else the UI renders it reads out of FHIR: the forms are
Questionnaires, the hierarchy is Locations, the server's own identity is the CapabilityStatement.
This is the one class of fact that is none of those - not something the guide published, but
something about *how this process was started*. `[serve] basemap` is the whole of it today: the
organisation-unit map draws raster tiles under the boundaries, and which tiles (or none at all) is
a deployment decision made in fhir.toml or on the command line, which a bundle compiled weeks
earlier cannot know.

WHY NOT `/metadata`. A CapabilityStatement describes the FHIR interface - what a client may read,
search, and post. A tile template is not part of that interface and would have to ride in an
extension on a document every FHIR client parses, to say something no FHIR client wants.

SO IT IS `/spool`'s SHAPE, FOR `/spool`'s REASONS. A plain typed JSON endpoint, `application/json`,
Pydantic models rather than a Bundle, on a single lowercase segment. FHIR resource types are
PascalCase, so `/uiconfig` can never shadow one, and the router mounts with the other fixed paths -
ahead of `/{resource_type}`, which would otherwise claim it and answer that this server does not
serve the resource type `uiconfig`. `dhis2w_fhir_serve.routes.spool` argues that choice in full;
this module inherits it rather than restating it.

WHAT IT DELIBERATELY DOES NOT CARRY. Not the profile, not the host and port, not `live`, not
`strict_codes`. Those describe the process to whoever runs it, and a browser that could read them
would be a browser that leaks them. Only the settings the UI has to act on belong here, and the
model is the enumeration of exactly those.
"""

from __future__ import annotations

from dhis2w_fhir.config import BASEMAP_DISABLED, DEFAULT_BASEMAP_TEMPLATE
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request

from dhis2w_fhir_serve.routes.context import serve_context

#: Where the settings are served from. One lowercase segment, so no FHIR resource type can collide.
UI_CONFIG_PATH = "/uiconfig"

#: The attribution OpenStreetMap's tile policy requires of anything drawing its standard tiles.
#:
#: Rendered by MapLibre's own attribution control, which is why it is markup: the control accepts
#: an HTML string and the link to the copyright page is not optional.
OPENSTREETMAP_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" '
    'rel="noreferrer">OpenStreetMap</a> contributors'
)

#: The host whose tiles this server knows the attribution for.
OPENSTREETMAP_TILE_HOST = "tile.openstreetmap.org"

router = APIRouter()


class BasemapConfig(BaseModel):
    """The raster tiles the organisation-unit map draws under the boundaries, and who to credit for them.

    `attribution` is derived rather than configured, and the rule is narrow on purpose: this server
    knows what OpenStreetMap's tile policy requires because it ships that template as its default,
    and it knows nothing about the terms of a tile source someone else points it at. So a custom
    template gets no attribution string from here, and the guide says that crediting it is the
    deployment's own obligation - which is more honest than inventing a credit line or, worse,
    leaving OpenStreetMap's on somebody else's tiles.
    """

    model_config = ConfigDict(frozen=True)

    template: str
    """The `{z}/{x}/{y}` raster tile URL template."""

    attribution: str | None = None
    """The credit line the map must display, as HTML, or None when this server cannot know it."""


class UiConfig(BaseModel):
    """What the capture UI may know about how this facade was started.

    `basemap` is None when the tiles are off, which is a state the UI renders rather than an
    absence it has to guess at: the map falls back to the boundary-only canvas it drew before
    tiles existed.
    """

    model_config = ConfigDict(frozen=True)

    basemap: BasemapConfig | None = None


@router.get(UI_CONFIG_PATH)
async def read_ui_config(request: Request) -> UiConfig:
    """Answer the run-time settings the UI acts on, resolved for this process."""
    settings = serve_context(request).settings
    return UiConfig(basemap=basemap_config(settings.basemap))


def basemap_config(template: str) -> BasemapConfig | None:
    """One `[serve] basemap` value as the UI reads it, or None when it turns the tiles off."""
    resolved = None if template.strip().lower() == BASEMAP_DISABLED else template.strip()
    if resolved is None or resolved == "":
        return None
    return BasemapConfig(template=resolved, attribution=_attribution(resolved))


def _attribution(template: str) -> str | None:
    """The credit line for a tile template, which this server knows only for its own default."""
    if template == DEFAULT_BASEMAP_TEMPLATE or OPENSTREETMAP_TILE_HOST in template:
        return OPENSTREETMAP_ATTRIBUTION
    return None
