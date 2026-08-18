"""The conversion layer's public surface: one import path, the form lookup, and the payload accessor."""

from __future__ import annotations

import dhis2w_fhir
from dhis2w_client.generated.v42.oas import DataValueSet, TrackerEnrollment, TrackerEvent, TrackerTrackedEntity
from dhis2w_fhir import conversion
from dhis2w_fhir.config import GenerateConfig
from dhis2w_fhir.conversion import ConversionContext, ConversionNaming, ConversionResult, FormSpec
from dhis2w_fhir.conversion.schemas import ConversionRefusal, ConversionRefusalCategory, ConversionTargetKind

_CANONICAL = "http://example.org/fhir"


def test_the_package_re_exports_the_whole_conversion_surface() -> None:
    """Every public conversion name is importable from `dhis2w_fhir` itself - the one stable surface.

    The package docstring promises one stable import surface, so a conversion name reachable only
    through the subpackage is a rule a caller cannot infer. The subpackage stays importable too,
    and both paths hand back the same object.
    """
    missing = [name for name in conversion.__all__ if name not in dhis2w_fhir.__all__]
    assert missing == []
    for name in conversion.__all__:
        assert getattr(dhis2w_fhir, name) is getattr(conversion, name), name


def _form(canonical: str) -> FormSpec:
    """One minimal served form under the given canonical."""
    return FormSpec(canonical=canonical, form_kind="aggregate", target_kind=ConversionTargetKind.DATA_VALUE_SET)


def _context_with(forms: dict[str, FormSpec]) -> ConversionContext:
    """A context carrying the given forms and nothing else."""
    return ConversionContext(naming=ConversionNaming.from_config(GenerateConfig(), _CANONICAL), forms=forms)


def test_form_for_resolves_the_canonical_and_the_bare_form_id() -> None:
    """A response carries the canonical; a UI holds the trailing id - both name the same form."""
    canonical = f"{_CANONICAL}/Questionnaire/d2-ds-child-health-q"
    context = _context_with({canonical: _form(canonical)})

    assert context.form_for(canonical) is context.forms[canonical]
    assert context.form_for("d2-ds-child-health-q") is context.forms[canonical]


def test_form_for_answers_none_for_nothing_named_and_nothing_served() -> None:
    """No reference and an unserved reference are the same answer: no form to read a response against."""
    canonical = f"{_CANONICAL}/Questionnaire/d2-ds-child-health-q"
    context = _context_with({canonical: _form(canonical)})

    assert context.form_for(None) is None
    assert context.form_for("") is None
    assert context.form_for("d2-ds-somewhere-else-q") is None
    assert context.form_for(f"{_CANONICAL}/Questionnaire/d2-ds-somewhere-else-q") is None


def test_the_payload_accessor_answers_whichever_field_the_translation_set() -> None:
    """One accessor for the produced document, whichever of the four exclusive fields carries it."""
    data_value_set = DataValueSet()
    event = TrackerEvent(program="PrGaaaaaaaa", orgUnit="Ouaaaaaaaaa")
    tracked_entity = TrackerTrackedEntity(trackedEntityType="Tetaaaaaaaa", orgUnit="Ouaaaaaaaaa")
    enrollment = TrackerEnrollment(program="PrGaaaaaaaa", orgUnit="Ouaaaaaaaaa")

    assert ConversionResult(data_value_set=data_value_set).payload is data_value_set
    assert ConversionResult(event=event).payload is event
    assert ConversionResult(tracked_entity=tracked_entity).payload is tracked_entity
    assert ConversionResult(enrollment=enrollment).payload is enrollment


def test_a_refused_result_carries_no_payload() -> None:
    """A refusal is the absence of a payload, and the accessor says so rather than guessing."""
    refused = ConversionResult(
        refusals=(
            ConversionRefusal(
                category=ConversionRefusalCategory.NO_FORM_TYPE,
                element="QuestionnaireResponse.extension",
                reason="the response declares no DHIS2 form kind",
            ),
        )
    )

    assert refused.is_refused
    assert refused.payload is None
