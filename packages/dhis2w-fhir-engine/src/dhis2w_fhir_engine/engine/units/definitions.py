"""UCUM unit definitions for clinical calculations.

Based on the UCUM specification: https://ucum.org/ucum
Implements a subset of commonly used clinical units.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class Dimension(BaseModel):
    """The seven UCUM base dimensions as signed exponents."""

    model_config = ConfigDict(frozen=True)

    length: int = Field(default=0, description="Exponent of length, base unit metre.")
    mass: int = Field(default=0, description="Exponent of mass, base unit gram.")
    time: int = Field(default=0, description="Exponent of time, base unit second.")
    temperature: int = Field(default=0, description="Exponent of temperature, base unit kelvin.")
    amount: int = Field(default=0, description="Exponent of amount of substance, base unit mole.")
    current: int = Field(default=0, description="Exponent of electric current, base unit ampere.")
    luminosity: int = Field(default=0, description="Exponent of luminous intensity, base unit candela.")

    def __mul__(self, other: "Dimension") -> "Dimension":
        return Dimension(
            length=self.length + other.length,
            mass=self.mass + other.mass,
            time=self.time + other.time,
            temperature=self.temperature + other.temperature,
            amount=self.amount + other.amount,
            current=self.current + other.current,
            luminosity=self.luminosity + other.luminosity,
        )

    def __truediv__(self, other: "Dimension") -> "Dimension":
        return Dimension(
            length=self.length - other.length,
            mass=self.mass - other.mass,
            time=self.time - other.time,
            temperature=self.temperature - other.temperature,
            amount=self.amount - other.amount,
            current=self.current - other.current,
            luminosity=self.luminosity - other.luminosity,
        )

    def __pow__(self, power: int) -> "Dimension":
        return Dimension(
            length=self.length * power,
            mass=self.mass * power,
            time=self.time * power,
            temperature=self.temperature * power,
            amount=self.amount * power,
            current=self.current * power,
            luminosity=self.luminosity * power,
        )

    def is_dimensionless(self) -> bool:
        return all(
            v == 0
            for v in [
                self.length,
                self.mass,
                self.time,
                self.temperature,
                self.amount,
                self.current,
                self.luminosity,
            ]
        )


# Dimensionless
DIMENSIONLESS = Dimension()

# Base dimensions
LENGTH = Dimension(length=1)
MASS = Dimension(mass=1)
TIME = Dimension(time=1)
TEMPERATURE = Dimension(temperature=1)
AMOUNT = Dimension(amount=1)
CURRENT = Dimension(current=1)
LUMINOSITY = Dimension(luminosity=1)

# Derived dimensions
AREA = LENGTH**2
VOLUME = LENGTH**3
VELOCITY = LENGTH / TIME
ACCELERATION = VELOCITY / TIME
FORCE = MASS * ACCELERATION
ENERGY = FORCE * LENGTH
PRESSURE = FORCE / AREA
CONCENTRATION = MASS / VOLUME


class UnitDefinition(BaseModel):
    """Definition of one UCUM unit: its dimension and its conversion to the base unit."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(description="UCUM code, for example 'g', 'mg', or '[lb_av]'.")
    name: str = Field(description="Human-readable unit name.")
    dimension: Dimension = Field(description="Dimensional signature of the unit.")
    factor: Decimal = Field(description="Multiplier converting this unit to its base unit.")
    offset: Decimal = Field(default=Decimal("0"), description="Additive offset, used by temperature units.")
    is_metric: bool = Field(default=True, description="Whether SI prefixes may be applied to this unit.")
    is_special: bool = Field(default=False, description="Whether conversion needs special handling.")


# SI Prefixes with their factors
SI_PREFIXES: dict[str, Decimal] = {
    "Y": Decimal("1e24"),  # yotta
    "Z": Decimal("1e21"),  # zetta
    "E": Decimal("1e18"),  # exa
    "P": Decimal("1e15"),  # peta
    "T": Decimal("1e12"),  # tera
    "G": Decimal("1e9"),  # giga
    "M": Decimal("1e6"),  # mega
    "k": Decimal("1e3"),  # kilo
    "h": Decimal("1e2"),  # hecto
    "da": Decimal("1e1"),  # deca
    "d": Decimal("1e-1"),  # deci
    "c": Decimal("1e-2"),  # centi
    "m": Decimal("1e-3"),  # milli
    "u": Decimal("1e-6"),  # micro (UCUM uses 'u' not 'μ')
    "n": Decimal("1e-9"),  # nano
    "p": Decimal("1e-12"),  # pico
    "f": Decimal("1e-15"),  # femto
    "a": Decimal("1e-18"),  # atto
    "z": Decimal("1e-21"),  # zepto
    "y": Decimal("1e-24"),  # yocto
}

# Base units (factor = 1 relative to themselves)
BASE_UNITS: dict[str, UnitDefinition] = {
    # Length - meter is base
    "m": UnitDefinition(code="m", name="meter", dimension=LENGTH, factor=Decimal("1")),
    # Mass - gram is UCUM base (not kg!)
    "g": UnitDefinition(code="g", name="gram", dimension=MASS, factor=Decimal("1")),
    # Time - second is base
    "s": UnitDefinition(code="s", name="second", dimension=TIME, factor=Decimal("1")),
    # Temperature - Kelvin is base
    "K": UnitDefinition(code="K", name="Kelvin", dimension=TEMPERATURE, factor=Decimal("1")),
    # Amount - mole is base
    "mol": UnitDefinition(code="mol", name="mole", dimension=AMOUNT, factor=Decimal("1")),
    # Current - Ampere is base
    "A": UnitDefinition(code="A", name="Ampere", dimension=CURRENT, factor=Decimal("1")),
    # Luminosity - candela is base
    "cd": UnitDefinition(code="cd", name="candela", dimension=LUMINOSITY, factor=Decimal("1")),
    # Dimensionless
    "1": UnitDefinition(code="1", name="unity", dimension=DIMENSIONLESS, factor=Decimal("1"), is_metric=False),
    "%": UnitDefinition(code="%", name="percent", dimension=DIMENSIONLESS, factor=Decimal("0.01"), is_metric=False),
}

# Derived metric units
DERIVED_UNITS: dict[str, UnitDefinition] = {
    # Volume
    "L": UnitDefinition(code="L", name="liter", dimension=VOLUME, factor=Decimal("1e-3")),  # 1 L = 0.001 m^3
    "l": UnitDefinition(code="l", name="liter", dimension=VOLUME, factor=Decimal("1e-3")),  # alternate
    # Force
    "N": UnitDefinition(
        code="N", name="Newton", dimension=FORCE, factor=Decimal("1000")
    ),  # 1 N = 1 kg*m/s^2 = 1000 g*m/s^2
    # Pressure
    "Pa": UnitDefinition(code="Pa", name="Pascal", dimension=PRESSURE, factor=Decimal("1000")),  # 1 Pa = 1 N/m^2
    "bar": UnitDefinition(code="bar", name="bar", dimension=PRESSURE, factor=Decimal("1e8")),  # 1 bar = 100000 Pa
    # Energy
    "J": UnitDefinition(code="J", name="Joule", dimension=ENERGY, factor=Decimal("1000")),  # 1 J = 1 N*m
    "cal": UnitDefinition(
        code="cal", name="calorie", dimension=ENERGY, factor=Decimal("4184")
    ),  # thermochemical calorie
    # Frequency
    "Hz": UnitDefinition(code="Hz", name="Hertz", dimension=TIME**-1, factor=Decimal("1")),
    # Time
    "min": UnitDefinition(code="min", name="minute", dimension=TIME, factor=Decimal("60"), is_metric=False),
    "h": UnitDefinition(code="h", name="hour", dimension=TIME, factor=Decimal("3600"), is_metric=False),
    "d": UnitDefinition(code="d", name="day", dimension=TIME, factor=Decimal("86400"), is_metric=False),
    "wk": UnitDefinition(code="wk", name="week", dimension=TIME, factor=Decimal("604800"), is_metric=False),
    "mo": UnitDefinition(
        code="mo", name="month", dimension=TIME, factor=Decimal("2629746"), is_metric=False
    ),  # avg month
    "a": UnitDefinition(
        code="a", name="year", dimension=TIME, factor=Decimal("31557600"), is_metric=False
    ),  # Julian year
    # Angle
    "rad": UnitDefinition(code="rad", name="radian", dimension=DIMENSIONLESS, factor=Decimal("1")),
    "deg": UnitDefinition(
        code="deg", name="degree", dimension=DIMENSIONLESS, factor=Decimal("0.0174532925199433")
    ),  # pi/180
}

# Special units (with square brackets in UCUM)
SPECIAL_UNITS: dict[str, UnitDefinition] = {
    # Temperature
    "Cel": UnitDefinition(
        code="Cel",
        name="degree Celsius",
        dimension=TEMPERATURE,
        factor=Decimal("1"),
        offset=Decimal("273.15"),
        is_metric=False,
        is_special=True,
    ),
    "[degF]": UnitDefinition(
        code="[degF]",
        name="degree Fahrenheit",
        dimension=TEMPERATURE,
        factor=Decimal("0.555555555555556"),
        offset=Decimal("255.372222222222"),
        is_metric=False,
        is_special=True,
    ),
    # US customary mass
    "[lb_av]": UnitDefinition(
        code="[lb_av]", name="pound", dimension=MASS, factor=Decimal("453.59237"), is_metric=False
    ),
    "[oz_av]": UnitDefinition(
        code="[oz_av]", name="ounce", dimension=MASS, factor=Decimal("28.349523125"), is_metric=False
    ),
    "[gr]": UnitDefinition(code="[gr]", name="grain", dimension=MASS, factor=Decimal("0.06479891"), is_metric=False),
    "[dr_av]": UnitDefinition(
        code="[dr_av]", name="dram", dimension=MASS, factor=Decimal("1.7718451953125"), is_metric=False
    ),
    "[stone_av]": UnitDefinition(
        code="[stone_av]", name="stone", dimension=MASS, factor=Decimal("6350.29318"), is_metric=False
    ),
    # US customary length
    "[in_i]": UnitDefinition(code="[in_i]", name="inch", dimension=LENGTH, factor=Decimal("0.0254"), is_metric=False),
    "[ft_i]": UnitDefinition(code="[ft_i]", name="foot", dimension=LENGTH, factor=Decimal("0.3048"), is_metric=False),
    "[yd_i]": UnitDefinition(code="[yd_i]", name="yard", dimension=LENGTH, factor=Decimal("0.9144"), is_metric=False),
    "[mi_i]": UnitDefinition(code="[mi_i]", name="mile", dimension=LENGTH, factor=Decimal("1609.344"), is_metric=False),
    # US customary volume
    "[gal_us]": UnitDefinition(
        code="[gal_us]", name="US gallon", dimension=VOLUME, factor=Decimal("0.003785411784"), is_metric=False
    ),
    "[qt_us]": UnitDefinition(
        code="[qt_us]", name="US quart", dimension=VOLUME, factor=Decimal("0.000946352946"), is_metric=False
    ),
    "[pt_us]": UnitDefinition(
        code="[pt_us]", name="US pint", dimension=VOLUME, factor=Decimal("0.000473176473"), is_metric=False
    ),
    "[foz_us]": UnitDefinition(
        code="[foz_us]", name="US fluid ounce", dimension=VOLUME, factor=Decimal("0.0000295735295625"), is_metric=False
    ),
    "[tbs_us]": UnitDefinition(
        code="[tbs_us]", name="US tablespoon", dimension=VOLUME, factor=Decimal("0.00001478676478125"), is_metric=False
    ),
    "[tsp_us]": UnitDefinition(
        code="[tsp_us]", name="US teaspoon", dimension=VOLUME, factor=Decimal("0.00000492892159375"), is_metric=False
    ),
    "[cup_us]": UnitDefinition(
        code="[cup_us]", name="US cup", dimension=VOLUME, factor=Decimal("0.0002365882365"), is_metric=False
    ),
    # Clinical units
    "[IU]": UnitDefinition(
        code="[IU]", name="international unit", dimension=DIMENSIONLESS, factor=Decimal("1"), is_metric=False
    ),
    "[iU]": UnitDefinition(
        code="[iU]", name="international unit", dimension=DIMENSIONLESS, factor=Decimal("1"), is_metric=False
    ),
    "[arb'U]": UnitDefinition(
        code="[arb'U]", name="arbitrary unit", dimension=DIMENSIONLESS, factor=Decimal("1"), is_metric=False
    ),
    "[USP'U]": UnitDefinition(
        code="[USP'U]", name="USP unit", dimension=DIMENSIONLESS, factor=Decimal("1"), is_metric=False
    ),
    # Equivalents
    "eq": UnitDefinition(code="eq", name="equivalent", dimension=AMOUNT, factor=Decimal("1")),
    "osm": UnitDefinition(code="osm", name="osmole", dimension=AMOUNT, factor=Decimal("1")),
    # Pressure
    "mm[Hg]": UnitDefinition(
        code="mm[Hg]",
        name="millimeter of mercury",
        dimension=PRESSURE,
        factor=Decimal("133322.387415"),
        is_metric=False,
    ),
    "[psi]": UnitDefinition(
        code="[psi]", name="pound per square inch", dimension=PRESSURE, factor=Decimal("6894757.29"), is_metric=False
    ),
    # pH and logarithmic
    "[pH]": UnitDefinition(code="[pH]", name="pH", dimension=DIMENSIONLESS, factor=Decimal("1"), is_metric=False),
}

# Build complete unit registry
UNIT_REGISTRY: dict[str, UnitDefinition] = {}
UNIT_REGISTRY.update(BASE_UNITS)
UNIT_REGISTRY.update(DERIVED_UNITS)
UNIT_REGISTRY.update(SPECIAL_UNITS)

# Common aliases
UNIT_ALIASES: dict[str, str] = {
    "mcg": "ug",  # microgram
    "sec": "s",
    "hr": "h",
    "yr": "a",
    "cc": "mL",  # cubic centimeter = milliliter
    "lbs": "[lb_av]",
    "lb": "[lb_av]",
    "oz": "[oz_av]",
    "in": "[in_i]",
    "ft": "[ft_i]",
    "mi": "[mi_i]",
    "gal": "[gal_us]",
    "degC": "Cel",
    "degF": "[degF]",
    "celsius": "Cel",
    "fahrenheit": "[degF]",
    "meter": "m",
    "gram": "g",
    "second": "s",
    "liter": "L",
    "litre": "L",
}


def get_unit(code: str) -> UnitDefinition | None:
    """Look up a unit by its UCUM code."""
    # Check aliases first
    if code in UNIT_ALIASES:
        code = UNIT_ALIASES[code]

    # Direct lookup
    if code in UNIT_REGISTRY:
        return UNIT_REGISTRY[code]

    return None


class PrefixedUnit(BaseModel):
    """A unit definition together with the multiplier contributed by its SI prefix."""

    model_config = ConfigDict(frozen=True)

    unit_definition: UnitDefinition = Field(description="Definition of the unprefixed base unit.")
    prefix_factor: Decimal = Field(description="Multiplier the SI prefix contributes, 1 when there is no prefix.")


def get_prefixed_unit(code: str) -> PrefixedUnit | None:
    """Try to parse a prefixed unit (e.g., 'mg' -> 'm' + 'g')."""
    # Check aliases first
    if code in UNIT_ALIASES:
        code = UNIT_ALIASES[code]

    # Direct lookup first
    if code in UNIT_REGISTRY:
        return PrefixedUnit(unit_definition=UNIT_REGISTRY[code], prefix_factor=Decimal("1"))

    # Try prefix parsing (longest prefix first for 'da')
    for prefix in sorted(SI_PREFIXES.keys(), key=len, reverse=True):
        if code.startswith(prefix) and len(code) > len(prefix):
            base_code = code[len(prefix) :]
            if base_code in UNIT_REGISTRY:
                base_unit = UNIT_REGISTRY[base_code]
                if base_unit.is_metric:
                    return PrefixedUnit(unit_definition=base_unit, prefix_factor=SI_PREFIXES[prefix])

    return None
