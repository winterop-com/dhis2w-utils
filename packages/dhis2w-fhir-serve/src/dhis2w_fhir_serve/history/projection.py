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

A VALUE THE TERMINOLOGY CANNOT CODE IS CARRIED AS THE STRING DHIS2 STORED, and so is a number the
instance holds in a spelling its own value type does not admit. That is `dhis2w_fhir`'s own emitter
rule (`_fallback` in `dhis2w_fhir.resources.examples`), kept here so the served document and the
published example corpus say the same thing about the same value. Dropping it would hide a value the
instance holds; recoding it would be this server deciding what an option means.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

from dhis2w_fhir import response_status_code, zoned_date_time
from dhis2w_fhir.names import flatten_whitespace
from dhis2w_fhir.r4 import (
    Coding,
    Extension,
    Identifier,
    Meta,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
    is_fhir_date,
    is_fhir_date_time,
    is_fhir_time,
)
from dhis2w_fhir.resources.questionnaires.schemas import FormKind
from pydantic import BaseModel, ConfigDict, PrivateAttr

from dhis2w_fhir_serve.capture.index import CaptureIndex, CaptureIndexCache, UnreadableQuestionnaireError
from dhis2w_fhir_serve.capture.naming import CaptureNaming
from dhis2w_fhir_serve.capture.resolve import CodingResolutionError, CodingResolverSet
from dhis2w_fhir_serve.store import IdentifierToken, ResourceStore, SearchQuery

if TYPE_CHECKING:
    from dhis2w_fhir_serve.capture.index import CaptureQuestion
    from dhis2w_fhir_serve.history.wire import RecordedEvent, RecordedValue, TrackedEntityRecord

#: The resource type a served form is held as, and the one an organisation unit is referenced by.
QUESTIONNAIRE_RESOURCE_TYPE = "Questionnaire"
LOCATION_RESOURCE_TYPE = "Location"

#: The form kind an event of a tracker program's stage is captured under, and the one it is served as.
TRACKER_EVENT_FORM_KIND: FormKind = "tracker-event"

#: The DHIS2 value type whose stored value is several values, and the character separating them.
MULTI_VALUE_TYPE = "MULTI_TEXT"
MULTI_VALUE_SEPARATOR = ","

#: The `value[x]` elements carrying an R4 primitive with a spelling of its own to check.
_TEMPORAL_ELEMENTS = ("valueDate", "valueDateTime", "valueTime")

#: The literals DHIS2 stores a boolean as, either way round.
_TRUE_LITERALS = frozenset({"true", "1"})
_FALSE_LITERALS = frozenset({"false", "0"})

#: The `value[x]` element no served value is ever written on: DHIS2 stores a file or an image as a
#: UID naming a document this facade does not serve, so an attachment here would reference nothing.
_UNSERVED_ANSWER_ELEMENT = "valueAttachment"

#: The `QuestionnaireResponse.status` codes R4 admits, which a DHIS2 event status maps onto.
_ResponseStatusCode = Literal["in-progress", "completed", "amended", "entered-in-error", "stopped"]


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
                status=_status_code(response_status_code(event.status)),
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
            value.data_element_uid: self._answers(index.questions[value.data_element_uid], value)
            for value in event.values
            if value.data_element_uid in index.questions
        }

        children: dict[str | None, list[str]] = {}
        for link_id in index.item_link_ids:
            gate = index.gates.get(link_id)
            children.setdefault(None if gate is None else gate.parent_link_id, []).append(link_id)
        return _answered_items(children, answers, None)

    def _answers(self, question: CaptureQuestion, value: RecordedValue) -> list[QuestionnaireResponseAnswer]:
        """Every answer one stored value becomes: several for a multi-text question, one for the rest."""
        if question.answer_element == _UNSERVED_ANSWER_ELEMENT:
            return []
        if question.option_system is not None:
            parts = (
                value.value.split(MULTI_VALUE_SEPARATOR) if question.value_type == MULTI_VALUE_TYPE else [value.value]
            )
            return [self._coded_answer(question, part.strip()) for part in parts if part.strip()]
        return [_typed_answer(question, value.value, self.timezone)]

    def _coded_answer(self, question: CaptureQuestion, value: str) -> QuestionnaireResponseAnswer:
        """One option value as the coding the published CodeSystem states for it, else as DHIS2 stored it.

        The value DHIS2 stores is the option's own code, and the served CodeSystem publishes that code
        beside the concept code whichever spelling it was generated in - so resolution is the same
        tiered lookup a received answer goes through, leniently, since the instance is not a client
        that can be asked to send the contract's spelling.
        """
        system = question.option_system
        resolver = self._resolvers.for_system(system) if system is not None else None
        if system is None or resolver is None:
            return QuestionnaireResponseAnswer(valueString=value)
        try:
            resolved = resolver.resolve(value, strict=False)
        except CodingResolutionError:
            return QuestionnaireResponseAnswer(valueString=value)
        return QuestionnaireResponseAnswer(
            valueCoding=Coding(
                system=system,
                code=resolved.concept_code,
                display=flatten_whitespace(resolved.display) if resolved.display else None,
            )
        )


def _answered_items(
    children: dict[str | None, list[str]],
    answers: dict[str, list[QuestionnaireResponseAnswer]],
    parent: str | None,
) -> list[QuestionnaireResponseItem]:
    """The form's tree with the stored values in it, and every branch that reaches none left out."""
    items: list[QuestionnaireResponseItem] = []
    for link_id in children.get(parent, []):
        nested = _answered_items(children, answers, link_id)
        answered = answers.get(link_id, [])
        if answered or nested:
            items.append(QuestionnaireResponseItem(linkId=link_id, answer=answered or None, item=nested or None))
    return items


def _status_code(value: str) -> _ResponseStatusCode:
    """Read a status computed as a plain string as the R4 code it is; a test pins the two together."""
    return cast(_ResponseStatusCode, value)


def _typed_answer(question: CaptureQuestion, value: str, timezone: str | None) -> QuestionnaireResponseAnswer:
    """Cast one stored value onto the `value[x]` element its question asks it on, else onto a string."""
    text = value.strip()
    element = question.answer_element
    if element == "valueInteger":
        return _number_answer(text, whole=True)
    if element == "valueDecimal":
        return _number_answer(text, whole=False)
    if element == "valueBoolean":
        return _boolean_answer(text)
    if element in _TEMPORAL_ELEMENTS:
        return _temporal_answer(text, element, timezone)
    if element == "valueUri":
        return QuestionnaireResponseAnswer(valueUri=text)
    if element == "valueReference":
        return QuestionnaireResponseAnswer(valueReference=Reference(reference=f"{LOCATION_RESOURCE_TYPE}/{text}"))
    return QuestionnaireResponseAnswer(valueString=flatten_whitespace(value))


def _number_answer(text: str, *, whole: bool) -> QuestionnaireResponseAnswer:
    """A stored number on its own element, or as the string the instance holds when it is not one."""
    try:
        number = int(text) if whole else float(text)
    except ValueError:
        return QuestionnaireResponseAnswer(valueString=text)
    if whole:
        return QuestionnaireResponseAnswer(valueInteger=int(number))
    return QuestionnaireResponseAnswer(valueDecimal=number)


def _boolean_answer(text: str) -> QuestionnaireResponseAnswer:
    """A stored boolean from DHIS2's `true`/`false` (or `1`/`0`) spellings, else the string as stored."""
    lowered = text.lower()
    if lowered in _TRUE_LITERALS:
        return QuestionnaireResponseAnswer(valueBoolean=True)
    if lowered in _FALSE_LITERALS:
        return QuestionnaireResponseAnswer(valueBoolean=False)
    return QuestionnaireResponseAnswer(valueString=text)


def _temporal_answer(text: str, element: str, timezone: str | None) -> QuestionnaireResponseAnswer:
    """A stored date, dateTime, or time normalised into the R4 primitive, else the string as stored.

    A DHIS2 `DATETIME` value is a zone-less wall-clock reading exactly as `occurredAt` is (BUGS.md 62),
    so it takes the offset the project's zone stood at on that reading before it is checked - which is
    what the example corpus does to the same value.
    """
    if element == "valueDate":
        normalized = text.partition("T")[0]
        return (
            QuestionnaireResponseAnswer(valueDate=normalized)
            if is_fhir_date(normalized)
            else QuestionnaireResponseAnswer(valueString=text)
        )
    if element == "valueDateTime":
        zoned = zoned_date_time(text, timezone)
        return (
            QuestionnaireResponseAnswer(valueDateTime=zoned)
            if is_fhir_date_time(zoned)
            else QuestionnaireResponseAnswer(valueString=text)
        )
    return (
        QuestionnaireResponseAnswer(valueTime=text)
        if is_fhir_time(text)
        else QuestionnaireResponseAnswer(valueString=text)
    )
