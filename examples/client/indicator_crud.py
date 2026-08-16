"""Indicator CRUD — create a typed Indicator with a formula, use it, clean up.

DHIS2 indicators are computed fields (`numerator / denominator * factor`)
where both numerator and denominator are expressions referencing data elements
or other indicators. This script creates an indicator that computes
`Immunization coverage = #{fClA2Erf6IO} / #{UOlfIjgN8X6}` and links it to a
default indicator type, then tears it down.

Shows: `IndicatorType` accessor for the type lookup, `Indicator` typed model
with a real formula payload, typed PUT-update via `update()`, `delete()`.

Usage:
    uv run python examples/client/indicator_crud.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import Dhis2Client, generate_uid

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.common import Reference
from dhis2w_client.generated.v42.schemas import Indicator
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

# IndicatorType is imported lazily inside _ensure_indicator_type so the example
# stays self-contained even when the seeded fixture doesn't ship one.


async def _ensure_indicator_type(client: Dhis2Client) -> str:
    """Return an existing IndicatorType UID, or create a throwaway one if none exist."""
    types = await client.resources.indicator_types.list(fields="id,name", page_size=1)
    if types:
        return str(types[0].id)
    # Seed fixture didn't ship one; create a minimal IndicatorType so the rest
    # of the demo has something to reference. No cleanup — it's harmless leftover.
    from dhis2w_client.generated.v42.schemas import IndicatorType

    type_uid = generate_uid()
    await client.resources.indicator_types.create(
        IndicatorType(id=type_uid, name=f"Example IT {type_uid[:4]}", factor=1, number=False),
    )
    return type_uid


async def main() -> None:
    """Create one indicator, update its shortName, delete it."""
    async with open_client(profile_from_env()) as client:
        uid = generate_uid()
        type_uid = await _ensure_indicator_type(client)
        print(f"minted indicator uid={uid}  indicatorType={type_uid}")

        indicator = Indicator(
            id=uid,
            code=f"EX_IND_{uid}",
            name=f"Example immunization coverage {uid}",
            shortName=f"Imm cov {uid[:4]}",
            # Formula: DHIS2 expression language — `#{DE_UID}` is a data-element placeholder.
            numerator="#{fClA2Erf6IO}",
            numeratorDescription="Penta1 doses given",
            denominator="#{UOlfIjgN8X6}",
            denominatorDescription="Fully Immunized child",
            indicatorType=Reference(id=type_uid),
            annualized=False,
        )
        await client.resources.indicators.create(indicator)
        print(f"CREATE  uid={uid}")

        try:
            fetched = await client.resources.indicators.get(
                uid,
                fields="id,name,shortName,numerator,denominator,indicatorType[id,name]",
            )
            print(f"READ    name={fetched.name}  numerator={fetched.numerator}  denominator={fetched.denominator}")

            # PUT-replace through the typed accessor.
            fetched.shortName = f"Updated {uid[:4]}"
            await client.resources.indicators.update(fetched)
            refreshed = await client.resources.indicators.get(uid, fields="id,shortName,lastUpdated")
            print(f"UPDATE  shortName={refreshed.shortName}  lastUpdated={refreshed.lastUpdated}")
        finally:
            await client.resources.indicators.delete(uid)
            print(f"DELETE  {uid}")


if __name__ == "__main__":
    run_example(main)
