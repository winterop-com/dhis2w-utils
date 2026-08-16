"""OptionSet integration helpers — `client.option_sets` end-to-end.

Demonstrates every method on `OptionSetsAccessor`:

1. **`get_by_code`** — resolve an OptionSet by its business code. The
   canonical integration lookup (external systems know the set by a
   stable code, not the DHIS2 UID).
2. **`list_options`** — walk every option in sort-order.
3. **`find_option`** — pinpoint one option by code or name without
   pulling the whole set into memory.
4. **`upsert_options` (dry-run)** — preview the diff an idempotent sync
   would produce against the current set.
5. **`upsert_options` (real)** — commit the sync. Adds new options,
   updates names for existing codes, optionally removes options missing
   from the spec.
6. **Rollback** — same helper again with `remove_missing=True` to return
   the set to its original state.

The example targets the `VACCINE_TYPE` OptionSet the e2e seed creates —
if you're running against a fresh DHIS2 without the dhis2-utils seed,
seed it first via `uv run python infra/scripts/build_e2e_dump.py` (or
point the CODE constant below at a set that already exists).

Usage:
    uv run python examples/client/options_integration.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import OptionSpec
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

OPTION_SET_CODE = "VACCINE_TYPE"


async def main() -> None:
    """Run every `OptionSetsAccessor` method against the active profile."""
    async with open_client(profile_from_env()) as client:
        # 1. Resolve the set by its business code.
        option_set = await client.option_sets.get_by_code(OPTION_SET_CODE)
        if option_set is None:
            print(
                f"no OptionSet with code={OPTION_SET_CODE!r} — "
                "run `uv run python infra/scripts/build_e2e_dump.py` first",
            )
            return
        print(f"[get_by_code] {option_set.id}  {option_set.name!r}  valueType={option_set.valueType}")
        set_uid = option_set.id
        if set_uid is None:
            print("OptionSet has no UID (unexpected); aborting.")
            return

        # 2. List options in sort-order.
        options = await client.option_sets.list_options(set_uid)
        print(f"\n[list_options] {len(options)} options:")
        for opt in options:
            print(f"   {opt.sortOrder}. {opt.code}  {opt.name!r}")

        # 3. Find a specific option two ways.
        bcg = await client.option_sets.find_option(set_uid, option_code="BCG")
        print(f"\n[find_option code='BCG'] → {bcg.id if bcg else None}  {bcg.name if bcg else '-'!r}")
        missing = await client.option_sets.find_option(set_uid, option_code="NOT_REAL")
        print(f"[find_option code='NOT_REAL'] → {missing}")

        # 4. Preview a sync without writing — rename MEASLES + add HPV and YF.
        extended_spec = [
            OptionSpec(code="BCG", name="BCG"),
            OptionSpec(code="MEASLES", name="Measles vaccine"),
            OptionSpec(code="POLIO", name="Polio"),
            OptionSpec(code="DPT", name="DPT"),
            OptionSpec(code="HEPB", name="Hepatitis B"),
            OptionSpec(code="HPV", name="HPV vaccine"),
            OptionSpec(code="YF", name="Yellow fever"),
        ]
        dry = await client.option_sets.upsert_options(set_uid, extended_spec, dry_run=True)
        print(
            f"\n[upsert_options dry_run=True]  added={dry.added}  updated={dry.updated}  skipped={dry.skipped}",
        )

        # 5. Commit the sync.
        report = await client.option_sets.upsert_options(set_uid, extended_spec)
        print(
            f"[upsert_options real]           added={report.added}  updated={report.updated}  skipped={report.skipped}",
        )

        # 6. Rollback — remove HPV + YF, restore MEASLES's original name.
        rollback_spec = [
            OptionSpec(code="BCG", name="BCG"),
            OptionSpec(code="MEASLES", name="Measles"),
            OptionSpec(code="POLIO", name="Polio"),
            OptionSpec(code="DPT", name="DPT"),
            OptionSpec(code="HEPB", name="Hepatitis B"),
        ]
        rollback = await client.option_sets.upsert_options(
            set_uid,
            rollback_spec,
            remove_missing=True,
        )
        print(
            f"[rollback remove_missing=True]  added={rollback.added}  "
            f"updated={rollback.updated}  removed={rollback.removed}",
        )
        final = await client.option_sets.list_options(set_uid)
        print(f"[final codes] → {[o.code for o in final]}")

        # 7. External-system code mapping — SNOMED CT codes attached as attribute values.
        print("\n--- external-system code mapping ---")

        # 7a. Read the SNOMED code off BCG. Accessor resolves the attribute's
        # business code to its UID internally.
        snomed = await client.option_sets.get_option_attribute_value("OptVacBCG01", "SNOMED_CODE")
        print(f"[get_option_attribute_value] BCG.SNOMED_CODE = {snomed}")

        # 7b. Reverse lookup — THE killer integration helper. External system
        # hands us a SNOMED code; we return the DHIS2 Option it maps to.
        hit = await client.option_sets.find_option_by_attribute(
            set_uid,
            "SNOMED_CODE",
            "386661006",  # Measles vaccine immunisation
        )
        print(
            f"[find_option_by_attribute] SNOMED=386661006 → {hit.code if hit else None}  {hit.name if hit else '-'!r}",
        )
        miss = await client.option_sets.find_option_by_attribute(
            set_uid,
            "SNOMED_CODE",
            "NOT_A_REAL_CODE",
        )
        print(f"[find_option_by_attribute] NOT_A_REAL_CODE → {miss}")

        # 7c. Update an attribute value — read-merge-write in one call.
        await client.option_sets.set_option_attribute_value(
            "OptVacBCG01",
            "SNOMED_CODE",
            "TESTING-XYZ",
        )
        new_snomed = await client.option_sets.get_option_attribute_value(
            "OptVacBCG01",
            "SNOMED_CODE",
        )
        print(f"[set_option_attribute_value] BCG.SNOMED_CODE overridden to {new_snomed!r}")

        # Rollback so reruns stay idempotent.
        await client.option_sets.set_option_attribute_value(
            "OptVacBCG01",
            "SNOMED_CODE",
            "77656005",
        )


if __name__ == "__main__":
    run_example(main)
