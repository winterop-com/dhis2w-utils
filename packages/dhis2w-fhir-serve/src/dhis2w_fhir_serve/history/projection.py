"""One recorded event as the document the guide already publishes for it - a `QuestionnaireResponse`.

THE SHAPE IS THE CAPTURE CONTRACT'S, READ BACKWARDS. A tracker event captured through this facade
arrives as a `D2TrackerEventResponse`: the stage's Questionnaire as `questionnaire`, the tracked
entity as `subject`, the enrollment and the reporting unit as extensions, the event's own instant as
`authored`, and one item per data value under the `linkId` its data element is asked as. This module
builds exactly that document out of what the instance now holds, so the record a client reads back is
the record a client could have written - one shape for both legs rather than two readings of one
event.

NOTHING HERE IS INVENTED, AND THE PROJECTION IS THE SERVED FORM'S. Every question's item type,
terminology binding, and DHIS2 value type is read off the very `CaptureIndex` a received response is
validated against, so a value can never be typed one way on the way in and another on the way out.
The same rule the capture path and `$generate` hold to holds here: the item type decides which
`value[x]` element carries the answer, and the DHIS2 value the instance stored decides what that
element carries.

WHAT IT REFUSES TO SAY. A stage this project publishes no form for is not projected at all - there is
no `questionnaire` to name, and a document naming none is not one this guide describes. Those events
are counted and their stages named, so a reader of the answer learns the record is wider than the
guide, rather than reading a short answer as a short record. An event missing a fact its profile
requires - no tracked entity, no enrollment, no reporting unit, no instant - is served without
claiming the profile, which is the same rule the example corpus follows for the same reason.

HOW A STORED VALUE BECOMES AN ANSWER IS NOT THIS MODULE'S. `dhis2w_fhir_serve.history.answers` casts
one DHIS2 string onto the `value[x]` element its question asks it on, resolves a coded one against
the served terminology, and hangs the results in the form's own tree - and the data set read-back
beside this reads the same functions, so one form can never type a value one way for a tracker event
and another for an aggregate cell.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dhis2w_fhir import response_status_code, zoned_date_time
from dhis2w_fhir.r4 import (
    Extension,
    Identifier,
    Meta,
    QuestionnaireResponse,
    QuestionnaireResponseItem,
    Reference,
    is_fhir_date_time,
)
from dhis2w_fhir.resources.questionnaires.schemas import FormKind
from pydantic import BaseModel, ConfigDict, PrivateAttr

from dhis2w_fhir_serve.capture.index import CaptureIndex, CaptureIndexCache, UnreadableQuestionnaireError
from dhis2w_fhir_serve.capture.naming import CaptureNaming
from dhis2w_fhir_serve.capture.resolve import CodingResolverSet
from dhis2w_fhir_serve.history.answers import (
    LOCATION_RESOURCE_TYPE,
    answered_items,
    item_children,
    question_answers,
    response_status,
)
from dhis2w_fhir_serve.store import IdentifierToken, ResourceStore, SearchQuery

if TYPE_CHECKING:
    from dhis2w_fhir_serve.history.wire import RecordedEvent, TrackedEntityRecord

#: The resource type a served form is held as.
QUESTIONNAIRE_RESOURCE_TYPE = "Questionnaire"

#: The form kind an event of a tracker program's stage is captured under, and the one it is served as.
TRACKER_EVENT_FORM_KIND: FormKind = "tracker-event"


class ProjectedEvent(BaseModel):
    """One event of the record as this facade answers it: the document, or the reason there is none."""

    model_config = ConfigDict(frozen=True)

    event_uid: str
    response: QuestionnaireResponse | None = None
    unpublished_stage_uid: str | None = None
    """The program stage this project publishes no form for, on an event that could not be projected."""


class ProjectedRecord(BaseModel):
    """One page of a record, projected: the documents it carries and what it could not carry."""

    model_config = ConfigDict(frozen=True)

    responses: tuple[QuestionnaireResponse, ...] = ()
    unpublished_stage_uids: tuple[str, ...] = ()
    """Every stage on this page the guide publishes no form for, once each, in the order they occurred."""

    unprojected_events: int = 0
    """How many events on this page carry no document, which is one per event of an unpublished stage."""


class RecordProjection(BaseModel):
    """What one record read is projected through: the project's names, what it serves, and its zone.

    Built per request and dropped with it, over state the process already holds: the store is loaded
    once at startup and the index cache is the very cache a capture validates against, so the forms a
    record is projected through are the forms this facade checks submissions against.
    """

    model_config = ConfigDict(frozen=True)

    naming: CaptureNaming
    store: ResourceStore
    indexes: CaptureIndexCache
    timezone: str | None = None
    """The IANA zone the instance's zone-less timestamps are wall-clock readings in (BUGS.md 62)."""

    _resolvers: CodingResolverSet = PrivateAttr()
    _indexes_by_stage: dict[str, CaptureIndex | None] = PrivateAttr(default_factory=dict)

    def model_post_init(self, context: Any, /) -> None:
        """Open the terminology resolvers over the served store (private attributes stay settable)."""
        self._resolvers = CodingResolverSet(store=self.store)

    def project(self, record: TrackedEntityRecord, events: tuple[RecordedEvent, ...]) -> ProjectedRecord:
        """Project the events of one page, keeping the record's own order and naming what it could not carry."""
        projected = [self.project_event(record, event) for event in events]
        stages: dict[str, None] = {}
        for entry in projected:
            if entry.unpublished_stage_uid is not None:
                stages.setdefault(entry.unpublished_stage_uid, None)
        return ProjectedRecord(
            responses=tuple(entry.response for entry in projected if entry.response is not None),
            unpublished_stage_uids=tuple(stages),
            unprojected_events=sum(1 for entry in projected if entry.response is None),
        )

    def project_event(self, record: TrackedEntityRecord, event: RecordedEvent) -> ProjectedEvent:
        """Build the document one event is served as, or state the stage this project publishes no form for."""
        index = self.form_for(event.program_stage_uid)
        if index is None:
            return ProjectedEvent(event_uid=event.event_uid, unpublished_stage_uid=event.program_stage_uid or "")
        authored = self._authored(event)
        complete = authored is not None and event.enrollment_uid is not None and event.organisation_unit_uid is not None
        return ProjectedEvent(
            event_uid=event.event_uid,
            response=QuestionnaireResponse(
                id=event.event_uid,
                meta=Meta(profile=[self.naming.response_profile_url(TRACKER_EVENT_FORM_KIND)]) if complete else None,
                extension=self._extensions(event),
                questionnaire=index.canonical,
                status=response_status(response_status_code(event.status)),
                subject=Reference(
                    type=index.subject_type,
                    identifier=Identifier(system=self.naming.tracked_entity_system, value=record.tracked_entity_uid),
                ),
                authored=authored,
                item=self._items(index, event) or None,
            ),
        )

    def form_for(self, program_stage_uid: str | None) -> CaptureIndex | None:
        """The served form one program stage published, or None when this project publishes none for it.

        The lookup is by the DHIS2 identifier the generated Questionnaire carries, which is the same
        `{base}/id/program-stage` system the guide publishes the stage under - never by a name and
        never by a canonical this server composed, because what a form is called is the naming
        source's decision and what it is about is the identifier's.
        """
        if program_stage_uid is None:
            return None
        if program_stage_uid in self._indexes_by_stage:
            return self._indexes_by_stage[program_stage_uid]
        self._indexes_by_stage[program_stage_uid] = self._read_form(program_stage_uid)
        return self._indexes_by_stage[program_stage_uid]

    def _read_form(self, program_stage_uid: str) -> CaptureIndex | None:
        """Read the one served Questionnaire a stage UID names, or None when nothing served names it."""
        token = IdentifierToken(system=self.naming.program_stage_identifier_system, value=program_stage_uid)
        for entry in self.store.search(QUESTIONNAIRE_RESOURCE_TYPE, SearchQuery(identifiers=(token,))):
            if entry.canonical_url is None:
                continue
            try:
                return self.indexes.resolve(entry.canonical_url, self.naming, self.store)
            except UnreadableQuestionnaireError:
                continue
        return None

    def _authored(self, event: RecordedEvent) -> str | None:
        """When the event occurred, as an R4 `dateTime`, or nothing when the instance stated no readable instant.

        DHIS2 answers `occurredAt` as a zone-less wall-clock reading (BUGS.md 62), so it is given the
        offset the project's own zone stood at on that reading - the same normalisation the example
        corpus applies to the same field.
        """
        if event.occurred_at is None:
            return None
        normalized = zoned_date_time(event.occurred_at.strip(), self.timezone)
        return normalized if is_fhir_date_time(normalized) else None

    def _extensions(self, event: RecordedEvent) -> list[Extension]:
        """The extensions a stage response carries, in the order its own profile slices them.

        The reporting unit first, then the enrollment the event belongs to, then the form kind - and
        each is left off when the instance stated no value for it, because an extension pointing at
        nothing is worse than an absent one.
        """
        extensions: list[Extension] = []
        if event.organisation_unit_uid is not None:
            extensions.append(
                Extension(
                    url=self.naming.organisation_unit_url,
                    valueReference=Reference(reference=f"{LOCATION_RESOURCE_TYPE}/{event.organisation_unit_uid}"),
                )
            )
        if event.enrollment_uid is not None:
            extensions.append(
                Extension(
                    url=self.naming.tracker_enrollment_url,
                    valueIdentifier=Identifier(
                        system=self.naming.tracker_enrollment_system, value=event.enrollment_uid
                    ),
                )
            )
        extensions.append(Extension(url=self.naming.form_type_url, valueCode=TRACKER_EVENT_FORM_KIND))
        return extensions

    def _items(self, index: CaptureIndex, event: RecordedEvent) -> list[QuestionnaireResponseItem]:
        """Mirror the form's item tree in document order, keeping the branches a stored value reaches.

        A value whose data element the form does not ask is not carried: the response would answer a
        question this project's guide never published, and a client validating it against the form
        would be told so. The form's own tree is what the answers hang in, so a value stays inside the
        section its question was asked in.
        """
        answers = {
            value.data_element_uid: question_answers(
                index.questions[value.data_element_uid],
                value.value,
                resolvers=self._resolvers,
                timezone=self.timezone,
            )
            for value in event.values
            if value.data_element_uid in index.questions
        }
        return answered_items(item_children(index), answers, None)
