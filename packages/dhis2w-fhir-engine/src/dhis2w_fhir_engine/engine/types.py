"""Type system shared between FHIRPath and CQL."""

import re
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class FHIRPathType(Enum):
    """FHIRPath primitive types."""

    BOOLEAN = "Boolean"
    STRING = "String"
    INTEGER = "Integer"
    DECIMAL = "Decimal"
    DATE = "Date"
    DATETIME = "DateTime"
    TIME = "Time"
    QUANTITY = "Quantity"

    # Complex types
    RESOURCE = "Resource"
    ELEMENT = "Element"

    # Special
    NULL = "Null"


class Quantity(BaseModel):
    """FHIRPath Quantity type with value and unit."""

    model_config = ConfigDict(frozen=True)

    value: Decimal
    unit: str
    # Original unit name for calendar durations (e.g., "week" instead of "wk")
    original_unit: str | None = None

    def _convert_for_comparison(self, other: "Quantity") -> tuple[Decimal, Decimal] | None:
        """Try to convert both quantities to comparable units."""
        if self.unit == other.unit:
            return (self.value, other.value)
        # Try unit conversion
        try:
            from dhis2w_fhir_engine.engine.units import convert_quantity

            converted = convert_quantity(other.value, other.unit, self.unit)
            if converted is not None:
                return (self.value, Decimal(str(converted)))
        except (ImportError, ValueError):
            pass
        return None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Quantity):
            result = self._convert_for_comparison(other)
            if result:
                return result[0] == result[1]
            return False
        return False

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        result = self._convert_for_comparison(other)
        if result:
            return result[0] < result[1]
        raise TypeError(f"Cannot compare quantities with incompatible units: {self.unit} and {other.unit}")

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        result = self._convert_for_comparison(other)
        if result:
            return result[0] <= result[1]
        raise TypeError(f"Cannot compare quantities with incompatible units: {self.unit} and {other.unit}")

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        result = self._convert_for_comparison(other)
        if result:
            return result[0] > result[1]
        raise TypeError(f"Cannot compare quantities with incompatible units: {self.unit} and {other.unit}")

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        result = self._convert_for_comparison(other)
        if result:
            return result[0] >= result[1]
        raise TypeError(f"Cannot compare quantities with incompatible units: {self.unit} and {other.unit}")

    def __hash__(self) -> int:
        return hash((self.value, self.unit))

    def __add__(self, other: object) -> "Quantity":
        """Add two quantities.

        Per CQL spec: Units must be the same for addition.
        """
        if not isinstance(other, Quantity):
            return NotImplemented
        if self.unit != other.unit:
            raise TypeError(f"Cannot add quantities with different units: {self.unit} and {other.unit}")
        return Quantity(value=self.value + other.value, unit=self.unit)

    def __sub__(self, other: object) -> "Quantity":
        """Subtract two quantities.

        Per CQL spec: Units must be the same for subtraction.
        """
        if not isinstance(other, Quantity):
            return NotImplemented
        if self.unit != other.unit:
            raise TypeError(f"Cannot subtract quantities with different units: {self.unit} and {other.unit}")
        return Quantity(value=self.value - other.value, unit=self.unit)

    def __mul__(self, other: object) -> "Quantity":
        """Multiply two quantities.

        Per CQL spec: Units are combined (e.g., cm * cm = cm2).
        """
        if not isinstance(other, Quantity):
            return NotImplemented
        # Combine units - if same unit, use exponential notation (cm * cm = cm2)
        if other.unit == "1":
            new_unit = self.unit
        elif self.unit == "1":
            new_unit = other.unit
        elif self.unit == other.unit:
            # Same unit - use exponential form (e.g., cm * cm = cm2)
            new_unit = f"{self.unit}2"
        else:
            # Different units - combine with dot
            new_unit = f"{self.unit}.{other.unit}"
        return Quantity(value=self.value * other.value, unit=new_unit)

    def __truediv__(self, other: object) -> "Quantity":
        """Divide two quantities.

        Per CQL spec: Units are combined (e.g., g/cm3 / g/cm3 = 1).
        """
        if not isinstance(other, Quantity):
            return NotImplemented
        if other.value == 0:
            raise ZeroDivisionError("Cannot divide by zero quantity")
        # If units are the same, result is dimensionless
        if self.unit == other.unit:
            return Quantity(value=self.value / other.value, unit="1")
        # Otherwise combine units
        new_unit = f"{self.unit}/{other.unit}"
        return Quantity(value=self.value / other.value, unit=new_unit)

    def __mod__(self, other: object) -> "Quantity":
        """Modulo of two quantities.

        Per CQL spec: Units must be the same.
        """
        if not isinstance(other, Quantity):
            return NotImplemented
        if self.unit != other.unit:
            raise TypeError(f"Cannot compute modulo of quantities with different units: {self.unit} and {other.unit}")
        if other.value == 0:
            raise ZeroDivisionError("Cannot modulo by zero quantity")
        return Quantity(value=self.value % other.value, unit=self.unit)

    def __floordiv__(self, other: object) -> "Quantity":
        """Truncated division of two quantities.

        Per CQL spec: Units must be the same, result is same unit.
        Result is a Decimal with .0 to indicate integer-like value.
        """
        if not isinstance(other, Quantity):
            return NotImplemented
        if self.unit != other.unit:
            raise TypeError(f"Cannot divide quantities with different units: {self.unit} and {other.unit}")
        if other.value == 0:
            raise ZeroDivisionError("Cannot divide by zero quantity")
        # Use truncation toward zero (like int()) instead of floor
        result = int(self.value / other.value)
        # Return as Decimal with .0 to indicate it's a truncated value
        return Quantity(value=Decimal(str(float(result))), unit=self.unit)

    def __str__(self) -> str:
        return f"{self.value} '{self.unit}'"


class FHIRDate(BaseModel):
    """FHIRPath Date type with partial precision support."""

    model_config = ConfigDict(frozen=True)

    year: int
    month: int | None = None
    day: int | None = None

    @classmethod
    def parse(cls, value: str) -> "FHIRDate | None":
        """Parse a date string (YYYY, YYYY-MM, or YYYY-MM-DD)."""
        match = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$", value)
        if match:
            year = int(match.group(1))
            month = int(match.group(2)) if match.group(2) else None
            day = int(match.group(3)) if match.group(3) else None
            return cls(year=year, month=month, day=day)
        return None

    def to_date(self) -> date | None:
        """Convert to Python date (requires full precision)."""
        if self.month is not None and self.day is not None:
            return date(self.year, self.month, self.day)
        return None

    def __str__(self) -> str:
        if self.month is None:
            return f"{self.year:04d}"
        if self.day is None:
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FHIRDate):
            return self.year == other.year and self.month == other.month and self.day == other.day
        return False

    def __hash__(self) -> int:
        return hash((self.year, self.month, self.day))

    def __lt__(self, other: "FHIRDate") -> bool:
        if self.year != other.year:
            return self.year < other.year
        if self.month is None or other.month is None:
            return False  # Incomparable precision
        if self.month != other.month:
            return self.month < other.month
        if self.day is None or other.day is None:
            return False
        return self.day < other.day

    def __le__(self, other: "FHIRDate") -> bool:
        return self == other or self < other

    def __gt__(self, other: "FHIRDate") -> bool:
        if self.year != other.year:
            return self.year > other.year
        if self.month is None or other.month is None:
            return False  # Incomparable precision
        if self.month != other.month:
            return self.month > other.month
        if self.day is None or other.day is None:
            return False
        return self.day > other.day

    def __ge__(self, other: "FHIRDate") -> bool:
        return self == other or self > other


class FHIRDateTime(BaseModel):
    """FHIRPath DateTime type with timezone support."""

    model_config = ConfigDict(frozen=True)

    year: int
    month: int | None = None
    day: int | None = None
    hour: int | None = None
    minute: int | None = None
    second: int | None = None
    millisecond: int | None = None
    tz_offset: str | None = None  # e.g., "Z", "+05:00", "-08:00"

    @classmethod
    def parse(cls, value: str, raise_on_malformed: bool = False) -> "FHIRDateTime | None":
        """Parse a datetime string."""
        from dhis2w_fhir_engine.engine.exceptions import CQLError

        # Remove @ prefix if present (from FHIRPath literals)
        if value.startswith("@"):
            value = value[1:]

        # Check for malformed date strings (e.g., slashes instead of dashes)
        if re.match(r"^\d{4}/", value):
            if raise_on_malformed:
                raise CQLError(f"Malformed datetime string: {value} (use dashes as separators, not slashes)")
            return None

        # Handle partial DateTime with T suffix but no time (e.g., "2015T", "2015-01T")
        # This indicates DateTime type (vs Date) even without time components
        partial_match = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?T$", value)
        if partial_match:
            groups = partial_match.groups()
            return cls(
                year=int(groups[0]),
                month=int(groups[1]) if groups[1] else None,
                day=int(groups[2]) if groups[2] else None,
            )

        # Pattern: YYYY[-MM[-DD[Thh[:mm[:ss[.fff]]][tz]]]]
        pattern = (
            r"^(\d{4})(?:-(\d{2})(?:-(\d{2})"
            r"(?:T(\d{2})(?::(\d{2})(?::(\d{2})(?:\.(\d+))?)?)?(Z|[+-]\d{2}:\d{2})?)?)?)?$"
        )
        match = re.match(pattern, value)
        if match:
            groups = match.groups()
            ms = None
            if groups[6]:
                # Convert fractional seconds to milliseconds
                frac = groups[6][:3].ljust(3, "0")
                ms = int(frac)
            return cls(
                year=int(groups[0]),
                month=int(groups[1]) if groups[1] else None,
                day=int(groups[2]) if groups[2] else None,
                hour=int(groups[3]) if groups[3] else None,
                minute=int(groups[4]) if groups[4] else None,
                second=int(groups[5]) if groups[5] else None,
                millisecond=ms,
                tz_offset=groups[7],
            )
        return None

    def to_datetime(self) -> datetime | None:
        """Convert to Python datetime (requires at least date precision)."""
        if self.month is None or self.day is None:
            return None
        tz = None
        if self.tz_offset:
            if self.tz_offset == "Z":
                tz = UTC
            elif ":" in self.tz_offset:
                # Format: +HH:MM or -HH:MM
                sign = 1 if self.tz_offset[0] == "+" else -1
                hours = int(self.tz_offset[1:3])
                mins = int(self.tz_offset[4:6])
                tz = timezone(timedelta(hours=sign * hours, minutes=sign * mins))
            else:
                # Numeric offset in hours (e.g., "-7.0" or "5.5")
                try:
                    offset_hours = float(self.tz_offset)
                    tz = timezone(timedelta(hours=offset_hours))
                except ValueError:
                    pass  # Invalid offset, leave tz as None

        return datetime(
            self.year,
            self.month,
            self.day,
            self.hour or 0,
            self.minute or 0,
            self.second or 0,
            (self.millisecond or 0) * 1000,
            tz,
        )

    def __str__(self) -> str:
        result = f"{self.year:04d}"
        if self.month is not None:
            result += f"-{self.month:02d}"
        if self.day is not None:
            result += f"-{self.day:02d}"
        if self.hour is not None:
            result += f"T{self.hour:02d}"
            if self.minute is not None:
                result += f":{self.minute:02d}"
                if self.second is not None:
                    result += f":{self.second:02d}"
                    if self.millisecond is not None:
                        result += f".{self.millisecond:03d}"
        if self.tz_offset:
            result += self.tz_offset
        return result

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FHIRDateTime):
            return (
                self.year == other.year
                and self.month == other.month
                and self.day == other.day
                and self.hour == other.hour
                and self.minute == other.minute
                and self.second == other.second
                and self.millisecond == other.millisecond
                and self.tz_offset == other.tz_offset
            )
        return False

    def __hash__(self) -> int:
        return hash(
            (self.year, self.month, self.day, self.hour, self.minute, self.second, self.millisecond, self.tz_offset)
        )

    def _to_tuple(self) -> tuple[int, int, int, int, int, int, int]:
        """Convert to tuple for comparison (with defaults for missing precision)."""
        return (
            self.year,
            self.month or 1,
            self.day or 1,
            self.hour or 0,
            self.minute or 0,
            self.second or 0,
            self.millisecond or 0,
        )

    def _to_utc_tuple(self) -> tuple[int, int, int, int, int, int, int]:
        """Convert to UTC-normalized tuple for timezone-aware comparison."""
        if not self.tz_offset or self.hour is None:
            return self._to_tuple()

        # Parse timezone offset and convert to UTC
        py_dt = self.to_datetime()
        if py_dt is None:
            return self._to_tuple()

        # Convert to UTC

        utc_dt = py_dt.astimezone(UTC)
        return (
            utc_dt.year,
            utc_dt.month,
            utc_dt.day,
            utc_dt.hour,
            utc_dt.minute,
            utc_dt.second,
            utc_dt.microsecond // 1000,
        )

    def _has_comparable_precision(self, other: "FHIRDateTime") -> bool:
        """Check if both datetimes have comparable precision levels."""
        # Both must have same precision level for reliable comparison
        self_precision = sum(
            1 for x in [self.month, self.day, self.hour, self.minute, self.second, self.millisecond] if x is not None
        )
        other_precision = sum(
            1
            for x in [other.month, other.day, other.hour, other.minute, other.second, other.millisecond]
            if x is not None
        )
        return self_precision == other_precision

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, FHIRDateTime):
            return NotImplemented
        # Use UTC-normalized comparison for timezone-aware datetimes
        return self._to_utc_tuple() < other._to_utc_tuple()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, FHIRDateTime):
            return NotImplemented
        return self._to_utc_tuple() <= other._to_utc_tuple()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, FHIRDateTime):
            return NotImplemented
        return self._to_utc_tuple() > other._to_utc_tuple()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, FHIRDateTime):
            return NotImplemented
        return self._to_utc_tuple() >= other._to_utc_tuple()

    def __sub__(self, other: object) -> "Quantity":
        """Subtract two datetimes to get a duration Quantity.

        Returns the difference in the most appropriate unit based on precision:
        - Day precision: returns days
        - Full precision: returns milliseconds
        """
        if not isinstance(other, FHIRDateTime):
            return NotImplemented

        # Convert both to datetime objects for calculation
        self_dt = self.to_datetime()
        other_dt = other.to_datetime()

        if self_dt is None or other_dt is None:
            # For partial dates, calculate at the available precision
            if self.hour is None and other.hour is None:
                # Day precision - calculate in days
                from datetime import date as python_date

                self_date = python_date(self.year, self.month or 1, self.day or 1)
                other_date = python_date(other.year, other.month or 1, other.day or 1)
                diff_days = (self_date - other_date).days
                return Quantity(value=Decimal(str(diff_days)), unit="days")
            return Quantity(value=Decimal("0"), unit="ms")

        # Full precision - calculate in milliseconds
        delta = self_dt - other_dt
        if self.hour is None:
            # Day precision - return days
            return Quantity(value=Decimal(str(delta.days)), unit="days")
        else:
            # Full precision - return milliseconds
            total_ms = int(delta.total_seconds() * 1000)
            return Quantity(value=Decimal(str(total_ms)), unit="ms")


class FHIRTime(BaseModel):
    """FHIRPath Time type."""

    model_config = ConfigDict(frozen=True)

    hour: int
    minute: int | None = None
    second: int | None = None
    millisecond: int | None = None

    @classmethod
    def parse(cls, value: str) -> "FHIRTime | None":
        """Parse a time string (hh:mm:ss.fff).

        Handles optional timezone offset which is ignored for time values.
        """
        from dhis2w_fhir_engine.engine.exceptions import CQLError

        # Remove T prefix if present
        if value.startswith("T"):
            value = value[1:]

        # Check for malformed time strings (e.g., dashes instead of colons)
        # Malformed pattern: digits separated by dashes that looks like a time
        if re.match(r"^\d{2}-\d{2}", value):
            raise CQLError(f"Malformed time string: {value} (use colons as separators, not dashes)")

        # Pattern includes optional timezone offset (Z or +/-hh:mm)
        pattern = r"^(\d{2})(?::(\d{2})(?::(\d{2})(?:\.(\d+))?)?)?(?:Z|[+-]\d{2}:\d{2})?$"
        match = re.match(pattern, value)
        if match:
            groups = match.groups()
            hour = int(groups[0])
            minute = int(groups[1]) if groups[1] else None
            second = int(groups[2]) if groups[2] else None
            ms = None
            if groups[3]:
                frac = groups[3]
                # Check for invalid milliseconds (> 999)
                if len(frac) > 3 and int(frac) > 999:
                    raise CQLError(f"Time millisecond {int(frac)} out of range (0-999)")
                frac = frac[:3].ljust(3, "0")
                ms = int(frac)
            # Validate ranges
            if hour < 0 or hour > 23:
                raise CQLError(f"Time hour {hour} out of range (0-23)")
            if minute is not None and (minute < 0 or minute > 59):
                raise CQLError(f"Time minute {minute} out of range (0-59)")
            if second is not None and (second < 0 or second > 59):
                raise CQLError(f"Time second {second} out of range (0-59)")
            return cls(
                hour=hour,
                minute=minute,
                second=second,
                millisecond=ms,
            )
        return None

    def to_time(self) -> time | None:
        """Convert to Python time."""
        return time(
            self.hour,
            self.minute or 0,
            self.second or 0,
            (self.millisecond or 0) * 1000,
        )

    def __str__(self) -> str:
        result = f"{self.hour:02d}"
        if self.minute is not None:
            result += f":{self.minute:02d}"
            if self.second is not None:
                result += f":{self.second:02d}"
                if self.millisecond is not None:
                    result += f".{self.millisecond:03d}"
        return result

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FHIRTime):
            # Exact equality only if all components match (including precision)
            return (
                self.hour == other.hour
                and self.minute == other.minute
                and self.second == other.second
                and self.millisecond == other.millisecond
            )
        return False

    def equals_with_uncertainty(self, other: object) -> bool | None:
        """Compare times with CQL precision semantics.

        Returns:
            True if definitely equal
            False if definitely not equal
            None if uncertain (precision mismatch)
        """
        if not isinstance(other, FHIRTime):
            return False

        # Compare at the precision level of the less precise value
        if self.hour != other.hour:
            return False

        # Check minute precision
        if self.minute is None or other.minute is None:
            return None if (self.minute is None) != (other.minute is None) else True
        if self.minute != other.minute:
            return False

        # Check second precision
        if self.second is None or other.second is None:
            return None if (self.second is None) != (other.second is None) else True
        if self.second != other.second:
            return False

        # Check millisecond precision
        if self.millisecond is None or other.millisecond is None:
            return None if (self.millisecond is None) != (other.millisecond is None) else True
        return self.millisecond == other.millisecond

    def __hash__(self) -> int:
        return hash((self.hour, self.minute, self.second, self.millisecond))

    def _to_tuple(self) -> tuple[int, int, int, int]:
        """Convert to tuple for comparison (with defaults for missing precision)."""
        return (
            self.hour,
            self.minute or 0,
            self.second or 0,
            self.millisecond or 0,
        )

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, FHIRTime):
            return NotImplemented
        return self._to_tuple() < other._to_tuple()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, FHIRTime):
            return NotImplemented
        return self._to_tuple() <= other._to_tuple()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, FHIRTime):
            return NotImplemented
        return self._to_tuple() > other._to_tuple()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, FHIRTime):
            return NotImplemented
        return self._to_tuple() >= other._to_tuple()

    def __add__(self, other: Any) -> "FHIRTime":
        """Add a duration (Quantity) to this time."""
        if hasattr(other, "value") and hasattr(other, "unit"):
            # Get duration in milliseconds
            unit = other.unit.rstrip("s")  # Handle 'hours', 'hour', etc.
            value = int(other.value)

            if unit in ("hour", "h"):
                delta_ms = value * 3600000
            elif unit in ("minute", "min"):
                delta_ms = value * 60000
            elif unit in ("second", "s"):
                delta_ms = value * 1000
            elif unit in ("millisecond", "ms"):
                delta_ms = value
            else:
                raise ValueError(f"Unsupported time unit: {other.unit}")

            # Convert current time to milliseconds
            current_ms = (
                (self.hour * 3600000) + (self.minute or 0) * 60000 + (self.second or 0) * 1000 + (self.millisecond or 0)
            )

            # Add and wrap around 24 hours
            new_ms = (current_ms + delta_ms) % 86400000

            # Convert back to time components
            hours = new_ms // 3600000
            new_ms %= 3600000
            minutes = new_ms // 60000
            new_ms %= 60000
            seconds = new_ms // 1000
            milliseconds = new_ms % 1000

            return FHIRTime(
                hour=hours,
                minute=minutes if self.minute is not None else None,
                second=seconds if self.second is not None else None,
                millisecond=milliseconds if self.millisecond is not None else None,
            )
        return NotImplemented

    def __sub__(self, other: Any) -> "FHIRTime | Quantity":
        """Subtract a duration (Quantity) or another time from this time."""
        if isinstance(other, FHIRTime):
            # Return difference in milliseconds as a Quantity
            self_ms = (
                (self.hour * 3600000) + (self.minute or 0) * 60000 + (self.second or 0) * 1000 + (self.millisecond or 0)
            )
            other_ms = (
                (other.hour * 3600000)
                + (other.minute or 0) * 60000
                + (other.second or 0) * 1000
                + (other.millisecond or 0)
            )
            return Quantity(value=Decimal(str(self_ms - other_ms)), unit="milliseconds")

        if hasattr(other, "value") and hasattr(other, "unit"):
            # Negate the duration and add
            negated = type(other)(value=-other.value, unit=other.unit)
            return self.__add__(negated)
        return NotImplemented


def get_fhirpath_type(value: Any) -> FHIRPathType:
    """Determine the FHIRPath type of a Python value."""
    if value is None:
        return FHIRPathType.NULL
    if isinstance(value, bool):
        return FHIRPathType.BOOLEAN
    if isinstance(value, int):
        return FHIRPathType.INTEGER
    if isinstance(value, float | Decimal):
        return FHIRPathType.DECIMAL
    if isinstance(value, str):
        # Could be String, Date, DateTime, or Time based on format
        # For now, treat as String (parsing happens elsewhere)
        return FHIRPathType.STRING
    if isinstance(value, Quantity):
        return FHIRPathType.QUANTITY
    if isinstance(value, dict):
        if "resourceType" in value:
            return FHIRPathType.RESOURCE
        return FHIRPathType.ELEMENT
    return FHIRPathType.ELEMENT


def is_truthy(value: Any) -> bool:
    """Determine if a FHIRPath value is truthy.

    FHIRPath truthiness:
    - Empty collection: false
    - Single boolean: its value
    - Single non-boolean: true
    - Multiple items: error (but we return true for simplicity)
    """
    if value is None:
        return False
    if isinstance(value, list):
        if len(value) == 0:
            return False
        if len(value) == 1:
            return is_truthy(value[0])
        return True  # Non-empty collection with multiple items
    if isinstance(value, bool):
        return value
    return True  # Non-boolean singleton is truthy


def to_collection(value: Any) -> list[Any]:
    """Ensure a value is a collection (list)."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def singleton(collection: list[Any]) -> Any:
    """Get singleton value from collection.

    Returns None if empty, the single value if one item,
    or the list itself if multiple items.
    """
    if not collection:
        return None
    if len(collection) == 1:
        return collection[0]
    return collection
