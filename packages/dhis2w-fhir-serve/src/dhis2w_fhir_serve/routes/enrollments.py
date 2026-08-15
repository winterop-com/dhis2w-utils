"""`GET /tracked-entities/{uid}/enrollments` - which programs one tracked entity is enrolled in, for the picker.

WHY THIS IS NOT A FHIR RESOURCE. A DHIS2 enrollment is one tracked entity's participation in a program, and
FHIR has two candidate resources for that - `EpisodeOfCare` and `CarePlan` - which mean different
things and would commit this project to one reading of what a DHIS2 program is. That choice is
deliberately still open: it is roadmap decision 5.2, and picking it here, inside a picker's data
feed, would settle by accident a question that deserves settling on purpose. So the listing is
typed JSON on a path of its own, and the day the decision lands it becomes a resource without
having had to un-publish one first.

SO IT IS `/spool`'s AND `/uiconfig`'s SHAPE, FOR THEIR REASONS. Plain `application/json`, Pydantic
models rather than a Bundle, on lowercase segments no FHIR resource type can collide with, mounted
ahead of the read catch-alls. `dhis2w_fhir_serve.routes.spool` argues that choice in full.

WHAT IT IS FOR. A capture client that has found a subject still has to answer a stage form against
one of that subject's enrollments, and the enrollment UID is what the response carries. This is the
list it picks from.

WHY THE PATH NAMES A TRACKED ENTITY. DHIS2 enrols tracked entities, and a tracked entity is whatever
the project tracks - so a path spelt `/patients/` would be a lie the moment a project registers a
type the published map takes onto something other than `Patient`. The listing is keyed by the DHIS2
tracked entity UID and serves every one of them, whichever FHIR resource its type is registered as.

A COMPLETED ENROLLMENT IS LISTED, AND SAID TO BE COMPLETED. DHIS2 accepts an event into a completed
enrollment with no error and no warning (BUGS.md 70), so nothing downstream will tell a user that
what they just captured went into a closed episode. This server does not enforce the rule - the
instance is the authority on what it accepts, and a facade that hid a completed enrollment would be
hiding data the instance is perfectly willing to be given - it states the status, and `active` is
the one field a picker needs to grade it on.

The read is entity-scoped and never names a program, because naming one the entity is not enrolled
in answers 404 asserting the entity does not exist (BUGS.md 72). The enrollments come off the
entity.

This listing is part of the register, so `[serve.tracked_entities] enabled = false` refuses it along
with the FHIR routes: a project that serves no tracked entity serves nothing about its enrollments
either.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from dhis2w_client.errors import Dhis2ClientError
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from dhis2w_fhir_serve.errors import (
    NoPublishedSubjectTypeError,
    NotFoundError,
    NotServedFromCompiledIgError,
    RegisterDisabledError,
    UpstreamError,
)
from dhis2w_fhir_serve.register.wire import fetch_tracked_entity, upstream_refusal_text
from dhis2w_fhir_serve.routes.context import live_client, serve_context

if TYPE_CHECKING:
    from dhis2w_client.generated.v42.oas import TrackerEnrollment

    from dhis2w_fhir_serve.register.index import TrackedEntityIndex

#: Where the listing is served from. Lowercase segments, so no FHIR resource type can collide.
TRACKED_ENTITY_ENROLLMENTS_PATH = "/tracked-entities/{tracked_entity_uid}/enrollments"

#: What the live-only refusals name, so a client reads one word for the whole listing.
ENROLLMENTS_SURFACE_NAME = "enrollments"

#: The DHIS2 enrollment status that means the episode is open to new events without qualification.
ACTIVE_ENROLLMENT_STATUS = "ACTIVE"

router = APIRouter()


class TrackedEntityEnrollment(BaseModel):
    """One enrollment of one tracked entity: what it is, where it sits, and whether it is still open."""

    model_config = ConfigDict(frozen=True)

    enrollment_uid: str
    program_uid: str
    program_name: str | None = None
    """The name this project's guide publishes the program under, or None when it publishes none."""

    status: str
    """The DHIS2 enrollment status verbatim - `ACTIVE`, `COMPLETED`, or `CANCELLED`."""

    active: bool
    """False for a completed or cancelled enrollment. DHIS2 still accepts events into one (BUGS.md 70)."""

    enrolled_at: str | None = None
    """When the enrollment began, as DHIS2 dated it, in ISO 8601."""

    organisation_unit_uid: str | None = None
    organisation_unit_name: str | None = None
    """The name the published registry gives that organisation unit, or None when it publishes none."""


class TrackedEntityEnrollments(BaseModel):
    """Every enrollment one tracked entity holds, in the order DHIS2 returned them."""

    model_config = ConfigDict(frozen=True)

    tracked_entity_uid: str
    enrollments: list[TrackedEntityEnrollment] = Field(default_factory=list)


@router.get(TRACKED_ENTITY_ENROLLMENTS_PATH)
async def read_tracked_entity_enrollments(request: Request, tracked_entity_uid: str) -> TrackedEntityEnrollments:
    """List the programs one tracked entity is enrolled in, read off the entity itself."""
    surface = serve_context(request).register_surface
    if not surface.tracked_entities.enabled:
        raise RegisterDisabledError(ENROLLMENTS_SURFACE_NAME)
    client = live_client(request)
    if client is None:
        raise NotServedFromCompiledIgError(ENROLLMENTS_SURFACE_NAME)
    if not surface.serves_tracked_entities():
        raise NoPublishedSubjectTypeError(ENROLLMENTS_SURFACE_NAME)
    index = surface.index
    try:
        entity = await fetch_tracked_entity(client, tracked_entity_uid)
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity read: {upstream_refusal_text(error)}"
        ) from error
    if entity is None:
        raise NotFoundError(ENROLLMENTS_SURFACE_NAME, tracked_entity_uid)
    return TrackedEntityEnrollments(
        tracked_entity_uid=tracked_entity_uid,
        enrollments=[_listed(enrollment, index) for enrollment in entity.enrollments or [] if enrollment.enrollment],
    )


def _instant(value: datetime | int | None) -> str | None:
    """One DHIS2 instant as ISO 8601 - the tracker's own spelling, not Python's `str()` of a datetime.

    The generated model types the element as an instant or an epoch integer, because the OpenAPI
    document allows both; an integer is carried through as it arrived rather than guessed a unit for.
    """
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _listed(enrollment: TrackerEnrollment, index: TrackedEntityIndex) -> TrackedEntityEnrollment:
    """Project one DHIS2 enrollment onto the row a picker renders, names joined from the published guide."""
    program_uid = enrollment.program or ""
    status = "" if enrollment.status is None else str(enrollment.status.value)
    organisation_unit_uid = enrollment.orgUnit
    return TrackedEntityEnrollment(
        enrollment_uid=enrollment.enrollment or "",
        program_uid=program_uid,
        program_name=index.program_name(program_uid),
        status=status,
        active=status == ACTIVE_ENROLLMENT_STATUS,
        enrolled_at=_instant(enrollment.enrolledAt),
        organisation_unit_uid=organisation_unit_uid,
        organisation_unit_name=(
            None if organisation_unit_uid is None else index.organisation_unit_name(organisation_unit_uid)
        ),
    )
