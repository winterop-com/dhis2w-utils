"""One captured aggregate response beside the `/api/dataValueSets` payload it becomes - offline, no server.

If you know DHIS2 and not FHIR, this is the file to read first. A `QuestionnaireResponse`
answering a data set's form carries exactly the five things an aggregate import needs, and
`translate_response` is what moves each one into the field DHIS2 reads it from:

    the form the response answers  ->  `dataSet`      (off the Questionnaire's DHIS2 identifier,
                                                       never off the response - the response names
                                                       the form, and the form names the data set)
    the D2Period extension         ->  `period`       (the ISO period DHIS2 imports against)
    the Location the subject is    ->  `orgUnit`      (a published Location id resolved to its UID)
    one answered item              ->  one data value (its `linkId` IS the DHIS2 key: a plain link
                                                       id is a data element UID, and a
                                                       `<dataElement>.<categoryOptionCombo>` link
                                                       id is a disaggregated cell)
    `status = completed`           ->  a `completeDataSetRegistration` for the tuple, written
                                       after DHIS2 has taken the values

Nothing here talks to DHIS2 and nothing here talks to a capture server. The translation is a
pure function of the response plus the project's published guide, which is why the payload
below can be checked by eye against the response above it.

The payload itself is the generated OpenAPI model `DataValueSet` - the same class the aggregate
plugin posts - so what is printed at the end is the literal body a forward would send.

Usage:
    uv run python examples/fhir/client/convert_aggregate_to_dhis2.py

Reads the example project's guide through the shared fixture; see the README beside this file.
"""

from __future__ import annotations

from _fixture import aggregate_form_id, conversion_context
from dhis2w_fhir import ConversionContext, translate_response
from dhis2w_fhir.conversion import PERIOD_ISO_SUB_EXTENSION, FormSpec, QuestionSpec, WireValueKind
from dhis2w_fhir.r4 import (
    Extension,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: The ISO period the response reports for. A data set's own period type is published on the form
#: as `D2PeriodType`, and this is the monthly spelling of it - the very string DHIS2 imports against.
REPORTING_PERIOD = "202601"

#: The logical id of the submission. A capture server mints one per receipt; this file states its
#: own so the run is reproducible.
RESPONSE_ID = "aggregate-capture-example"

#: How many cells this example answers, and what it answers them with. Three is enough to show the
#: link-id grammar and short enough to read whole.
ANSWERED_VALUES = (12, 7, 5)


def _form(context: ConversionContext, form_id: str) -> FormSpec:
    """The published form one Questionnaire id names, as the translator reads it."""
    for canonical, form in context.forms.items():
        if canonical.rsplit("/", 1)[-1] == form_id:
            return form
    raise LookupError(f"the project publishes no Questionnaire `{form_id}`")


def _answered_cells(form: FormSpec) -> list[QuestionSpec]:
    """The disaggregated integer cells this example answers, in the order the form asks them."""
    cells = [question for question in form.questions.values() if question.wire_kind == WireValueKind.INTEGER]
    return cells[: len(ANSWERED_VALUES)]


def _captured_response(
    context: ConversionContext, form: FormSpec, location_id: str, cells: list[QuestionSpec]
) -> QuestionnaireResponse:
    """Build the aggregate submission by hand, exactly as a capture client would post it."""
    return QuestionnaireResponse(
        id=RESPONSE_ID,
        questionnaire=form.canonical,
        # An aggregate response is stored as reported, so its status is `completed` - which is also
        # the claim that registers the tuple complete once DHIS2 has taken the values.
        status="completed",
        # The subject of an aggregate report is a place, so the organisation unit rides `subject`.
        subject=Reference(reference=f"Location/{location_id}"),
        extension=[
            # Which of the five DHIS2 form kinds this submission claims to be. The translator reads
            # it before anything else, and checks it against the kind the named form actually is.
            Extension(url=context.naming.form_type_url, valueCode=form.form_kind),
            # The reporting period, carried as the ISO identifier DHIS2 imports against. A date
            # range may ride beside it, and is decoration: the ISO period is what is read.
            Extension(
                url=context.naming.period_url,
                extension=[Extension(url=PERIOD_ISO_SUB_EXTENSION, valueString=REPORTING_PERIOD)],
            ),
        ],
        item=[
            QuestionnaireResponseItem(
                linkId=question.link_id,
                answer=[QuestionnaireResponseAnswer(valueInteger=value)],
            )
            for question, value in zip(cells, ANSWERED_VALUES, strict=False)
        ],
    )


def main() -> None:
    """Translate one captured aggregate response and print it beside the payload it becomes."""
    context = conversion_context()
    form = _form(context, aggregate_form_id())
    location_id = sorted(context.organisation_unit_uids_by_location_id)[0]
    cells = _answered_cells(form)
    if not cells:
        print(f"{form.canonical} asks no integer question, so there is no cell to answer")
        return
    response = _captured_response(context, form, location_id, cells)

    result = translate_response(response, context)
    envelope = result.data_value_set
    if envelope is None:
        for refusal in result.refusals:
            print(f"refused [{refusal.category}] {refusal.reason}")
        return

    print(f"form: {form.canonical}")
    print(f"target: {result.target_kind}\n")

    print(f"{'the captured QuestionnaireResponse':46}    the /api/dataValueSets envelope")
    print(f"{'questionnaire (the form above)':46} -> dataSet              {envelope.dataSet}")
    print(f"{'extension D2Period.iso ' + REPORTING_PERIOD:46} -> period               {envelope.period}")
    print(f"{'subject.reference Location/' + location_id:46} -> orgUnit              {envelope.orgUnit}")
    print(f"{'status ' + (response.status or ''):46} -> attributeOptionCombo {envelope.attributeOptionCombo or '-'}")
    print("the data set is the form's own DHIS2 identifier, so no field of the response states it")
    if form.attribute_option_combo_value_set is None:
        print("the form declares no attribute-option-combo vocabulary, so DHIS2 keys the values by its own default")
    print()

    # One answered item, one data value. The link id is not a name the guide invented: it is the
    # DHIS2 key itself, split on the dot into the data element and the category option combo.
    print(f"{'item.linkId':26} {'answer':22}    {'dataElement':13} {'categoryOptionCombo':20} value")
    for question, value, answered in zip(cells, envelope.dataValues or [], ANSWERED_VALUES, strict=False):
        print(
            f"{question.link_id:26} {'valueInteger ' + str(answered):22} -> {value.dataElement:13} "
            f"{value.categoryOptionCombo or '-':20} {value.value}"
        )
    print()

    # A data value's value is a string on the DHIS2 wire whatever its value type, which is why a
    # lexical decimal survives the crossing unchanged.
    print("the body a forward posts to /api/dataValueSets:")
    print(envelope.model_dump_json(indent=2, by_alias=True, exclude_none=True))

    # Completeness is a second write to a second resource, so it is carried beside the values
    # rather than inside them: DHIS2 takes the values first, and the tuple is registered after.
    if result.completeness is not None:
        print("\nand, because the response reports itself completed, to /api/completeDataSetRegistrations:")
        print(result.completeness.model_dump_json(indent=2, by_alias=True, exclude_none=True))

    # A note is the translator saying what it had to interpret. Nothing here is a failure.
    for note in result.notes:
        print(f"note [{note.category}] {note.message}")


if __name__ == "__main__":
    main()
