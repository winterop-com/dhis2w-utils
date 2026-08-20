"""Tests for ELM datetime operations including DurationBetween and Successor/Predecessor."""

from decimal import Decimal

from dhis2w_fhir_engine.engine.cql.context import CQLContext
from dhis2w_fhir_engine.engine.elm.visitor import ELMExpressionVisitor
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime


class TestDurationBetween:
    """Test DurationBetween operation."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.context = CQLContext()
        self.visitor = ELMExpressionVisitor(self.context)

    def test_duration_between_days_same_date(self) -> None:
        """Test duration between same dates is 0."""
        node = {
            "type": "DurationBetween",
            "precision": "Day",
            "operand": [
                {"type": "Date", "year": 2024, "month": 1, "day": 1},
                {"type": "Date", "year": 2024, "month": 1, "day": 1},
            ],
        }
        result = self.visitor.evaluate(node)
        assert result == 0

    def test_duration_between_days(self) -> None:
        """Test duration between dates in days."""
        node = {
            "type": "DurationBetween",
            "precision": "Day",
            "operand": [
                {"type": "Date", "year": 2024, "month": 1, "day": 1},
                {"type": "Date", "year": 2024, "month": 1, "day": 15},
            ],
        }
        result = self.visitor.evaluate(node)
        assert result == 14

    def test_duration_between_weeks(self) -> None:
        """Test duration between dates in weeks."""
        node = {
            "type": "DurationBetween",
            "precision": "Week",
            "operand": [
                {"type": "Date", "year": 2024, "month": 1, "day": 1},
                {"type": "Date", "year": 2024, "month": 1, "day": 22},
            ],
        }
        result = self.visitor.evaluate(node)
        assert result == 3  # 21 days = 3 weeks

    def test_duration_between_months(self) -> None:
        """Test duration between dates in months."""
        node = {
            "type": "DurationBetween",
            "precision": "Month",
            "operand": [
                {"type": "Date", "year": 2024, "month": 1, "day": 15},
                {"type": "Date", "year": 2024, "month": 4, "day": 15},
            ],
        }
        result = self.visitor.evaluate(node)
        assert result == 3

    def test_duration_between_months_incomplete(self) -> None:
        """Test duration between dates with incomplete months."""
        node = {
            "type": "DurationBetween",
            "precision": "Month",
            "operand": [
                {"type": "Date", "year": 2024, "month": 1, "day": 20},
                {"type": "Date", "year": 2024, "month": 4, "day": 15},
            ],
        }
        result = self.visitor.evaluate(node)
        assert result == 2  # Not 3 because we haven't reached the 20th

    def test_duration_between_years(self) -> None:
        """Test duration between dates in years."""
        node = {
            "type": "DurationBetween",
            "precision": "Year",
            "operand": [
                {"type": "Date", "year": 2020, "month": 6, "day": 15},
                {"type": "Date", "year": 2024, "month": 6, "day": 15},
            ],
        }
        result = self.visitor.evaluate(node)
        assert result == 4

    def test_duration_between_years_incomplete(self) -> None:
        """Test duration between dates with incomplete years."""
        node = {
            "type": "DurationBetween",
            "precision": "Year",
            "operand": [
                {"type": "Date", "year": 2020, "month": 6, "day": 15},
                {"type": "Date", "year": 2024, "month": 3, "day": 15},
            ],
        }
        result = self.visitor.evaluate(node)
        assert result == 3  # Not 4 because we haven't reached June

    def test_duration_between_hours(self) -> None:
        """Test duration between datetimes in hours."""
        node = {
            "type": "DurationBetween",
            "precision": "Hour",
            "operand": [
                {
                    "type": "DateTime",
                    "year": 2024,
                    "month": 1,
                    "day": 1,
                    "hour": 10,
                    "minute": 0,
                    "second": 0,
                },
                {
                    "type": "DateTime",
                    "year": 2024,
                    "month": 1,
                    "day": 1,
                    "hour": 15,
                    "minute": 30,
                    "second": 0,
                },
            ],
        }
        result = self.visitor.evaluate(node)
        assert result == 5

    def test_duration_between_null_operand(self) -> None:
        """Test duration between with null operand returns null."""
        node = {
            "type": "DurationBetween",
            "precision": "Day",
            "operand": [
                {"type": "Null"},
                {"type": "Date", "year": 2024, "month": 1, "day": 15},
            ],
        }
        result = self.visitor.evaluate(node)
        assert result is None


class TestSuccessorPredecessor:
    """Test Successor and Predecessor operations."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.context = CQLContext()
        self.visitor = ELMExpressionVisitor(self.context)

    def test_successor_integer(self) -> None:
        """Test successor of integer."""
        node = {
            "type": "Successor",
            "operand": {"type": "Literal", "valueType": "Integer", "value": "5"},
        }
        result = self.visitor.evaluate(node)
        assert result == 6

    def test_predecessor_integer(self) -> None:
        """Test predecessor of integer."""
        node = {
            "type": "Predecessor",
            "operand": {"type": "Literal", "valueType": "Integer", "value": "5"},
        }
        result = self.visitor.evaluate(node)
        assert result == 4

    def test_successor_decimal(self) -> None:
        """Test successor of decimal."""
        node = {
            "type": "Successor",
            "operand": {"type": "Literal", "valueType": "Decimal", "value": "1.5"},
        }
        result = self.visitor.evaluate(node)
        assert result == Decimal("1.5") + Decimal("0.00000001")

    def test_successor_date(self) -> None:
        """Test successor of date (next day)."""
        node = {
            "type": "Successor",
            "operand": {"type": "Date", "year": 2024, "month": 1, "day": 31},
        }
        result = self.visitor.evaluate(node)
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 2
        assert result.day == 1

    def test_predecessor_date(self) -> None:
        """Test predecessor of date (previous day)."""
        node = {
            "type": "Predecessor",
            "operand": {"type": "Date", "year": 2024, "month": 2, "day": 1},
        }
        result = self.visitor.evaluate(node)
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 31

    def test_successor_date_year_boundary(self) -> None:
        """Test successor of date across year boundary."""
        node = {
            "type": "Successor",
            "operand": {"type": "Date", "year": 2024, "month": 12, "day": 31},
        }
        result = self.visitor.evaluate(node)
        assert isinstance(result, FHIRDate)
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1

    def test_successor_datetime(self) -> None:
        """Test successor of datetime (next millisecond)."""
        # Test simple millisecond increment
        node = {
            "type": "Successor",
            "operand": {
                "type": "DateTime",
                "year": 2024,
                "month": 1,
                "day": 1,
                "hour": 12,
                "minute": 30,
                "second": 0,
                "millisecond": 0,
            },
        }
        result = self.visitor.evaluate(node)
        assert isinstance(result, FHIRDateTime)
        assert result.millisecond == 1

    def test_successor_partial_date(self) -> None:
        """Test successor of partial date (year-month only)."""
        node = {
            "type": "Successor",
            "operand": {"type": "Date", "year": 2024, "month": 12},
        }
        result = self.visitor.evaluate(node)
        assert isinstance(result, FHIRDate)
        assert result.year == 2025
        assert result.month == 1

    def test_successor_null(self) -> None:
        """Test successor of null returns null."""
        node = {
            "type": "Successor",
            "operand": {"type": "Null"},
        }
        result = self.visitor.evaluate(node)
        assert result is None


class TestDifferenceBetween:
    """Test DifferenceBetween operation (delegates to DurationBetween)."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.context = CQLContext()
        self.visitor = ELMExpressionVisitor(self.context)

    def test_difference_between_days(self) -> None:
        """Test difference between in days."""
        node = {
            "type": "DifferenceBetween",
            "precision": "Day",
            "operand": [
                {"type": "Date", "year": 2024, "month": 1, "day": 1},
                {"type": "Date", "year": 2024, "month": 1, "day": 10},
            ],
        }
        result = self.visitor.evaluate(node)
        assert result == 9
