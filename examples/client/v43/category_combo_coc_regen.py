"""v43-only — saving a CategoryCombo no longer auto-generates CategoryOptionCombos (BUGS.md #33).

On DHIS2 v42 and earlier, `POST /api/categoryCombos` triggered server-side
generation of every `CategoryOptionCombo` (the cross-product of the
referenced `Categories`' `CategoryOption`s). v43 stopped doing this
automatically — the combo persists with `categoryOptionCombos: []` until
`POST /api/maintenance/categoryOptionComboUpdate` runs.

`dhis2w_client.v43.category_combos.CategoryCombosAccessor.wait_for_coc_generation(uid, expected_count=N)`
fires the maintenance trigger once + polls until the matrix lands or
times out. This example creates a 2-category combo, saves it, then
waits for the 2x2=4 COC matrix to materialise.

On v42 the same code path works but the maintenance trigger is a no-op —
the matrix is already there when `wait_for_coc_generation` is called.
v43 specifically NEEDS the trigger; without it, downstream lookups
(data entry, analytics, viz pivots) against the combo silently fail.

Pairs with `examples/client/v43/removed_resources.py` — together they
showcase the v43 schema + behaviour divergences from v42.

Usage:
    uv run python examples/client/v43/category_combo_coc_regen.py

Requires: at least 2 CategoryOptions with at least 1 Category referencing
each, in the active profile's instance (the seeded Sierra Leone fixture
qualifies).
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.client_context import open_client


async def main() -> None:
    """Create a 2-category combo on v43 and wait for the COC matrix to regenerate."""
    async with open_client(profile_from_env()) as client:
        if client.version_key != "v43":
            print(f"skipping: this example targets v43; profile is on {client.version_key}")
            return

        # Find 2 distinct Categories whose CategoryOptions yield non-trivial COCs.
        categories = await client.resources.categories.list(
            fields="id,name,categoryOptions[id]",
            filters=["categoryOptions:!empty"],
            page_size=2,
        )
        if len(categories) < 2:
            print("need 2+ Categories with options — skipping demo")
            return
        cat_a, cat_b = categories[0], categories[1]
        if not cat_a.id or not cat_b.id:
            print("first two Categories missing an id — skipping demo")
            return
        cat_a_uid = cat_a.id
        cat_b_uid = cat_b.id
        expected_coc_count = len(cat_a.categoryOptions or []) * len(cat_b.categoryOptions or [])
        if expected_coc_count == 0:
            print("seeded categories have no options — skipping")
            return

        # Create the combo. On v43, this returns 201 + persists the row but the
        # categoryOptionCombos list comes back empty until the maintenance trigger fires.
        new_combo = await client.category_combos.create(
            name=f"v43_probe_{cat_a_uid[:6]}_{cat_b_uid[:6]}", categories=[cat_a_uid, cat_b_uid]
        )
        combo_uid = new_combo.id
        if not combo_uid:
            print("create did not return a UID — skipping wait")
            return
        print(f"created combo: {combo_uid}")
        before_count = len(new_combo.categoryOptionCombos or [])
        print(f"  categoryOptionCombos right after create: {before_count} (expected 0 on v43)")

        try:
            # Fire the maintenance trigger + poll. Default 60s timeout, 1s interval.
            landed = await client.category_combos.wait_for_coc_generation(
                combo_uid,
                expected_count=expected_coc_count,
                timeout_seconds=30.0,
                poll_interval_seconds=0.5,
            )
            print(f"  after wait_for_coc_generation: {landed} COCs (expected {expected_coc_count})")
        finally:
            await client.category_combos.delete(combo_uid)
            print(f"  cleaned up probe combo {combo_uid}")


if __name__ == "__main__":
    run_example(main)
