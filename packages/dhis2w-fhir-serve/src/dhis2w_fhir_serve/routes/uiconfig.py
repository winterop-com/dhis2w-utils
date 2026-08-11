"""`GET /uiconfig` - the handful of run-time settings the capture UI is allowed to know.

WHY THIS EXISTS AT ALL. Everything else the UI renders it reads out of FHIR: the forms are
Questionnaires, the hierarchy is Locations, the server's own identity is the CapabilityStatement.
This is the one class of fact that is none of those - not something the guide published, but
something about *how this process was started*. Two things are that today. `[serve.basemaps]` names
the raster layers the organisation-unit map may draw under the boundaries, which is a deployment
decision made in fhir.toml or on the command line that a bundle compiled weeks earlier cannot know.
And the profile this run resolved names the DHIS2 instance the guide was generated from, which is
what lets a published organisation unit, form, or data element link back to the object it came from.

WHY NOT `/metadata`. A CapabilityStatement describes the FHIR interface - what a client may read,
search, and post. A tile template is not part of that interface and would have to ride in an
extension on a document every FHIR client parses, to say something no FHIR client wants.

SO IT IS `/spool`'s SHAPE, FOR `/spool`'s REASONS. A plain typed JSON endpoint, `application/json`,
Pydantic models rather than a Bundle, on a single lowercase segment. FHIR resource types are
PascalCase, so `/uiconfig` can never shadow one, and the router mounts with the other fixed paths -
ahead of `/{resource_type}`, which would otherwise claim it and answer that this server does not
serve the resource type `uiconfig`. `dhis2w_fhir_serve.routes.spool` argues that choice in full;
this module inherits it rather than restating it.

WHAT IT DELIBERATELY DOES NOT CARRY. Not the profile's name, not the credentials it holds, not the
host and port this process listens on, not `live`, not `strict_codes`. Those describe the process to
whoever runs it, and a browser that could read them would be a browser that leaks them. The
instance's address is the one fact about the profile that crosses, because it is the fact the links
are made of - and it crosses without whatever userinfo somebody wrote into it, since a password in
a base url is a credential wherever it is written. Only the settings the UI has to act on belong
here, and the model is the enumeration of exactly those.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from dhis2w_fhir.config import DEFAULT_BASEMAP_TEMPLATE, BasemapSource
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
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


class BasemapLayer(BaseModel):
    """One raster layer the organisation-unit map offers under the boundaries, and who to credit for it.

    `attribution` is derived rather than configured, and the rule is narrow on purpose: this server
    knows what OpenStreetMap's tile policy requires because it ships that template as its default,
    and it knows nothing about the terms of a tile source someone else points it at. So a custom
    template gets no attribution string from here, and the guide says that crediting it is the
    deployment's own obligation - which is more honest than inventing a credit line or, worse,
    leaving OpenStreetMap's on somebody else's tiles.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    """What the map's layer control calls this layer - the deployment's own word for it."""

    url: str
    """The `{z}/{x}/{y}` raster tile URL template."""

    attribution: str | None = None
    """The credit line the map must display, as HTML, or None when this server cannot know it."""


class UiConfig(BaseModel):
    """What the capture UI may know about how this facade was started.

    `basemaps` is empty when this run offers no tiles, which is a state the UI renders rather than
    an absence it has to guess at: the map's layer control is then a control with `None` alone in
    it, and the boundary-only canvas is what it draws.

    `dhis2_base_url` is None when no profile resolved, and the UI answers that by rendering no
    links out at all - a guide with no named instance behind it has nowhere honest to point.
    """

    model_config = ConfigDict(frozen=True)

    basemaps: list[BasemapLayer] = Field(default_factory=list)
    dhis2_base_url: str | None = None


@router.get(UI_CONFIG_PATH)
async def read_ui_config(request: Request) -> UiConfig:
    """Answer the run-time settings the UI acts on, resolved for this process."""
    settings = serve_context(request).settings
    return UiConfig(
        basemaps=basemap_layers(settings.basemaps),
        dhis2_base_url=public_instance_url(settings.dhis2_base_url),
    )


def basemap_layers(sources: list[BasemapSource]) -> list[BasemapLayer]:
    """The configured tile sources as the UI reads them, each credited where this server can credit it.

    A source whose template is blank is dropped rather than offered: a layer that draws nothing is
    a layer control entry that lies about what picking it does, and `None` is already in the list.
    """
    layers: list[BasemapLayer] = []
    for source in sources:
        url = source.url.strip()
        if url == "":
            continue
        layers.append(BasemapLayer(name=source.name.strip() or url, url=url, attribution=_attribution(url)))
    return layers


def public_instance_url(base_url: str | None) -> str | None:
    """One profile's DHIS2 address as a browser may be handed it - the same address, minus any userinfo.

    A profile is expected to keep its credentials in its own fields, but nothing stops somebody
    writing `https://user:password@instance/` as the base url, and this is the one value here that
    leaves the process. Stripping the userinfo is what makes "the address crosses, the credential
    does not" true of every profile rather than of the well-formed ones.
    """
    if base_url is None or base_url.strip() == "":
        return None
    parts = urlsplit(base_url.strip())
    if parts.hostname is None or "@" not in parts.netloc:
        return base_url.strip()
    netloc = parts.hostname if parts.port is None else f"{parts.hostname}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _attribution(url: str) -> str | None:
    """The credit line for a tile template, which this server knows only for its own default."""
    if url == DEFAULT_BASEMAP_TEMPLATE or OPENSTREETMAP_TILE_HOST in url:
        return OPENSTREETMAP_ATTRIBUTION
    return None
