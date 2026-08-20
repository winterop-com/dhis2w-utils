"""Tests for the retrieve filters on the R4 FHIR data sources."""

from typing import Any

import pytest

from dhis2w_fhir_engine.binding import FhirVersionBinding
from dhis2w_fhir_engine.engine.cql import CQLCode, PatientContext
from dhis2w_fhir_engine.engine.cql.types import CQLConcept, CQLInterval
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime
from dhis2w_fhir_engine.r4 import BundleDataSource, InMemoryDataSource, PatientBundleDataSource
from dhis2w_fhir_engine.r4.binding import R4_BINDING
from dhis2w_fhir_engine.r4.datasource import FHIRDataSource

LOINC = "http://loinc.org"
SNOMED = "http://snomed.info/sct"


def observation(
    resource_id: str,
    code: str,
    system: str = LOINC,
    subject: str | None = None,
    effective: Any = None,
) -> dict[str, Any]:
    """Build an Observation with a single coding and an optional subject and effective element."""
    resource: dict[str, Any] = {
        "resourceType": "Observation",
        "id": resource_id,
        "status": "final",
        "code": {"coding": [{"system": system, "code": code}]},
    }
    if subject is not None:
        resource["subject"] = {"reference": subject}
    if effective is not None:
        resource["effectiveDateTime"] = effective
    return resource


class TestBaseDataSourceInterface:
    """Tests for the abstract FHIRDataSource surface."""

    def test_binding_defaults_to_r4(self) -> None:
        assert FHIRDataSource().binding is R4_BINDING

    def test_binding_keeps_the_supplied_binding(self) -> None:
        binding = FhirVersionBinding(
            name="Custom",
            fhir_version="4.0.1",
            patient_reference_paths={"Observation": ("performer.reference",)},
            default_patient_reference_paths=("subject.reference",),
        )
        assert FHIRDataSource(binding).binding is binding

    def test_retrieve_is_not_implemented_on_the_base_class(self) -> None:
        with pytest.raises(NotImplementedError):
            FHIRDataSource().retrieve("Patient")

    def test_resolve_reference_is_not_implemented_on_the_base_class(self) -> None:
        with pytest.raises(NotImplementedError):
            FHIRDataSource().resolve_reference("Patient/1")


class TestNestedValueLookup:
    """Tests for the dot-notation path walk used by every filter."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("code.coding.0.code", "1234-5"),
            ("code.coding.0.system", LOINC),
            ("status", "final"),
            ("code.coding.5.code", None),
            ("status.missing", None),
            ("code.missing", None),
            ("code.missing.deeper", None),
        ],
    )
    def test_paths(self, path: str, expected: Any) -> None:
        data_source = InMemoryDataSource()
        assert data_source._get_nested_value(observation("o1", "1234-5"), path) == expected

    def test_index_into_a_non_list_returns_none(self) -> None:
        data_source = InMemoryDataSource()
        assert data_source._get_nested_value(observation("o1", "1234-5"), "code.0") is None

    def test_a_list_element_flattens_nested_lists(self) -> None:
        data_source = InMemoryDataSource()
        patient = {
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"given": ["Ada", "Grace"]}, {"given": ["Alan"]}],
        }
        assert data_source._get_nested_value(patient, "name.given") == ["Ada", "Grace", "Alan"]

    def test_a_list_element_collects_scalar_values(self) -> None:
        data_source = InMemoryDataSource()
        patient = {
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"family": "Lovelace"}, {"family": "Hopper"}],
        }
        assert data_source._get_nested_value(patient, "name.family") == ["Lovelace", "Hopper"]

    def test_a_list_element_with_no_matching_key_returns_none(self) -> None:
        data_source = InMemoryDataSource()
        patient = {"resourceType": "Patient", "id": "p1", "name": [{"family": "Lovelace"}]}
        assert data_source._get_nested_value(patient, "name.given") is None


class TestCodeFilter:
    """Tests for the code-path filter."""

    def test_a_missing_code_path_does_not_match(self) -> None:
        data_source = InMemoryDataSource()
        resource = {"resourceType": "Observation", "id": "o1"}
        assert data_source._matches_code(resource, "code", [CQLCode(code="1234-5", system=LOINC)]) is False

    def test_a_bare_coding_at_the_code_path_matches(self) -> None:
        data_source = InMemoryDataSource()
        resource = {"resourceType": "Observation", "id": "o1", "code": {"system": LOINC, "code": "1234-5"}}
        assert data_source._matches_code(resource, "code", [CQLCode(code="1234-5", system=LOINC)]) is True
        assert data_source._matches_code(resource, "code", [CQLCode(code="9999-9", system=LOINC)]) is False

    def test_a_codeable_concept_with_only_text_does_not_match(self) -> None:
        data_source = InMemoryDataSource()
        resource = {"resourceType": "Observation", "id": "o1", "code": {"text": "blood pressure"}}
        assert data_source._matches_code(resource, "code", [CQLCode(code="1234-5", system=LOINC)]) is False

    def test_a_list_of_codeable_concepts_matches_on_any_coding(self) -> None:
        data_source = InMemoryDataSource()
        resource = {
            "resourceType": "Observation",
            "id": "o1",
            "category": [
                {"coding": [{"system": LOINC, "code": "vital-signs"}]},
                {"coding": [{"system": LOINC, "code": "laboratory"}]},
            ],
        }
        assert data_source._matches_code(resource, "category", [CQLCode(code="laboratory", system=LOINC)]) is True
        assert data_source._matches_code(resource, "category", [CQLCode(code="survey", system=LOINC)]) is False

    def test_a_list_of_codings_matches_on_any_element(self) -> None:
        data_source = InMemoryDataSource()
        resource = {
            "resourceType": "Observation",
            "id": "o1",
            "code": {"coding": [{"system": LOINC, "code": "1234-5"}, {"system": SNOMED, "code": "271649006"}]},
        }
        assert data_source._matches_code(resource, "code.coding", [CQLCode(code="271649006", system=SNOMED)]) is True

    def test_a_concept_matches_when_any_of_its_codes_matches(self) -> None:
        data_source = InMemoryDataSource()
        concept = CQLConcept(
            codes=(CQLCode(code="9999-9", system=LOINC), CQLCode(code="1234-5", system=LOINC)),
            display="Systolic",
        )
        assert data_source._matches_code(observation("o1", "1234-5"), "code", [concept]) is True

    def test_a_concept_with_no_matching_code_does_not_match(self) -> None:
        data_source = InMemoryDataSource()
        concept = CQLConcept(codes=(CQLCode(code="9999-9", system=LOINC),))
        assert data_source._matches_code(observation("o1", "1234-5"), "code", [concept]) is False

    @pytest.mark.parametrize(
        ("match_code", "expected"),
        [
            ({"code": "1234-5", "system": LOINC}, True),
            ({"code": "1234-5"}, True),
            ({"code": "1234-5", "system": SNOMED}, False),
            ({"code": "9999-9", "system": LOINC}, False),
        ],
    )
    def test_a_plain_dict_code(self, match_code: dict[str, str], expected: bool) -> None:
        data_source = InMemoryDataSource()
        assert data_source._matches_code(observation("o1", "1234-5"), "code", [match_code]) is expected

    @pytest.mark.parametrize(("match_code", "expected"), [("1234-5", True), ("9999-9", False)])
    def test_a_bare_string_code(self, match_code: str, expected: bool) -> None:
        data_source = InMemoryDataSource()
        assert data_source._matches_code(observation("o1", "1234-5"), "code", [match_code]) is expected

    def test_valueset_codes_match_independently_of_the_code_list(self) -> None:
        data_source = InMemoryDataSource()
        valueset_codes = [CQLCode(code="1234-5", system=LOINC)]
        assert data_source._matches_code(observation("o1", "1234-5"), "code", None, valueset_codes) is True
        assert data_source._matches_code(observation("o1", "9999-9"), "code", None, valueset_codes) is False

    def test_any_coded_value_matches_when_no_criteria_are_given(self) -> None:
        data_source = InMemoryDataSource()
        assert data_source._matches_code(observation("o1", "1234-5"), "code") is True


class TestDateRangeFilter:
    """Tests for the date-path filter."""

    def test_a_resource_without_the_date_element_is_kept(self) -> None:
        data_source = InMemoryDataSource()
        date_range: CQLInterval[FHIRDate] = CQLInterval(
            low=FHIRDate(year=2023, month=1, day=1), high=FHIRDate(year=2023, month=12, day=31)
        )
        assert data_source._matches_date_range(observation("o1", "1234-5"), "effectiveDateTime", date_range) is True

    @pytest.mark.parametrize(
        ("effective", "expected"),
        [("2023-06-15", True), ("2022-12-31", False), ("2024-01-01", False)],
    )
    def test_a_date_string(self, effective: str, expected: bool) -> None:
        data_source = InMemoryDataSource()
        date_range: CQLInterval[FHIRDate] = CQLInterval(
            low=FHIRDate(year=2023, month=1, day=1), high=FHIRDate(year=2023, month=12, day=31)
        )
        resource = observation("o1", "1234-5", effective=effective)
        assert data_source._matches_date_range(resource, "effectiveDateTime", date_range) is expected

    def test_a_datetime_string(self) -> None:
        data_source = InMemoryDataSource()
        date_range: CQLInterval[FHIRDateTime] = CQLInterval(
            low=FHIRDateTime(year=2023, month=1, day=1, hour=0, minute=0, second=0),
            high=FHIRDateTime(year=2023, month=12, day=31, hour=23, minute=59, second=59),
        )
        inside = observation("o1", "1234-5", effective="2023-06-15T08:30:00")
        outside = observation("o2", "1234-5", effective="2024-06-15T08:30:00")
        assert data_source._matches_date_range(inside, "effectiveDateTime", date_range) is True
        assert data_source._matches_date_range(outside, "effectiveDateTime", date_range) is False

    @pytest.mark.parametrize(
        ("period", "expected"),
        [
            ({"start": "2023-03-01", "end": "2023-04-01"}, True),
            ({"start": "2022-11-01", "end": "2023-02-01"}, True),
            ({"start": "2024-02-01", "end": "2024-03-01"}, False),
            ({"start": "2021-01-01", "end": "2022-06-30"}, False),
            ({"start": "2023-05-01"}, True),
            ({"end": "2023-05-01"}, True),
            ({}, True),
        ],
    )
    def test_a_period_overlapping_the_range(self, period: dict[str, str], expected: bool) -> None:
        data_source = InMemoryDataSource()
        date_range: CQLInterval[FHIRDate] = CQLInterval(
            low=FHIRDate(year=2023, month=1, day=1), high=FHIRDate(year=2023, month=12, day=31)
        )
        resource: dict[str, Any] = {"resourceType": "Encounter", "id": "e1", "period": period}
        assert data_source._matches_date_range(resource, "period", date_range) is expected


class TestInMemoryRetrieve:
    """Tests for InMemoryDataSource.retrieve."""

    def test_a_resource_without_a_type_is_not_stored(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resource({"id": "no-type"})
        assert data_source._resources == {}
        assert data_source._by_id == {}

    def test_visitor_keyword_arguments_override_the_positional_filters(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resources([observation("o1", "1234-5"), observation("o2", "9999-9")])

        retrieved = data_source.retrieve(
            "Patient",
            resourceType="Observation",
            codePath="code",
            code=CQLCode(code="1234-5", system=LOINC),
        )

        assert [r["id"] for r in retrieved] == ["o1"]

    def test_a_null_code_keyword_argument_clears_the_code_filter(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resources([observation("o1", "1234-5"), observation("o2", "9999-9")])

        retrieved = data_source.retrieve("Observation", codePath="code", code=None)

        assert [r["id"] for r in retrieved] == ["o1", "o2"]

    def test_a_valueset_filter_keeps_only_expanded_members(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resources([observation("o1", "1234-5"), observation("o2", "9999-9")])
        data_source.add_valueset("http://example.org/vs/vitals", [CQLCode(code="9999-9", system=LOINC)])

        retrieved = data_source.retrieve("Observation", code_path="code", valueset="http://example.org/vs/vitals")

        assert [r["id"] for r in retrieved] == ["o2"]

    def test_a_date_range_filter_narrows_the_result(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resources(
            [
                observation("o1", "1234-5", effective="2023-06-15"),
                observation("o2", "1234-5", effective="2021-06-15"),
            ]
        )
        date_range: CQLInterval[FHIRDate] = CQLInterval(
            low=FHIRDate(year=2023, month=1, day=1), high=FHIRDate(year=2023, month=12, day=31)
        )

        retrieved = data_source.retrieve("Observation", date_path="effectiveDateTime", date_range=date_range)

        assert [r["id"] for r in retrieved] == ["o1"]

    def test_patient_context_scopes_to_the_context_patient(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resources(
            [
                observation("o1", "1234-5", subject="Patient/p1"),
                observation("o2", "1234-5", subject="Patient/p2"),
                {
                    "resourceType": "Immunization",
                    "id": "i1",
                    "patient": {"reference": "Patient/p1"},
                },
            ]
        )
        context = PatientContext(resource={"resourceType": "Patient", "id": "p1"})

        assert [r["id"] for r in data_source.retrieve("Observation", context=context)] == ["o1"]
        assert [r["id"] for r in data_source.retrieve("Immunization", context=context)] == ["i1"]

    def test_patient_context_does_not_scope_the_patient_type_itself(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resources([{"resourceType": "Patient", "id": "p1"}, {"resourceType": "Patient", "id": "p2"}])
        context = PatientContext(resource={"resourceType": "Patient", "id": "p1"})

        assert [r["id"] for r in data_source.retrieve("Patient", context=context)] == ["p1", "p2"]

    def test_a_resource_type_with_no_patient_path_falls_back_to_the_default_paths(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resources(
            [
                {"resourceType": "ServiceRequest", "id": "s1", "subject": {"reference": "Patient/p1"}},
                {"resourceType": "ServiceRequest", "id": "s2", "subject": {"reference": "Patient/p2"}},
            ]
        )
        context = PatientContext(resource={"resourceType": "Patient", "id": "p1"})

        assert [r["id"] for r in data_source.retrieve("ServiceRequest", context=context)] == ["s1"]

    def test_a_resource_with_no_patient_reference_is_dropped_from_a_patient_context(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resources([observation("o1", "1234-5")])
        context = PatientContext(resource={"resourceType": "Patient", "id": "p1"})

        assert data_source.retrieve("Observation", context=context) == []

    def test_resolve_reference_reads_the_identifier_index(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resource(observation("o1", "1234-5"))

        assert data_source.resolve_reference("Observation/o1") is not None
        assert data_source.resolve_reference("Observation/o1")["id"] == "o1"  # type: ignore[index]
        assert data_source.resolve_reference("Observation/missing") is None

    def test_clear_empties_resources_index_and_valuesets(self) -> None:
        data_source = InMemoryDataSource()
        data_source.add_resource(observation("o1", "1234-5"))
        data_source.add_valueset("http://example.org/vs/vitals", [CQLCode(code="1234-5", system=LOINC)])

        data_source.clear()

        assert data_source.retrieve("Observation") == []
        assert data_source.resolve_reference("Observation/o1") is None
        assert data_source.get_valueset_codes("http://example.org/vs/vitals") is None


class TestBundleDataSource:
    """Tests for the Bundle-backed data sources."""

    def test_a_bundle_loads_every_entry_resource(self) -> None:
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1"}},
                {"resource": observation("o1", "1234-5", subject="Patient/p1")},
            ],
        }
        data_source = BundleDataSource(bundle)

        assert sorted(data_source.resources) == ["Observation", "Patient"]
        assert [r["id"] for r in data_source.retrieve("Observation")] == ["o1"]

    def test_entries_without_a_resource_are_skipped(self) -> None:
        bundle = {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [
                {"search": {"mode": "match"}},
                {"resource": {"resourceType": "Patient", "id": "p1"}},
            ],
        }
        data_source = BundleDataSource(bundle)

        assert [r["id"] for r in data_source.retrieve("Patient")] == ["p1"]

    def test_a_bundle_without_entries_loads_nothing(self) -> None:
        data_source = BundleDataSource({"resourceType": "Bundle", "type": "collection"})

        assert data_source.resources == {}

    def test_a_non_bundle_payload_loads_as_a_single_resource(self) -> None:
        data_source = BundleDataSource(observation("o1", "1234-5"))

        assert [r["id"] for r in data_source.retrieve("Observation")] == ["o1"]

    def test_an_omitted_bundle_leaves_the_data_source_empty(self) -> None:
        data_source = BundleDataSource()

        assert data_source.resources == {}
        assert data_source.resolve_reference("Patient/p1") is None

    def test_valuesets_reach_the_backing_store(self) -> None:
        data_source = BundleDataSource({"resourceType": "Bundle", "entry": [{"resource": observation("o1", "1234-5")}]})
        codes = [CQLCode(code="1234-5", system=LOINC)]
        data_source.add_valueset("http://example.org/vs/vitals", codes)

        assert data_source.get_valueset_codes("http://example.org/vs/vitals") == codes
        assert data_source.get_valueset_codes("http://example.org/vs/other") is None
        retrieved = data_source.retrieve("Observation", code_path="code", valueset="http://example.org/vs/vitals")
        assert [r["id"] for r in retrieved] == ["o1"]

    def test_reference_resolution_reads_the_bundle(self) -> None:
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {"resourceType": "Patient", "id": "p1"}}],
        }
        data_source = BundleDataSource(bundle)

        assert data_source.resolve_reference("Patient/p1") == {"resourceType": "Patient", "id": "p1"}
        assert data_source.resolve_reference("Patient/p2") is None


class TestPatientBundleDataSource:
    """Tests for the patient-scoped bundle data source."""

    def test_the_first_patient_in_the_bundle_becomes_the_context(self) -> None:
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1"}},
                {"resource": {"resourceType": "Patient", "id": "p2"}},
                {"resource": observation("o1", "1234-5", subject="Patient/p1")},
                {"resource": observation("o2", "1234-5", subject="Patient/p2")},
            ],
        }
        data_source = PatientBundleDataSource(bundle)

        assert data_source.patient is not None
        assert data_source.patient["id"] == "p1"
        assert [r["id"] for r in data_source.retrieve("Observation")] == ["o1"]

    def test_an_explicit_context_wins_over_the_bundle_patient(self) -> None:
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1"}},
                {"resource": observation("o1", "1234-5", subject="Patient/p1")},
                {"resource": observation("o2", "1234-5", subject="Patient/p2")},
            ],
        }
        data_source = PatientBundleDataSource(bundle)
        context = PatientContext(resource={"resourceType": "Patient", "id": "p2"})

        assert [r["id"] for r in data_source.retrieve("Observation", context=context)] == ["o2"]

    def test_a_bundle_without_a_patient_leaves_the_patient_unset(self) -> None:
        bundle = {"resourceType": "Bundle", "entry": [{"resource": observation("o1", "1234-5")}]}
        data_source = PatientBundleDataSource(bundle)

        assert data_source.patient is None
        assert [r["id"] for r in data_source.retrieve("Observation")] == ["o1"]

    def test_an_omitted_bundle_leaves_the_patient_unset(self) -> None:
        data_source = PatientBundleDataSource()

        assert data_source.patient is None
        assert data_source.retrieve("Observation") == []
