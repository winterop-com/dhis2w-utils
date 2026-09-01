"""One stored DHIS2 value as the answer its question asks for - the typing both served projections share.

A tracker event and an aggregate data value are two different reads of DHIS2 and one question about
each value: which `value[x]` element does the form ask this on, and what does the string the instance
stored become on it. That question has one answer, and it lives here so a record and a data set
read-back can never type the same value two ways.

THE FORM DECIDES THE ELEMENT AND THE INSTANCE DECIDES THE VALUE. Every question's item type,
terminology binding, and DHIS2 value type is read off the very `CaptureIndex` a received response is
validated against - so a value can never be typed one way on the way in and another on the way out.

A VALUE THE TERMINOLOGY CANNOT CODE IS CARRIED AS THE STRING DHIS2 STORED, and so is a number the
instance holds in a spelling its own value type does not admit. That is `dhis2w_fhir`'s own emitter
rule (`_fallback` in `dhis2w_fhir.resources.examples`), kept here so a served document and the
published example corpus say the same thing about the same value. Dropping it would hide a value the
instance holds; recoding it would be this server deciding what an option means.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from dhis2w_fhir import zoned_date_time
from dhis2w_fhir.names import flatten_whitespace
from dhis2w_fhir.r4 import (
    Coding,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
    is_fhir_date,
    is_fhir_date_time,
    is_fhir_time,
)

from dhis2w_fhir_serve.capture.resolve import CodingResolutionError, CodingResolverSet

if TYPE_CHECKING:
    from dhis2w_fhir_serve.capture.index import CaptureIndex, CaptureQuestion

#: The resource type an organisation unit is referenced by, which is what an `ORGANISATION_UNIT`
#: value answers onto.
LOCATION_RESOURCE_TYPE = "Location"

#: The DHIS2 value type whose stored value is several values, and the character separating them.
MULTI_VALUE_TYPE = "MULTI_TEXT"
MULTI_VALUE_SEPARATOR = ","

#: The `value[x]` element no served value is ever written on: DHIS2 stores a file or an image as a
#: UID naming a document this facade does not serve, so an attachment here would reference nothing.
UNSERVED_ANSWER_ELEMENT = "valueAttachment"

ResponseStatusCode = Literal["in-progress", "completed", "amended", "entered-in-error", "stopped"]
"""The `QuestionnaireResponse.status` codes R4 admits, which a DHIS2 status maps onto."""

#: The `value[x]` elements carrying an R4 primitive with a spelling of its own to check.
_TEMPORAL_ELEMENTS = ("valueDate", "valueDateTime", "valueTime")

#: The literals DHIS2 stores a boolean as, either way round.
_TRUE_LITERALS = frozenset({"true", "1"})
_FALSE_LITERALS = frozenset({"false", "0"})


def question_answers(
    question: CaptureQuestion,
    value: str,
    *,
    resolvers: CodingResolverSet,
    timezone: str | None,
) -> list[QuestionnaireResponseAnswer]:
    """Every answer one stored value becomes: several for a multi-text question, one for the rest."""
    if question.answer_element == UNSERVED_ANSWER_ELEMENT:
        return []
    if question.option_system is not None:
        parts = value.split(MULTI_VALUE_SEPARATOR) if question.value_type == MULTI_VALUE_TYPE else [value]
        return [coded_answer(question, part.strip(), resolvers) for part in parts if part.strip()]
    return [typed_answer(question, value, timezone)]


def coded_answer(question: CaptureQuestion, value: str, resolvers: CodingResolverSet) -> QuestionnaireResponseAnswer:
    """One option value as the coding the published CodeSystem states for it, else as DHIS2 stored it."""
    system = question.option_system
    coding = None if system is None else served_coding(system, value, resolvers)
    if coding is None:
        return QuestionnaireResponseAnswer(valueString=value)
    return QuestionnaireResponseAnswer(valueCoding=coding)


def served_coding(system: str, value: str, resolvers: CodingResolverSet) -> Coding | None:
    """One DHIS2 value as the coding the served CodeSystem states for it, or None when it states none.

    The value DHIS2 stores is the option's own code, and the served CodeSystem publishes that code
    beside the concept code whichever spelling it was generated in - so resolution is the same tiered
    lookup a received answer goes through, leniently, since the instance is not a client that can be
    asked to send the contract's spelling.

    Both things this facade reads back out of DHIS2 and codes come through here: a coded answer to a
    question, and the attribute option combo an aggregate form is filed under. One resolution means
    one spelling, whichever of the two is being written.
    """
    resolver = resolvers.for_system(system)
    if resolver is None:
        return None
    try:
        resolved = resolver.resolve(value, strict=False)
    except CodingResolutionError:
        return None
    return Coding(
        system=system,
        code=resolved.concept_code,
        display=flatten_whitespace(resolved.display) if resolved.display else None,
    )


def typed_answer(question: CaptureQuestion, value: str, timezone: str | None) -> QuestionnaireResponseAnswer:
    """Cast one stored value onto the `value[x]` element its question asks it on, else onto a string."""
    text = value.strip()
    element = question.answer_element
    if element == "valueInteger":
        return number_answer(text, whole=True)
    if element == "valueDecimal":
        return number_answer(text, whole=False)
    if element == "valueBoolean":
        return boolean_answer(text)
    if element in _TEMPORAL_ELEMENTS:
        return temporal_answer(text, element, timezone)
    if element == "valueUri":
        return QuestionnaireResponseAnswer(valueUri=text)
    if element == "valueReference":
        return QuestionnaireResponseAnswer(valueReference=Reference(reference=f"{LOCATION_RESOURCE_TYPE}/{text}"))
    return QuestionnaireResponseAnswer(valueString=flatten_whitespace(value))


def number_answer(text: str, *, whole: bool) -> QuestionnaireResponseAnswer:
    """A stored number on its own element, or as the string the instance holds when it is not one."""
    try:
        number = int(text) if whole else float(text)
    except ValueError:
        return QuestionnaireResponseAnswer(valueString=text)
    if whole:
        return QuestionnaireResponseAnswer(valueInteger=int(number))
    return QuestionnaireResponseAnswer(valueDecimal=number)


def boolean_answer(text: str) -> QuestionnaireResponseAnswer:
    """A stored boolean from DHIS2's `true`/`false` (or `1`/`0`) spellings, else the string as stored."""
    lowered = text.lower()
    if lowered in _TRUE_LITERALS:
        return QuestionnaireResponseAnswer(valueBoolean=True)
    if lowered in _FALSE_LITERALS:
        return QuestionnaireResponseAnswer(valueBoolean=False)
    return QuestionnaireResponseAnswer(valueString=text)


def temporal_answer(text: str, element: str, timezone: str | None) -> QuestionnaireResponseAnswer:
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


def answered_items(
    children: dict[str | None, list[str]],
    answers: dict[str, list[QuestionnaireResponseAnswer]],
    parent: str | None,
) -> list[QuestionnaireResponseItem]:
    """The form's tree with the stored values in it, and every branch that reaches none left out."""
    items: list[QuestionnaireResponseItem] = []
    for link_id in children.get(parent, []):
        nested = answered_items(children, answers, link_id)
        answered = answers.get(link_id, [])
        if answered or nested:
            items.append(QuestionnaireResponseItem(linkId=link_id, answer=answered or None, item=nested or None))
    return items


def response_status(value: str) -> ResponseStatusCode:
    """Read a status computed as a plain string as the R4 code it is; a test pins the two together."""
    return cast(ResponseStatusCode, value)


def item_children(index: CaptureIndex) -> dict[str | None, list[str]]:
    """The form's item tree as a parent-to-children map, in the document order the index holds it in.

    The index flattens the form for lookup and keeps the order separately, so the tree is rebuilt
    here rather than walked off the compiled Questionnaire again - which is what keeps a served
    document's items in the order the form asks them, section by section.
    """
    children: dict[str | None, list[str]] = {}
    for link_id in index.item_link_ids:
        gate = index.gates.get(link_id)
        children.setdefault(None if gate is None else gate.parent_link_id, []).append(link_id)
    return children
