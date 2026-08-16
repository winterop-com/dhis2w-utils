"""How a receipt id decides the DHIS2 event UID it imports under, and what happens when a capture is sent twice.

A tracker event needs a UID, and a captured response carries none - so the forwarder derives one
from the receipt's own logical id: `<response id>:event:0`, hashed with SHA-256 and shaped into
the eleven characters DHIS2 spells a UID in. `receipt_event_uid` is that derivation, and it is
stable: the same receipt names the same event on the dry run, on the import that follows it, on
this machine, and on the next.

That single property decides what a second send does, and the two sides of DHIS2 answer very
differently.

**On the tracker side, the second send of one receipt collides.** Events are posted to
`/api/tracker` under plain `importStrategy=CREATE`, so a receipt whose event DHIS2 already holds
is refused as an object that exists rather than filed as a second copy of one visit. That is the
guarantee: **one receipt names one event.**

What is *not* guaranteed is one encounter naming one event. Capturing the same visit again mints
a fresh receipt, a fresh receipt derives a fresh event UID, and DHIS2 accepts it - as a second
event, not as a correction of the first.

**On the aggregate side, the second send overwrites in place.** A data value set carries no UID
at all: its identity is the tuple `(dataSet, period, orgUnit, attributeOptionCombo)` plus the
`(dataElement, categoryOptionCombo)` of each value. `/api/dataValueSets` takes a re-post of a
tuple it already holds as an update to it - that is the endpoint's own default, and it is what
makes re-capturing an aggregate report a correction of the earlier one, silently.

So the same act - sending a capture twice - is a collision on one side and a correction on the
other, and neither is configured anywhere. It falls out of what each DHIS2 endpoint does with an
identity it has seen before.

Usage:
    uv run python examples/fhir/client/derive_receipt_event_uid.py

Reads the example project's guide through the shared fixture; see the README beside this file.
"""

from __future__ import annotations

from _fixture import aggregate_form_id, conversion_context, event_form_id
from dhis2w_fhir import ConversionContext, translate_response
from dhis2w_fhir.conversion import PERIOD_ISO_SUB_EXTENSION, FormSpec, WireValueKind, receipt_event_uid
from dhis2w_fhir.r4 import (
    Extension,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: Two receipts of the same visit, as a capture server mints them: a `uuid4` hex per submission,
#: never taken from the client. The second is what re-capturing the same encounter produces.
FIRST_RECEIPT_ID = "edbb74be9d504684ad05cdf1aecedbdb"
SECOND_RECEIPT_ID = "cffa2a84ccf64fbfa24ba772b3408072"

#: When the captured event occurred - the same moment in both submissions, which is the point.
CAPTURED_AT = "2026-01-04T08:30:00+00:00"

#: The period the aggregate half of this example reports for.
REPORTING_PERIOD = "202601"


def _form(context: ConversionContext, form_id: str) -> FormSpec:
    """The published form one Questionnaire id names, as the translator reads it."""
    for canonical, form in context.forms.items():
        if canonical.rsplit("/", 1)[-1] == form_id:
            return form
    raise LookupError(f"the project publishes no Questionnaire `{form_id}`")


def _event_response(
    context: ConversionContext, form: FormSpec, location_id: str, response_id: str
) -> QuestionnaireResponse:
    """The same captured event, submitted under one receipt id."""
    boolean = next(
        (question for question in form.questions.values() if question.wire_kind == WireValueKind.BOOLEAN), None
    )
    return QuestionnaireResponse(
        id=response_id,
        questionnaire=form.canonical,
        status="completed",
        authored=CAPTURED_AT,
        subject=Reference(reference=f"Location/{location_id}"),
        extension=[Extension(url=context.naming.form_type_url, valueCode=form.form_kind)],
        item=[]
        if boolean is None
        else [
            QuestionnaireResponseItem(linkId=boolean.link_id, answer=[QuestionnaireResponseAnswer(valueBoolean=True)])
        ],
    )


def _aggregate_response(
    context: ConversionContext, form: FormSpec, location_id: str, response_id: str
) -> QuestionnaireResponse:
    """The same aggregate report, submitted under one receipt id."""
    cell = next(question for question in form.questions.values() if question.wire_kind == WireValueKind.INTEGER)
    return QuestionnaireResponse(
        id=response_id,
        questionnaire=form.canonical,
        status="completed",
        subject=Reference(reference=f"Location/{location_id}"),
        extension=[
            Extension(url=context.naming.form_type_url, valueCode=form.form_kind),
            Extension(
                url=context.naming.period_url,
                extension=[Extension(url=PERIOD_ISO_SUB_EXTENSION, valueString=REPORTING_PERIOD)],
            ),
        ],
        item=[QuestionnaireResponseItem(linkId=cell.link_id, answer=[QuestionnaireResponseAnswer(valueInteger=12)])],
    )


def main() -> None:
    """Derive the event UID two receipts of one visit produce, then say what a second send does on each side."""
    context = conversion_context()
    event_form = _form(context, event_form_id())
    aggregate_form = _form(context, aggregate_form_id())
    location_id = sorted(context.organisation_unit_uids_by_location_id)[0]

    print("receipt_event_uid, on its own:")
    print(f"  {'receipt id':34} {'event UID':13} what it is")
    print(f"  {FIRST_RECEIPT_ID:34} {receipt_event_uid(FIRST_RECEIPT_ID):13} one receipt, one event")
    print(f"  {FIRST_RECEIPT_ID:34} {receipt_event_uid(FIRST_RECEIPT_ID):13} the same receipt, the same event")
    print(f"  {SECOND_RECEIPT_ID:34} {receipt_event_uid(SECOND_RECEIPT_ID):13} a second capture of the same visit")
    print("  the derivation is a hash of the receipt id, so it is the same on every run and every machine\n")

    # The same visit captured twice: same form, same place, same moment, two receipts.
    print(f"the same event captured twice against {event_form.canonical}:")
    for receipt_id in (FIRST_RECEIPT_ID, SECOND_RECEIPT_ID):
        result = translate_response(_event_response(context, event_form, location_id, receipt_id), context)
        event = result.event
        if event is None:
            for refusal in result.refusals:
                print(f"  refused [{refusal.category}] {refusal.reason}")
            continue
        print(f"  receipt {receipt_id} -> event {event.event}, occurredAt {event.occurredAt}, orgUnit {event.orgUnit}")
    print("  re-forwarding one receipt collides: /api/tracker is posted importStrategy=CREATE, and DHIS2")
    print("  refuses an event UID it already holds. Re-capturing the visit does not collide - the second")
    print("  receipt derives a second UID, and DHIS2 stores a second event for the one encounter.\n")

    # The aggregate side names no UID at all, and its identity is the tuple its values are keyed by.
    print(f"the same report captured twice against {aggregate_form.canonical}:")
    for receipt_id in (FIRST_RECEIPT_ID, SECOND_RECEIPT_ID):
        result = translate_response(_aggregate_response(context, aggregate_form, location_id, receipt_id), context)
        envelope = result.data_value_set
        if envelope is None:
            for refusal in result.refusals:
                print(f"  refused [{refusal.category}] {refusal.reason}")
            continue
        value = (envelope.dataValues or [])[0]
        print(
            f"  receipt {receipt_id} -> no payload UID; keyed by "
            f"({envelope.dataSet}, {envelope.period}, {envelope.orgUnit}, "
            f"{envelope.attributeOptionCombo or 'default combo'}) "
            f"/ ({value.dataElement}, {value.categoryOptionCombo})"
        )
    print("  both submissions key the same cell, so the second write replaces the first value in place:")
    print("  /api/dataValueSets takes a re-post of a tuple it holds as an update to it. Correcting an")
    print("  aggregate report is therefore just reporting it again; correcting an event is not.")


if __name__ == "__main__":
    main()
