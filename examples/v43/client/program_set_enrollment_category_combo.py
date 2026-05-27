"""v43-only — set an alternative `enrollmentCategoryCombo` on a Program.

DHIS2 2.43 added `Program.enrollmentCategoryCombo` — an alternative
CategoryCombo applied specifically at enrollment time, distinct from
the program's regular `categoryCombo`. Lets programs carry one
disaggregation for the Program-level metadata and a different one for
enrollment-time data capture.

Unrelated to the v43 UI label overrides demoed in `program_set_labels.py`
or the `enableChangeLog` audit toggle in `program_set_change_log.py` —
they just happen to ship in the same v43 Program schema delta.

This example picks the first WITH_REGISTRATION program and an arbitrary
CategoryCombo (other than the program's existing `categoryCombo`), then
calls `set_enrollment_category_combo(uid, cc_uid)` and prints the result.

Usage:
    uv run python examples/v43/client/program_set_enrollment_category_combo.py

Requires: a DHIS2 v43 profile + at least one WITH_REGISTRATION program +
at least two CategoryCombos.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.client_context import open_client


async def main() -> None:
    """Set `enrollmentCategoryCombo` to the first non-default combo on the first tracker program."""
    async with open_client(profile_from_env()) as client:
        if client.version_key != "v43":
            print(f"skipping: this example targets v43; profile is on {client.version_key}")
            return

        programs = await client.programs.list_all(program_type="WITH_REGISTRATION", page_size=1)
        if not programs:
            print("skipping: no WITH_REGISTRATION programs found")
            return
        target = programs[0]
        if not target.id:
            print("skipping: first program has no id")
            return

        # Pick a CategoryCombo other than the program's current one.
        combos = await client.resources.category_combos.list(fields="id,name", page_size=5)
        current_combo_id = target.categoryCombo.id if target.categoryCombo else None
        alt_combo = next((cc for cc in combos if cc.id and cc.id != current_combo_id), None)
        if alt_combo is None or not alt_combo.id:
            print("skipping: instance has fewer than 2 CategoryCombos; can't pick an alt")
            return

        original_cc = target.enrollmentCategoryCombo.id if target.enrollmentCategoryCombo else None
        # When the field was unset, restoring to the program's main categoryCombo
        # (always the default in seeded fixtures) gives the same downstream
        # behaviour — v43 only rejects enrollments when enrollmentCategoryCombo
        # is non-null *and* non-default.
        restore_cc = original_cc or (target.categoryCombo.id if target.categoryCombo else None)
        print(f"before: {target.id} name={target.name!r} enrollmentCategoryCombo={original_cc}")
        print(f"  using alt CC: {alt_combo.id} name={alt_combo.name!r}")

        try:
            updated = await client.programs.set_enrollment_category_combo(target.id, alt_combo.id)
            print(
                f"after:  {updated.id} "
                f"enrollmentCategoryCombo="
                f"{updated.enrollmentCategoryCombo.id if updated.enrollmentCategoryCombo else None}"
            )
        finally:
            # Restore — otherwise downstream verify-examples runs that enroll
            # against this Program get rejected by v43 with the misleading
            # `E1055 Default AttributeOptionCombo is not allowed as Program has
            # non-default CategoryCombo` (the message says `categoryCombo` but
            # the actual constraint is on the v43-only `enrollmentCategoryCombo`).
            if restore_cc and restore_cc != alt_combo.id:
                await client.programs.set_enrollment_category_combo(target.id, restore_cc)
                print(f"restored: enrollmentCategoryCombo to {restore_cc}")


if __name__ == "__main__":
    run_example(main)
