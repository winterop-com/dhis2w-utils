"""Serialising one question's answers into the DHIS2 wire value, exhaustively per value type.

This is the inverse of what the examples emitter wrote forward, and it is written as one branch
per `WireValueKind` so the two directions can be read side by side:

    TRUE_ONLY          `"true"`, or no data value at all - DHIS2 never stores `"false"` here.
    BOOLEAN            `"true"` / `"false"`.
    INTEGER family     the integer verbatim; the form's own `minValue` / `maxValue` are DHIS2's to enforce.
    NUMBER family      the lexical decimal the R4 primitive carries - a whole number stays whole.
    MULTI_TEXT         every selected option's DHIS2 code, joined by the separator DHIS2 splits on.
    option-coded       the resolved option's DHIS2 code, falling back to its UID.
    DATE / TIME        the R4 primitive verbatim; both are already what DHIS2 stores.
    DATETIME           the zone-less wall clock behind the zoned R4 instant (BUGS.md #62).
    URL / text         the string verbatim, which is where `COORDINATE` lands too.
    ORGANISATION_UNIT  the DHIS2 UID behind the answered Location reference.
    attachment         refused - DHIS2's file-resource wire is a separate upload, not a data value.

Nothing here reaches for a default. A question the translator cannot serialise answers with a
typed refusal naming the link id, so a caller never posts a payload with a value quietly missing
from the middle of it.
"""

from __future__ import annotations

import datetime
import zoneinfo
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.conversion.schemas import (
    CONCEPT_CODE_TIER,
    OPTION_CODE_TIER,
    OPTION_UID_TIER,
    CodedAnswerMode,
    ConversionNote,
    ConversionNoteCategory,
    ConversionRefusal,
    ConversionRefusalCategory,
    OptionEntry,
    OptionLookup,
    OptionTable,
    ResolvedOption,
    WireValueKind,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dhis2w_fhir.conversion.schemas import ConversionContext, QuestionSpec
    from dhis2w_fhir.r4 import QuestionnaireResponseAnswer

__all__ = [
    "ANSWER_VALUE_ELEMENTS",
    "LOCATION_REFERENCE_PREFIX",
    "MULTI_VALUE_SEPARATOR",
    "OrganisationUnitResolution",
    "WallClockReading",
    "WireValue",
    "answer_wire_value",
    "decimal_wire_value",
    "resolve_option",
    "resolve_organisation_unit",
    "wall_clock_reading",
    "wall_clock_notes",
]

#: The separator DHIS2 joins a MULTI_TEXT value's option codes with.
MULTI_VALUE_SEPARATOR = ","

#: The prefix an organisation-unit answer references its published Location under.
LOCATION_REFERENCE_PREFIX = "Location/"

#: Every `value[x]` element an answer may carry, in the order R4 declares them.
ANSWER_VALUE_ELEMENTS = (
    "valueBoolean",
    "valueDecimal",
    "valueInteger",
    "valueDate",
    "valueDateTime",
    "valueTime",
    "valueString",
    "valueUri",
    "valueAttachment",
    "valueCoding",
    "valueReference",
)

#: The DHIS2 wire spellings of a true and a false value, which is what a boolean answer becomes.
_TRUE_WIRE_VALUE = "true"
_FALSE_WIRE_VALUE = "false"


class WireValue(BaseModel):
    """One DHIS2 data value the translator produced, and what producing it had to interpret or refuse.

    `value` is None on two very different outcomes, which `refusals` separates: a `TRUE_ONLY`
    question answered `false` writes no data value *because that is how DHIS2 spells false*, while
    a refused answer writes none because the response is not translatable at all.
    """

    model_config = ConfigDict(frozen=True)

    value: str | None = None
    notes: tuple[ConversionNote, ...] = ()
    refusals: tuple[ConversionRefusal, ...] = ()


class WallClockReading(BaseModel):
    """One R4 timestamp read back to the zone-less wall clock DHIS2 stores, and what reading it took."""

    model_config = ConfigDict(frozen=True)

    value: str
    derived: bool = False
    """Whether an offset was present and read back through the project's zone."""

    unzoned: bool = False
    """Whether no offset was present, so the timestamp was taken as already being the wall clock."""

    moment: datetime.datetime | None = None
    """The same wall clock as a zone-less `datetime`, which is what `TrackerEvent.occurredAt` takes."""


def answer_wire_value(
    question: QuestionSpec,
    answers: Sequence[QuestionnaireResponseAnswer],
    context: ConversionContext,
) -> WireValue:
    """Serialise every answer to one question into the single data value DHIS2 stores for it."""
    if not answers:
        return _refuse(
            question,
            ConversionRefusalCategory.MISSING_ANSWER_VALUE,
            f"`{question.link_id}` carries no answer",
        )
    mismatch = _element_refusal(question, answers)
    if mismatch is not None:
        return WireValue(refusals=(mismatch,))
    if question.wire_kind == WireValueKind.MULTI_TEXT:
        return _multi_text_value(question, answers, context)
    if len(answers) > 1:
        return _refuse(
            question,
            ConversionRefusalCategory.REPEATED_ANSWER,
            f"`{question.link_id}` stores one DHIS2 data value, and {len(answers)} answers were sent",
        )
    return _single_value(question, answers[0], context)


def resolve_option(table: OptionTable, code: str, mode: CodedAnswerMode) -> OptionLookup:
    """Resolve one received code to the option it names, as strictly as the run's dial asks.

    Strict accepts the concept code the served CodeSystem publishes and nothing else. Lenient
    then tries the DHIS2 option UID and the DHIS2 option code, because the generated CodeSystem
    carries every option under both spellings and a client that sent the other one still named
    exactly one option. Two matches inside one tier is an ambiguity leniency cannot paper over.
    """
    matched = _tier(table, code, CONCEPT_CODE_TIER)
    if matched.option is not None or matched.ambiguous_option_uids:
        return matched
    if mode == CodedAnswerMode.STRICT:
        return OptionLookup()
    by_uid = _tier(table, code, OPTION_UID_TIER)
    if by_uid.option is not None or by_uid.ambiguous_option_uids:
        return by_uid
    return _tier(table, code, OPTION_CODE_TIER)


def wall_clock_reading(value: str, timezone: str | None) -> WallClockReading:
    """Read one R4 timestamp back to the zone-less wall clock DHIS2 stores - the inverse of `zoned_date_time`.

    DHIS2 serves and accepts `occurredAt` and `DATETIME` data values as zone-less local timestamps
    under fields its OpenAPI types as `Instant` (BUGS.md #62), so the offset an R4 `dateTime`
    requires is exactly what has to come back off. `timezone` is the IANA zone those wall-clock
    readings are taken in, which the project states as `[generate] timezone`; naming none reads
    the clock in UTC, which is the same guess the forward direction makes.

    A date-only value carries no clock and passes through, and so does a timestamp already written
    without an offset - the caller is told which through `unzoned` rather than left to assume.
    """
    if "T" not in value:
        return WallClockReading(value=value, moment=_moment(value))
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return WallClockReading(value=value, unzoned=True)
    if parsed.tzinfo is None:
        return WallClockReading(value=value, unzoned=True, moment=parsed)
    local = parsed.astimezone(_zone(timezone)).replace(tzinfo=None)
    return WallClockReading(value=local.isoformat(), derived=True, moment=local)


def _moment(value: str) -> datetime.datetime | None:
    """One timestamp as the zone-less `datetime` it names, or None when it names no instant at all."""
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def decimal_wire_value(value: int | float) -> str:
    """Write one R4 decimal answer as the DHIS2 wire value it is, without a float round trip.

    A whole number stays whole - the R4 model types `valueDecimal` as `int | float` for exactly
    that reason, so `2896` never becomes `2896.0`. A fractional number is written as the shortest
    decimal that reads back as the same number, and never in exponent notation, which DHIS2's
    numeric value types do not accept.
    """
    if isinstance(value, int):
        return str(value)
    text = repr(value)
    if "e" in text or "E" in text:
        return format(Decimal(text), "f")
    return text


def _single_value(question: QuestionSpec, answer: QuestionnaireResponseAnswer, context: ConversionContext) -> WireValue:
    """Serialise the one answer a non-repeating question carries."""
    kind = question.wire_kind
    if kind == WireValueKind.INTEGER:
        return WireValue(value=str(answer.valueInteger))
    if kind == WireValueKind.DECIMAL and answer.valueDecimal is not None:
        return WireValue(value=decimal_wire_value(answer.valueDecimal))
    if kind == WireValueKind.TRUE_ONLY:
        return _true_only_value(question, answer)
    if kind == WireValueKind.BOOLEAN:
        return _boolean_value(question, answer)
    if kind == WireValueKind.CODED:
        return _coded_answers(question, [answer], context)
    if kind == WireValueKind.DATE:
        return WireValue(value=answer.valueDate)
    if kind == WireValueKind.DATE_TIME:
        return _date_time_value(question, answer, context)
    if kind == WireValueKind.TIME:
        return WireValue(value=answer.valueTime)
    if kind == WireValueKind.URI:
        return WireValue(value=answer.valueUri)
    if kind == WireValueKind.ORGANISATION_UNIT:
        return _organisation_unit_value(question, answer, context)
    if kind == WireValueKind.ATTACHMENT:
        return _refuse(
            question,
            ConversionRefusalCategory.UNSUPPORTED_ANSWER_VALUE,
            f"`{question.link_id}` answers with an attachment, which DHIS2 stores as a file resource "
            f"rather than as a data value",
        )
    return WireValue(value=answer.valueString)


def _true_only_value(question: QuestionSpec, answer: QuestionnaireResponseAnswer) -> WireValue:
    """Serialise a `TRUE_ONLY` answer, which DHIS2 spells as `"true"` or as no data value at all."""
    if answer.valueBoolean:
        return WireValue(value=_TRUE_WIRE_VALUE)
    return WireValue(
        notes=(
            _note(
                question,
                ConversionNoteCategory.TRUE_ONLY_FALSE_DROPPED,
                f"`{question.link_id}` is a TRUE_ONLY question answered `false`, which DHIS2 stores as "
                f"no data value; the answer is written as nothing rather than as `{_FALSE_WIRE_VALUE}`",
            ),
        )
    )


def _boolean_value(question: QuestionSpec, answer: QuestionnaireResponseAnswer) -> WireValue:
    """Serialise a `BOOLEAN` answer, noting when the context could not rule out `TRUE_ONLY`."""
    if answer.valueBoolean:
        return WireValue(value=_TRUE_WIRE_VALUE)
    notes: tuple[ConversionNote, ...] = ()
    if question.value_type is None:
        notes = (
            _note(
                question,
                ConversionNoteCategory.BOOLEAN_VALUE_TYPE_ASSUMED,
                f"`{question.link_id}` answers `false` and the context carries no DHIS2 value type for it, "
                f"so it is written as BOOLEAN; a TRUE_ONLY data element rejects `{_FALSE_WIRE_VALUE}`",
            ),
        )
    return WireValue(value=_FALSE_WIRE_VALUE, notes=notes)


def _date_time_value(
    question: QuestionSpec, answer: QuestionnaireResponseAnswer, context: ConversionContext
) -> WireValue:
    """Serialise a `DATETIME` answer as the zone-less wall clock DHIS2 stores."""
    reading = wall_clock_reading(answer.valueDateTime or "", context.timezone)
    return WireValue(value=reading.value, notes=wall_clock_notes(reading, context, link_id=question.link_id))


def _organisation_unit_value(
    question: QuestionSpec, answer: QuestionnaireResponseAnswer, context: ConversionContext
) -> WireValue:
    """Serialise an `ORGANISATION_UNIT` answer as the DHIS2 UID behind the Location it references."""
    reference = answer.valueReference.reference if answer.valueReference is not None else None
    if not reference or not reference.startswith(LOCATION_REFERENCE_PREFIX):
        return _refuse(
            question,
            ConversionRefusalCategory.MISSING_ORGANISATION_UNIT,
            f"`{question.link_id}` carries no `{LOCATION_REFERENCE_PREFIX}<id>` reference",
        )
    resolution = resolve_organisation_unit(reference, context)
    if resolution.uid is None:
        return _refuse(
            question,
            ConversionRefusalCategory.UNRESOLVABLE_ORGANISATION_UNIT,
            f"`{question.link_id}` references `{reference}`, which no published Location identifies "
            f"a DHIS2 organisation unit for",
        )
    notes = () if resolution.note is None else (resolution.note.model_copy(update={"link_id": question.link_id}),)
    return WireValue(value=resolution.uid, notes=notes)


def _multi_text_value(
    question: QuestionSpec, answers: Sequence[QuestionnaireResponseAnswer], context: ConversionContext
) -> WireValue:
    """Serialise every selection of a `MULTI_TEXT` question as the one comma-joined value DHIS2 stores."""
    return _coded_answers(question, answers, context)


def _coded_answers(
    question: QuestionSpec, answers: Sequence[QuestionnaireResponseAnswer], context: ConversionContext
) -> WireValue:
    """Resolve every coding of one question and join the DHIS2 option values it selected."""
    table = context.option_tables.get(question.option_system or "")
    values: list[str] = []
    notes: list[ConversionNote] = []
    for answer in answers:
        coding = answer.valueCoding
        code = coding.code if coding is not None else None
        if not code:
            return _refuse(
                question,
                ConversionRefusalCategory.MISSING_CODING,
                f"`{question.link_id}` carries a coding with no code",
            )
        if table is None:
            notes.append(
                _note(
                    question,
                    ConversionNoteCategory.CODED_ANSWER_UNCHECKED,
                    f"`{question.link_id}` binds terminology the context does not carry, so `{code}` "
                    f"goes to DHIS2 as sent",
                )
            )
            values.append(code)
            continue
        lookup = resolve_option(table, code, context.coded_answer_mode)
        if lookup.ambiguous_option_uids:
            return _refuse(
                question,
                ConversionRefusalCategory.AMBIGUOUS_CODING,
                f"`{question.link_id}` answers `{code}`, which names more than one option of "
                f"`{table.system}` ({', '.join(lookup.ambiguous_option_uids)})",
            )
        if lookup.option is None:
            return _refuse(
                question,
                ConversionRefusalCategory.UNRESOLVABLE_CODING,
                f"`{question.link_id}` answers `{code}`, which `{table.system}` holds no option for "
                f"under the `{context.coded_answer_mode}` coded-answer dial",
            )
        notes.extend(_option_notes(question, code, lookup.option))
        values.append(lookup.option.entry.wire_value)
    return WireValue(value=MULTI_VALUE_SEPARATOR.join(values), notes=tuple(notes))


def _option_notes(question: QuestionSpec, code: str, resolved: ResolvedOption) -> list[ConversionNote]:
    """What one resolved coding is worth telling the caller: a fall-back spelling, or an unrecoverable code."""
    notes: list[ConversionNote] = []
    if not resolved.matched_contract_spelling:
        notes.append(
            _note(
                question,
                ConversionNoteCategory.CODED_ANSWER_FALLBACK,
                f"`{question.link_id}` answers `{code}`, which matched option {resolved.entry.option_uid} by "
                f"{resolved.matched_by}; the contract asks for concept code `{resolved.entry.concept_code}`",
            )
        )
    if resolved.entry.option_code is None:
        notes.append(
            _note(
                question,
                ConversionNoteCategory.OPTION_CODE_UNRECOVERABLE,
                f"the served terminology carries no DHIS2 code for option {resolved.entry.option_uid}, so "
                f"`{question.link_id}` is written with the option UID",
            )
        )
    return notes


class OrganisationUnitResolution(BaseModel):
    """The DHIS2 organisation unit one `Location/<id>` reference names, and what resolving it took."""

    model_config = ConfigDict(frozen=True)

    uid: str | None = None
    note: ConversionNote | None = None


def resolve_organisation_unit(reference: str, context: ConversionContext) -> OrganisationUnitResolution:
    """Resolve a `Location/<id>` reference to the DHIS2 organisation unit UID the published Location identifies.

    A Location id is an identity stem, and under `naming.source = "code"` that stem is the unit's
    DHIS2 code rather than its UID - so the resolution goes through the org-unit identifier the
    registry wrote and never assumes the id is the UID. A context given no Location table has
    nothing to go through and falls back to reading the id as a UID, which it says out loud.
    """
    location_id = reference.removeprefix(LOCATION_REFERENCE_PREFIX)
    if not location_id:
        return OrganisationUnitResolution()
    if not context.resolves_organisation_units:
        return OrganisationUnitResolution(
            uid=location_id,
            note=ConversionNote(
                category=ConversionNoteCategory.ORGANISATION_UNIT_ASSUMED,
                message=f"the context carries no published Location, so `{reference}` is read as the DHIS2 "
                f"organisation unit UID `{location_id}`",
            ),
        )
    return OrganisationUnitResolution(uid=context.organisation_unit_uids_by_location_id.get(location_id))


def wall_clock_notes(
    reading: WallClockReading, context: ConversionContext, *, link_id: str | None
) -> tuple[ConversionNote, ...]:
    """The note one wall-clock reading is worth, so a stripped offset is never silent."""
    if reading.derived:
        zone = context.timezone or "UTC"
        return (
            ConversionNote(
                category=ConversionNoteCategory.WALL_CLOCK_DERIVED,
                link_id=link_id,
                message=f"the zoned timestamp was read in `{zone}` and written as the zone-less "
                f"wall clock `{reading.value}` DHIS2 stores",
            ),
        )
    if reading.unzoned:
        return (
            ConversionNote(
                category=ConversionNoteCategory.TIMESTAMP_UNZONED,
                link_id=link_id,
                message=f"`{reading.value}` carries no UTC offset, so it is taken as already being the "
                f"wall clock DHIS2 stores",
            ),
        )
    return ()


def _element_refusal(
    question: QuestionSpec, answers: Sequence[QuestionnaireResponseAnswer]
) -> ConversionRefusal | None:
    """Check every answer carries exactly the one `value[x]` element the question answers on."""
    for answer in answers:
        carried = [name for name in ANSWER_VALUE_ELEMENTS if getattr(answer, name) is not None]
        if not carried:
            return _refusal(
                question,
                ConversionRefusalCategory.MISSING_ANSWER_VALUE,
                f"`{question.link_id}` carries an answer with no value",
            )
        if len(carried) > 1 or carried[0] != question.answer_element:
            return _refusal(
                question,
                ConversionRefusalCategory.ANSWER_ELEMENT_MISMATCH,
                f"`{question.link_id}` answers as `{question.item_type}`, so it carries "
                f"`{question.answer_element}`, not {', '.join(f'`{name}`' for name in carried)}",
            )
    return None


def _tier(table: OptionTable, code: str, tier: str) -> OptionLookup:
    """The single option matching the code on one spelling, or the ambiguity that tier holds."""
    matches = [entry for entry in table.entries if _spelling(entry, tier) == code]
    if len(matches) > 1:
        return OptionLookup(ambiguous_option_uids=tuple(entry.option_uid for entry in matches))
    if not matches:
        return OptionLookup()
    return OptionLookup(option=ResolvedOption(entry=matches[0], matched_by=tier))


def _spelling(entry: OptionEntry, tier: str) -> str | None:
    """One option's code under the spelling a resolution tier matches on."""
    if tier == CONCEPT_CODE_TIER:
        return entry.concept_code
    if tier == OPTION_UID_TIER:
        return entry.option_uid
    return entry.option_code


def _zone(timezone: str | None) -> datetime.tzinfo:
    """The zone a wall clock is read in: the project's, or UTC when it names none or names one nobody has."""
    if timezone is None:
        return datetime.UTC
    try:
        return zoneinfo.ZoneInfo(timezone)
    except (ValueError, zoneinfo.ZoneInfoNotFoundError):
        return datetime.UTC


def _note(question: QuestionSpec, category: ConversionNoteCategory, message: str) -> ConversionNote:
    """One note about one question."""
    return ConversionNote(category=category, link_id=question.link_id, message=message)


def _refusal(question: QuestionSpec, category: ConversionRefusalCategory, reason: str) -> ConversionRefusal:
    """One refusal about one question."""
    return ConversionRefusal(category=category, link_id=question.link_id, reason=reason)


def _refuse(question: QuestionSpec, category: ConversionRefusalCategory, reason: str) -> WireValue:
    """One refused question, as the wire value it writes nothing for."""
    return WireValue(refusals=(_refusal(question, category, reason),))
