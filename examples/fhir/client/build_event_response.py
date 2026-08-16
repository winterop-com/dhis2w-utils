"""Capture one event of a program without registration: no person, a date, an organisation unit.

A DHIS2 **event program** - a program without registration - records things that happen at a place,
not to a person. A supervision visit, a water-point inspection, a case report with no case file
behind it. There is no tracked entity, no enrollment, and no reporting period: an event happened on
a date, and that date is the whole of its "when".

So this envelope is the smallest of the five. Against the aggregate one it drops the period and
gains `authored`, and the two differences are the same fact seen twice: an aggregate report covers a
stretch of time, an event happened at a moment.

| DHIS2 fact | Where it rides |
| --- | --- |
| which program | `questionnaire` - the form's canonical url |
| when the event occurred | `authored`, and nothing else - this is not bookkeeping |
| where it was captured | `subject`, a reference to that unit's published `Location` |
| this is an event capture | the `D2FormType` extension, `valueCode` of `event` |
| the event's own state | `status`, which maps onto the DHIS2 event status |

`authored` deserves a second look, because in most FHIR resources it is metadata about the document.
Here it is data: it is what becomes `occurredAt` on the DHIS2 event, and a response carrying none is
refused for having no occurrence rather than for missing a timestamp.

`status` maps onto the DHIS2 event status - `completed` to COMPLETED, `in-progress` to ACTIVE,
`stopped` to SKIPPED. `entered-in-error` means a deletion, which a capture is not, so it is refused.

Usage:
    uv run python examples/fhir/client/build_event_response.py

Requires a DHIS2 profile (`d2w profile list`).
"""

from __future__ import annotations

from _fixture import conversion_context, event_form_id, form_canonical
from _runner import run_example
from dhis2w_fhir import translate_response
from dhis2w_fhir.r4 import (
    Extension,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: Gbenikoro MCHP, a facility the seeded instance assigns the Supervision visit program to.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"

#: When the visit happened. An R4 `dateTime` - a date alone is legal too, and DHIS2 stores the
#: wall clock either way. The project's own time zone is what an offset here is read back through.
OCCURRED_AT = "2026-01-19T10:30:00"

#: What the supervisor recorded on the visit, by data element UID.
RECORDED = {
    "s46m5MS0hxu": 21,
    "YtbsuPPo010": 4.5,
}


async def main() -> None:
    """Capture one standalone event and prove it becomes the DHIS2 event it describes."""
    context = conversion_context()
    canonical = form_canonical(event_form_id())
    form = context.forms[canonical]

    response = QuestionnaireResponse(
        questionnaire=canonical,
        status="completed",
        # `authored` is the event's occurrence date, not a document timestamp.
        authored=OCCURRED_AT,
        extension=[Extension(url=context.naming.form_type_url, valueCode="event")],
        # An event is captured *at a place*, so the place is the subject - the same reading as an
        # aggregate report. It is the three tracker kinds that put a person here instead.
        subject=Reference(reference=f"Location/{ORGANISATION_UNIT_UID}"),
        item=[
            QuestionnaireResponseItem(
                linkId=link_id,
                # The form types every question off its DHIS2 value type, so which `value[x]`
                # element an answer uses is the form's decision, not the client's: an INTEGER data
                # element answers `valueInteger` and a NUMBER one `valueDecimal`.
                answer=[_answer(form.questions[link_id].answer_element, recorded)],
            )
            for link_id, recorded in RECORDED.items()
        ],
    )

    for link_id in RECORDED:
        question = form.questions[link_id]
        print(f"{link_id}  DHIS2 value type {question.value_type}  answers {question.answer_element}")

    print()
    print(response.model_dump_json(indent=2, exclude_none=True, by_alias=True))

    result = translate_response(response, context)
    for refusal in result.refusals:
        print(f"refused [{refusal.category}] {refusal.reason}")
    if result.event is not None:
        print(
            f"\nconverts to an {result.target_kind}: program {result.event.program}, "
            f"organisation unit {result.event.orgUnit}, occurred {result.event.occurredAt}, "
            f"status {result.event.status}, {len(result.event.dataValues or [])} data value(s)"
        )
    for note in result.notes:
        print(f"note [{note.category}] {note.message}")


def _answer(answer_element: str, recorded: float) -> QuestionnaireResponseAnswer:
    """Put one recorded number on whichever `value[x]` element the form types that question as."""
    if answer_element == "valueInteger":
        return QuestionnaireResponseAnswer(valueInteger=int(recorded))
    return QuestionnaireResponseAnswer(valueDecimal=recorded)


if __name__ == "__main__":
    run_example(main)
