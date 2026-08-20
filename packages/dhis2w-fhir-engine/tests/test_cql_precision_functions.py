"""Tests for CQL Precision and Boundary functions.

Tests for:
- Precision(value) - get precision of a value
- LowBoundary(value, precision) - get lowest possible value
- HighBoundary(value, precision) - get highest possible value
- MinValue(type) - get minimum representable value
- MaxValue(type) - get maximum representable value
"""

from decimal import Decimal

from dhis2w_fhir_engine.engine.cql import evaluate
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime, Quantity

# =============================================================================
# Precision Tests
# =============================================================================


class TestPrecisionDecimal:
    """Test Precision function for decimal values."""

    def test_precision_integer(self) -> None:
        """Integer has 0 decimal places."""
        assert evaluate("Precision(42)") == 0

    def test_precision_decimal_one_place(self) -> None:
        """Decimal with one decimal place."""
        assert evaluate("Precision(3.1)") == 1

    def test_precision_decimal_two_places(self) -> None:
        """Decimal with two decimal places."""
        assert evaluate("Precision(3.14)") == 2

    def test_precision_decimal_many_places(self) -> None:
        """Decimal with many decimal places."""
        assert evaluate("Precision(3.14159265)") == 8

    def test_precision_null(self) -> None:
        """Null input returns null."""
        assert evaluate("Precision(null)") is None


class TestPrecisionDate:
    """Test Precision function for date values."""

    def test_precision_date_full(self) -> None:
        """Full date precision."""
        result = evaluate("Precision(@2024-03-15)")
        assert result == 8  # Day precision

    def test_precision_date_year_month(self) -> None:
        """Year-month precision."""
        result = evaluate("Precision(@2024-03)")
        assert result == 6  # Month precision

    def test_precision_date_year_only(self) -> None:
        """Year-only precision."""
        result = evaluate("Precision(@2024)")
        assert result == 4  # Year precision


class TestPrecisionDateTime:
    """Test Precision function for datetime values."""

    def test_precision_datetime_full(self) -> None:
        """Full datetime precision with milliseconds."""
        result = evaluate("Precision(@2024-03-15T10:30:45.123)")
        assert result == 17  # Millisecond precision

    def test_precision_datetime_second(self) -> None:
        """DateTime with second precision."""
        result = evaluate("Precision(@2024-03-15T10:30:45)")
        assert result == 14  # Second precision

    def test_precision_datetime_minute(self) -> None:
        """DateTime with minute precision."""
        result = evaluate("Precision(@2024-03-15T10:30)")
        assert result == 12  # Minute precision


class TestPrecisionTime:
    """Test Precision function for time values."""

    def test_precision_time_full(self) -> None:
        """Full time precision with milliseconds."""
        result = evaluate("Precision(@T10:30:45.123)")
        assert result == 9  # Millisecond precision

    def test_precision_time_second(self) -> None:
        """Time with second precision."""
        result = evaluate("Precision(@T10:30:45)")
        assert result == 6  # Second precision

    def test_precision_time_minute(self) -> None:
        """Time with minute precision."""
        result = evaluate("Precision(@T10:30)")
        assert result == 4  # Minute precision


# =============================================================================
# LowBoundary Tests
# =============================================================================


class TestLowBoundaryDecimal:
    """Test LowBoundary function for decimal values."""

    def test_low_boundary_decimal(self) -> None:
        """Low boundary for decimal at precision 2."""
        result = evaluate("LowBoundary(3.14, 2)")
        assert result == Decimal("3.14")

    def test_low_boundary_integer(self) -> None:
        """Low boundary for integer at precision 0."""
        result = evaluate("LowBoundary(42, 0)")
        assert result == Decimal("42")

    def test_low_boundary_null(self) -> None:
        """Null input returns null."""
        assert evaluate("LowBoundary(null, 2)") is None


class TestLowBoundaryDate:
    """Test LowBoundary function for date values."""

    def test_low_boundary_year_only(self) -> None:
        """Low boundary for year-only date fills in Jan 1."""
        result = evaluate("LowBoundary(@2024, 4)")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_low_boundary_year_month(self) -> None:
        """Low boundary for year-month date fills in day 1."""
        result = evaluate("LowBoundary(@2024-03, 6)")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 1


class TestLowBoundaryDateTime:
    """Test LowBoundary function for datetime values."""

    def test_low_boundary_datetime_date_only(self) -> None:
        """Low boundary for datetime with date only."""
        result = evaluate("LowBoundary(@2024-03-15T00:00:00, 8)")
        assert isinstance(result, FHIRDateTime)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0


# =============================================================================
# HighBoundary Tests
# =============================================================================


class TestHighBoundaryDecimal:
    """Test HighBoundary function for decimal values."""

    def test_high_boundary_decimal(self) -> None:
        """High boundary for decimal."""
        result = evaluate("HighBoundary(3.14, 2)")
        assert isinstance(result, Decimal)

    def test_high_boundary_null(self) -> None:
        """Null input returns null."""
        assert evaluate("HighBoundary(null, 2)") is None


class TestHighBoundaryDate:
    """Test HighBoundary function for date values."""

    def test_high_boundary_year_only(self) -> None:
        """High boundary for year-only date fills in Dec 31."""
        result = evaluate("HighBoundary(@2024, 4)")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 12
        assert result.day == 31

    def test_high_boundary_year_month_31_days(self) -> None:
        """High boundary for month with 31 days."""
        result = evaluate("HighBoundary(@2024-01, 6)")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 31

    def test_high_boundary_year_month_30_days(self) -> None:
        """High boundary for month with 30 days."""
        result = evaluate("HighBoundary(@2024-04, 6)")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 4
        assert result.day == 30

    def test_high_boundary_february_leap_year(self) -> None:
        """High boundary for February in leap year."""
        result = evaluate("HighBoundary(@2024-02, 6)")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 2
        assert result.day == 29  # Leap year

    def test_high_boundary_february_non_leap(self) -> None:
        """High boundary for February in non-leap year."""
        result = evaluate("HighBoundary(@2023-02, 6)")
        assert isinstance(result, FHIRDate)
        assert result.year == 2023
        assert result.month == 2
        assert result.day == 28


class TestHighBoundaryDateTime:
    """Test HighBoundary function for datetime values."""

    def test_high_boundary_datetime_with_time(self) -> None:
        """High boundary for datetime with time keeps time, fills in millisecond."""
        result = evaluate("HighBoundary(@2024-03-15T10:30:45, 14)")
        assert isinstance(result, FHIRDateTime)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15
        assert result.hour == 10  # Specified, kept
        assert result.minute == 30  # Specified, kept
        assert result.second == 45  # Specified, kept
        assert result.millisecond == 999  # Unspecified, filled with max


# =============================================================================
# MinValue Tests
# =============================================================================


class TestMinValue:
    """Test MinValue function."""

    def test_min_value_integer(self) -> None:
        """MinValue for Integer."""
        result = evaluate("MinValue('Integer')")
        assert isinstance(result, int)
        assert result < 0

    def test_min_value_decimal(self) -> None:
        """MinValue for Decimal."""
        result = evaluate("MinValue('Decimal')")
        assert isinstance(result, Decimal)
        assert result < 0

    def test_min_value_date(self) -> None:
        """MinValue for Date."""
        result = evaluate("MinValue('Date')")
        assert isinstance(result, FHIRDate)
        assert result.year == 1
        assert result.month == 1
        assert result.day == 1

    def test_min_value_datetime(self) -> None:
        """MinValue for DateTime."""
        result = evaluate("MinValue('DateTime')")
        assert isinstance(result, FHIRDateTime)
        assert result.year == 1
        assert result.hour == 0

    def test_min_value_time(self) -> None:
        """MinValue for Time."""
        result = evaluate("MinValue('Time')")
        assert isinstance(result, FHIRTime)
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0

    def test_min_value_quantity(self) -> None:
        """MinValue for Quantity."""
        result = evaluate("MinValue('Quantity')")
        assert isinstance(result, Quantity)
        assert result.value < 0

    def test_min_value_unknown_type(self) -> None:
        """MinValue for unknown type returns null."""
        result = evaluate("MinValue('Unknown')")
        assert result is None


# =============================================================================
# MaxValue Tests
# =============================================================================


class TestMaxValue:
    """Test MaxValue function."""

    def test_max_value_integer(self) -> None:
        """MaxValue for Integer."""
        result = evaluate("MaxValue('Integer')")
        assert isinstance(result, int)
        assert result > 0

    def test_max_value_decimal(self) -> None:
        """MaxValue for Decimal."""
        result = evaluate("MaxValue('Decimal')")
        assert isinstance(result, Decimal)
        assert result > 0

    def test_max_value_date(self) -> None:
        """MaxValue for Date."""
        result = evaluate("MaxValue('Date')")
        assert isinstance(result, FHIRDate)
        assert result.year == 9999
        assert result.month == 12
        assert result.day == 31

    def test_max_value_datetime(self) -> None:
        """MaxValue for DateTime."""
        result = evaluate("MaxValue('DateTime')")
        assert isinstance(result, FHIRDateTime)
        assert result.year == 9999
        assert result.hour == 23
        assert result.minute == 59

    def test_max_value_time(self) -> None:
        """MaxValue for Time."""
        result = evaluate("MaxValue('Time')")
        assert isinstance(result, FHIRTime)
        assert result.hour == 23
        assert result.minute == 59
        assert result.second == 59

    def test_max_value_quantity(self) -> None:
        """MaxValue for Quantity."""
        result = evaluate("MaxValue('Quantity')")
        assert isinstance(result, Quantity)
        assert result.value > 0

    def test_max_value_unknown_type(self) -> None:
        """MaxValue for unknown type returns null."""
        result = evaluate("MaxValue('Unknown')")
        assert result is None


# =============================================================================
# Combined/Integration Tests
# =============================================================================


class TestPrecisionBoundaryIntegration:
    """Integration tests combining precision and boundary functions."""

    def test_precision_of_low_boundary(self) -> None:
        """Precision of low boundary date."""
        result = evaluate("Precision(LowBoundary(@2024, 4))")
        # Low boundary fills in all components, so full day precision
        assert result == 8

    def test_precision_of_high_boundary(self) -> None:
        """Precision of high boundary date."""
        result = evaluate("Precision(HighBoundary(@2024, 4))")
        assert result == 8
