"""The conversion layer's public surface: one import path, the form lookup, and the payload accessor."""

from __future__ import annotations

import dhis2w_fhir
from dhis2w_client.generated.v42.oas import DataValueSet, TrackerEnrollment, TrackerEvent, TrackerTrackedEntity
from dhis2w_fhir import conversion
from dhis2w_fhir.config import GenerateConfig
from dhis2w_fhir.conversion import (
    ConversionContext,
    ConversionNaming,
    ConversionReport,
    ConversionResult,
    FormSpec,
)
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


_DATA_VALUE_SET = DataValueSet()
_EVENT = TrackerEvent(program="PrGaaaaaaaa", orgUnit="Ouaaaaaaaaa")
_TRACKED_ENTITY = TrackerTrackedEntity(trackedEntityType="Tetaaaaaaaa", orgUnit="Ouaaaaaaaaa")
_ENROLLMENT = TrackerEnrollment(program="PrGaaaaaaaa", orgUnit="Ouaaaaaaaaa")

#: One result per target kind, each carrying the payload that kind names.
_RESULTS_BY_TARGET_KIND = {
    ConversionTargetKind.DATA_VALUE_SET: ConversionResult(
        target_kind=ConversionTargetKind.DATA_VALUE_SET, data_value_set=_DATA_VALUE_SET
    ),
    ConversionTargetKind.EVENT: ConversionResult(target_kind=ConversionTargetKind.EVENT, event=_EVENT),
    ConversionTargetKind.TRACKER_EVENT: ConversionResult(target_kind=ConversionTargetKind.TRACKER_EVENT, event=_EVENT),
    ConversionTargetKind.TRACKED_ENTITY: ConversionResult(
        target_kind=ConversionTargetKind.TRACKED_ENTITY, tracked_entity=_TRACKED_ENTITY
    ),
    ConversionTargetKind.TRACKER: ConversionResult(
        target_kind=ConversionTargetKind.TRACKER, tracked_entity=_TRACKED_ENTITY
    ),
    ConversionTargetKind.TRACKER_ENROLLMENT: ConversionResult(
        target_kind=ConversionTargetKind.TRACKER_ENROLLMENT, enrollment=_ENROLLMENT
    ),
}

#: Which payload each target kind names, which is what the accessor is asserted to answer.
_PAYLOADS_BY_TARGET_KIND = {
    ConversionTargetKind.DATA_VALUE_SET: _DATA_VALUE_SET,
    ConversionTargetKind.EVENT: _EVENT,
    ConversionTargetKind.TRACKER_EVENT: _EVENT,
    ConversionTargetKind.TRACKED_ENTITY: _TRACKED_ENTITY,
    ConversionTargetKind.TRACKER: _TRACKED_ENTITY,
    ConversionTargetKind.TRACKER_ENROLLMENT: _ENROLLMENT,
}


def test_every_target_kind_names_the_payload_the_accessor_answers() -> None:
    """The accessor is keyed by target kind, and every kind the taxonomy declares has an answer."""
    assert set(_PAYLOADS_BY_TARGET_KIND) == set(ConversionTargetKind)
    for target_kind, payload in _PAYLOADS_BY_TARGET_KIND.items():
        assert _RESULTS_BY_TARGET_KIND[target_kind].payload is payload, target_kind


def test_the_two_registration_kinds_answer_the_payload_each_of_them_carries() -> None:
    """A registration minting its person and one enrolling a person the instance holds are two kinds."""
    assert _RESULTS_BY_TARGET_KIND[ConversionTargetKind.TRACKER].payload is _TRACKED_ENTITY
    assert _RESULTS_BY_TARGET_KIND[ConversionTargetKind.TRACKER_ENROLLMENT].payload is _ENROLLMENT


def test_the_narrowing_accessor_answers_only_the_wire_shape_asked_for() -> None:
    """`payload_of` hands back the payload when it is that shape, and None for every other kind."""
    aggregate = _RESULTS_BY_TARGET_KIND[ConversionTargetKind.DATA_VALUE_SET]

    assert aggregate.payload_of(DataValueSet) is _DATA_VALUE_SET
    assert aggregate.payload_of(TrackerEvent) is None
    assert _RESULTS_BY_TARGET_KIND[ConversionTargetKind.TRACKER].payload_of(TrackerEnrollment) is None


def test_the_batch_accessor_reads_one_wire_shape_in_the_order_the_responses_were_drained() -> None:
    """The four posting properties are `payloads_of` under the names a caller posts them by."""
    report = ConversionReport(results=tuple(_RESULTS_BY_TARGET_KIND.values()))

    assert report.data_value_sets == (_DATA_VALUE_SET,)
    assert report.events == (_EVENT, _EVENT)
    assert report.tracked_entities == (_TRACKED_ENTITY, _TRACKED_ENTITY)
    assert report.enrollments == (_ENROLLMENT,)
    assert report.payloads_of(DataValueSet) == report.data_value_sets


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
    assert refused.payload_of(DataValueSet) is None
    assert ConversionReport(results=(refused,)).payloads_of(DataValueSet) == ()
