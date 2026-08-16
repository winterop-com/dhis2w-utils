"""Build the minimal aggregate capture: a data set's numbers for one period at one organisation unit.

This is the "I have a paper form's numbers, what do I send?" example. In DHIS2 you are reporting a
**data set** for a **period** at an **organisation unit**, and every number on the form is a
**data value**. FHIR carries that as a `QuestionnaireResponse`: the form it answers, the facts about
when and where, and one answer per number.

Five things are required, and nothing else is:

| DHIS2 fact | Where it rides |
| --- | --- |
| which data set | `questionnaire` - the form's canonical url, not its name |
| the report is finished | `status = "completed"` |
| this is an aggregate report | the `D2FormType` extension, `valueCode` of `aggregate` |
| the reporting period | the `D2Period` extension, ISO period plus its period type |
| the organisation unit | `subject`, a reference to that unit's published `Location` |

An **extension** is FHIR's way of carrying a fact the base resource has no field for. It is a url
naming what the fact is plus one typed value - so `D2Period` is not a new kind of object, it is the
reporting period hung off the response under a url this guide publishes. The urls come off the
translation context rather than being typed out here, because every one of them is built from the
guide's own canonical.

The **link id** is what names a question. Here it is a DHIS2 data element UID, and where a data
element is disaggregated it gains a suffix - see `build_aggregate_disaggregated_response.py`, which
is about exactly that. Child Health disaggregates all of its data elements, so every link id below
carries one; the envelope is what this file is about.

Usage:
    uv run python examples/fhir/client/build_aggregate_response.py

Requires a DHIS2 profile (`d2w profile list`). The fixture scaffolds its project on first run.
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

#: Gbenikoro MCHP, a facility the seeded instance assigns Child Health to. A response naming an
#: organisation unit the data set is not assigned to is stored, and DHIS2 answers `E1029` on import.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"

#: January 2026 as DHIS2 spells a monthly period: `yyyyMM`. The form itself states which period type
#: it expects - the `D2PeriodType` extension on the Questionnaire - so a client never guesses this.
REPORTING_PERIOD = "202601"
REPORTING_PERIOD_TYPE = "Monthly"

#: Four numbers off the form: BCG doses given, split by where and to whom. The value after the dot is
#: the category option combo; `build_aggregate_disaggregated_response.py` is the example about that.
REPORTED_NUMBERS = {
    "s46m5MS0hxu.Prlt0C1RF0s": 12,
    "s46m5MS0hxu.psbwp3CQEhs": 8,
    "s46m5MS0hxu.V6L425pT3A0": 5,
    "s46m5MS0hxu.hEFKSsPV5et": 3,
}


def build_response(canonical: str, form_type_url: str, period_url: str) -> QuestionnaireResponse:
    """Assemble the whole aggregate response - envelope first, then one item per reported number."""
    return QuestionnaireResponse(
        questionnaire=canonical,
        # An aggregate response is stored as reported, so a facade refuses any other status: a
        # receipt for a half-finished report would be a report nobody made. A client that lets a
        # reporter save a draft keeps it on its own side and posts once, on the submit.
        status="completed",
        extension=[
            Extension(url=form_type_url, valueCode="aggregate"),
            # The period's two required slices. `iso` is what DHIS2 files the values under; `type`
            # says which period type that string is spelled in, so `202601` cannot be read as a week.
            Extension(
                url=period_url,
                extension=[
                    Extension(url="iso", valueString=REPORTING_PERIOD),
                    Extension(url="type", valueCode=REPORTING_PERIOD_TYPE),
                ],
            ),
        ],
        # An aggregate report is *about a place*, so the place is the subject. The three tracker
        # kinds are about a person instead, and their organisation unit moves to its own extension.
        subject=Reference(reference=f"Location/{ORGANISATION_UNIT_UID}"),
        item=[
            QuestionnaireResponseItem(
                linkId=link_id,
                answer=[QuestionnaireResponseAnswer(valueInteger=value)],
            )
            for link_id, value in REPORTED_NUMBERS.items()
        ],
    )


async def main() -> None:
    """Build one aggregate response, print it as it would go on the wire, and prove it converts."""
    context = conversion_context()
    canonical = form_canonical(aggregate_form_id())
    response = build_response(canonical, context.naming.form_type_url, context.naming.period_url)

    print(response.model_dump_json(indent=2, exclude_none=True, by_alias=True))

    # The proof. Translation is what `d2w fhir forward` runs before it posts anything, so a response
    # that translates is one DHIS2 will be offered - and the payload names the same three keys the
    # envelope carried, which is the whole point of the envelope.
    result = translate_response(response, context)
    for refusal in result.refusals:
        print(f"refused [{refusal.category}] {refusal.reason}")
    if result.data_value_set is not None:
        values = result.data_value_set.dataValues or []
        print(
            f"\nconverts to a {result.target_kind}: data set {result.data_value_set.dataSet}, "
            f"period {result.data_value_set.period}, organisation unit {result.data_value_set.orgUnit}, "
            f"{len(values)} data value(s)"
        )
    for note in result.notes:
        print(f"note [{note.category}] {note.message}")


if __name__ == "__main__":
    run_example(main)
