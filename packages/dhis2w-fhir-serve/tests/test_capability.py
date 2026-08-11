"""The CapabilityStatement builder: what it states, and that it round-trips through the R4 model."""

from __future__ import annotations

from dhis2w_fhir.config import FhirProject
from dhis2w_fhir.r4 import CapabilityStatement
from dhis2w_fhir_serve.capability import build_server_capability
from dhis2w_fhir_serve.metadata import build_metadata_body
from dhis2w_fhir_serve.patients.index import PatientIndex
from dhis2w_fhir_serve.patients.surface import PatientSurface
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import ResourceStore, StoreSummary

CANONICAL = "http://example.org/fhir"

FULL_SUMMARY = StoreSummary(
    counts_by_type={
        "CodeSystem": 2,
        "ImplementationGuide": 1,
        "Location": 4,
        "Organization": 3,
        "Questionnaire": 5,
        "StructureDefinition": 7,
        "ValueSet": 2,
    }
)


def _patient_surface(project: FhirProject) -> PatientSurface:
    """The surface over an empty store - no published registration form, so no Patient is declared."""
    return PatientSurface.resolve(PatientIndex.from_store(project, ResourceStore()), project.config.serve.patients)


def _capability(project: FhirProject, summary: StoreSummary, *, live: bool = False) -> CapabilityStatement:
    return build_server_capability(
        project=project,
        store_summary=summary,
        spool_count=11,
        settings=ServeSettings(project_dir=project.project_root, live=live),
        patient_surface=_patient_surface(project),
        server_version="9.9.9",
    )


def test_capability_states_the_instance_it_describes(compiled_project: FhirProject) -> None:
    capability = _capability(compiled_project, FULL_SUMMARY)

    assert capability.kind == "instance"
    assert capability.status == "active"
    assert capability.fhirVersion == "4.0.1"
    assert capability.format == ["json"]
    assert capability.date is not None
    assert capability.date.endswith("Z")
    assert capability.software is not None
    assert capability.software.name == "d2w fhir serve"
    assert capability.software.version == "9.9.9"
    assert capability.instantiates == [f"{CANONICAL}/CapabilityStatement/d2-capture-server"]


def test_capability_reports_the_store_and_spool_it_started_with(compiled_project: FhirProject) -> None:
    capability = _capability(compiled_project, FULL_SUMMARY)

    assert capability.description is not None
    assert "24 resources across 7 types" in capability.description
    assert "11 stored responses at startup" in capability.description


def test_capability_names_the_store_mode(compiled_project: FhirProject) -> None:
    compiled = _capability(compiled_project, FULL_SUMMARY)
    live = _capability(compiled_project, FULL_SUMMARY, live=True)

    assert compiled.implementation is not None
    assert live.implementation is not None
    assert "(compiled store)" in (compiled.implementation.description or "")
    assert "(live store)" in (live.implementation.description or "")


def test_capability_lists_the_read_types_in_the_captured_order(compiled_project: FhirProject) -> None:
    capability = _capability(compiled_project, FULL_SUMMARY)

    assert capability.rest is not None
    resources = capability.rest[0].resource or []
    assert [resource.type for resource in resources] == [
        "QuestionnaireResponse",
        "Questionnaire",
        "CodeSystem",
        "ValueSet",
        "Location",
        "Organization",
    ]


def test_concept_map_joins_the_read_types_when_the_store_holds_maps(compiled_project: FhirProject) -> None:
    """The maps are published artifacts in the same store, so they are read like every other type."""
    with_maps = StoreSummary(counts_by_type={**FULL_SUMMARY.counts_by_type, "ConceptMap": 3})

    capability = _capability(compiled_project, with_maps)

    assert capability.rest is not None
    resources = capability.rest[0].resource or []
    assert [resource.type for resource in resources] == [
        "QuestionnaireResponse",
        "Questionnaire",
        "CodeSystem",
        "ValueSet",
        "Location",
        "Organization",
        "ConceptMap",
    ]
    concept_map = resources[-1]
    assert [interaction.code for interaction in concept_map.interaction or []] == ["read", "search-type"]
    assert concept_map.operation is None
    assert [operation.name for operation in capability.rest[0].operation or []] == ["translate"]


def test_a_store_without_maps_declares_neither_the_read_type_nor_the_operation(
    compiled_project: FhirProject,
) -> None:
    capability = _capability(compiled_project, FULL_SUMMARY)

    assert capability.rest is not None
    assert "ConceptMap" not in [resource.type for resource in capability.rest[0].resource or []]
    assert capability.rest[0].operation is None


def test_a_type_the_store_lost_drops_out_of_the_statement(compiled_project: FhirProject) -> None:
    without_organizations = StoreSummary(
        counts_by_type={key: count for key, count in FULL_SUMMARY.counts_by_type.items() if key != "Organization"}
    )

    capability = _capability(compiled_project, without_organizations)

    assert capability.rest is not None
    assert "Organization" not in [resource.type for resource in capability.rest[0].resource or []]


def test_capability_round_trips_through_the_r4_model(compiled_project: FhirProject) -> None:
    capability = _capability(compiled_project, FULL_SUMMARY)

    body = build_metadata_body(
        project=compiled_project,
        store_summary=FULL_SUMMARY,
        spool_count=11,
        settings=ServeSettings(project_dir=compiled_project.project_root),
        patient_surface=_patient_surface(compiled_project),
        server_version="9.9.9",
    )
    revalidated = CapabilityStatement.model_validate(body)

    assert revalidated.model_dump(exclude={"date"}) == capability.model_dump(exclude={"date"})
    assert "url" not in body
    assert "experimental" not in body
