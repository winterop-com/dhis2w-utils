"""Cross-resource AttributeValue helpers — `client.attribute_values` end-to-end.

`AttributeValuesAccessor` works against any DHIS2 resource that carries
an `attributeValues` field — DataElements, Options, OrganisationUnits,
Indicators, Dashboards, the whole metadata surface. Integrations use it
for cross-system code mapping: ICD-10 on DataElements, SNOMED on
Options, external-warehouse IDs on OrganisationUnits.

This example uses the seeded `SNOMED_CODE` attribute (attached to every
vaccine Option on a fresh e2e dump) to demonstrate the canonical flows:

1. `resolve_attribute_uid` — business code → UID (needed for BUGS.md
   #21's filter quirk under the hood).
2. `get_value(resource, uid, attribute)` — read one value.
3. `set_value(...)` + `delete_value(...)` — read-merge-write round-trip.
4. `find_uids_by_value(...)` — the integration killer: given an external
   code, return every resource UID it matches.

`client.option_sets` keeps Option-typed convenience wrappers
(`get_option_attribute_value`, `find_option_by_attribute`); those
delegate here, so this module is the single place to reach when the
resource isn't an Option.

Usage:
    uv run python examples/client/attribute_values.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Walk every `AttributeValuesAccessor` method against the seeded profile."""
    async with open_client(profile_from_env()) as client:
        # 1. Resolve a business code to the DHIS2 Attribute UID.
        attr_uid = await client.attribute_values.resolve_attribute_uid("SNOMED_CODE")
        print(f"[resolve_attribute_uid] SNOMED_CODE → {attr_uid}")

        # 2. Read the SNOMED code off one seeded Option via the generic path.
        bcg_snomed = await client.attribute_values.get_value(
            "options",
            "OptVacBCG01",
            "SNOMED_CODE",
        )
        print(f"[get_value] options/OptVacBCG01.SNOMED_CODE = {bcg_snomed}")

        # 3. Reverse lookup — every Option in the seeded VACCINE_TYPE set
        # whose SNOMED matches. Limited here to the set via `extra_filters`.
        matches = await client.attribute_values.find_uids_by_value(
            "options",
            "SNOMED_CODE",
            "386661006",  # Measles vaccine immunisation
            extra_filters=["optionSet.id:eq:OsVaccType1"],
        )
        print(f"[find_uids_by_value] SNOMED=386661006 → {matches}")

        # 4. Convenience: the single-result wrapper for "first match only".
        first = await client.attribute_values.find_one_uid_by_value(
            "options",
            "SNOMED_CODE",
            "396449007",  # Polio vaccine immunisation
        )
        print(f"[find_one_uid_by_value] SNOMED=396449007 → {first}")

        # 5. Round-trip: set + delete + set. Read-merge-writes the full
        # resource each time. Rollback restores the original value.
        await client.attribute_values.set_value(
            "options",
            "OptVacBCG01",
            "SNOMED_CODE",
            "TEMPORARY-VALUE",
        )
        overridden = await client.attribute_values.get_value(
            "options",
            "OptVacBCG01",
            "SNOMED_CODE",
        )
        print(f"[set_value     ] BCG.SNOMED_CODE overridden to {overridden!r}")

        was_removed = await client.attribute_values.delete_value(
            "options",
            "OptVacBCG01",
            "SNOMED_CODE",
        )
        post_delete = await client.attribute_values.get_value(
            "options",
            "OptVacBCG01",
            "SNOMED_CODE",
        )
        print(f"[delete_value  ] removed? {was_removed}  |  now: {post_delete}")

        # Rollback so reruns stay idempotent.
        await client.attribute_values.set_value(
            "options",
            "OptVacBCG01",
            "SNOMED_CODE",
            "77656005",
        )

        # 6. Same surface works on other resources. The seed doesn't carry
        # attribute values on DataElements (SNOMED_CODE is
        # optionAttribute-only), so this is a demonstration of the generic
        # wire shape: get a DE, get_value returns None because no value is
        # attached. No HTTP error, no exception — just None.
        de_result = await client.attribute_values.get_value(
            "dataElements",
            "fClA2Erf6IO",
            "SNOMED_CODE",
        )
        print(f"[get_value] dataElements/fClA2Erf6IO.SNOMED_CODE = {de_result}")


if __name__ == "__main__":
    run_example(main)
