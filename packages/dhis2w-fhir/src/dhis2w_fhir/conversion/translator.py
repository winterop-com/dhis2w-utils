"""The entry point: one QuestionnaireResponse in, one typed DHIS2 payload or a named refusal out.

Translation is three questions asked in order, and the first that cannot be answered ends the
response: which DHIS2 form kind the submission claims to be, which served form it answers, and
whether the two agree. Only then does the form kind's payload translator run.

The batch form drains a spool the same way one response at a time, so a `ConversionReport` is one
result per submission in the order they were drained - a refusal never stops the responses behind
it, and a caller posts `report.data_value_sets` and `report.events` while routing `report.refused`
back to whoever sent them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.conversion.payloads import (
    translate_aggregate_response,
    translate_event_response,
    translate_tracker_event_response,
)
from dhis2w_fhir.conversion.schemas import (
    TARGET_KINDS_BY_FORM_KIND,
    ConversionRefusal,
    ConversionRefusalCategory,
    ConversionReport,
    ConversionResult,
)
from dhis2w_fhir.resources.questionnaires.schemas import FORM_KIND_PROFILES, FormKind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dhis2w_fhir.conversion.schemas import ConversionContext, FormSpec
    from dhis2w_fhir.r4 import QuestionnaireResponse

__all__ = ["translate_response", "translate_responses"]


def translate_response(response: QuestionnaireResponse, context: ConversionContext) -> ConversionResult:
    """Translate one captured response into the DHIS2 import payload its form kind reports as."""
    declared = _declared_form_kind(response, context)
    if declared is None:
        return _refused(
            response,
            ConversionRefusalCategory.NO_FORM_TYPE,
            "QuestionnaireResponse.extension",
            f"the response declares no DHIS2 form kind under `{context.naming.form_type_url}`",
        )
    form = context.forms.get(response.questionnaire or "")
    if form is None:
        return _refused(
            response,
            ConversionRefusalCategory.UNKNOWN_FORM,
            "QuestionnaireResponse.questionnaire",
            f"`{response.questionnaire}` is no form this context carries",
        )
    if form.form_kind != declared:
        return _refused(
            response,
            ConversionRefusalCategory.FORM_KIND_MISMATCH,
            "QuestionnaireResponse.extension",
            f"the response declares form kind `{declared}`, and `{form.canonical}` is a `{form.form_kind}` form",
        )
    if form.form_kind == "aggregate":
        return _aggregate_result(response, form, context)
    return _event_result(response, form, context)


def translate_responses(responses: Sequence[QuestionnaireResponse], context: ConversionContext) -> ConversionReport:
    """Translate a batch of captured responses, one result each, in the order they were drained."""
    return ConversionReport(results=tuple(translate_response(response, context) for response in responses))


def _aggregate_result(response: QuestionnaireResponse, form: FormSpec, context: ConversionContext) -> ConversionResult:
    """Run the aggregate translator and carry its outcome onto the result the caller reads."""
    translation = translate_aggregate_response(response, form, context)
    return ConversionResult(
        response_id=response.id,
        questionnaire=form.canonical,
        target_kind=TARGET_KINDS_BY_FORM_KIND[form.form_kind],
        data_value_set=translation.data_value_set,
        notes=translation.notes,
        refusals=translation.refusals,
    )


def _event_result(response: QuestionnaireResponse, form: FormSpec, context: ConversionContext) -> ConversionResult:
    """Run the event translator its form kind names and carry the outcome onto the result."""
    translation = (
        translate_tracker_event_response(response, form, context)
        if form.form_kind == "tracker-event"
        else translate_event_response(response, form, context)
    )
    return ConversionResult(
        response_id=response.id,
        questionnaire=form.canonical,
        target_kind=translation.target_kind,
        event=translation.event,
        notes=translation.notes,
        refusals=translation.refusals,
    )


def _declared_form_kind(response: QuestionnaireResponse, context: ConversionContext) -> FormKind | None:
    """Which DHIS2 form kind the submission claims to be - everything after this branches on it."""
    declared = {
        extension.valueCode
        for extension in response.extension or []
        if extension.url == context.naming.form_type_url and extension.valueCode is not None
    }
    if len(declared) != 1:
        return None
    for kind in FORM_KIND_PROFILES:
        if kind in declared:
            return kind
    return None


def _refused(
    response: QuestionnaireResponse,
    category: ConversionRefusalCategory,
    element: str,
    reason: str,
) -> ConversionResult:
    """One response refused before any payload translator ran."""
    return ConversionResult(
        response_id=response.id,
        questionnaire=response.questionnaire,
        refusals=(ConversionRefusal(category=category, element=element, reason=reason),),
    )
