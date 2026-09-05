"""A Bundle entry's `fullUrl` is one of the identities its resource answers to.

The same four resources written three ways - relative references, absolute entry URLs, and
`urn:uuid:` entry URLs, the spelling this repo's own document Bundles use - are one dataset, so
retrieval, reference resolution, patient scoping, and measure results agree across all three.
"""

from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql import CQLEvaluator, PatientContext
from dhis2w_fhir_engine.r4 import BundleDataSource, MeasureEvaluator

_ABSOLUTE_BASE = "http://example.org/fhir"
_PATIENT_URN = "urn:uuid:00000000-0000-0000-0000-000000000001"
_CONDITION_URN = "urn:uuid:00000000-0000-0000-0000-000000000002"
_OBSERVATION_URN = "urn:uuid:00000000-0000-0000-0000-000000000003"

_COUNTING_MEASURE = """
    library ObservationCount version '1.0'

    define "Initial Population":
        true

    define "Denominator":
        true

    define "Numerator":
        exists [Observation]
"""


def _resources(patient_reference: str) -> list[dict[str, Any]]:
    """The four resources of the dataset, with every subject named the given way."""
    return [
        {"resourceType": "Patient", "id": "Kj9HgT4mQpz", "gender": "female", "birthDate": "2024-06-01"},
        {
            "resourceType": "Condition",
            "id": "cond-1",
            "subject": {"reference": patient_reference},
            "code": {"coding": [{"system": "http://snomed.info/sct", "code": "1287211007"}]},
        },
        {
            "resourceType": "Observation",
            "id": "obs-1",
            "status": "final",
            "subject": {"reference": patient_reference},
            "code": {"coding": [{"system": "http://example.org/fhir/de", "code": "UXz7xuGCEhU"}]},
            "effectiveDateTime": "2024-06-02T00:00:00Z",
            "valueString": "3.2",
        },
        {
            "resourceType": "Observation",
            "id": "obs-2",
            "status": "final",
            "subject": {"reference": "Patient/someone-else"},
            "code": {"coding": [{"system": "http://example.org/fhir/de", "code": "UXz7xuGCEhU"}]},
            "effectiveDateTime": "2024-06-03T00:00:00Z",
            "valueString": "4.1",
        },
    ]


def _bundle(full_urls: list[str | None], patient_reference: str) -> dict[str, Any]:
    """A document Bundle carrying the four resources under the given entry identities."""
    entries: list[dict[str, Any]] = []
    for full_url, resource in zip(full_urls, _resources(patient_reference), strict=True):
        entry: dict[str, Any] = {"resource": resource}
        if full_url is not None:
            entry["fullUrl"] = full_url
        entries.append(entry)
    return {"resourceType": "Bundle", "type": "document", "entry": entries}


def _relative_bundle() -> dict[str, Any]:
    """The dataset with relative entry identities and relative subject references."""
    return _bundle(
        ["Patient/Kj9HgT4mQpz", "Condition/cond-1", "Observation/obs-1", "Observation/obs-2"],
        "Patient/Kj9HgT4mQpz",
    )


def _absolute_bundle() -> dict[str, Any]:
    """The dataset with absolute entry identities, whose subject references spell the same URL."""
    return _bundle(
        [
            f"{_ABSOLUTE_BASE}/Patient/Kj9HgT4mQpz",
            f"{_ABSOLUTE_BASE}/Condition/cond-1",
            f"{_ABSOLUTE_BASE}/Observation/obs-1",
            f"{_ABSOLUTE_BASE}/Observation/obs-2",
        ],
        f"{_ABSOLUTE_BASE}/Patient/Kj9HgT4mQpz",
    )


def _urn_bundle() -> dict[str, Any]:
    """The dataset in the shape this repo's document Bundles emit: `urn:uuid:` entry identities."""
    return _bundle(
        [
            _PATIENT_URN,
            _CONDITION_URN,
            _OBSERVATION_URN,
            "urn:uuid:00000000-0000-0000-0000-000000000004",
        ],
        _PATIENT_URN,
    )


@pytest.fixture(params=["relative", "absolute", "urn"])
def data_source(request: pytest.FixtureRequest) -> BundleDataSource:
    """One data source per spelling of the same dataset."""
    builders = {"relative": _relative_bundle, "absolute": _absolute_bundle, "urn": _urn_bundle}
    return BundleDataSource(builders[str(request.param)]())


def _patient_context(data_source: BundleDataSource) -> PatientContext:
    """The context naming the dataset's patient."""
    return PatientContext(resource=data_source.retrieve("Patient")[0])


class TestUnscopedRetrieval:
    """Every spelling holds the same resources."""

    def test_every_observation_is_retrieved(self, data_source: BundleDataSource) -> None:
        assert sorted(o["id"] for o in data_source.retrieve("Observation")) == ["obs-1", "obs-2"]

    def test_every_condition_is_retrieved(self, data_source: BundleDataSource) -> None:
        assert [c["id"] for c in data_source.retrieve("Condition")] == ["cond-1"]


class TestReferenceResolution:
    """A resource answers to `Type/id` and to the identity its Bundle entry gave it."""

    def test_the_canonical_reference_resolves(self, data_source: BundleDataSource) -> None:
        resolved = data_source.resolve_reference("Observation/obs-1")
        assert resolved is not None
        assert resolved["valueString"] == "3.2"

    def test_the_entry_identity_resolves(self, data_source: BundleDataSource) -> None:
        subject = data_source.retrieve("Observation")[0]["subject"]["reference"]
        resolved = data_source.resolve_reference(subject)
        assert resolved is not None
        assert resolved["resourceType"] == "Patient"
        assert resolved["id"] == "Kj9HgT4mQpz"

    def test_an_unknown_reference_resolves_to_nothing(self, data_source: BundleDataSource) -> None:
        assert data_source.resolve_reference("Observation/obs-99") is None


class TestPatientScopedRetrieval:
    """A patient context narrows to that person, whichever spelling the subject reference uses."""

    def test_only_the_context_patients_observations_are_retrieved(self, data_source: BundleDataSource) -> None:
        scoped = data_source.retrieve("Observation", context=_patient_context(data_source))
        assert [o["id"] for o in scoped] == ["obs-1"]

    def test_the_context_patients_condition_is_retrieved(self, data_source: BundleDataSource) -> None:
        scoped = data_source.retrieve("Condition", context=_patient_context(data_source))
        assert [c["id"] for c in scoped] == ["cond-1"]

    def test_a_cql_retrieve_reads_the_same_scope(self, data_source: BundleDataSource) -> None:
        evaluator = CQLEvaluator(data_source=data_source)
        patient = data_source.retrieve("Patient")[0]
        assert evaluator.evaluate_expression("Count([Observation])", resource=patient) == 1


class TestMeasureResults:
    """A measure counts the same numerator across all three spellings."""

    def test_the_patient_is_in_the_numerator(self, data_source: BundleDataSource) -> None:
        measure_evaluator = MeasureEvaluator(data_source=data_source)
        measure_evaluator.load_measure(_COUNTING_MEASURE)
        report = measure_evaluator.evaluate_population(data_source.retrieve("Patient"))
        populations = report.groups[0].populations
        assert populations["initial-population"].count == 1
        assert populations["numerator"].count == 1


def test_the_three_spellings_agree_on_every_answer() -> None:
    """The three bundles are one dataset, so retrieval and scoping answer identically."""
    sources = [BundleDataSource(build()) for build in (_relative_bundle, _absolute_bundle, _urn_bundle)]
    unscoped = [sorted(o["id"] for o in source.retrieve("Observation")) for source in sources]
    scoped = [
        sorted(o["id"] for o in source.retrieve("Observation", context=_patient_context(source))) for source in sources
    ]
    assert unscoped[0] == unscoped[1] == unscoped[2]
    assert scoped[0] == scoped[1] == scoped[2] == ["obs-1"]
