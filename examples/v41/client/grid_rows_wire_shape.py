"""v41-only — Grid rows wire-shape lie: OAS says `list[list[dict[str, Any]]]`, wire carries scalars.

DHIS2 v41's emitted OAS for `Grid.rows` declares the cell type as
`dict[str, Any]`, but the actual `/api/analytics*` wire returns each
row as a list of scalars (numbers / strings / null). v42 + v43 OAS
correctly type rows as `list[list[Object]]`.

`dhis2w_client.v41.analytics.Grid` subclasses the generated `Grid`
and widens `rows: list[list[Any]] | None` so analytics responses
parse cleanly without a custom validator. Without the override,
pydantic would reject the wire response on v41 with a
`dict_type` validation error.

This example prints the first 5 rows from a small analytics query
against the v41-pinned client, so readers can see scalar cells coming
back where the OAS would suggest dicts.

Usage:
    uv run python examples/v41/client/grid_rows_wire_shape.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client.v41 import Grid
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v41.client_context import open_client


async def main() -> None:
    """Run a small analytics query and inspect `Grid.rows` cell types."""
    async with open_client(profile_from_env()) as client:
        # Pick the first available DataElement + a recent monthly period so
        # the response actually has rows on a seeded fixture.
        de_envelope = await client.get_raw("/api/dataElements", params={"fields": "id", "pageSize": "1"})
        de_rows = de_envelope.get("dataElements") or []
        if not de_rows:
            print("no DataElements on this instance — analytics query would be empty")
            return
        de_uid = de_rows[0]["id"]
        ou_envelope = await client.get_raw("/api/organisationUnits", params={"fields": "id", "pageSize": "1"})
        ou_uid = (ou_envelope.get("organisationUnits") or [{}])[0].get("id")
        if not ou_uid:
            print("no OrganisationUnits — analytics query would be empty")
            return

        grid = await client.analytics.aggregate(
            dx=de_uid,
            pe="LAST_12_MONTHS",
            ou=ou_uid,
            extra_params={"skipMeta": "true"},
        )
        assert isinstance(grid, Grid)
        print(f"v41 Grid.rows annotation widened to: {Grid.model_fields['rows'].annotation!r}")
        print(f"row count: {len(grid.rows or [])}")
        for row in (grid.rows or [])[:5]:
            cell_types = [type(c).__name__ for c in row]
            print(f"  row cells: {row!r}  (types: {cell_types})")
        print()
        print("Note: v41 OAS declares cells as `dict[str, Any]` but the wire returns scalars/null.")
        print("The v41 Grid subclass widens rows to `list[list[Any]]` — see BUGS.md (v41 OAS section).")


if __name__ == "__main__":
    run_example(main)
