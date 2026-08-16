"""A response the translator will not read whole, and the typed refusal that says which question and why.

Nothing translates partially. A response the translator cannot read produces named refusals and
no payload at all - not a payload carrying the half of itself that happened to parse. That is
the rule this file exists to show: below, a submission with three perfectly good answers and one
bad one imports nothing, and the reason is that half a form reaching DHIS2 is worse than a form
that did not arrive, because nobody can tell by looking that it is half.

A refusal is a `ConversionRefusal` - a typed category, the question it stumbled on, the FHIR
element or DHIS2 field it names, and a sentence stating the fix. Never a bare error string, so a
caller can route on the category rather than parse prose. The categories below are four of the
thirty-odd in `ConversionRefusalCategory`:

    `unknown-link-id`                 an answered item names a question the form does not ask
    `answer-element-mismatch`         the answer arrived on a `value[x]` the question does not use
    `missing-period`                  an aggregate response carries no D2Period, so there is no
                                      DHIS2 period to import against
    `unresolvable-organisation-unit`  the Location the response names resolves to no organisation
                                      unit this guide published
    `entered-in-error-is-a-deletion`  the submission withdraws something already recorded, which
                                      is a deletion rather than an import

The last one is the only category that is not a data problem or a guide problem: no change to
either can resolve it, which is why a forwarder files such a receipt instead of retrying it.

Usage:
    uv run python examples/fhir/client/read_conversion_refusal.py

Reads the example project's guide through the shared fixture; see the README beside this file.
"""

from __future__ import annotations

from _fixture import aggregate_form_id, conversion_context, event_form_id
from dhis2w_fhir import ConversionContext, ConversionResult, translate_response
from dhis2w_fhir.conversion import PERIOD_ISO_SUB_EXTENSION, FormSpec, QuestionSpec, WireValueKind
from dhis2w_fhir.r4 import (
    Extension,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: The ISO period the well-formed half of the first submission reports for.
REPORTING_PERIOD = "202601"

#: A link id no form asks, and a Location no guide published - each is one of the refusals below.
UNASKED_LINK_ID = "notAQuestion"
UNPUBLISHED_LOCATION_ID = "NotAPlace01"


def _form(context: ConversionContext, form_id: str) -> FormSpec:
    """The published form one Questionnaire id names, as the translator reads it."""
    for canonical, form in context.forms.items():
        if canonical.rsplit("/", 1)[-1] == form_id:
            return form
    raise LookupError(f"the project publishes no Questionnaire `{form_id}`")


def _integer_cells(form: FormSpec, count: int) -> list[QuestionSpec]:
    """The first few integer cells of the form, which are what the good answers below answer."""
    return [question for question in form.questions.values() if question.wire_kind == WireValueKind.INTEGER][:count]


def _period_extension(context: ConversionContext) -> Extension:
    """The D2Period extension an aggregate response reports its ISO period on."""
    return Extension(
        url=context.naming.period_url,
        extension=[Extension(url=PERIOD_ISO_SUB_EXTENSION, valueString=REPORTING_PERIOD)],
    )


def _print_result(label: str, result: ConversionResult) -> None:
    """Print one translated response's outcome: the payload, or every refusal that stopped it."""
    print(label)
    print(f"  payload: {'none' if result.is_refused else result.target_kind}")
    for refusal in result.refusals:
        located = refusal.link_id or refusal.element or "the response"
        print(f"  [{refusal.category}] {located}")
        print(f"      {refusal.reason}")
    print()


def main() -> None:
    """Translate three responses the translator refuses, and print what each refusal names."""
    context = conversion_context()
    aggregate = _form(context, aggregate_form_id())
    event = _form(context, event_form_id())
    location_id = sorted(context.organisation_unit_uids_by_location_id)[0]
    cells = _integer_cells(aggregate, 4)
    if len(cells) < 4:
        print(f"{aggregate.canonical} asks too few integer questions for this example")
        return

    # One submission, three good answers, two bad items - and no data value reaches DHIS2.
    part_answered = QuestionnaireResponse(
        id="refusal-example-one-bad-answer",
        questionnaire=aggregate.canonical,
        status="completed",
        subject=Reference(reference=f"Location/{location_id}"),
        extension=[
            Extension(url=context.naming.form_type_url, valueCode=aggregate.form_kind),
            _period_extension(context),
        ],
        item=[
            *(
                QuestionnaireResponseItem(
                    linkId=question.link_id, answer=[QuestionnaireResponseAnswer(valueInteger=value)]
                )
                for question, value in zip(cells[:3], (12, 7, 5), strict=False)
            ),
            # A question this form does not ask. The form is the contract, and a link id outside it
            # names nothing the translator could key a data value by.
            QuestionnaireResponseItem(linkId=UNASKED_LINK_ID, answer=[QuestionnaireResponseAnswer(valueInteger=1)]),
            # An integer question answered as a string. R4 lets any `value[x]` carry any answer;
            # the question's own item type says which one it is answered on.
            QuestionnaireResponseItem(
                linkId=cells[3].link_id, answer=[QuestionnaireResponseAnswer(valueString="seventeen")]
            ),
        ],
    )
    _print_result(
        "three answers the translator read fine, and two items it could not - so nothing imports:",
        translate_response(part_answered, context),
    )

    # A submission whose envelope is wrong rather than its answers: no period at all, and a place
    # the guide never published.
    misplaced = QuestionnaireResponse(
        id="refusal-example-envelope",
        questionnaire=aggregate.canonical,
        status="completed",
        subject=Reference(reference=f"Location/{UNPUBLISHED_LOCATION_ID}"),
        extension=[Extension(url=context.naming.form_type_url, valueCode=aggregate.form_kind)],
        item=[
            QuestionnaireResponseItem(linkId=cells[0].link_id, answer=[QuestionnaireResponseAnswer(valueInteger=12)])
        ],
    )
    _print_result("the answers are fine and the envelope is not:", translate_response(misplaced, context))

    # The one refusal no change to the guide and no change to the data can resolve.
    withdrawn = QuestionnaireResponse(
        id="refusal-example-withdrawal",
        questionnaire=event.canonical,
        status="entered-in-error",
        authored="2026-01-04T08:30:00+00:00",
        subject=Reference(reference=f"Location/{location_id}"),
        extension=[Extension(url=context.naming.form_type_url, valueCode=event.form_kind)],
        item=[],
    )
    _print_result(
        "a submission that withdraws a record rather than making one:", translate_response(withdrawn, context)
    )

    print("every refusal names a category, so a caller routes on the category rather than on prose:")
    print("  a data problem goes back to whoever captured it, a guide problem goes to whoever generates")
    print("  the guide, and a withdrawal is filed rather than retried, because retrying cannot fix it.")


if __name__ == "__main__":
    main()
