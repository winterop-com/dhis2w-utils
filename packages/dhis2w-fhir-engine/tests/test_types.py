"""Tests for FHIR types module."""

from datetime import UTC, date, timedelta, timezone
from decimal import Decimal

from dhis2w_fhir_engine.engine.types import (
    FHIRDate,
    FHIRDateTime,
    FHIRPathType,
    FHIRTime,
    Quantity,
    get_fhirpath_type,
    is_truthy,
    singleton,
    to_collection,
)


class TestFHIRDate:
    """Tests for FHIRDate type."""

    def test_parse_full_date(self) -> None:
        """Test parsing YYYY-MM-DD format."""
        d = FHIRDate.parse("2024-03-15")
        assert d is not None
        assert d.year == 2024
        assert d.month == 3
        assert d.day == 15

    def test_parse_year_month(self) -> None:
        """Test parsing YYYY-MM format."""
        d = FHIRDate.parse("2024-03")
        assert d is not None
        assert d.year == 2024
        assert d.month == 3
        assert d.day is None

    def test_parse_year_only(self) -> None:
        """Test parsing YYYY format."""
        d = FHIRDate.parse("2024")
        assert d is not None
        assert d.year == 2024
        assert d.month is None
        assert d.day is None

    def test_parse_invalid(self) -> None:
        """Test parsing invalid date strings."""
        assert FHIRDate.parse("not-a-date") is None
        assert FHIRDate.parse("2024/03/15") is None
        assert FHIRDate.parse("03-15-2024") is None

    def test_to_date_full(self) -> None:
        """Test conversion to Python date with full precision."""
        d = FHIRDate(year=2024, month=3, day=15)
        assert d.to_date() == date(2024, 3, 15)

    def test_to_date_partial(self) -> None:
        """Test conversion to Python date with partial precision returns None."""
        d = FHIRDate(year=2024, month=3)
        assert d.to_date() is None

        d = FHIRDate(year=2024)
        assert d.to_date() is None

    def test_str_full_date(self) -> None:
        """Test string representation of full date."""
        d = FHIRDate(year=2024, month=3, day=15)
        assert str(d) == "2024-03-15"

    def test_str_year_month(self) -> None:
        """Test string representation of year-month."""
        d = FHIRDate(year=2024, month=3)
        assert str(d) == "2024-03"

    def test_str_year_only(self) -> None:
        """Test string representation of year only."""
        d = FHIRDate(year=2024)
        assert str(d) == "2024"

    def test_equality(self) -> None:
        """Test date equality."""
        d1 = FHIRDate(year=2024, month=3, day=15)
        d2 = FHIRDate(year=2024, month=3, day=15)
        d3 = FHIRDate(year=2024, month=3, day=16)
        assert d1 == d2
        assert d1 != d3
        assert d1 != "2024-03-15"

    def test_hash(self) -> None:
        """Test date hashing for set operations."""
        d1 = FHIRDate(year=2024, month=3, day=15)
        d2 = FHIRDate(year=2024, month=3, day=15)
        assert hash(d1) == hash(d2)
        s = {d1, d2}
        assert len(s) == 1

    def test_lt_same_year_different_month(self) -> None:
        """Test less than comparison with same year."""
        d1 = FHIRDate(year=2024, month=2, day=1)
        d2 = FHIRDate(year=2024, month=3, day=1)
        assert d1 < d2
        assert not d2 < d1

    def test_lt_different_year(self) -> None:
        """Test less than comparison with different years."""
        d1 = FHIRDate(year=2023, month=12, day=31)
        d2 = FHIRDate(year=2024, month=1, day=1)
        assert d1 < d2

    def test_lt_same_year_month_different_day(self) -> None:
        """Test less than comparison with same year and month."""
        d1 = FHIRDate(year=2024, month=3, day=14)
        d2 = FHIRDate(year=2024, month=3, day=15)
        assert d1 < d2

    def test_lt_incomparable_precision_month(self) -> None:
        """Test less than returns False for incomparable month precision."""
        d1 = FHIRDate(year=2024)
        d2 = FHIRDate(year=2024, month=3)
        assert not (d1 < d2)

    def test_lt_incomparable_precision_day(self) -> None:
        """Test less than returns False for incomparable day precision."""
        d1 = FHIRDate(year=2024, month=3)
        d2 = FHIRDate(year=2024, month=3, day=15)
        assert not (d1 < d2)


class TestFHIRDateTime:
    """Tests for FHIRDateTime type."""

    def test_parse_full_datetime(self) -> None:
        """Test parsing full datetime with timezone."""
        dt = FHIRDateTime.parse("2024-03-15T10:30:45.123Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 3
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.second == 45
        assert dt.millisecond == 123
        assert dt.tz_offset == "Z"

    def test_parse_with_at_prefix(self) -> None:
        """Test parsing FHIRPath literal with @ prefix."""
        dt = FHIRDateTime.parse("@2024-03-15T10:30:00")
        assert dt is not None
        assert dt.year == 2024

    def test_parse_with_positive_offset(self) -> None:
        """Test parsing datetime with positive timezone offset."""
        dt = FHIRDateTime.parse("2024-03-15T10:30:00+05:30")
        assert dt is not None
        assert dt.tz_offset == "+05:30"

    def test_parse_with_negative_offset(self) -> None:
        """Test parsing datetime with negative timezone offset."""
        dt = FHIRDateTime.parse("2024-03-15T10:30:00-08:00")
        assert dt is not None
        assert dt.tz_offset == "-08:00"

    def test_parse_date_only(self) -> None:
        """Test parsing date-only string."""
        dt = FHIRDateTime.parse("2024-03-15")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 3
        assert dt.day == 15
        assert dt.hour is None

    def test_parse_year_only(self) -> None:
        """Test parsing year-only string."""
        dt = FHIRDateTime.parse("2024")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month is None

    def test_parse_invalid(self) -> None:
        """Test parsing invalid datetime strings."""
        assert FHIRDateTime.parse("invalid") is None
        assert FHIRDateTime.parse("2024/03/15") is None

    def test_to_datetime_full_utc(self) -> None:
        """Test conversion to Python datetime with UTC timezone."""
        dt = FHIRDateTime(year=2024, month=3, day=15, hour=10, minute=30, second=45, millisecond=123, tz_offset="Z")
        result = dt.to_datetime()
        assert result is not None
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 45
        assert result.tzinfo == UTC

    def test_to_datetime_positive_offset(self) -> None:
        """Test conversion with positive timezone offset."""
        dt = FHIRDateTime(year=2024, month=3, day=15, hour=10, minute=30, tz_offset="+05:30")
        result = dt.to_datetime()
        assert result is not None
        expected_tz = timezone(timedelta(hours=5, minutes=30))
        assert result.tzinfo == expected_tz

    def test_to_datetime_negative_offset(self) -> None:
        """Test conversion with negative timezone offset."""
        dt = FHIRDateTime(year=2024, month=3, day=15, hour=10, minute=30, tz_offset="-08:00")
        result = dt.to_datetime()
        assert result is not None
        expected_tz = timezone(timedelta(hours=-8, minutes=0))
        assert result.tzinfo == expected_tz

    def test_to_datetime_partial_returns_none(self) -> None:
        """Test conversion returns None for partial datetime."""
        dt = FHIRDateTime(year=2024)
        assert dt.to_datetime() is None

        dt = FHIRDateTime(year=2024, month=3)
        assert dt.to_datetime() is None

    def test_str_full(self) -> None:
        """Test string representation of full datetime."""
        dt = FHIRDateTime(year=2024, month=3, day=15, hour=10, minute=30, second=45, millisecond=123, tz_offset="Z")
        assert str(dt) == "2024-03-15T10:30:45.123Z"

    def test_str_partial(self) -> None:
        """Test string representation of partial datetime."""
        dt = FHIRDateTime(year=2024)
        assert str(dt) == "2024"

        dt = FHIRDateTime(year=2024, month=3)
        assert str(dt) == "2024-03"

        dt = FHIRDateTime(year=2024, month=3, day=15)
        assert str(dt) == "2024-03-15"

        dt = FHIRDateTime(year=2024, month=3, day=15, hour=10)
        assert str(dt) == "2024-03-15T10"

        dt = FHIRDateTime(year=2024, month=3, day=15, hour=10, minute=30)
        assert str(dt) == "2024-03-15T10:30"

        dt = FHIRDateTime(year=2024, month=3, day=15, hour=10, minute=30, second=45)
        assert str(dt) == "2024-03-15T10:30:45"

    def test_equality(self) -> None:
        """Test datetime equality."""
        dt1 = FHIRDateTime(year=2024, month=3, day=15, hour=10)
        dt2 = FHIRDateTime(year=2024, month=3, day=15, hour=10)
        dt3 = FHIRDateTime(year=2024, month=3, day=15, hour=11)
        assert dt1 == dt2
        assert dt1 != dt3
        assert dt1 != "2024-03-15T10"

    def test_hash(self) -> None:
        """Test datetime hashing."""
        dt1 = FHIRDateTime(year=2024, month=3, day=15)
        dt2 = FHIRDateTime(year=2024, month=3, day=15)
        assert hash(dt1) == hash(dt2)


class TestFHIRTime:
    """Tests for FHIRTime type."""

    def test_parse_full_time(self) -> None:
        """Test parsing full time with milliseconds."""
        t = FHIRTime.parse("10:30:45.123")
        assert t is not None
        assert t.hour == 10
        assert t.minute == 30
        assert t.second == 45
        assert t.millisecond == 123

    def test_parse_with_t_prefix(self) -> None:
        """Test parsing time with T prefix."""
        t = FHIRTime.parse("T10:30:45")
        assert t is not None
        assert t.hour == 10

    def test_parse_hour_minute(self) -> None:
        """Test parsing hour:minute format."""
        t = FHIRTime.parse("10:30")
        assert t is not None
        assert t.hour == 10
        assert t.minute == 30
        assert t.second is None

    def test_parse_hour_only(self) -> None:
        """Test parsing hour-only format."""
        t = FHIRTime.parse("10")
        assert t is not None
        assert t.hour == 10
        assert t.minute is None

    def test_parse_invalid(self) -> None:
        """Test parsing invalid time strings."""
        assert FHIRTime.parse("invalid") is None
        assert FHIRTime.parse("abc:00:00") is None

    def test_to_time(self) -> None:
        """Test conversion to Python time."""
        t = FHIRTime(hour=10, minute=30, second=45, millisecond=123)
        result = t.to_time()
        assert result is not None
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 45

    def test_to_time_partial(self) -> None:
        """Test conversion with partial precision."""
        t = FHIRTime(hour=10)
        result = t.to_time()
        assert result is not None
        assert result.hour == 10
        assert result.minute == 0
        assert result.second == 0

    def test_str_full(self) -> None:
        """Test string representation of full time."""
        t = FHIRTime(hour=10, minute=30, second=45, millisecond=123)
        assert str(t) == "10:30:45.123"

    def test_str_partial(self) -> None:
        """Test string representation of partial time."""
        t = FHIRTime(hour=10)
        assert str(t) == "10"

        t = FHIRTime(hour=10, minute=30)
        assert str(t) == "10:30"

        t = FHIRTime(hour=10, minute=30, second=45)
        assert str(t) == "10:30:45"

    def test_equality(self) -> None:
        """Test time equality."""
        t1 = FHIRTime(hour=10, minute=30)
        t2 = FHIRTime(hour=10, minute=30)
        t3 = FHIRTime(hour=10, minute=31)
        assert t1 == t2
        assert t1 != t3
        assert t1 != "10:30"

    def test_hash(self) -> None:
        """Test time hashing."""
        t1 = FHIRTime(hour=10, minute=30)
        t2 = FHIRTime(hour=10, minute=30)
        assert hash(t1) == hash(t2)


class TestQuantity:
    """Tests for Quantity type."""

    def test_creation(self) -> None:
        """Test quantity creation."""
        q = Quantity(value=Decimal("10.5"), unit="mg")
        assert q.value == Decimal("10.5")
        assert q.unit == "mg"

    def test_equality(self) -> None:
        """Test quantity equality."""
        q1 = Quantity(value=Decimal("10"), unit="mg")
        q2 = Quantity(value=Decimal("10"), unit="mg")
        q3 = Quantity(value=Decimal("10"), unit="g")
        assert q1 == q2
        assert q1 != q3
        assert q1 != "10 mg"

    def test_hash(self) -> None:
        """Test quantity hashing."""
        q1 = Quantity(value=Decimal("10"), unit="mg")
        q2 = Quantity(value=Decimal("10"), unit="mg")
        assert hash(q1) == hash(q2)

    def test_str(self) -> None:
        """Test quantity string representation."""
        q = Quantity(value=Decimal("10.5"), unit="mg")
        assert str(q) == "10.5 'mg'"


class TestGetFHIRPathType:
    """Tests for get_fhirpath_type function."""

    def test_null(self) -> None:
        """Test null type detection."""
        assert get_fhirpath_type(None) == FHIRPathType.NULL

    def test_boolean(self) -> None:
        """Test boolean type detection."""
        assert get_fhirpath_type(True) == FHIRPathType.BOOLEAN
        assert get_fhirpath_type(False) == FHIRPathType.BOOLEAN

    def test_integer(self) -> None:
        """Test integer type detection."""
        assert get_fhirpath_type(42) == FHIRPathType.INTEGER
        assert get_fhirpath_type(-1) == FHIRPathType.INTEGER
        assert get_fhirpath_type(0) == FHIRPathType.INTEGER

    def test_decimal(self) -> None:
        """Test decimal type detection."""
        assert get_fhirpath_type(3.14) == FHIRPathType.DECIMAL
        assert get_fhirpath_type(Decimal("10.5")) == FHIRPathType.DECIMAL

    def test_string(self) -> None:
        """Test string type detection."""
        assert get_fhirpath_type("hello") == FHIRPathType.STRING
        assert get_fhirpath_type("") == FHIRPathType.STRING

    def test_quantity(self) -> None:
        """Test quantity type detection."""
        q = Quantity(value=Decimal("10"), unit="mg")
        assert get_fhirpath_type(q) == FHIRPathType.QUANTITY

    def test_resource(self) -> None:
        """Test resource type detection."""
        resource = {"resourceType": "Patient", "id": "123"}
        assert get_fhirpath_type(resource) == FHIRPathType.RESOURCE

    def test_element(self) -> None:
        """Test element type detection."""
        element = {"family": "Smith", "given": ["John"]}
        assert get_fhirpath_type(element) == FHIRPathType.ELEMENT

    def test_list_as_element(self) -> None:
        """Test that lists are treated as elements."""
        assert get_fhirpath_type([1, 2, 3]) == FHIRPathType.ELEMENT


class TestIsTruthy:
    """Tests for is_truthy function."""

    def test_none_is_falsy(self) -> None:
        """Test None is falsy."""
        assert is_truthy(None) is False

    def test_empty_list_is_falsy(self) -> None:
        """Test empty list is falsy."""
        assert is_truthy([]) is False

    def test_single_true_is_truthy(self) -> None:
        """Test single True is truthy."""
        assert is_truthy(True) is True
        assert is_truthy([True]) is True

    def test_single_false_is_falsy(self) -> None:
        """Test single False is falsy."""
        assert is_truthy(False) is False
        assert is_truthy([False]) is False

    def test_non_boolean_singleton_is_truthy(self) -> None:
        """Test non-boolean singleton is truthy."""
        assert is_truthy(42) is True
        assert is_truthy("hello") is True
        assert is_truthy([42]) is True

    def test_multiple_items_is_truthy(self) -> None:
        """Test collection with multiple items is truthy."""
        assert is_truthy([1, 2, 3]) is True
        assert is_truthy([False, False]) is True


class TestToCollection:
    """Tests for to_collection function."""

    def test_none_returns_empty(self) -> None:
        """Test None returns empty list."""
        assert to_collection(None) == []

    def test_list_returned_as_is(self) -> None:
        """Test list is returned unchanged."""
        lst = [1, 2, 3]
        assert to_collection(lst) is lst

    def test_singleton_wrapped(self) -> None:
        """Test singleton value is wrapped in list."""
        assert to_collection(42) == [42]
        assert to_collection("hello") == ["hello"]


class TestSingleton:
    """Tests for singleton function."""

    def test_empty_returns_none(self) -> None:
        """Test empty list returns None."""
        assert singleton([]) is None

    def test_single_item_unwrapped(self) -> None:
        """Test single item is unwrapped."""
        assert singleton([42]) == 42
        assert singleton(["hello"]) == "hello"

    def test_multiple_items_returns_list(self) -> None:
        """Test multiple items returns original list."""
        lst = [1, 2, 3]
        assert singleton(lst) is lst
