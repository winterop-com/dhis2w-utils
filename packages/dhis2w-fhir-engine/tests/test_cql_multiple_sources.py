"""Tests for CQL multiple query sources (cross join).

Tests cover:
- Two source cross join
- Three or more sources
- Cross join with where clause filtering
- Cross join with return clause
- Empty source handling
- Cross join with FHIR Retrieve
"""

from typing import Any

from dhis2w_fhir_engine.engine.cql import CQLEvaluator
from dhis2w_fhir_engine.engine.cql.context import CQLContext, DataSource


class MockDataSource(DataSource):
    """Mock data source for testing, backed by a map from resource type to resources."""

    def __init__(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.data = data

    def retrieve(
        self,
        resource_type: str,
        context: CQLContext | None = None,
        code_path: str | None = None,
        codes: list[Any] | None = None,
        valueset: str | None = None,
        date_path: str | None = None,
        date_range: Any | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Return every stored resource of the requested type."""
        return self.data.get(resource_type, [])

    def resolve_reference(self, reference: str) -> dict[str, Any] | None:
        """Resolve a "ResourceType/id" reference against the stored resources."""
        resource_type, _, resource_id = reference.partition("/")
        for resource in self.data.get(resource_type, []):
            if resource.get("id") == resource_id:
                return resource
        return None


class TestMultipleQuerySources:
    """Test CQL multiple query sources (cross join)."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.evaluator = CQLEvaluator()

    def test_two_source_cross_join(self) -> None:
        """Test basic cross join with two sources."""
        cql = """
        define Colors: { 'red', 'green', 'blue' }
        define Sizes: { 'S', 'M', 'L' }

        define Combinations:
            from Colors C, Sizes S
            return Tuple { color: C, size: S }
        """
        self.evaluator.compile(cql)
        result = self.evaluator.evaluate_definition("Combinations", {})

        # 3 colors * 3 sizes = 9 combinations
        assert len(result) == 9

        # Check some specific combinations exist
        colors = [r.elements["color"] for r in result]
        sizes = [r.elements["size"] for r in result]
        assert colors.count("red") == 3
        assert sizes.count("S") == 3

    def test_three_source_cross_join(self) -> None:
        """Test cross join with three sources."""
        cql = """
        define A: { 1, 2 }
        define B: { 'x', 'y' }
        define C: { true, false }

        define Triple:
            from A a, B b, C c
            return Tuple { num: a, letter: b, flag: c }
        """
        self.evaluator.compile(cql)
        result = self.evaluator.evaluate_definition("Triple", {})

        # 2 * 2 * 2 = 8 combinations
        assert len(result) == 8

    def test_cross_join_with_where(self) -> None:
        """Test cross join filtered by where clause."""
        cql = """
        define Numbers1: { 1, 2, 3 }
        define Numbers2: { 2, 4, 6 }

        define DoublePairs:
            from Numbers1 A, Numbers2 B
            where B = A * 2
            return Tuple { a: A, b: B }
        """
        self.evaluator.compile(cql)
        result = self.evaluator.evaluate_definition("DoublePairs", {})

        # Only pairs where B = A * 2: (1,2), (2,4), (3,6)
        assert len(result) == 3

        pairs = [(r.elements["a"], r.elements["b"]) for r in result]
        assert (1, 2) in pairs
        assert (2, 4) in pairs
        assert (3, 6) in pairs

    def test_cross_join_simple_return(self) -> None:
        """Test cross join with simple return (not tuple)."""
        cql = """
        define X: { 1, 2 }
        define Y: { 10, 20 }

        define Sums:
            from X x, Y y
            return x + y
        """
        self.evaluator.compile(cql)
        result = self.evaluator.evaluate_definition("Sums", {})

        # (1+10, 1+20, 2+10, 2+20) = (11, 21, 12, 22)
        assert sorted(result) == [11, 12, 21, 22]

    def test_cross_join_empty_first_source(self) -> None:
        """Test cross join when first source is empty."""
        cql = """
        define ListA: List<Integer> { }
        define ListB: { 1, 2, 3 }

        define Result:
            from ListA a, ListB b
            return Tuple { x: a, y: b }
        """
        self.evaluator.compile(cql)
        result = self.evaluator.evaluate_definition("Result", {})
        assert result == []

    def test_cross_join_empty_second_source(self) -> None:
        """Test cross join when second source is empty."""
        cql = """
        define A: { 1, 2, 3 }
        define B: List<Integer> { }

        define Result:
            from A a, B b
            return Tuple { x: a, y: b }
        """
        self.evaluator.compile(cql)
        result = self.evaluator.evaluate_definition("Result", {})
        assert result == []

    def test_cross_join_single_element_sources(self) -> None:
        """Test cross join with single element sources."""
        cql = """
        define A: { 42 }
        define B: { 'only' }

        define Result:
            from A a, B b
            return Tuple { num: a, str: b }
        """
        self.evaluator.compile(cql)
        result = self.evaluator.evaluate_definition("Result", {})
        assert len(result) == 1
        assert result[0].elements["num"] == 42
        assert result[0].elements["str"] == "only"

    def test_cross_join_with_let(self) -> None:
        """Test cross join with let clause."""
        cql = """
        define X: { 2, 3 }
        define Y: { 5, 7 }

        define Products:
            from X x, Y y
            let product: x * y
            return product
        """
        self.evaluator.compile(cql)
        result = self.evaluator.evaluate_definition("Products", {})

        # 2*5=10, 2*7=14, 3*5=15, 3*7=21
        assert sorted(result) == [10, 14, 15, 21]

    def test_cross_join_same_source_twice(self) -> None:
        """Test cross join using same source with different aliases."""
        cql = """
        define Numbers: { 1, 2, 3 }

        define OrderedPairs:
            from Numbers A, Numbers B
            where A < B
            return Tuple { smaller: A, larger: B }
        """
        self.evaluator.compile(cql)
        result = self.evaluator.evaluate_definition("OrderedPairs", {})

        # Pairs where A < B: (1,2), (1,3), (2,3)
        assert len(result) == 3
        pairs = [(r.elements["smaller"], r.elements["larger"]) for r in result]
        assert (1, 2) in pairs
        assert (1, 3) in pairs
        assert (2, 3) in pairs

    def test_cross_join_tuples(self) -> None:
        """Test cross join of tuple sources."""
        cql = """
        define People: {
            Tuple { name: 'Alice', age: 30 },
            Tuple { name: 'Bob', age: 25 }
        }
        define Jobs: {
            Tuple { title: 'Engineer' },
            Tuple { title: 'Designer' }
        }

        define Assignments:
            from People P, Jobs J
            return Tuple { person: P.name, job: J.title }
        """
        self.evaluator.compile(cql)
        result = self.evaluator.evaluate_definition("Assignments", {})

        # 2 people * 2 jobs = 4 assignments
        assert len(result) == 4


class TestMultipleSourcesFHIR:
    """Test multiple query sources with FHIR Retrieve."""

    def test_cross_join_fhir_resources(self) -> None:
        """Test cross join of FHIR resources."""
        data: dict[str, list[dict[str, Any]]] = {
            "Patient": [
                {"resourceType": "Patient", "id": "P1", "gender": "male"},
                {"resourceType": "Patient", "id": "P2", "gender": "female"},
            ],
            "Practitioner": [
                {"resourceType": "Practitioner", "id": "Dr1"},
                {"resourceType": "Practitioner", "id": "Dr2"},
            ],
        }
        data_source = MockDataSource(data)
        evaluator = CQLEvaluator(data_source=data_source)

        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        define PatientDoctorPairs:
            from [Patient] P, [Practitioner] D
            return Tuple { patient: P.id, doctor: D.id }
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("PatientDoctorPairs", {})

        # 2 patients * 2 doctors = 4 pairs
        assert len(result) == 4

    def test_filtered_cross_join_fhir(self) -> None:
        """Test filtered cross join of FHIR resources."""
        data: dict[str, list[dict[str, Any]]] = {
            "Patient": [
                {"resourceType": "Patient", "id": "P1", "managingOrganization": {"reference": "Organization/O1"}},
                {"resourceType": "Patient", "id": "P2", "managingOrganization": {"reference": "Organization/O2"}},
            ],
            "Organization": [
                {"resourceType": "Organization", "id": "O1", "name": "Hospital A"},
                {"resourceType": "Organization", "id": "O2", "name": "Hospital B"},
            ],
        }
        data_source = MockDataSource(data)
        evaluator = CQLEvaluator(data_source=data_source)

        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        define PatientOrganizations:
            from [Patient] P, [Organization] O
            where P.managingOrganization.reference = 'Organization/' + O.id
            return Tuple { patientId: P.id, orgName: O.name }
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("PatientOrganizations", {})

        # Only matching pairs
        assert len(result) == 2
        patient_orgs = {r.elements["patientId"]: r.elements["orgName"] for r in result}
        assert patient_orgs["P1"] == "Hospital A"
        assert patient_orgs["P2"] == "Hospital B"
