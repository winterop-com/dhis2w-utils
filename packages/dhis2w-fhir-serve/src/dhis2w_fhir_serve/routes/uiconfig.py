"""`GET /uiconfig` - the handful of run-time settings the capture UI is allowed to know.

WHY THIS EXISTS AT ALL. Everything else the UI renders it reads out of FHIR: the forms are
Questionnaires, the hierarchy is Locations, the server's own identity is the CapabilityStatement.
This is the one class of fact that is none of those - not something the guide published, but
something about *how this process was started*. Four things are that today. `[serve] capture` says
whether this server receives submissions at all, which is what lets a form screen say so rather than
offer a Submit that answers 405. `[serve.basemaps]` names
the raster layers the organisation-unit map may draw under the boundaries, which is a deployment
decision made in fhir.toml or on the command line that a bundle compiled weeks earlier cannot know.
The profile this run resolved names the DHIS2 instance the guide was generated from, which is what
lets a published organisation unit, form, or data element link back to the object it came from. And
`[serve.tracked_entities]` decides whether there is a register to navigate to at all, which no
published resource states: a Questionnaire that registers people is published by projects whose
server answers for none.

WHY NOT `/metadata`. A CapabilityStatement describes the FHIR interface - what a client may read,
search, and post. A tile template is not part of that interface and would have to ride in an
extension on a document every FHIR client parses, to say something no FHIR client wants.

SO IT IS `/spool`'s SHAPE, FOR `/spool`'s REASONS. A plain typed JSON endpoint, `application/json`,
Pydantic models rather than a Bundle, on a single lowercase segment. FHIR resource types are
PascalCase, so `/uiconfig` can never shadow one, and the router mounts with the other fixed paths -
ahead of `/{resource_type}`, which would otherwise claim it and answer that this server does not
serve the resource type `uiconfig`. `dhis2w_fhir_serve.routes.spool` argues that choice in full;
this module inherits it rather than restating it.

THE AUTHENTICATION POSTURE IS HERE FOR THE SAME REASON `capture` is: it is a fact about how this
process was started that a screen has to act on, and the screen's alternative is parsing a
conformance document to decide which prompt to draw. THE NAME AND NOTHING ELSE crosses - `none`,
`token`, `dhis2`, or `jwt`, plus how much of the surface the posture covers and, under `jwt`, the
issuer a caller has to go to for a token. No token, no realm, no username, no signing key, no
audience, no claim name, no DHIS2 address beyond the one this document already carries. The sign-in gate in the
capture UI reads the posture off `/metadata` instead, because `/metadata` is open in every scope and
this document is not: under `[serve] auth_scope = "all"` a caller with no credentials is refused
here, which is the correct answer and a useless one to draw a prompt from.

WHAT IT DELIBERATELY DOES NOT CARRY. Not the profile's name, not the credentials it holds, not the
host and port this process listens on, not `live`, not `strict_codes`, and nothing an authentication
posture holds beyond its name. Those describe the process to
whoever runs it, and a browser that could read them would be a browser that leaks them. The
instance's address is the one fact about the profile that crosses, because it is the fact the links
are made of - and it crosses without whatever userinfo somebody wrote into it, since a password in
a base url is a credential wherever it is written. Only the settings the UI has to act on belong
here, and the model is the enumeration of exactly those.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from dhis2w_fhir.config import DEFAULT_BASEMAP_TEMPLATE, BasemapSource, ServeAuth, ServeAuthScope
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from dhis2w_fhir_serve.routes.context import serve_context

if TYPE_CHECKING:
    from dhis2w_fhir_serve.register.surface import RegisterSurface

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


class RegisteredTypeUiConfig(BaseModel):
    """One tracked entity type a register rides, as a screen has to name it."""

    model_config = ConfigDict(frozen=True)

    uid: str
    """The DHIS2 tracked entity type UID, which is what a served resource carries as its `meta.tag`."""

    name: str | None = None
    """The name the instance holds for the type, as `D2TET_CM` published it, or None when it published none."""


class FilterableAttributeUiConfig(BaseModel):
    """One tracked entity attribute a register is filtered by, and what a screen needs to offer it.

    Five facts, and each of them is one a control cannot be drawn without. `uid` is what
    `d2-attribute={uid}|{value}` names, `name` is what a label reads, `value_type` is what DHIS2 says
    the values are, `value_set` is the vocabulary a coded attribute's values come from - so an
    attribute bound to a DHIS2 option set is drawn as a choice over the published ValueSet's concepts,
    and one bound to nothing is drawn as a box the person types into - and `types` is which of the
    register's tracked entity types collect the attribute at all.

    WHY `types` IS ONE OF THEM. A register is the union of its types, so its filter list is the union
    of what their forms ask - and a screen narrowed to one of those types must not offer the others'
    attributes. A register of people carrying a person type and a focus-area type would otherwise
    offer a focus area's reader a filter on first name, which the focus area's own form never asks
    and which matches nobody.

    IT IS HERE AS WELL AS IN `/metadata` FOR THE REASON THE REGISTER'S TYPE LIST IS. The
    CapabilityStatement's `d2-attribute` entry names the same attributes in its documentation, because
    that is where a FHIR client reads what a search parameter means - but it names them in prose, and
    a screen drawing a select over a vocabulary needs the canonical as a value rather than as a
    sentence.

    WHAT IT DOES NOT CARRY IS THE VALUES. A coded attribute's concepts are published as a CodeSystem
    and a ValueSet this server already serves, so the canonical is the whole of what crosses; copying
    the concepts here would be a second statement of a vocabulary that can go stale against the first.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    """The DHIS2 tracked entity attribute UID - the left half of a `d2-attribute` filter's value."""

    name: str | None = None
    """The name the instance holds for the attribute, as `D2TEA_CS` published it, or None when it published none."""

    value_type: str | None = None
    """The DHIS2 value type of the attribute's values, or None where this guide publishes none."""

    value_set: str | None = None
    """The canonical of the ValueSet a coded attribute's values come from, or None where nothing binds it."""

    types: list[str] = Field(default_factory=list)
    """The tracked entity type UIDs whose registration forms declare this attribute, in the order they ride.

    Empty states nothing rather than nothing declares it, and a screen reads it as the attribute being
    offered under every type of the register: an emptiness that hid the filter would turn a guide
    saying less into a control a reader cannot reach.
    """


class RegisterUiConfig(BaseModel):
    """One FHIR resource type this run serves from the instance, the types that ride it, and what filters it."""

    model_config = ConfigDict(frozen=True)

    resource: str
    """The FHIR resource type - the path a screen reads and pages under."""

    types: list[RegisteredTypeUiConfig] = Field(default_factory=list)

    filter_attributes: list[FilterableAttributeUiConfig] = Field(default_factory=list)
    """The attributes `d2-attribute` filters this register by, in the order its forms ask them.

    EQUALITY IS ALL ANY OF THEM ANSWERS. A screen offering these as a filter has to say so - the
    control matches the value exactly and case-insensitively, it does not match a prefix, and a person
    typing half a district's name gets nobody rather than a shorter list. `_content` is the search
    that matches part of a value, and it is a different control.

    Empty when this run serves no register, and empty for a register whose types the guide publishes
    no form for: a filter over attributes nobody declared would be a control with nothing behind it.

    The list is the union over the register's types, and each entry names the types that declare it,
    so a screen narrowed to one type offers that type's own attributes and no others'.
    """


class TrackedEntitiesUiConfig(BaseModel):
    """Whether this process answers for the instance's tracked entities, what it serves them as, and whether it lists.

    `enabled` and `listing` are resolved facts rather than the `[serve.tracked_entities]` table read
    back: `enabled` is false for a compiled run and for a project publishing no registration form,
    exactly as it is for one whose table switches the register off, because all three mean the same
    thing to a screen - there is nothing here to show. `listing` is the same question for the screen
    that shows everything.

    `registers` is what makes the screen honest about what it is showing. A run whose every type is
    published as `Patient` carries one entry and the screen is the one it always was; a run that also
    registers samples carries a second, and the screen names each section by the types riding it
    rather than calling a specimen batch a person. The resource is what a screen reads and pages
    under, and the type names are what it titles a section with.

    So the UI gates its navigation on this and never asks `/metadata` a second question about it: the
    CapabilityStatement's resource entries say the same thing, but reading them means parsing a
    conformance document to decide whether to draw a link and what to call it.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool
    """Whether the register's resource routes and the enrollment listing answer at all in this process."""

    listing: bool
    """Whether a register search naming no identifier answers with a page of the register."""

    registers: list[RegisterUiConfig] = Field(default_factory=list)
    """One entry per FHIR resource type served, each carrying its types and what it filters by.

    Empty when this process serves none. The filter declaration rides the register rather than the
    table above it because two registers of one run filter on different attributes: a register of
    people is filtered by what a person's forms ask, and a register of samples by what a sample's do.
    """


class AuthUiConfig(BaseModel):
    """How this process decides who is calling, as a screen has to name it - the posture, never a secret.

    `posture` is what decides which prompt the capture UI draws: `token` a field for one of this
    deployment's tokens, `dhis2` a DHIS2 username and password, `jwt` a field for a token somebody
    else issued, `none` nothing at all. `scope` is what decides whether browsing this server needs a
    credential or only submitting does.

    `issuer` is stated under `jwt` and None otherwise. It is the one part of `[serve.jwt]` that
    crosses - the audience, the claim name, and whether the token is forwarded are this deployment's
    business, and none of them is something a screen acts on. The issuer is: a person asked for a
    token has to be told whose token, and the answer was never secret to begin with. The sign-in gate
    reads it off `/metadata` rather than here, for the reason this module's own note gives, and it is
    carried here for the Server page.
    """

    model_config = ConfigDict(frozen=True)

    posture: ServeAuth = ServeAuth.NONE
    scope: ServeAuthScope = ServeAuthScope.WRITE
    issuer: str | None = None
    """The OpenID Connect issuer this server takes tokens from, under `jwt`, and None otherwise."""


class UiConfig(BaseModel):
    """What the capture UI may know about how this facade was started.

    `capture` is whether this server receives submissions. It is here as well as in `/metadata`
    for the reason `tracked_entities` is: the CapabilityStatement says the same thing, and reading
    it means parsing a conformance document to decide whether to draw a button. A screen that reads
    false states the fact and offers no Submit, rather than offering one that answers 405.

    `basemaps` is empty when this run offers no tiles, which is a state the UI renders rather than
    an absence it has to guess at: the map's layer control is then a control with `None` alone in
    it, and the boundary-only canvas is what it draws.

    `dhis2_base_url` is None when no profile resolved, and the UI answers that by rendering no
    links out at all - a guide with no named instance behind it has nowhere honest to point.

    `tracked_entities` is None on the same terms: a server that says nothing about its register is
    one a screen must assume nothing about, and reads exactly as `enabled = false` does. This
    process always states it, because it always knows.

    `auth` is always stated, and a document that omitted it would be read as `none` - which is the
    right reading of silence for a screen, and the reason the sign-in gate does not learn the posture
    here. See this module's own note.
    """

    model_config = ConfigDict(frozen=True)

    capture: bool = True
    auth: AuthUiConfig = Field(default_factory=AuthUiConfig)
    basemaps: list[BasemapLayer] = Field(default_factory=list)
    dhis2_base_url: str | None = None
    tracked_entities: TrackedEntitiesUiConfig | None = None


@router.get(UI_CONFIG_PATH)
async def read_ui_config(request: Request) -> UiConfig:
    """Answer the run-time settings the UI acts on, resolved for this process."""
    context = serve_context(request)
    settings = context.settings
    return UiConfig(
        capture=settings.capture,
        auth=AuthUiConfig(
            posture=settings.auth,
            scope=settings.auth_scope,
            issuer=settings.jwt.issuer if settings.auth is ServeAuth.JWT else None,
        ),
        basemaps=basemap_layers(settings.basemaps),
        dhis2_base_url=public_instance_url(settings.dhis2_base_url),
        tracked_entities=tracked_entities_config(live=settings.live, surface=context.register_surface),
    )


def tracked_entities_config(*, live: bool, surface: RegisterSurface) -> TrackedEntitiesUiConfig:
    """The register as a screen has to read it: served or not, listing or not, and what it is served as.

    `registers` is empty whenever the register is not served, because a screen that draws no link has
    nothing to name; a resource stated beside `enabled = false` would be a section heading for a page
    the navigation does not offer.
    """
    enabled = live and surface.serves_tracked_entities()
    return TrackedEntitiesUiConfig(
        enabled=enabled,
        listing=enabled and surface.serves_listing(),
        registers=[
            RegisterUiConfig(
                resource=register.resource_type,
                types=[
                    RegisteredTypeUiConfig(uid=published.uid, name=published.name)
                    for published in register.tracked_entity_types
                ],
                filter_attributes=[
                    FilterableAttributeUiConfig(
                        uid=attribute.attribute_uid,
                        name=attribute.display,
                        value_type=attribute.value_type,
                        value_set=attribute.value_set,
                        types=list(register.filter_attribute_type_uids.get(attribute.attribute_uid, ())),
                    )
                    for attribute in register.filter_attributes
                ],
            )
            for register in (surface.registers() if enabled else ())
        ],
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
