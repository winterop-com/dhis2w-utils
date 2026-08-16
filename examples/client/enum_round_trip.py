"""Generated StrEnums — type-safe access to DHIS2's CONSTANT property values.

Every CONSTANT property across every DHIS2 resource schema (`valueType`,
`domainType`, `aggregationType`, `periodType`, `access level`, ...) resolves
to a `StrEnum` in `dhis2w_client.generated.v{N}.enums`. Because `StrEnum`
subclasses `str`, both `ValueType.NUMBER` and bare `"NUMBER"` work as values
— the enum gives IDE discoverability and narrow type checking without
forcing callers to import anything.

Usage:
    uv run python examples/client/enum_round_trip.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import Dhis2Client, NoProfileError, generate_uid, open_client, profile_from_env_raw

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.common import Reference
from dhis2w_client.generated.v42.enums import (
    AggregationType,
    DataElementDomain,
    PeriodType,
    ValueType,
)
from dhis2w_client.generated.v42.schemas import DataElement


async def _default_cc_uid(client: Dhis2Client) -> str:
    """Typed lookup for the built-in default category combo."""
    combos = await client.resources.category_combos.list(filters=["name:eq:default"], fields="id")
    return str(combos[0].id)


async def main() -> None:
    """Show enum equality, creation with enum values, and filtering responses."""
    # StrEnum equality: the wire value and the enum member are interchangeable.
    assert ValueType.NUMBER == "NUMBER"
    assert ValueType("INTEGER_POSITIVE") is ValueType.INTEGER_POSITIVE
    print(
        f"ValueType has {len(list(ValueType))} members; ValueType.NUMBER == 'NUMBER' -> {ValueType.NUMBER == 'NUMBER'}"
    )
    period_samples = sorted(m.value for m in PeriodType)[:5]
    print(f"PeriodType members: {period_samples}... (+{len(list(PeriodType)) - 5} more)")
    # PeriodType is hand-written (see dhis2w_client.v42.periods) because DHIS2's
    # /api/schemas reports it as TEXT, not CONSTANT — PeriodType is a class
    # hierarchy upstream, not a Java enum.

    profile = profile_from_env_raw()
    if profile is None:
        raise NoProfileError("set DHIS2_URL + DHIS2_PAT (or DHIS2_USERNAME + DHIS2_PASSWORD)")
    async with open_client(profile) as client:
        uid = generate_uid()
        cc_uid = await _default_cc_uid(client)

        # Create with enum values — typos fail at edit time.
        de = DataElement(
            id=uid,
            code=f"EX_ENUM_{uid}",
            name=f"Enum example {uid}",
            shortName=f"Enum {uid[:4]}",
            domainType=DataElementDomain.AGGREGATE,
            valueType=ValueType.NUMBER,
            aggregationType=AggregationType.SUM,
            categoryCombo=Reference(id=cc_uid),
        )
        await client.resources.data_elements.create(de)
        print(f"\ncreated DataElement {uid} with ValueType.NUMBER / DataElementDomain.AGGREGATE / AggregationType.SUM")

        # Read back — the enum values in the response are already typed.
        back = await client.resources.data_elements.get(uid)
        print(f"  valueType={back.valueType!r}  (type={type(back.valueType).__name__})")
        print(f"  domainType={back.domainType!r}  (type={type(back.domainType).__name__})")

        # Use the enum in a filter query to narrow results by value.
        numbers = await client.resources.data_elements.list(
            filters=[f"valueType:eq:{ValueType.NUMBER}"],
            fields="id,name,valueType",
            page_size=5,
        )
        print(f"\nvalueType:eq:{ValueType.NUMBER} -> {len(numbers)} data elements (showing up to 5)")
        for item in numbers[:5]:
            print(f"  {item.id}  {item.valueType}  {item.name}")

        await client.resources.data_elements.delete(uid)
        print(f"\ncleaned up {uid}")


if __name__ == "__main__":
    run_example(main)
