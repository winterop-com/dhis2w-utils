"""Answer a data element that is cut by a category combination: which cell is which, and why.

In DHIS2 a data element on a **category combination** is not one number, it is a row of cells. "BCG
doses given" cut by "Location and age group" is four numbers - fixed and outreach, under and over
one year - and each cell is keyed by the **category option combo** naming that intersection. A data
value carries both keys: the data element, and the category option combo.

FHIR has no second key on an answer. A `QuestionnaireResponse` item names its question with a
`linkId` and nothing else, so the guide puts both DHIS2 keys in the link id, joined by a dot:

    <dataElementUid>.<categoryOptionComboUid>
    s46m5MS0hxu     .Prlt0C1RF0s              -> BCG doses given, Fixed <1y

That is the whole grammar. An undisaggregated data element's link id is the bare data element UID,
and every cell of a disaggregated one is a separate question with its own answer. On the published
form the cells sit inside a `#group` item named for the data element, which is what a capture UI
renders as one labelled row - but a response does not repeat that nesting, because the link id
already says which cell each answer is.

The cells are not a client's to invent: they are published on the form, one question per cell that
DHIS2 actually captures. A greyed-out operand - a cell the instance refuses input on - is published
as no question at all, so a response answering it is answering something that is not of the form.

This example reads the four cells off the form itself rather than typing them out, which is what a
real capture client does.

Usage:
    uv run python examples/fhir/client/build_aggregate_disaggregated_response.py

Requires a DHIS2 profile (`d2w profile list`).
"""

from __future__ import annotations

from _fixture import aggregate_form_id, conversion_context, form_canonical
from _runner import run_example
from dhis2w_fhir import translate_response
from dhis2w_fhir.r4 import (
    Extension,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: Gbenikoro MCHP, a facility the seeded instance assigns Child Health to.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"

REPORTING_PERIOD = "202601"
REPORTING_PERIOD_TYPE = "Monthly"

#: The one data element this example reports, "BCG doses given". Its category combination is
#: "Location and age group", so the form publishes one question per cell of it.
DATA_ELEMENT_UID = "s46m5MS0hxu"

#: What the reporter counted, cell by cell, in the order the form publishes them.
COUNTED_PER_CELL = (14, 9, 6, 2)


async def main() -> None:
    """Report every cell of one disaggregated data element, and read the cells off the form to do it."""
    context = conversion_context()
    canonical = form_canonical(aggregate_form_id())
    form = context.forms[canonical]

    # Every question whose link id names this data element. `category_option_combo_uid` is the half
    # after the dot, already split out for us - a client that has the form never parses the link id.
    cells = [question for question in form.questions.values() if question.data_element_uid == DATA_ELEMENT_UID]
    print(f"{DATA_ELEMENT_UID} is captured as {len(cells)} cell(s) on {canonical.rsplit('/', 1)[-1]}:")
    for question, counted in zip(cells, COUNTED_PER_CELL, strict=False):
        print(
            f"  {question.link_id:30} category option combo {question.category_option_combo_uid} "
            f"answers {question.answer_element} = {counted}"
        )

    response = QuestionnaireResponse(
        questionnaire=canonical,
        status="completed",
        extension=[
            Extension(url=context.naming.form_type_url, valueCode="aggregate"),
            Extension(
                url=context.naming.period_url,
                extension=[
                    Extension(url="iso", valueString=REPORTING_PERIOD),
                    Extension(url="type", valueCode=REPORTING_PERIOD_TYPE),
                ],
            ),
        ],
        subject=Reference(reference=f"Location/{ORGANISATION_UNIT_UID}"),
        # One item per cell, flat. The group the form nests these cells under is for rendering; a
        # response repeats no structure, because each link id already says which cell it answers.
        item=[
            QuestionnaireResponseItem(
                linkId=question.link_id,
                answer=[QuestionnaireResponseAnswer(valueInteger=counted)],
            )
            for question, counted in zip(cells, COUNTED_PER_CELL, strict=False)
        ],
    )

    print()
    print(response.model_dump_json(indent=2, exclude_none=True, by_alias=True))

    # The proof, and the point: one answer became one data value carrying *both* DHIS2 keys.
    result = translate_response(response, context)
    for refusal in result.refusals:
        print(f"refused [{refusal.category}] {refusal.reason}")
    if result.data_value_set is not None:
        print(f"\nconverts to {len(result.data_value_set.dataValues or [])} data value(s), each with both keys:")
        for data_value in result.data_value_set.dataValues or []:
            print(
                f"  dataElement {data_value.dataElement}  "
                f"categoryOptionCombo {data_value.categoryOptionCombo}  value {data_value.value}"
            )


if __name__ == "__main__":
    run_example(main)
