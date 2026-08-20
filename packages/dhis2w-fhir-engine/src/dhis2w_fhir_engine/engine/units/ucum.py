"""UCUM unit parser and converter.

Implements parsing and conversion of UCUM (Unified Code for Units of Measure) units
for clinical calculations.

Example usage:
    >>> from dhis2w_fhir_engine.engine.units import convert_quantity
    >>> convert_quantity(1, "g", "mg")
    1000.0
    >>> convert_quantity(98.6, "[degF]", "Cel")
    37.0
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .definitions import (
    DIMENSIONLESS,
    UNIT_ALIASES,
    UNIT_REGISTRY,
    Dimension,
    get_prefixed_unit,
)


class UCUMError(Exception):
    """Base exception for UCUM errors."""


class UnitParseError(UCUMError):
    """Error parsing a unit string."""


class IncompatibleUnitsError(UCUMError):
    """Units are not dimensionally compatible for conversion."""


class ParsedUnit(BaseModel):
    """A UCUM unit string resolved into a dimension and a conversion to the base unit."""

    model_config = ConfigDict(frozen=True)

    original: str = Field(description="The unit string as written.")
    dimension: Dimension = Field(description="Dimensional signature the unit resolves to.")
    factor: Decimal = Field(description="Combined multiplier converting this unit to its base unit.")
    offset: Decimal = Field(default=Decimal("0"), description="Additive offset, used by temperature units.")
    is_special: bool = Field(default=False, description="Whether conversion needs special handling.")

    def is_compatible(self, other: ParsedUnit) -> bool:
        """Check if two units are dimensionally compatible."""
        return self.dimension == other.dimension


class UCUMConverter:
    """Parser and converter for UCUM units."""

    # Pattern for parsing unit terms: optional sign, unit, optional power
    # e.g., "mg", "m2", "s-1", "kg.m/s2"
    TERM_PATTERN = re.compile(
        r"""
        (?P<prefix>[YZEPTGMkhdcmunpfazy]|da)?  # SI prefix
        (?P<unit>\[[^\]]+\]|[A-Za-z%]+)         # Unit (bracketed or regular)
        (?P<power>-?\d+)?                        # Optional power
        """,
        re.VERBOSE,
    )

    def __init__(self) -> None:
        """Initialize the converter."""
        self._cache: dict[str, ParsedUnit] = {}

    def parse(self, unit_str: str) -> ParsedUnit:
        """Parse a UCUM unit string into its components.

        Args:
            unit_str: UCUM unit string (e.g., "mg/dL", "mmol/L", "[lb_av]")

        Returns:
            ParsedUnit with dimension and conversion factor

        Raises:
            UnitParseError: If the unit cannot be parsed
        """
        if not unit_str:
            raise UnitParseError("Empty unit string")

        # Check cache
        if unit_str in self._cache:
            return self._cache[unit_str]

        # Handle "1" as dimensionless
        if unit_str == "1":
            result = ParsedUnit(original=unit_str, dimension=DIMENSIONLESS, factor=Decimal("1"))
            self._cache[unit_str] = result
            return result

        # Normalize aliases
        normalized = UNIT_ALIASES.get(unit_str, unit_str)

        # Check if it's a simple unit
        if normalized in UNIT_REGISTRY:
            unit_def = UNIT_REGISTRY[normalized]
            result = ParsedUnit(
                original=unit_str,
                dimension=unit_def.dimension,
                factor=unit_def.factor,
                offset=unit_def.offset,
                is_special=unit_def.is_special,
            )
            self._cache[unit_str] = result
            return result

        # Try as prefixed simple unit
        prefixed = get_prefixed_unit(normalized)
        if prefixed:
            unit_def = prefixed.unit_definition
            prefix_factor = prefixed.prefix_factor
            result = ParsedUnit(
                original=unit_str,
                dimension=unit_def.dimension,
                factor=unit_def.factor * prefix_factor,
                offset=unit_def.offset,
                is_special=unit_def.is_special,
            )
            self._cache[unit_str] = result
            return result

        # Parse compound units (with . and /)
        try:
            result = self._parse_compound(unit_str)
            self._cache[unit_str] = result
            return result
        except Exception as e:
            raise UnitParseError(f"Cannot parse unit '{unit_str}': {e}") from e

    def _parse_compound(self, unit_str: str) -> ParsedUnit:
        """Parse a compound unit like mg/dL or kg.m/s2."""
        # Split by / to get numerator and denominator
        parts = unit_str.split("/")

        if len(parts) > 2:
            # Handle multiple divisions by combining: a/b/c = a/(b*c)
            numerator = parts[0]
            denominator = ".".join(parts[1:])
        elif len(parts) == 2:
            numerator, denominator = parts
        else:
            numerator = parts[0]
            denominator = ""

        # Parse numerator terms (separated by .)
        num_dim = DIMENSIONLESS
        num_factor = Decimal("1")

        if numerator:
            for term in self._split_terms(numerator):
                parsed = self._parse_term(term)
                num_dim = num_dim * parsed.dimension
                num_factor *= parsed.factor

        # Parse denominator terms
        denom_dim = DIMENSIONLESS
        denom_factor = Decimal("1")

        if denominator:
            for term in self._split_terms(denominator):
                parsed = self._parse_term(term)
                denom_dim = denom_dim * parsed.dimension
                denom_factor *= parsed.factor

        # Combine
        final_dim = num_dim / denom_dim
        final_factor = num_factor / denom_factor

        return ParsedUnit(original=unit_str, dimension=final_dim, factor=final_factor)

    def _split_terms(self, term_str: str) -> list[str]:
        """Split a term string by . while respecting brackets."""
        terms = []
        current = ""
        in_bracket = 0

        for char in term_str:
            if char == "[":
                in_bracket += 1
                current += char
            elif char == "]":
                in_bracket -= 1
                current += char
            elif char == "." and in_bracket == 0:
                if current:
                    terms.append(current)
                current = ""
            else:
                current += char

        if current:
            terms.append(current)

        return terms

    def _parse_term(self, term: str) -> ParsedUnit:
        """Parse a single unit term like 'mg', 'm2', 's-1'."""
        if not term:
            return ParsedUnit(original="1", dimension=DIMENSIONLESS, factor=Decimal("1"))

        # Check for power at the end
        power_match = re.search(r"(-?\d+)$", term)
        power = 1
        base_term = term

        if power_match:
            power = int(power_match.group(1))
            base_term = term[: power_match.start()]

        # Try to resolve the base term
        # First check aliases
        base_term = UNIT_ALIASES.get(base_term, base_term)

        # Direct lookup
        if base_term in UNIT_REGISTRY:
            unit_def = UNIT_REGISTRY[base_term]
            return ParsedUnit(original=term, dimension=unit_def.dimension**power, factor=unit_def.factor**power)

        # Try prefixed unit
        prefixed = get_prefixed_unit(base_term)
        if prefixed:
            unit_def = prefixed.unit_definition
            combined_factor = unit_def.factor * prefixed.prefix_factor
            return ParsedUnit(original=term, dimension=unit_def.dimension**power, factor=combined_factor**power)

        raise UnitParseError(f"Unknown unit term: '{base_term}'")

    def convert(
        self,
        value: float | Decimal,
        from_unit: str,
        to_unit: str,
    ) -> float:
        """Convert a value from one unit to another.

        Args:
            value: The numeric value to convert
            from_unit: Source unit (UCUM code)
            to_unit: Target unit (UCUM code)

        Returns:
            Converted value as float

        Raises:
            IncompatibleUnitsError: If units are not compatible
            UnitParseError: If a unit cannot be parsed
        """
        from_parsed = self.parse(from_unit)
        to_parsed = self.parse(to_unit)

        if not from_parsed.is_compatible(to_parsed):
            raise IncompatibleUnitsError(
                f"Cannot convert '{from_unit}' to '{to_unit}': "
                f"incompatible dimensions ({from_parsed.dimension} vs {to_parsed.dimension})"
            )

        # Handle special units (temperature with offset)
        if from_parsed.is_special or to_parsed.is_special:
            return self._convert_special(value, from_parsed, to_parsed)

        # Standard conversion: value * from_factor / to_factor
        try:
            result = Decimal(str(value)) * from_parsed.factor / to_parsed.factor
            return float(result)
        except (InvalidOperation, ZeroDivisionError) as e:
            raise UCUMError(f"Conversion error: {e}") from e

    def _convert_special(
        self,
        value: float | Decimal,
        from_parsed: ParsedUnit,
        to_parsed: ParsedUnit,
    ) -> float:
        """Handle special unit conversions (like temperature)."""
        val = Decimal(str(value))

        # Convert to base unit (Kelvin for temperature)
        # Formula: K = (value * factor) + offset
        base_value = (val * from_parsed.factor) + from_parsed.offset

        # Convert from base to target
        # Formula: target = (K - offset) / factor
        result = (base_value - to_parsed.offset) / to_parsed.factor

        return float(result)

    def is_compatible(self, unit1: str, unit2: str) -> bool:
        """Check if two units are dimensionally compatible."""
        try:
            parsed1 = self.parse(unit1)
            parsed2 = self.parse(unit2)
            return parsed1.is_compatible(parsed2)
        except UCUMError:
            return False


# Module-level converter instance
_converter = UCUMConverter()


def parse_unit(unit_str: str) -> ParsedUnit:
    """Parse a UCUM unit string.

    Args:
        unit_str: UCUM unit string

    Returns:
        ParsedUnit with dimension and factor
    """
    return _converter.parse(unit_str)


def convert_quantity(
    value: float | Decimal | Any,
    from_unit: str,
    to_unit: str,
) -> float | None:
    """Convert a quantity between units.

    Args:
        value: Numeric value to convert
        from_unit: Source unit (UCUM code)
        to_unit: Target unit (UCUM code)

    Returns:
        Converted value as float, or None if conversion fails

    Examples:
        >>> convert_quantity(1, "g", "mg")
        1000.0
        >>> convert_quantity(180, "mg/dL", "mg/L")
        1800.0
        >>> convert_quantity(98.6, "[degF]", "Cel")
        37.0
    """
    try:
        # A Quantity-like input carries its magnitude on a `value` attribute
        magnitude = getattr(value, "value", value)

        if magnitude is None:
            return None

        return _converter.convert(magnitude, from_unit, to_unit)
    except UCUMError:
        return None


def is_compatible(unit1: str, unit2: str) -> bool:
    """Check if two units are dimensionally compatible.

    Args:
        unit1: First unit
        unit2: Second unit

    Returns:
        True if units can be converted between each other
    """
    return _converter.is_compatible(unit1, unit2)
