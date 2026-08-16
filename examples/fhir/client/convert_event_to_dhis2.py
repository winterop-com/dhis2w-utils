"""One captured event response beside the `/api/tracker` event it becomes - offline, no server.

An event program collects one event at a time against a place, with no person and no
enrollment, and a `QuestionnaireResponse` answering its form carries exactly that. Which
element carries what is the whole lesson, because an event's two hardest fields are the two
that are not answers:

    `authored`                 ->  `occurredAt`   the moment the event occurred. The response's
                                                  own timestamp is what dates the event; there is
                                                  no separate date question, and a response
                                                  carrying no `authored` is refused rather than
                                                  dated now.
    `subject.reference`        ->  `orgUnit`      an event response reports *for a place*, so the
                                                  place is the subject - `Location/<id>`, resolved
                                                  through the guide's published Locations to the
                                                  DHIS2 organisation unit UID.
    the form the response answers ->  `program`   off the Questionnaire's own DHIS2 identifier.
    `status`                   ->  `status`       the R4 lifecycle status read onto a DHIS2 event
                                                  status.
    one answered item          ->  one data value keyed by the data element its `linkId` is. An
                                                  event data value carries no category option
                                                  combo, so the link ids are plain UIDs here.
    `id`                       ->  `event`        the DHIS2 UID the event imports under, derived
                                                  from the receipt's own id. See
                                                  `derive_receipt_event_uid.py` for what that
                                                  buys and what it costs.

An event that belongs to a tracker programme's enrollment is a different form kind - see
`convert_registration_to_dhis2.py` for the enrollment such an event answers against.

Usage:
    uv run python examples/fhir/client/convert_event_to_dhis2.py

Reads the example project's guide through the shared fixture; see the README beside this file.
"""

from __future__ import annotations

from _fixture import conversion_context, event_form_id
from dhis2w_fhir import ConversionContext, translate_response
from dhis2w_fhir.conversion import FormSpec, QuestionSpec, WireValueKind
from dhis2w_fhir.r4 import (
    Extension,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: When the event happened, as the R4 `dateTime` a capture client stamps the submission with. DHIS2
#: stores a zone-less wall clock, so the offset here is read off through the project's own zone.
CAPTURED_AT = "2026-01-04T08:30:00+00:00"

#: The logical id of the submission. A capture server mints one per receipt; this file states its
#: own so the run is reproducible - and so the event UID below is the same on every run.
RESPONSE_ID = "event-capture-example"

#: What this example answers each kind of question with, one literal per wire spelling.
ANSWERED_BOOLEAN = True
ANSWERED_DECIMAL = 3.5


def _form(context: ConversionContext, form_id: str) -> FormSpec:
    """The published form one Questionnaire id names, as the translator reads it."""
    for canonical, form in context.forms.items():
        if canonical.rsplit("/", 1)[-1] == form_id:
            return form
    raise LookupError(f"the project publishes no Questionnaire `{form_id}`")


def _first(form: FormSpec, wire_kind: WireValueKind) -> QuestionSpec | None:
    """The first question of the form answered on one wire spelling, or None where it asks none."""
    return next((question for question in form.questions.values() if question.wire_kind == wire_kind), None)


def _answered_items(form: FormSpec) -> list[QuestionnaireResponseItem]:
    """Answer one boolean and one decimal question, which is enough to show both wire spellings."""
    items: list[QuestionnaireResponseItem] = []
    boolean = _first(form, WireValueKind.BOOLEAN)
    if boolean is not None:
        items.append(
            QuestionnaireResponseItem(
                linkId=boolean.link_id, answer=[QuestionnaireResponseAnswer(valueBoolean=ANSWERED_BOOLEAN)]
            )
        )
    decimal = _first(form, WireValueKind.DECIMAL)
    if decimal is not None:
        items.append(
            QuestionnaireResponseItem(
                linkId=decimal.link_id, answer=[QuestionnaireResponseAnswer(valueDecimal=ANSWERED_DECIMAL)]
            )
        )
    return items


def _answered_literal(item: QuestionnaireResponseItem) -> str:
    """One answered item's `value[x]` element and the literal it carries, as the FHIR document spells it."""
    if not item.answer:
        return "-"
    return item.answer[0].model_dump_json(exclude_none=True, by_alias=True)


def _captured_response(context: ConversionContext, form: FormSpec, location_id: str) -> QuestionnaireResponse:
    """Build the event submission by hand, exactly as a capture client would post it."""
    return QuestionnaireResponse(
        id=RESPONSE_ID,
        questionnaire=form.canonical,
        # R4's own lifecycle status, which is what the DHIS2 event status is read off.
        status="completed",
        # The moment the event occurred - required on every event response, and the only date there is.
        authored=CAPTURED_AT,
        # An event report is about a place, so the place is the subject.
        subject=Reference(reference=f"Location/{location_id}"),
        extension=[Extension(url=context.naming.form_type_url, valueCode=form.form_kind)],
        item=_answered_items(form),
    )


def main() -> None:
    """Translate one captured event response and print it beside the event it becomes."""
    context = conversion_context()
    form = _form(context, event_form_id())
    location_id = sorted(context.organisation_unit_uids_by_location_id)[0]
    response = _captured_response(context, form, location_id)

    result = translate_response(response, context)
    event = result.event
    if event is None:
        for refusal in result.refusals:
            print(f"refused [{refusal.category}] {refusal.reason}")
        return

    print(f"form: {form.canonical}")
    print(f"target: {result.target_kind}\n")

    print(f"{'the captured QuestionnaireResponse':46}    the /api/tracker event")
    print(f"{'questionnaire (the form above)':46} -> program      {event.program}")
    print(f"{'authored ' + CAPTURED_AT:46} -> occurredAt   {event.occurredAt}")
    print(f"{'subject.reference Location/' + location_id:46} -> orgUnit      {event.orgUnit}")
    print(f"{'status ' + (response.status or ''):46} -> status       {event.status}")
    print(f"{'id ' + RESPONSE_ID:46} -> event        {event.event}")
    print()

    # `occurredAt` is a zone-less wall clock, which is what DHIS2 both serves and accepts on that
    # field: the offset the R4 timestamp carries is read off through the project's own time zone.
    print(f"the project reads zone-less DHIS2 timestamps as {context.timezone or 'UTC'}")
    print()

    # Every DHIS2 data value is a string on the wire whatever its value type, so the FHIR literal on
    # the left and the DHIS2 spelling on the right are worth reading against each other.
    print(f"{'item.linkId':16} {'answer':30}    {'dataElement':16} value")
    for item, value in zip(response.item or [], event.dataValues or [], strict=False):
        print(f"{item.linkId or '-':16} {_answered_literal(item):30} -> {value.dataElement or '-':16} {value.value}")
    print()

    print("the body a forward posts to /api/tracker, under `events`:")
    print(event.model_dump_json(indent=2, by_alias=True, exclude_none=True))

    # A note is the translator saying what it had to interpret rather than read off.
    for note in result.notes:
        print(f"\nnote [{note.category}] {note.message}")


if __name__ == "__main__":
    main()
