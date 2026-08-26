"""The CapabilityStatement builder: what it states, and that it round-trips through the R4 model."""

from __future__ import annotations

from dhis2w_fhir.config import FhirProject, ServeAuth, ServeAuthScope
from dhis2w_fhir.r4 import CapabilityStatement, CapabilityStatementSecurity
from dhis2w_fhir_serve.capability import (
    EVALUATE_OPERATION_DEFINITION,
    SECURITY_SERVICE_SYSTEM,
    build_server_capability,
)
from dhis2w_fhir_serve.metadata import build_metadata_body
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
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


def _register_surface(project: FhirProject) -> RegisterSurface:
    """The surface over an empty store - no published registration form, so no Patient is declared."""
    return RegisterSurface.resolve(
        TrackedEntityIndex.from_store(project, ResourceStore()), project.config.serve.tracked_entities
    )


def _capability(project: FhirProject, summary: StoreSummary, *, live: bool = False) -> CapabilityStatement:
    return build_server_capability(
        project=project,
        store_summary=summary,
        settings=ServeSettings(project_dir=project.project_root, live=live),
        register_surface=_register_surface(project),
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


def test_capability_reports_the_store_and_points_at_the_spool_for_the_queue(compiled_project: FhirProject) -> None:
    """The store is fixed for the life of the process and is counted; the spool is not, and is not."""
    capability = _capability(compiled_project, FULL_SUMMARY)

    assert capability.description is not None
    assert "24 resources in the store" in capability.description
    assert "`GET /spool` states how many responses are stored" in capability.description
    assert "stored responses at startup" not in capability.description


def test_the_stated_type_count_is_the_one_the_statement_itself_declares(compiled_project: FhirProject) -> None:
    """The summary sentence counts the entries below it, never the store's own types.

    The two numbers are different in both directions. A StructureMap is a compiled artifact this
    facade serves no read for, so it is in the store and in no entry; QuestionnaireResponse is the
    capture type, so it is an entry whether or not a receipt has ever been stored. Counting the store
    would put a number in the prose that the table of entries beside it contradicts.
    """
    with_unserved = StoreSummary(counts_by_type={**FULL_SUMMARY.counts_by_type, "StructureMap": 1})

    capability = _capability(compiled_project, with_unserved)
    declared = capability.rest[0].resource or [] if capability.rest else []

    assert "StructureMap" not in [resource.type for resource in declared]
    assert capability.description is not None
    assert f"served under the {len(declared)} resource types this statement declares" in capability.description
    assert "8 resource types" in capability.description


def test_each_store_mode_says_what_this_installation_is(compiled_project: FhirProject) -> None:
    """A live process stands in front of an instance and a compiled one in front of a build."""
    compiled = _capability(compiled_project, FULL_SUMMARY)
    live = _capability(compiled_project, FULL_SUMMARY, live=True)

    assert compiled.implementation is not None
    assert live.implementation is not None
    assert (compiled.implementation.description or "").startswith(
        "A FHIR capture facade over a compiled implementation guide."
    )
    assert (live.implementation.description or "").startswith("A FHIR capture facade over a live DHIS2 instance.")
    assert "receipts of submissions as they arrived" in (compiled.implementation.description or "")
    assert "receipts of submissions as they arrived" in (live.implementation.description or "")


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
        "StructureDefinition",
        "ImplementationGuide",
    ]


def test_the_conformance_entries_say_why_a_client_may_lean_on_them(compiled_project: FhirProject) -> None:
    """A server hosting its own guide's definitions is a fact a client has to be told, in the document."""
    capability = _capability(compiled_project, FULL_SUMMARY)
    resources = capability.rest[0].resource or [] if capability.rest else []
    conformance = [resource for resource in resources if resource.type == "StructureDefinition"]

    assert len(conformance) == 1
    documentation = conformance[0].documentation or ""
    assert "hosted here read-only" in documentation
    assert "the profiles a response claims" in documentation
    assert "url={canonical}" in documentation


def test_a_read_type_a_capture_client_already_knows_states_nothing_extra(compiled_project: FhirProject) -> None:
    """Only the conformance entries carry a sentence; a Questionnaire entry would restate its own type."""
    capability = _capability(compiled_project, FULL_SUMMARY)
    resources = capability.rest[0].resource or [] if capability.rest else []

    questionnaire = next(resource for resource in resources if resource.type == "Questionnaire")
    assert questionnaire.documentation is None


def test_a_store_with_no_compiled_guide_declares_no_conformance_type(compiled_project: FhirProject) -> None:
    """A live run over a project that was never compiled hosts none of them, and claims none."""
    without_conformance = StoreSummary(
        counts_by_type={
            key: count
            for key, count in FULL_SUMMARY.counts_by_type.items()
            if key not in ("StructureDefinition", "ImplementationGuide")
        }
    )

    capability = _capability(compiled_project, without_conformance, live=True)
    types = [resource.type for resource in capability.rest[0].resource or []] if capability.rest else []

    assert "StructureDefinition" not in types
    assert "ImplementationGuide" not in types
    assert "OperationDefinition" not in types


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
        "StructureDefinition",
        "ImplementationGuide",
    ]
    concept_map = next(resource for resource in resources if resource.type == "ConceptMap")
    assert [interaction.code for interaction in concept_map.interaction or []] == ["read", "search-type"]
    assert [operation.name for operation in concept_map.operation or []] == ["translate"]


def test_a_store_without_maps_declares_neither_the_read_type_nor_the_operation(
    compiled_project: FhirProject,
) -> None:
    capability = _capability(compiled_project, FULL_SUMMARY)

    assert capability.rest is not None
    assert "ConceptMap" not in [resource.type for resource in capability.rest[0].resource or []]
    assert [operation.name for operation in capability.rest[0].operation or []] == ["evaluate"]


def test_the_server_level_slot_holds_the_one_operation_whose_url_is_the_service_base(
    compiled_project: FhirProject,
) -> None:
    """`$evaluate` runs over whatever the request names, so no resource type owns it and it rides here."""
    capability = _capability(compiled_project, FULL_SUMMARY)

    assert capability.rest is not None
    declared = capability.rest[0].operation or []
    assert [operation.name for operation in declared] == ["evaluate"]
    assert declared[0].definition == EVALUATE_OPERATION_DEFINITION
    assert "Parameters resource" in (declared[0].documentation or "")


def test_every_resource_operation_rides_the_entry_whose_url_answers_it(
    compiled_project: FhirProject,
) -> None:
    """A resource operation's URL is the resource's, so declaring one server-level would name a 404."""
    with_maps = StoreSummary(counts_by_type={**FULL_SUMMARY.counts_by_type, "ConceptMap": 3})

    capability = _capability(compiled_project, with_maps)

    assert capability.rest is not None
    declared = {
        resource.type: [operation.name for operation in resource.operation or []]
        for resource in capability.rest[0].resource or []
        if resource.operation
    }
    assert declared == {"Questionnaire": ["generate"], "ConceptMap": ["translate"]}


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
        settings=ServeSettings(project_dir=compiled_project.project_root),
        register_surface=_register_surface(compiled_project),
        server_version="9.9.9",
    )
    revalidated = CapabilityStatement.model_validate(body)

    assert revalidated.model_dump(exclude={"date"}) == capability.model_dump(exclude={"date"})
    assert "url" not in body
    assert "experimental" not in body


def test_the_security_element_is_declared_in_every_posture_including_the_one_that_checks_no_credential(
    compiled_project: FhirProject,
) -> None:
    """An absent element would leave "checks no credential" and "did not say" indistinguishable."""
    statement = _capability(compiled_project, FULL_SUMMARY)
    security = statement.rest[0].security if statement.rest else None

    assert security is not None
    assert security.cors is False
    assert security.service is None
    assert (security.description or "").startswith("This server checks no credential.")
    assert "listens on the loopback interface only" in (security.description or "")


def test_the_token_posture_names_the_scheme_and_the_variable_but_never_a_token(
    compiled_project: FhirProject,
) -> None:
    """A conformance document is public, so what it says about a credential is how to send one."""
    security = _security(compiled_project, ServeAuth.TOKEN, ServeAuthScope.WRITE)

    assert [concept.text for concept in security.service or []] == ["Bearer token"]
    assert "D2W_FHIR_SERVE_TOKENS" in (security.description or "")
    assert "Bearer <token>" in (security.description or "")


def test_the_dhis2_posture_names_basic_by_its_r4_code_and_the_access_token_as_text(
    compiled_project: FhirProject,
) -> None:
    """The value set has a code for one of the two schemes, and an extensible binding is for the other."""
    security = _security(compiled_project, ServeAuth.DHIS2, ServeAuthScope.WRITE)
    codings = [coding for concept in security.service or [] for coding in concept.coding or []]

    assert [coding.code for coding in codings] == ["Basic"]
    assert [coding.system for coding in codings] == [SECURITY_SERVICE_SYSTEM]
    assert "DHIS2 personal access token" in [concept.text for concept in security.service or []]
    assert "/api/me" in (security.description or "")


def test_each_scope_says_how_much_of_the_surface_the_posture_covers(compiled_project: FhirProject) -> None:
    """A client reading the document learns whether browsing needs a credential or only submitting does."""
    write = _security(compiled_project, ServeAuth.TOKEN, ServeAuthScope.WRITE)
    everything = _security(compiled_project, ServeAuth.TOKEN, ServeAuthScope.ALL)

    assert "Every read" in (write.description or "")
    assert "every interaction except reading this document" in (everything.description or "")


def test_the_dhis2_posture_states_that_the_register_is_read_as_the_caller(compiled_project: FhirProject) -> None:
    """The rule a client meets on the register is stated ahead of the request, not discovered from a refusal."""
    security = _security(compiled_project, ServeAuth.DHIS2, ServeAuthScope.WRITE)

    assert "under your own DHIS2 authorization" in (security.description or "")


def test_the_write_scope_under_the_dhis2_posture_never_claims_every_read_is_open(
    compiled_project: FhirProject,
) -> None:
    """A register read asks for credentials in either scope, so the scope sentence cannot promise otherwise."""
    security = _security(compiled_project, ServeAuth.DHIS2, ServeAuthScope.WRITE)

    assert "read or search the register" in (security.description or "")
    assert "Every read, every search, this document" not in (security.description or "")


def _security(project: FhirProject, posture: ServeAuth, scope: ServeAuthScope) -> CapabilityStatementSecurity:
    """The `rest.security` one process declares, built the way `/metadata` builds it."""
    statement = build_server_capability(
        project=project,
        store_summary=FULL_SUMMARY,
        settings=ServeSettings(project_dir=project.project_root, auth=posture, auth_scope=scope),
        register_surface=_register_surface(project),
        server_version="9.9.9",
    )
    security = statement.rest[0].security if statement.rest else None
    assert security is not None
    return security
