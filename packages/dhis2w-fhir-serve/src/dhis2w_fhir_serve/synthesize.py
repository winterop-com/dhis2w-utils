"""Synthesising one QuestionnaireResponse from a served form - what `Questionnaire/{id}/$generate` answers.

A served Questionnaire already says everything an answer to it has to satisfy: the `value[x]` element
each question takes, the inclusive bounds a numeric one admits, whether it repeats, and the ValueSet a
coded one is drawn from. The capture index reads exactly those facts to *check* a submission; this
module reads the same index to *write* one. The invariant that makes the operation worth having is the
round trip - a generated response posted back to this server's own `/QuestionnaireResponse` answers
201 - and the way it is held is that both directions read one index, so a rule can never be enforced
on receipt without being honoured on generation.

An answer is drawn on the axis DHIS2 grades it on, which is the DHIS2 value type rather than the FHIR
item type the question is asked as. R4 offers one `string` item for a coordinate, a phone number, an
email address, a letter, and a username, and DHIS2 parses all five: a `[longitude,latitude]` pair for
a `COORDINATE`, an address for an `EMAIL`, one letter for a `LETTER`. A value spelled outside what the
type admits is refused at import with `E1302`, so the value type decides the value and the item type
only decides which `value[x]` element carries it (`dhis2w_fhir.seeded_format_constrained_value`, the
one rule this server and the guide's example corpus both draw from). The value types DHIS2 stores a
document or a UID reference for - a file, an image, GeoJSON, a `REFERENCE`, a `TRACKER_ASSOCIATE` -
are left unanswered rather than invented, for the same reason a question bound to unpublished
terminology is: an invented answer names a target nothing resolves.

Nothing here invents terminology. A coded answer is a concept the served CodeSystem really publishes,
carried in the exact spelling the contract asks for (the concept code, never the DHIS2 code or UID
fall-backs), so a strict-codes server accepts what a lenient one does. A question bound to terminology
this project never published is left unanswered rather than answered with something invented. The
attribute option combo an aggregate response is filed under is drawn the same way, out of the very
vocabulary the form declares, so a data set on a non-default category combo generates a response its
own capture path accepts.

The organisation unit a response reports for is part of the seeded draw, not a fixture: the same
seed names the same unit and different seeds range over the whole admitted set - the form's
published assignment where it has one, the served registry where it does not. And a `unique`
tracked entity attribute is never answered with a constant: DHIS2 refuses the second registration
carrying a repeated unique value with `E1064`, so the answer embeds the response's own minted
tracked-entity UID - the one value no other generated registration holds - through the same rule
the examples emitter uses (`dhis2w_fhir.distinct_unique_value`).

A generated stage response answers against a person this server already knows. A tracker event names
a tracked entity and an enrollment, and DHIS2 refuses one naming a pair that never existed with
`E1079` and `E1313`, so the pair is adopted from a registration receipt in this project's own spool -
the same join the capture UI's enrollment picker makes, on the program the two forms share. Only when
the spool holds no registration of that program does a stage response mint a pair of its own. Which
means a generated stage response is a function of `(questionnaire, store, spool, seed, today)`: the
same seed against the same spool state produces the same bytes, and running `d2w fhir forward` between
two calls can move which pair is adopted, because a forwarded registration is one DHIS2 already holds.

A generated registration dates the enrollment it mints, and dates the incident that enrollment follows
exactly when the form says its program collects one. That is read off the form's own
`D2CollectsIncidentDate` declaration through the capture index, so a compiled store and a `--live`
store generate the same envelope for the same program: DHIS2 refuses a registration missing the
incident date of a program that collects one with `E1023`, and the declaration is what keeps a
generated response postable in both modes.

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
from dhis2w_fhir.resources.examples import (
    UNSYNTHESIZABLE_VALUE_TYPES,
    distinct_unique_value,
    seeded_format_constrained_value,
)
from dhis2w_fhir.resources.questionnaires.schemas import FormKind
from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationError

from dhis2w_fhir_serve.capture.index import (
    QUESTIONNAIRE_RESOURCE_TYPE,
    CaptureIndex,
    CaptureQuestion,
    asked_link_ids,
)
from dhis2w_fhir_serve.capture.naming import (
    PERIOD_ISO_SUB_EXTENSION,
    PERIOD_RANGE_SUB_EXTENSION,
    PERIOD_TYPE_SUB_EXTENSION,
    CaptureNaming,
)
from dhis2w_fhir_serve.capture.resolve import CodingResolverSet, ResolvedCoding
from dhis2w_fhir_serve.spool import ResponseLifecycle, ResponseSpool, StoredReceipt
from dhis2w_fhir_serve.store import IdentifierToken, ResourceStore, StoreEntry

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

#: The form kinds whose generated response carries a tracker context - the person and the enrollment.
_TRACKER_FORM_KINDS: tuple[FormKind, ...] = ("tracker", "tracker-event")

#: The form kind whose generated response names a person and no enrollment, because it creates none.
_ENTITY_FORM_KIND: FormKind = "tracked-entity"

#: Every form kind whose generated response is about a tracked entity rather than an organisation unit.
_SUBJECT_FORM_KINDS: tuple[FormKind, ...] = (*_TRACKER_FORM_KINDS, _ENTITY_FORM_KIND)

#: The form kinds that mint the person they are about, so a unique attribute is answered from that UID.
_MINTING_FORM_KINDS: tuple[FormKind, ...] = ("tracker", _ENTITY_FORM_KIND)

#: The form kind that mints a tracker context; the other tracker kind answers against an existing one.
_REGISTRATION_FORM_KIND: FormKind = "tracker"

#: The form kind whose generated response adopts a registration's pair out of the spool.
_STAGE_FORM_KIND: FormKind = "tracker-event"

#: The lifecycle states a registration receipt is adopted from, in the order they are preferred.
#: A forwarded receipt's pair names objects DHIS2 already holds; a received one's will only after
#: the next `d2w fhir forward` run. A rejected receipt is never adopted - DHIS2 refused the
#: registration, so its pair names nothing and no forwarder run will change that.
_ADOPTABLE_LIFECYCLES: tuple[ResponseLifecycle, ...] = (ResponseLifecycle.FORWARDED, ResponseLifecycle.RECEIVED)

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
    spool: ResponseSpool | None = None,
) -> QuestionnaireResponse:
    """Generate one synthetic response to a served form: its context, then an answer to every question.

    The whole document is a function of `(questionnaire, store, spool, seed, today)`. Two terms move
    on their own: `today` decides which completed reporting period an aggregate response is for and
    which thirty days an event's timestamps fall in, and `spool` decides which registration a stage
    response answers against. A caller naming no spool generates a stage response that mints its own
    tracker pair, which is what a form kind whose context is data rather than metadata otherwise does.
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
        adopted_pair=adopted_tracker_pair(index, naming, store, spool),
    )
    return generator.build(questionnaire, period)


class TrackerPair(BaseModel):
    """The tracked entity and the enrollment one registration minted - what a stage response answers against."""

    model_config = ConfigDict(frozen=True)

    tracked_entity_uid: str
    enrollment_uid: str


class _TrackerContext(BaseModel):
    """The DHIS2 data identifiers a generated tracker response carries, plus the dates a registration adds.

    A stage response names a person and an enrollment that already exist and dates neither. A
    registration response mints both and states when the enrollment began, which is what the
    contract requires of it - and, where the guide's own examples show one, when the incident it
    follows occurred.
    """

    model_config = ConfigDict(frozen=True)

    tracked_entity_uid: str
    enrollment_uid: str | None = None
    """The enrollment the response belongs to, or None on a person-only registration, which creates none."""

    enrolled_at: str | None = None
    incident_at: str | None = None


class _Generator(BaseModel):
    """One seeded generation pass: the form's rules, the terminology behind it, and the window it sits in."""

    model_config = ConfigDict(frozen=True)

    index: CaptureIndex
    naming: CaptureNaming
    resolvers: CodingResolverSet
    seed: int
    window: DateWindow
    location_id: str
    adopted_pair: TrackerPair | None = None
    """The spooled registration's pair a generated stage response answers against, or None to mint one."""

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
        tracker = self._tracker_context() if self.index.form_kind in _SUBJECT_FORM_KINDS else None
        unique_token = (
            tracker.tracked_entity_uid if tracker is not None and self.index.form_kind in _MINTING_FORM_KINDS else None
        )
        return QuestionnaireResponse(
            meta=Meta(profile=[self.naming.response_profile_url(self.index.form_kind)]),
            identifier=Identifier(system=self.naming.generate_seed_system, value=str(self.seed)),
            extension=self._extensions(period, tracker),
            questionnaire=self.index.canonical,
            status=GENERATED_STATUS,
            subject=self._subject(tracker),
            authored=authored,
            item=self._items(questionnaire.item or [], unique_token) or None,
        )

    def _tracker_context(self) -> _TrackerContext:
        """Name the tracked entity and the enrollment a generated tracker response is captured against.

        A stage response answers against the pair a spooled registration of the same program minted,
        and mints one of its own only where the spool holds no such registration. The adopted pair
        wins over the drawn one whatever the seed would have minted: a seed is a handle on values,
        and which person a stage event is about is a fact about this project's data, not about it.

        The two UIDs are drawn off the seeded stream whatever the kind, and whether or not the draw
        is then adopted over, so adoption moves those two identifiers and nothing else in the document.

        A person-only registration draws one UID rather than two, because it names the person it
        creates and no enrollment - there is none to name.
        """
        if self.index.form_kind == _ENTITY_FORM_KIND:
            return _TrackerContext(tracked_entity_uid=self._uid())
        tracked_entity_uid = self._uid()
        enrollment_uid = self._uid()
        if self.index.form_kind != _REGISTRATION_FORM_KIND:
            adopted = self.adopted_pair
            if adopted is not None:
                return _TrackerContext(
                    tracked_entity_uid=adopted.tracked_entity_uid, enrollment_uid=adopted.enrollment_uid
                )
            return _TrackerContext(tracked_entity_uid=tracked_entity_uid, enrollment_uid=enrollment_uid)
        return _TrackerContext(
            tracked_entity_uid=tracked_entity_uid,
            enrollment_uid=enrollment_uid,
            enrolled_at=self._date_time(),
            incident_at=self._date_time() if self.index.collects_incident_date else None,
        )

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
            if tracker.enrollment_uid is not None:
                extensions.append(
                    Extension(
                        url=self.naming.tracker_enrollment_url,
                        valueIdentifier=Identifier(
                            system=self.naming.tracker_enrollment_system, value=tracker.enrollment_uid
                        ),
                    )
                )
            if tracker.enrolled_at is not None:
                extensions.append(Extension(url=self.naming.enrolled_at_url, valueDateTime=tracker.enrolled_at))
            if tracker.incident_at is not None:
                extensions.append(Extension(url=self.naming.incident_at_url, valueDateTime=tracker.incident_at))
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
        """Who the response is about: the tracked entity of a tracker response, else the reporting unit.

        A tracked entity is named as the resource type the served form declares - a person unless
        the project generating it mapped its tracked entity type to something else - so a
        generated response carries the very type the form it answers asks for.
        """
        if tracker is not None:
            return Reference(
                type=self.index.subject_type,
                identifier=Identifier(system=self.naming.tracked_entity_system, value=tracker.tracked_entity_uid),
            )
        return Reference(reference=f"{LOCATION_RESOURCE_TYPE}/{self.location_id}")

    def _items(self, items: list[QuestionnaireItem], unique_token: str | None) -> list[QuestionnaireResponseItem]:
        """Mirror the form's item tree in document order, keeping only the branches an asked answer reaches.

        DRAW EVERYTHING, THEN DROP WHAT THE FORM TURNED OUT NOT TO ASK. A question's `enableWhen`
        names another question, and the answer that settles it is one this same pass draws - so
        which questions the form is asking is not known until the draw is over. Drawing first and
        filtering after is what keeps the draw itself seeded and order-free: every question consumes
        the generator in document order whatever the conditions do, so one seed reproduces one
        response.

        The filter runs to a fixed point rather than once, because dropping an answer can close the
        question that depended on it: a chain of three conditions settles in three sweeps. It always
        terminates - the answered set only ever shrinks - and what it lands on is the set the capture
        form would have asked, which is what makes a generated response postable to a UI's own rules.
        """
        drawn: dict[str, list[QuestionnaireResponseAnswer]] = {}
        self._draw(items, unique_token, drawn)
        asked = asked_link_ids(self.index, drawn)
        while True:
            kept = {link_id: answers for link_id, answers in drawn.items() if link_id in asked}
            if len(kept) == len(drawn):
                break
            drawn = kept
            asked = asked_link_ids(self.index, drawn)
        return self._answered_items(items, drawn)

    def _draw(
        self,
        items: list[QuestionnaireItem],
        unique_token: str | None,
        drawn: dict[str, list[QuestionnaireResponseAnswer]],
    ) -> None:
        """Draw one answer set per answerable question of the subtree, in document order."""
        for item in items:
            link_id = item.linkId
            if not link_id:
                continue
            if item.type not in _STRUCTURAL_ITEM_TYPES:
                answers = self._answers(self.index.questions.get(link_id), unique_token)
                if answers:
                    drawn[link_id] = answers
            self._draw(item.item or [], unique_token, drawn)

    def _answered_items(
        self,
        items: list[QuestionnaireItem],
        drawn: dict[str, list[QuestionnaireResponseAnswer]],
    ) -> list[QuestionnaireResponseItem]:
        """The form's tree with the surviving answers in it, and every branch that reaches none left out."""
        generated: list[QuestionnaireResponseItem] = []
        for item in items:
            link_id = item.linkId
            if not link_id:
                continue
            nested = self._answered_items(item.item or [], drawn)
            if item.type in _STRUCTURAL_ITEM_TYPES:
                if nested:
                    generated.append(QuestionnaireResponseItem(linkId=link_id, item=nested))
                continue
            answers = drawn.get(link_id, [])
            if answers or nested:
                generated.append(QuestionnaireResponseItem(linkId=link_id, answer=answers or None, item=nested or None))
        return generated

    def _answers(self, question: CaptureQuestion | None, unique_token: str | None) -> list[QuestionnaireResponseAnswer]:
        """Every answer one question gets: a repeating coded question two selections, everything else one.

        A question whose DHIS2 value type holds a document or a reference to a DHIS2 object - a file,
        an image, GeoJSON, a `REFERENCE`, a `TRACKER_ASSOCIATE` - is left unanswered, the rule the
        guide's example corpus follows: an invented one names a target nothing resolves, and DHIS2
        refuses it with `E1302`. The form still admits the response, because a question the form does
        not mark required is answerable and not obligatory.

        A read-only question is left unanswered for a stronger reason: the form states that DHIS2
        owns the value. A generated tracked entity attribute is minted by the instance on import, so
        a drawn value is a value the instance discards - and one drawn from the same shape as a real
        one is worse, because it reads as a claim about a person's identifier. The rule holds even
        when the form marks the question required, and the capture grading admits the absence on the
        same grounds: what DHIS2 answers is not something a client is waiting to be asked for.
        """
        if question is None or question.answer_element in _UNGENERATED_ANSWER_ELEMENTS:
            return []
        if question.read_only:
            return []
        if question.value_type in UNSYNTHESIZABLE_VALUE_TYPES:
            return []
        if question.answer_element == "valueCoding":
            return self._coded_answers(question)
        if unique_token is not None and question.unique:
            distinct = _distinct_answer(question, unique_token)
            if distinct is not None:
                return [distinct]
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
        """One typed answer: the `value[x]` element from the item type, the value from the DHIS2 value type.

        The item type decides only which element carries the answer. Which value it carries is the
        DHIS2 value type's to say, because that is what DHIS2 grades the value against on import -
        R4 asks a coordinate, a phone number, an email address, a letter, and a username all as
        `string` items, and DHIS2 parses each of the five. Only a value type DHIS2 stores as free
        text falls through to the wording that names the question.
        """
        element = question.answer_element
        if element == "valueInteger":
            return QuestionnaireResponseAnswer(valueInteger=self._integer(question))
        if element == "valueDecimal":
            return QuestionnaireResponseAnswer(valueDecimal=self._decimal(question))
        if element == "valueBoolean":
            return QuestionnaireResponseAnswer(valueBoolean=bool(self._random.randrange(2)))
        if element == "valueDate":
            return QuestionnaireResponseAnswer(valueDate=self._date(question))
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
        constrained = (
            seeded_format_constrained_value(question.value_type, self._random)
            if question.value_type is not None
            else None
        )
        if constrained is not None:
            return QuestionnaireResponseAnswer(valueString=constrained)
        return QuestionnaireResponseAnswer(valueString=f"Example {question.link_id}")

    def _date(self, question: CaptureQuestion) -> str:
        """A calendar day inside the window, moved into whatever range the question's bounds admit.

        The window is where a generated capture lives - the last few weeks, or the reporting period -
        and a date bound is a form saying which days it takes at all. The window is drawn from first
        so a bounded question and an unbounded one on the same form still land near each other, and
        the draw is then clamped rather than redrawn: a clamp cannot fall outside, and a redraw over
        a range the window does not overlap would never terminate.
        """
        drawn = self.window.pick_date(self._random).isoformat()
        bounds = question.bounds
        if bounds is None:
            return drawn
        minimum = bounds.minimum.date if bounds.minimum is not None else None
        maximum = bounds.maximum.date if bounds.maximum is not None else None
        if minimum is not None and drawn < minimum:
            drawn = minimum
        if maximum is not None and drawn > maximum:
            drawn = maximum
        return max(drawn, minimum) if minimum is not None else drawn

    def _integer(self, question: CaptureQuestion) -> int:
        """A whole number inside whatever the question's `minValue` / `maxValue` extensions admit."""
        minimum, maximum = _numeric_range(question)
        return self._random.randint(int(minimum), int(maximum))

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
        """A seeded DHIS2-shaped UID for a tracker identity this response is the first to name.

        A generated registration mints the two identifiers it creates, which is what a real client
        does too - the person and the enrollment come into existence with the submission that
        registers them. A generated stage response names a pair a spooled registration already
        minted, and mints one only where the spool holds no registration of its program to adopt
        from; that fall-back pair exists on no instance, and DHIS2 refuses a stage event naming it
        with `E1079` and `E1313`, which is exactly what the adoption is for.

        The capture contract checks the shape of these identifiers rather than their existence,
        which is what lets a form kind whose context is data rather than metadata be generated at
        all - and what keeps the 201 round trip standing whichever way the pair was decided.
        """
        return _shaped_uid(self._random)


def _distinct_answer(question: CaptureQuestion, token: str) -> QuestionnaireResponseAnswer | None:
    """The answer a `unique` tracked entity attribute gets: a value carrying the minted tracked-entity UID.

    DHIS2 refuses a second tracked entity repeating a unique attribute's value with `E1064`, so a
    generated registration answers such a question from its own minted UID - the one value no other
    generated response holds - through the very rule the examples emitter uses. The rule speaks
    DHIS2 value types, which is why the question's `value_type` fact gates it: a store serving no
    attribute CodeSystem states no value type, and the ordinary draw stands. A bounded integer
    stands on the ordinary draw too - a distinct value has to range wider than any bound admits,
    and generating outside the form's own bounds would break the post-back invariant.
    """
    if question.value_type is None:
        return None
    if question.bounds is not None:
        return None
    value = distinct_unique_value(question.display or question.link_id, question.value_type, token)
    if value is None:
        return None
    if question.answer_element == "valueString":
        return QuestionnaireResponseAnswer(valueString=value)
    if question.answer_element == "valueUri":
        return QuestionnaireResponseAnswer(valueUri=value)
    if question.answer_element == "valueInteger":
        return QuestionnaireResponseAnswer(valueInteger=int(value))
    return None


def adopted_tracker_pair(
    index: CaptureIndex, naming: CaptureNaming, store: ResourceStore, spool: ResponseSpool | None
) -> TrackerPair | None:
    """The pair a generated stage response answers against: what a spooled registration of its program minted.

    This is the join the capture UI's enrollment picker makes, made server-side. A stage form names
    its program on the `{base}/id/program` identifier, the registration form of that program carries
    the same identifier, and every receipt answering that form holds one minted pair - so the whole
    lookup is local to this project and touches no instance.

    The order is the picker's order. A forwarded registration is preferred over a received one
    because DHIS2 already holds its pair, and within a state the newest registration wins, which is
    the person most plausibly being followed up. A rejected registration is never adopted. A receipt
    holding half a pair, or one these models cannot read, is passed over rather than adopted from,
    because a stage event built on half a pair is refused exactly as surely as one built on a
    fabricated pair. None means the spool holds no registration of this program, and the caller mints.
    """
    if spool is None or index.form_kind != _STAGE_FORM_KIND or index.program_uid is None:
        return None
    forms = _program_form_entries(index.program_uid, naming, store)
    if not forms:
        return None
    reading = spool.search(form_kind=_REGISTRATION_FORM_KIND, lifecycles=_ADOPTABLE_LIFECYCLES)
    preferred = sorted(reading.receipts, key=lambda receipt: _ADOPTABLE_LIFECYCLES.index(receipt.lifecycle))
    for receipt in preferred:
        if not any(_answers_form(receipt, entry) for entry in forms):
            continue
        pair = _receipt_tracker_pair(receipt, naming)
        if pair is not None:
            return pair
    return None


def _program_form_entries(program_uid: str, naming: CaptureNaming, store: ResourceStore) -> tuple[StoreEntry, ...]:
    """Every served Questionnaire carrying one program's grouping identifier - its registration form among them.

    The program identifier alone names a program's registration form, its stage forms, and an event
    program's own form alike, so it is not on its own enough to say which form a receipt answered.
    What settles it is the receipt: the facade records the DHIS2 form kind it validated a submission
    as, and only a registration is recorded as `tracker`, so filtering the receipts by kind and their
    forms by program identifies the registrations of one program exactly.
    """
    token = IdentifierToken(system=naming.program_identifier_system, value=program_uid)
    return tuple(
        entry
        for entry in store.entries
        if entry.resource_type == QUESTIONNAIRE_RESOURCE_TYPE and token in entry.identifiers
    )


def _answers_form(receipt: StoredReceipt, entry: StoreEntry) -> bool:
    """Whether one receipt answered one served form, by the canonical it names or the id that canonical ends in."""
    return receipt.questionnaire == entry.canonical_url or receipt.questionnaire.rsplit("/", 1)[-1] == entry.resource_id


def _receipt_tracker_pair(receipt: StoredReceipt, naming: CaptureNaming) -> TrackerPair | None:
    """The whole pair one registration receipt minted, read off the resource as it was submitted."""
    try:
        response = QuestionnaireResponse.model_validate(receipt.response)
    except ValidationError:
        return None
    subject_identifier = response.subject.identifier if response.subject is not None else None
    tracked_entity_uid = (
        subject_identifier.value
        if subject_identifier is not None and subject_identifier.system == naming.tracked_entity_system
        else None
    )
    enrollment_uid = next(
        (
            extension.valueIdentifier.value
            for extension in response.extension or []
            if extension.url == naming.tracker_enrollment_url and extension.valueIdentifier is not None
        ),
        None,
    )
    if not tracked_entity_uid or not enrollment_uid:
        return None
    return TrackerPair(tracked_entity_uid=tracked_entity_uid, enrollment_uid=enrollment_uid)


def _shaped_uid(generator: random.Random) -> str:
    """A seeded DHIS2-shaped UID: one ASCII letter followed by ten alphanumeric places."""
    leading = generator.choice(_UID_LEADING_CHARACTERS)
    trailing = "".join(generator.choice(_UID_TRAILING_CHARACTERS) for _ in range(_UID_TRAILING_LENGTH))
    return f"{leading}{trailing}"


def _numeric_range(question: CaptureQuestion) -> tuple[float, float]:
    """The inclusive range a numeric answer is drawn from, opening whichever end the question leaves free.

    A date bound states nothing about a quantity, so a question carrying one is drawn from the open
    range exactly as an unbounded question is - `CaptureBound.number` is None for it, and None here
    means the end is free.
    """
    bounds = question.bounds
    minimum = bounds.minimum.number if bounds is not None and bounds.minimum is not None else None
    maximum = bounds.maximum.number if bounds is not None and bounds.maximum is not None else None
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
    """The Location a generated response reports for: a seeded draw across the units the form admits.

    The admitted set is the form's published assignment where it has one - a generated response is
    meant to be postable straight back, and DHIS2 refuses a capture outside the assignment with
    `E1029` - intersected with the served registry so the drawn unit really exists (the whole
    assignment stands when the store serves none of it). A form publishing no assignment draws
    across the whole served registry. The unit is part of the seed's draw like every other value:
    the same seed names the same unit, and different seeds range over the whole admitted set. A
    store publishing no registry (a project generated without an org-unit selection) falls back to
    a seeded UID, which the capture contract admits because it checks the reference's shape rather
    than its target.
    """
    admitted = _admitted_location_ids(index, store)
    generator = random.Random(seed)  # noqa: S311 - a reproducibility handle, not a secret
    if admitted:
        return admitted[generator.randrange(len(admitted))]
    return _shaped_uid(generator)


def _admitted_location_ids(index: CaptureIndex, store: ResourceStore) -> tuple[str, ...]:
    """The Location ids a generated response may report for, sorted so the seeded draw is stable."""
    prefix = f"{LOCATION_RESOURCE_TYPE}/"
    assignment = index.assignment
    assigned = (
        sorted({reference.removeprefix(prefix) for reference in assignment.references if reference.startswith(prefix)})
        if assignment is not None
        else []
    )
    served = {entry.resource_id for entry in store.entries if entry.resource_type == LOCATION_RESOURCE_TYPE}
    if assigned:
        intersected = [resource_id for resource_id in assigned if resource_id in served]
        return tuple(intersected or assigned)
    return tuple(sorted(served))
