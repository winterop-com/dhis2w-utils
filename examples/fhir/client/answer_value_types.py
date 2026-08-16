"""Type one answer correctly for every DHIS2 value type, and see what a wrong pairing costs.

A DHIS2 data element declares a value type - `INTEGER_POSITIVE`, `PERCENTAGE`, `TRUE_ONLY`,
`DATE`, `LONG_TEXT`, and twenty more. FHIR R4 has no such list. What it has is
`Questionnaire.item.type`, a much shorter vocabulary, and a rule that an answer rides the
`value[x]` element that item type asks for: an `integer` question is answered `valueInteger` and
on nothing else.

So each DHIS2 value type is published as one R4 item type, and that item type decides the single
element an answer may use. That is the whole contract, and it is what this example prints: one row
per DHIS2 value type, each with a real `QuestionnaireResponse.item.answer` built for it.

Correctly typed means two things, and the rows show both. The element has to be the one the item
type asks for - and the literal on it still has to be a shape DHIS2 accepts, because R4 sees only
`string` where DHIS2 sees a phone number, a coordinate pair, or a GeoJSON document.

Three rows deserve reading twice.

* **A question binding an option set answers `valueCoding` whatever its value type is.** The rows
  below are what a question takes when nothing constrains its answers to a published list - see
  examples/fhir/client/answer_coded_question.py for the other case, which is most of a tracker form.
* **`MULTI_TEXT` always binds an option set**, and it is the one DHIS2 value type whose question
  repeats: several `valueCoding` answers to one link id, which DHIS2 stores as one data value with
  the selected codes comma-joined.
* **`TRUE_ONLY` answered false stores no data value at all.** That absence is how DHIS2 spells
  false for that value type, and it is the one answer that imports as nothing rather than as a
  value.

The cost of getting the element wrong is not a coerced value - it is a refusal. The translator
reads the element the question's item type asks for and no other, so an integer sent as
`valueString` refuses the whole response by link id, rather than leaving a data value quietly
missing from the middle of one that imports.

Usage:
    uv run python examples/fhir/client/answer_value_types.py

The serialisation table is at docs/guides/fhir/401-capture-contract.md.
"""

from __future__ import annotations

from _fixture import conversion_context, event_form_id
from _runner import run_example
from dhis2w_fhir import ITEM_TYPES_BY_VALUE_TYPE, answer_element
from dhis2w_fhir.conversion import (
    ANSWER_ELEMENTS_BY_ITEM_TYPE,
    ConversionContext,
    QuestionSpec,
    answer_wire_value,
)
from dhis2w_fhir.r4 import Attachment, QuestionnaireResponseAnswer, Reference

#: The DHIS2 value type that always binds an option set, and the one whose question repeats.
MULTI_SELECT_VALUE_TYPE = "MULTI_TEXT"

#: One correctly typed literal per `value[x]` element - what a value type takes when its shape is free.
ANSWERS_BY_ELEMENT = {
    "valueBoolean": QuestionnaireResponseAnswer(valueBoolean=True),
    "valueInteger": QuestionnaireResponseAnswer(valueInteger=12),
    "valueDecimal": QuestionnaireResponseAnswer(valueDecimal=12.5),
    "valueDate": QuestionnaireResponseAnswer(valueDate="2026-03-14"),
    "valueDateTime": QuestionnaireResponseAnswer(valueDateTime="2026-03-14T09:30:00Z"),
    "valueTime": QuestionnaireResponseAnswer(valueTime="09:30:00"),
    "valueString": QuestionnaireResponseAnswer(valueString="seen at the clinic"),
    "valueUri": QuestionnaireResponseAnswer(valueUri="https://example.org/protocol/12"),
    "valueReference": QuestionnaireResponseAnswer(valueReference=Reference(reference="Location/DiszpKrYNg8")),
    "valueAttachment": QuestionnaireResponseAnswer(valueAttachment=Attachment(contentType="image/png")),
}

#: The value types whose literal DHIS2 constrains further than the R4 element does, each with one that fits.
ANSWERS_BY_VALUE_TYPE = {
    "COORDINATE": QuestionnaireResponseAnswer(valueString="[-13.2317,8.4657]"),
    "EMAIL": QuestionnaireResponseAnswer(valueString="clinic@example.org"),
    "GEOJSON": QuestionnaireResponseAnswer(valueString='{"type":"Point","coordinates":[-13.2317,8.4657]}'),
    "INTEGER_NEGATIVE": QuestionnaireResponseAnswer(valueInteger=-12),
    "INTEGER_ZERO_OR_POSITIVE": QuestionnaireResponseAnswer(valueInteger=0),
    "LETTER": QuestionnaireResponseAnswer(valueString="F"),
    "PERCENTAGE": QuestionnaireResponseAnswer(valueDecimal=62.5),
    "PHONE_NUMBER": QuestionnaireResponseAnswer(valueString="+23276111001"),
    "REFERENCE": QuestionnaireResponseAnswer(valueString="ImspTQPwCqd"),
    "TRACKER_ASSOCIATE": QuestionnaireResponseAnswer(valueString="dNpxRu1mWG5"),
    "UNIT_INTERVAL": QuestionnaireResponseAnswer(valueDecimal=0.25),
    "USERNAME": QuestionnaireResponseAnswer(valueString="district_officer"),
}


def _answered_on(value_type: str) -> str:
    """The `value[x]` element one value type's answers ride, decided by the item type it is published as.

    The item type is what an answer is read against, so it decides first; `answer_element` fills in
    the value types R4 gives no narrower item type than `string` to.
    """
    if value_type == MULTI_SELECT_VALUE_TYPE:
        return "valueCoding"
    item_type = ITEM_TYPES_BY_VALUE_TYPE[value_type]
    return ANSWER_ELEMENTS_BY_ITEM_TYPE.get(item_type) or answer_element(value_type)


def _rendered_answer(value_type: str, element: str) -> str:
    """One correctly typed answer as it goes on the wire, or a note where the element carries no literal."""
    answer = ANSWERS_BY_VALUE_TYPE.get(value_type) or ANSWERS_BY_ELEMENT.get(element)
    if answer is None:
        return "one concept of the question's own published option list"
    return str(answer.model_dump(exclude_none=True, by_alias=True))


def _numeric_question(context: ConversionContext, form_id: str) -> QuestionSpec | None:
    """The first question of one served form whose answers are a number, which is the row worth proving."""
    for form in context.forms.values():
        if not form.canonical.endswith(f"/Questionnaire/{form_id}"):
            continue
        numeric = [
            question
            for question in form.questions.values()
            if question.answer_element in ("valueInteger", "valueDecimal")
        ]
        return min(numeric, key=lambda question: question.link_id) if numeric else None
    return None


async def main() -> None:
    """Print the answer element every DHIS2 value type takes, then prove one row right and one wrong."""
    print(f"{'DHIS2 value type':26} {'R4 item type':12} {'answered on':16} a correct answer")
    for value_type in sorted(ITEM_TYPES_BY_VALUE_TYPE):
        element = _answered_on(value_type)
        rendered = _rendered_answer(value_type, element)
        print(f"{value_type:26} {ITEM_TYPES_BY_VALUE_TYPE[value_type]:12} {element:16} {rendered}")
    print()
    print("A `valueAttachment` answer is refused rather than imported: a DHIS2 file resource is uploaded")
    print("on its own endpoint, and a data value names it, so there is no data value an attachment becomes.")
    print("A `valueDateTime` carries an offset because R4 requires one; DHIS2 stores the wall clock behind it.")
    print()

    # Everything above is the published table. Below is one real question of one served form, put
    # through the same translator a submitted response goes through, so the table is not taken on trust.
    context = conversion_context()
    question = _numeric_question(context, event_form_id())
    if question is None:
        print(f"the form {event_form_id()} asks no numeric question, so there is no row to prove here")
        return

    print(f"{question.link_id} is a {question.item_type} question, so it is answered on {question.answer_element}.")
    right = answer_wire_value(question, [ANSWERS_BY_ELEMENT[question.answer_element]], context)
    print(f"  answered right: DHIS2 stores the data value {right.value!r}")

    # DHIS2 takes every data value as a string on the wire, so "12.5" would have crossed unharmed.
    # It is still refused: the element a question is answered on is the contract, not the bytes.
    wrong = answer_wire_value(question, [QuestionnaireResponseAnswer(valueString="12.5")], context)
    for refusal in wrong.refusals:
        print(f"  answered as valueString: {refusal.category} - {refusal.reason}")
    print("  a refused answer refuses its whole response - nothing of it imports, half of it least of all")


if __name__ == "__main__":
    run_example(main)
