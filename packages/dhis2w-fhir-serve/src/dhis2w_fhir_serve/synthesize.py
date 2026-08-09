"""Synthesising one QuestionnaireResponse from a served form - what `Questionnaire/{id}/$generate` answers.

A served Questionnaire already says everything an answer to it has to satisfy: the `value[x]` element
each question takes, the inclusive bounds a numeric one admits, whether it repeats, and the ValueSet a
coded one is drawn from. The capture index reads exactly those facts to *check* a submission; this
module reads the same index to *write* one. The invariant that makes the operation worth having is the
round trip - a generated response posted back to this server's own `/QuestionnaireResponse` answers
201 - and the way it is held is that both directions read one index, so a rule can never be enforced
on receipt without being honoured on generation.

Nothing here invents terminology. A coded answer is a concept the served CodeSystem really publishes,
carried in the exact spelling the contract asks for (the concept code, never the DHIS2 code or UID
fall-backs), so a strict-codes server accepts what a lenient one does. A question bound to terminology
this project never published is left unanswered rather than answered with something invented. The
attribute option combo an aggregate response is filed under is drawn the same way, out of the very
vocabulary the form declares, so a data set on a non-default category combo generates a response its
own capture path accepts.

Two facts a compiled Questionnaire does not carry, and how they are decided here:

* **The data set's period type.** A generated aggregate response needs a DHIS2 reporting period, and
  the compiled form says nothing about which type its data set reports on. The rule is: the period
  type declared by a served example response answering the same questionnaire - a compiled IG ships
  its `Usage: #example` instances, and each aggregate one carries the real type on its D2Period -
  and `Monthly` when the store holds no such example (which is every `--live` store, since a live
  build serves the read set and no examples). The response always carries the newest *completed*
  period of whichever type was decided, so the value moves with the calendar and nothing else.
* **`TRUE_ONLY` versus `BOOLEAN`.** The emitter answers both DHIS2 value types as a `boolean` item,
  so a generated answer to either is a random `true` or `false`. A `TRUE_ONLY` data element only ever
  holds `true` in DHIS2, and a generated `false` for one is a value the form admits but the instance
  would not store.
"""

from __future__ import annotations

import datetime
import random
import string
from typing import TYPE_CHECKING, Any, Final, Literal

from dhis2w_fhir.names import flatten_whitespace
from dhis2w_fhir.period import PERIOD_TYPE_NAMES, parse_period, recent_periods
from dhis2w_fhir.r4 import (
    Coding,
    Extension,
    Identifier,
    Meta,
    Period,
    Questionnaire,
    QuestionnaireItem,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)
from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationError

from dhis2w_fhir_serve.capture.index import CaptureIndex, CaptureQuestion
from dhis2w_fhir_serve.capture.naming import (
    PERIOD_ISO_SUB_EXTENSION,
    PERIOD_RANGE_SUB_EXTENSION,
    PERIOD_TYPE_SUB_EXTENSION,
    CaptureNaming,
)
from dhis2w_fhir_serve.capture.resolve import CodingResolverSet, ResolvedCoding
from dhis2w_fhir_serve.store import ResourceStore

if TYPE_CHECKING:
    from dhis2w_fhir.period.schemas import PeriodValue

#: The largest seed `$generate` accepts. A seed travels as an R4 `integer`, which is 32-bit signed,
#: so a seed a client cannot spell in the operation's own input parameter is not one this server draws.
MAXIMUM_SEED = 2**31 - 1

#: The period type an aggregate response falls back to when the store holds no example to read one off.
DEFAULT_PERIOD_TYPE = "Monthly"

#: The status a generated response carries. The aggregate contract requires it, and a generated
#: response is a finished submission whatever the form kind, so every kind is generated completed.
GENERATED_STATUS: Final[Literal["completed"]] = "completed"

#: The resource types this module reads out of the store: examples for the period type, Locations
#: for the organisation unit a generated response reports for.
RESPONSE_RESOURCE_TYPE = "QuestionnaireResponse"
LOCATION_RESOURCE_TYPE = "Location"

#: The resource type a tracker-event response names its tracked-entity subject as.
TRACKER_SUBJECT_TYPE = "Patient"

#: The item types that carry no answer of their own and only nest other items.
_STRUCTURAL_ITEM_TYPES = ("group", "display")

#: The value elements a generated answer is never written on. An invented attachment says nothing
#: about the form, and no DHIS2 value type reaches a Questionnaire as one.
_UNGENERATED_ANSWER_ELEMENTS = frozenset({"valueAttachment"})

#: How far a numeric answer ranges from whichever bound the question pins, when it pins only one.
_NUMERIC_SPAN = 1000

#: How many decimal places a generated decimal answer carries.
_DECIMAL_PLACES = 1

#: How many days back a generated event may have occurred, when no reporting period bounds it.
_EVENT_WINDOW_DAYS = 30

#: The hours of a day a generated timestamp lands on the hour of.
_HOURS_PER_DAY = 24

#: The character a DHIS2 UID opens on, and the characters its remaining ten places take.
_UID_LEADING_CHARACTERS = string.ascii_letters
_UID_TRAILING_CHARACTERS = string.ascii_letters + string.digits
_UID_TRAILING_LENGTH = 10

#: How many options a repeating coded question selects, when the bound CodeSystem holds that many.
_REPEATED_SELECTIONS = 2

#: The host a generated URL points at - `.invalid` is reserved by RFC 2606 and resolves nowhere.
_GENERATED_URL_HOST = "https://example.invalid"


def draw_seed() -> int:
    """Draw the seed a `$generate` call that named none is answered from."""
    return random.randrange(MAXIMUM_SEED + 1)  # noqa: S311 - a reproducibility handle, not a secret


class DateWindow(BaseModel):
    """The span a generated date, dateTime, or time answer is drawn from."""

    model_config = ConfigDict(frozen=True)

    start_date: datetime.date
    end_date: datetime.date

    @classmethod
    def of_period(cls, period: PeriodValue) -> DateWindow:
        """The window one reporting period covers."""
        return cls(start_date=period.start_date, end_date=period.end_date)

    @classmethod
    def recent(cls, today: datetime.date) -> DateWindow:
        """The thirty days before `today`, which is where an event carrying no period sits."""
        return cls(start_date=today - datetime.timedelta(days=_EVENT_WINDOW_DAYS), end_date=today)

    def pick_date(self, generator: random.Random) -> datetime.date:
        """A seeded day inside the window, its last day excluded so the value is already past."""
        span = max((self.end_date - self.start_date).days, 1)
        return self.start_date + datetime.timedelta(days=generator.randrange(span))


def generate_response(
    questionnaire: Questionnaire,
    index: CaptureIndex,
    naming: CaptureNaming,
    store: ResourceStore,
    *,
    seed: int,
    today: datetime.date,
) -> QuestionnaireResponse:
    """Generate one synthetic response to a served form: its context, then an answer to every question.

    The whole document is a function of `(questionnaire, store, seed, today)`, and the only term that
    moves on its own is `today` - it decides which completed reporting period an aggregate response
    is for, and which thirty days an event's timestamps fall in.
    """
    period = _reporting_period(index, naming, store, today) if index.form_kind == "aggregate" else None
    window = DateWindow.of_period(period) if period is not None else DateWindow.recent(today)
    generator = _Generator(
        index=index,
        naming=naming,
        resolvers=CodingResolverSet(store=store),
        seed=seed,
        window=window,
        location_id=_capture_location_id(index, store, seed),
    )
    return generator.build(questionnaire, period)


class _TrackerContext(BaseModel):
    """The two DHIS2 data identifiers a generated tracker event carries: its subject and its enrollment."""

    model_config = ConfigDict(frozen=True)

    tracked_entity_uid: str
    enrollment_uid: str


class _Generator(BaseModel):
    """One seeded generation pass: the form's rules, the terminology behind it, and the window it sits in."""

    model_config = ConfigDict(frozen=True)

    index: CaptureIndex
    naming: CaptureNaming
    resolvers: CodingResolverSet
    seed: int
    window: DateWindow
    location_id: str

    _random: random.Random = PrivateAttr(default_factory=random.Random)

    def model_post_init(self, context: Any, /) -> None:
        """Seed the generator (private attributes stay settable on a frozen model)."""
        self._random.seed(self.seed)

    def build(self, questionnaire: Questionnaire, period: PeriodValue | None) -> QuestionnaireResponse:
        """Assemble the response: the context its profile requires first, then the answered item tree.

        The context is drawn before the answers so that adding a question to a form moves only that
        question's value - a response's timestamp and its tracker UIDs stay what they were.
        """
        authored = self._date_time() if self.index.form_kind != "aggregate" else None
        tracker = self._tracker_context() if self.index.form_kind == "tracker-event" else None
        return QuestionnaireResponse(
            meta=Meta(profile=[self.naming.response_profile_url(self.index.form_kind)]),
            identifier=Identifier(system=self.naming.generate_seed_system, value=str(self.seed)),
            extension=self._extensions(period, tracker),
            questionnaire=self.index.canonical,
            status=GENERATED_STATUS,
            subject=self._subject(tracker),
            authored=authored,
            item=self._items(questionnaire.item or []) or None,
        )

    def _tracker_context(self) -> _TrackerContext:
        """Draw the tracked entity and the enrollment a generated tracker event belongs to."""
        return _TrackerContext(tracked_entity_uid=self._uid(), enrollment_uid=self._uid())

    def _extensions(self, period: PeriodValue | None, tracker: _TrackerContext | None) -> list[Extension]:
        """The extensions the declared form kind's response profile slices, in the order it slices them."""
        extensions: list[Extension] = []
        if tracker is not None:
            extensions.append(
                Extension(
                    url=self.naming.organisation_unit_url,
                    valueReference=Reference(reference=f"{LOCATION_RESOURCE_TYPE}/{self.location_id}"),
                )
            )
            extensions.append(
                Extension(
                    url=self.naming.tracker_enrollment_url,
                    valueIdentifier=Identifier(
                        system=self.naming.tracker_enrollment_system, value=tracker.enrollment_uid
                    ),
                )
            )
        if period is not None:
            extensions.append(_period_extension(period, self.naming))
        extensions.extend(self._attribute_option_combo())
        extensions.append(Extension(url=self.naming.form_type_url, valueCode=self.index.form_kind))
        return extensions

    def _attribute_option_combo(self) -> tuple[Extension, ...]:
        """The third key of an aggregate report, drawn from the vocabulary the form declares - or nothing.

        A data set on the default category combo declares none and its responses carry none, which
        is what the capture contract expects of them. Where a vocabulary is declared the concept is
        a real one of the published CodeSystem, carried in the spelling the contract asks for, so a
        `--strict-codes` server accepts the response its own `$generate` produced. A declared
        vocabulary this project never published leaves the extension off: inventing a code would
        make the server warn about its own output, exactly as an unpublished `answerValueSet` does.
        """
        declared = self.index.attribute_option_combos
        resolver = self.resolvers.for_system(declared.system) if declared and declared.system else None
        if declared is None or declared.system is None or resolver is None or not resolver.options:
            return ()
        drawn = resolver.options[self._random.randrange(len(resolver.options))]
        return (Extension(url=self.naming.attribute_option_combo_url, valueCoding=_coding(declared.system, drawn)),)

    def _subject(self, tracker: _TrackerContext | None) -> Reference:
        """Who the response is about: the tracked entity of a tracker event, else the reporting unit."""
        if tracker is not None:
            return Reference(
                type=TRACKER_SUBJECT_TYPE,
                identifier=Identifier(system=self.naming.tracked_entity_system, value=tracker.tracked_entity_uid),
            )
        return Reference(reference=f"{LOCATION_RESOURCE_TYPE}/{self.location_id}")

    def _items(self, items: list[QuestionnaireItem]) -> list[QuestionnaireResponseItem]:
        """Mirror the form's item tree in document order, keeping only the branches an answer reaches."""
        generated: list[QuestionnaireResponseItem] = []
        for item in items:
            link_id = item.linkId
            if not link_id:
                continue
            nested = self._items(item.item or [])
            if item.type in _STRUCTURAL_ITEM_TYPES:
                if nested:
                    generated.append(QuestionnaireResponseItem(linkId=link_id, item=nested))
                continue
            answers = self._answers(self.index.questions.get(link_id))
            if answers or nested:
                generated.append(QuestionnaireResponseItem(linkId=link_id, answer=answers or None, item=nested or None))
        return generated

    def _answers(self, question: CaptureQuestion | None) -> list[QuestionnaireResponseAnswer]:
        """Every answer one question gets: a repeating coded question two selections, everything else one."""
        if question is None or question.answer_element in _UNGENERATED_ANSWER_ELEMENTS:
            return []
        if question.answer_element == "valueCoding":
            return self._coded_answers(question)
        answer = self._answer(question)
        return [answer] if answer is not None else []

    def _coded_answers(self, question: CaptureQuestion) -> list[QuestionnaireResponseAnswer]:
        """Select real concepts of the CodeSystem the question binds, in the spelling the contract asks for.

        A question whose ValueSet this project never published, or whose CodeSystem holds no concept,
        is left unanswered: inventing a code would only make the server warn about its own output.
        """
        system = question.option_system
        resolver = self.resolvers.for_system(system) if system is not None else None
        if system is None or resolver is None or not resolver.options:
            return []
        wanted = _REPEATED_SELECTIONS if question.repeats else 1
        selected = self._random.sample(resolver.options, min(wanted, len(resolver.options)))
        return [QuestionnaireResponseAnswer(valueCoding=_coding(system, option)) for option in selected]

    def _answer(self, question: CaptureQuestion) -> QuestionnaireResponseAnswer | None:
        """One typed answer, on the `value[x]` element the question's own item type takes."""
        element = question.answer_element
        if element == "valueInteger":
            return QuestionnaireResponseAnswer(valueInteger=self._integer(question))
        if element == "valueDecimal":
            return QuestionnaireResponseAnswer(valueDecimal=self._decimal(question))
        if element == "valueBoolean":
            return QuestionnaireResponseAnswer(valueBoolean=bool(self._random.randrange(2)))
        if element == "valueDate":
            return QuestionnaireResponseAnswer(valueDate=self.window.pick_date(self._random).isoformat())
        if element == "valueDateTime":
            return QuestionnaireResponseAnswer(valueDateTime=self._date_time())
        if element == "valueTime":
            return QuestionnaireResponseAnswer(valueTime=f"{self._hour()}:00:00")
        if element == "valueUri":
            return QuestionnaireResponseAnswer(valueUri=f"{_GENERATED_URL_HOST}/{question.link_id}")
        if element == "valueReference":
            return QuestionnaireResponseAnswer(
                valueReference=Reference(reference=f"{LOCATION_RESOURCE_TYPE}/{self.location_id}")
            )
        return QuestionnaireResponseAnswer(valueString=f"Example {question.link_id}")

    def _integer(self, question: CaptureQuestion) -> int:
        """A whole number inside whatever the question's `minValue` / `maxValue` extensions admit."""
        minimum, maximum = _numeric_range(question)
        return self._random.randint(minimum, maximum)

    def _decimal(self, question: CaptureQuestion) -> float:
        """A one-place decimal inside the question's bounds, clamped so rounding cannot leave them."""
        minimum, maximum = _numeric_range(question)
        drawn = round(self._random.uniform(minimum, maximum), _DECIMAL_PLACES)
        return float(min(max(drawn, minimum), maximum))

    def _date_time(self) -> str:
        """A seeded instant inside the window, on the hour, stated in UTC."""
        return f"{self.window.pick_date(self._random).isoformat()}T{self._hour()}:00:00Z"

    def _hour(self) -> str:
        """A seeded two-digit hour - generated timestamps land on the hour."""
        return f"{self._random.randrange(_HOURS_PER_DAY):02d}"

    def _uid(self) -> str:
        """A seeded DHIS2-shaped UID for the tracker context this response is captured in.

        The tracked entity and the enrollment a generated tracker event names do not exist on any
        instance. The capture contract checks the shape of those identifiers, not their existence,
        which is what lets a form kind whose context is data rather than metadata be generated at all.
        """
        return _shaped_uid(self._random)


def _shaped_uid(generator: random.Random) -> str:
    """A seeded DHIS2-shaped UID: one ASCII letter followed by ten alphanumeric places."""
    leading = generator.choice(_UID_LEADING_CHARACTERS)
    trailing = "".join(generator.choice(_UID_TRAILING_CHARACTERS) for _ in range(_UID_TRAILING_LENGTH))
    return f"{leading}{trailing}"


def _numeric_range(question: CaptureQuestion) -> tuple[int, int]:
    """The inclusive range a numeric answer is drawn from, opening whichever end the question leaves free."""
    bounds = question.bounds
    minimum = bounds.minimum_value if bounds is not None else None
    maximum = bounds.maximum_value if bounds is not None else None
    if minimum is None and maximum is None:
        return 0, _NUMERIC_SPAN
    if minimum is None:
        return (maximum or 0) - _NUMERIC_SPAN, maximum or 0
    if maximum is None:
        return minimum, minimum + _NUMERIC_SPAN
    return minimum, max(minimum, maximum)


def _coding(system: str, option: ResolvedCoding) -> Coding:
    """One selected concept as the coding a capture accepts: the published system, code, and display."""
    return Coding(
        system=system,
        code=option.concept_code,
        display=flatten_whitespace(option.display) if option.display else None,
    )


def _period_extension(period: PeriodValue, naming: CaptureNaming) -> Extension:
    """The D2Period extension: the DHIS2 ISO identifier, its period type, and the range it resolves to."""
    return Extension(
        url=naming.period_url,
        extension=[
            Extension(url=PERIOD_ISO_SUB_EXTENSION, valueString=period.iso),
            Extension(url=PERIOD_TYPE_SUB_EXTENSION, valueCode=period.period_type),
            Extension(
                url=PERIOD_RANGE_SUB_EXTENSION,
                valuePeriod=Period(start=period.start_date.isoformat(), end=period.end_date.isoformat()),
            ),
        ],
    )


def _reporting_period(
    index: CaptureIndex, naming: CaptureNaming, store: ResourceStore, today: datetime.date
) -> PeriodValue | None:
    """The newest completed period of the form's decided period type, or None when even the default fails."""
    isos = recent_periods(resolve_period_type(index.canonical, naming, store), 1, today)
    if not isos:
        isos = recent_periods(DEFAULT_PERIOD_TYPE, 1, today)
    return parse_period(isos[0]) if isos else None


def resolve_period_type(canonical: str, naming: CaptureNaming, store: ResourceStore) -> str:
    """Decide which DHIS2 period type a generated aggregate response reports for.

    A compiled Questionnaire does not carry its data set's period type, so it is read off the first
    served example response answering the same form - a compiled IG ships those instances, and each
    aggregate one states the real type on its D2Period. A store holding no such example, which is
    every `--live` store, falls back to `Monthly`.
    """
    for entry in store.entries:
        if entry.resource_type != RESPONSE_RESOURCE_TYPE:
            continue
        try:
            example = QuestionnaireResponse.model_validate(entry.body)
        except ValidationError:
            continue
        if example.questionnaire != canonical:
            continue
        declared = _declared_period_type(example, naming)
        if declared in PERIOD_TYPE_NAMES:
            return declared
    return DEFAULT_PERIOD_TYPE


def _declared_period_type(example: QuestionnaireResponse, naming: CaptureNaming) -> str | None:
    """The period type one example response states on its D2Period extension, when it carries one."""
    for extension in example.extension or []:
        if extension.url != naming.period_url:
            continue
        for nested in extension.extension or []:
            if nested.url == PERIOD_TYPE_SUB_EXTENSION and nested.valueCode:
                return nested.valueCode
    return None


def _capture_location_id(index: CaptureIndex, store: ResourceStore, seed: int) -> str:
    """The Location a generated response reports for: one the form admits, else one served, else a shaped UID.

    The form's published assignment comes first, because a generated response is meant to be
    postable straight back and DHIS2 refuses a capture outside the assignment with `E1029`. Absent
    an assignment, any served Location will do - it makes the response forwardable, since the DHIS2
    organisation unit behind it really exists. A store publishing no registry (a project generated
    without an org-unit selection) falls back to a seeded UID, which the capture contract admits
    because it checks the reference's shape rather than its target.
    """
    assignment = index.assignment
    if assignment is not None and assignment.references:
        admitted = sorted(assignment.references)[0]
        return admitted.removeprefix(f"{LOCATION_RESOURCE_TYPE}/")
    for entry in store.entries:
        if entry.resource_type == LOCATION_RESOURCE_TYPE:
            return entry.resource_id
    return _shaped_uid(random.Random(seed))  # noqa: S311 - a shaped placeholder identifier, not a secret
