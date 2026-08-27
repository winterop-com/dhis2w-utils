"""Reading one person's doses out of the record this facade already serves.

THE DOSES COME OUT OF THE RECORD PROJECTION AND NOT OUT OF A SECOND READ. `GET
/tracked-entities/{uid}/events` answers one entity's events as the `QuestionnaireResponse` each
stage's published form describes, and a summary is a projection of that record rather than a rival
reading of the instance (`docs/fhir/design/ips.md` section 2, and R3: every read behind a summary is
scoped to one tracked entity). So this module takes the very `RecordProjection` the record surface
runs on, projects the events of the mapped stages through it, and reads the doses off the documents
that come back. A value can therefore never be typed one way at `/facade/tracked-entities/{uid}/events` and
another inside a summary: there is one projection and this is a reader of it.

WHAT A DOSE IS HERE. `[ips.sections.immunizations]` names the stages and, inside them, the data
elements that each record a dose of one vaccine - the shape a DHIS2 immunisation form has, one
element per vaccine with the value saying that the dose was given or which dose of the series it
was. So a value under a nominated element on an event of a nominated stage is a dose, and nothing
else is.

- **A boolean.** `true` is a dose with no dose number; `false` is not a dose at all and produces
  nothing. DHIS2 says the vaccine was not given and states no reason, and R4 requires a
  `statusReason` on a `not-done` immunization - a reason this project will not invent.
- **A coded value.** The dose number is the option's own display as the guide publishes it - `Dose
  2`, `IPT 1` - because that is what a person reading a summary needs and what the option actually
  means. The concept code behind it is a DHIS2 identifier under the default naming source and says
  nothing to a clinician.
- **Anything else.** The value as the instance stored it, carried as the dose number.

A MAPPED STAGE THIS GUIDE PUBLISHES NO FORM FOR CONTRIBUTES NO DOSE, and is named rather than
passed over. It is the same rule the record surface holds - a stage with no published form is
counted and named rather than served as something else - and the summary states it in the
Immunizations section's own narrative, so a reader never mistakes a guide that is narrower than the
mapping for a person who was never vaccinated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.summary import RecordedDose
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dhis2w_fhir.ips import ImmunizationsMapping
    from dhis2w_fhir.r4 import QuestionnaireResponseAnswer, QuestionnaireResponseItem

    from dhis2w_fhir_serve.history.projection import RecordProjection
    from dhis2w_fhir_serve.history.wire import TrackedEntityRecord

__all__ = ["SummaryDoses", "recorded_doses"]


class SummaryDoses(BaseModel):
    """What one record's mapped stages hold: the doses, and the stages the guide could not read."""

    model_config = ConfigDict(frozen=True)

    doses: tuple[RecordedDose, ...] = ()
    unpublished_stage_uids: tuple[str, ...] = ()
    """Every mapped stage this guide publishes no form for, once each, in the order they occurred."""


def recorded_doses(
    record: TrackedEntityRecord, projection: RecordProjection, mapping: ImmunizationsMapping
) -> SummaryDoses:
    """Read every dose one person's record holds under one immunisation mapping, newest event first.

    The record arrives ordered - newest first, by the instant the event occurred and then by its UID
    (`dhis2w_fhir_serve.history.wire`) - and that order is kept, which is what makes two assemblies
    of an unchanged record produce the same document (R4).
    """
    doses: list[RecordedDose] = []
    unpublished: dict[str, None] = {}
    for event in record.events:
        if event.program_stage_uid not in mapping.program_stages:
            continue
        projected = projection.project_event(record, event)
        if projected.response is None:
            unpublished.setdefault(projected.unpublished_stage_uid or event.program_stage_uid or "", None)
            continue
        index = projection.form_for(event.program_stage_uid)
        for item in _answered_items(projected.response.item or []):
            if item.linkId is None or not mapping.records_dose(event.program_stage_uid, item.linkId):
                continue
            question = None if index is None else index.questions.get(item.linkId)
            for answer in item.answer or []:
                dose_number = _dose_number(answer)
                if dose_number is _NOT_A_DOSE:
                    continue
                doses.append(
                    RecordedDose(
                        event_uid=event.event_uid,
                        data_element_uid=item.linkId,
                        display=None if question is None else question.display,
                        occurred_at=projected.response.authored,
                        dose_number=dose_number,
                    )
                )
    return SummaryDoses(doses=tuple(doses), unpublished_stage_uids=tuple(unpublished))


#: What `_dose_number` answers for a value that records no dose at all, told apart from `None` -
#: which is a dose given with no dose number, and is a different fact.
_NOT_A_DOSE = "!"


def _answered_items(items: list[QuestionnaireResponseItem]) -> list[QuestionnaireResponseItem]:
    """Every item of one response, however deep the form nested it, in document order.

    A form groups its questions, and a dose element sits inside whichever section its own form asks
    it in - so the walk is the tree's, not the top level's.
    """
    flattened: list[QuestionnaireResponseItem] = []
    for item in items:
        flattened.append(item)
        flattened.extend(_answered_items(item.item or []))
    return flattened


def _dose_number(answer: QuestionnaireResponseAnswer) -> str | None:
    """Which dose of a series one answer records, or `_NOT_A_DOSE` where it records no dose at all.

    Nothing - `None` - is a dose given with no dose number stated, which is a different fact from a
    value that records no dose, and the two never collapse. See this module's docstring for the
    three readings and why each is what it is.
    """
    if answer.valueBoolean is not None:
        return None if answer.valueBoolean else _NOT_A_DOSE
    if answer.valueCoding is not None:
        return answer.valueCoding.display or answer.valueCoding.code or _NOT_A_DOSE
    for stated in (answer.valueString, answer.valueDate, answer.valueDateTime, answer.valueTime, answer.valueUri):
        if stated:
            return stated
    if answer.valueInteger is not None:
        return str(answer.valueInteger)
    if answer.valueDecimal is not None:
        return str(answer.valueDecimal)
    return _NOT_A_DOSE
