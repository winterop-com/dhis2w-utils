"""Organisation-unit accessors — tree walk + group/set membership + level naming.

Exercises the four hand-written accessors introduced with the
organisation-unit surface:

* `client.organisation_units` — tree-aware reads, `list_descendants`,
  and the `create_under` / `move` write shape.
* `client.organisation_unit_groups` — per-item membership POST/DELETE.
* `client.organisation_unit_group_sets` — dimension assembly.
* `client.organisation_unit_levels` — rename levels by numeric depth.

The Sierra Leone hierarchy is the seeded fixture; `ImspTQPwCqd` is the
country root. Runs end-to-end against `make dhis2-run` and cleans up
after itself.

Usage:
    uv run python examples/client/organisation_units.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import OrganisationUnit
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

ROOT_UID = "ImspTQPwCqd"


async def main() -> None:
    """Walk the tree, rename a level, round-trip group + group-set membership."""
    async with open_client(profile_from_env()) as client:
        # ------------------------------------------------------------------
        # Tree navigation
        # ------------------------------------------------------------------
        roots = await client.organisation_units.list_by_level(1)
        print(f"level-1 roots: {[r.name for r in roots]}")

        descendants = await client.organisation_units.list_descendants(ROOT_UID, max_depth=2)
        print(f"Sierra Leone + 2 levels down: {len(descendants)} units")
        _print_tree_sample(descendants, limit=8)

        # ------------------------------------------------------------------
        # Level naming
        # ------------------------------------------------------------------
        levels = await client.organisation_unit_levels.list_all()
        for row in levels:
            print(f"  level {row.level}: {row.name or '(unnamed)'}  code={row.code or '-'}")

        # Rename one level then restore it so the example is idempotent.
        province = await client.organisation_unit_levels.get_by_level(2)
        if province is not None and province.id:
            original = province.name or ""
            renamed = await client.organisation_unit_levels.rename_by_level(2, name="Province (example)")
            print(f"renamed level 2 -> {renamed.name!r}")
            await client.organisation_unit_levels.rename(renamed.id or province.id, name=original)

        # ------------------------------------------------------------------
        # Groups + group sets — round-trip create / link / remove / delete
        # ------------------------------------------------------------------
        group = await client.organisation_unit_groups.create(
            name="Example demo group",
            short_name="ExDemoGrp",
            color="#3388ff",
        )
        print(f"created group {group.id} name={group.name!r}")

        # Add the first three districts to the demo group — descendants at
        # level 3 under Sierra Leone. DHIS2 returns `level` on responses;
        # the field lands in `model_extra` on the generated model.
        districts = [u for u in descendants if getattr(u, "level", None) == 3][:3]
        await client.organisation_unit_groups.add_members(
            group.id or "",
            ou_uids=[d.id or "" for d in districts],
        )
        members = await client.organisation_unit_groups.list_members(group.id or "", page_size=10)
        print(f"group now carries {len(members)} member(s): {[m.name for m in members]}")

        # Drop one, verify it's gone.
        if members:
            await client.organisation_unit_groups.remove_members(
                group.id or "",
                ou_uids=[members[0].id or ""],
            )

        # Wire the group into a fresh group set (analytics dimension).
        group_set = await client.organisation_unit_group_sets.create(
            name="Example demo dimension",
            short_name="ExDemoDim",
        )
        await client.organisation_unit_group_sets.add_groups(
            group_set.id or "",
            group_uids=[group.id or ""],
        )
        print(f"group set {group_set.id} now contains {group.id}")

        # ------------------------------------------------------------------
        # Cleanup
        # ------------------------------------------------------------------
        await client.organisation_unit_group_sets.delete(group_set.id or "")
        await client.organisation_unit_groups.delete(group.id or "")
        print("cleaned up demo group + group set")


def _print_tree_sample(units: list[OrganisationUnit], *, limit: int) -> None:
    """Tiny tree renderer — indents each unit by its DHIS2-reported `level`."""
    if not units:
        return
    root_level = units[0].level or 1
    for unit in units[:limit]:
        level = unit.level or root_level
        indent = "  " * max(level - root_level, 0)
        print(f"{indent}- {unit.name} ({unit.id}) [L{level}]")


if __name__ == "__main__":
    run_example(main)
