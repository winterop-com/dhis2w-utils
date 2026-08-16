"""PIVOT_TABLE + SINGLE_VALUE over the same data — two defaults side-by-side.

Pivots and KPI tiles are the two most-used non-chart visualization types.
Both consume the same underlying analytics query, but each has its own
default dimensional placement:

- `PIVOT_TABLE`: `rows=[ou]`, `columns=[pe]`, `filters=[dx]` — regions
  down the side, months across the top, one data element filter.
- `SINGLE_VALUE`: `rows=[]`, `columns=[dx]`, `filters=[pe, ou]` — grid
  collapses to exactly one cell so the tile renders a single big number.

Usage:
    uv run python examples/client/viz_pivot_and_kpi.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import VisualizationSpec

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.enums import VisualizationType
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

PIVOT_UID = "VizExPivot1"
KPI_UID = "VizExKpi001"
DISTRICTS = ["jUb8gELQApl", "PMa2VCrupOd", "qhqAxPSTUXp", "kJq2mPyFEHo"]
MONTHS_2024 = [f"2024{m:02d}" for m in range(1, 13)]


async def main() -> None:
    """Build a pivot of immunization doses + a KPI tile for the same DE."""
    async with open_client(profile_from_env()) as client:
        pivot = VisualizationSpec(
            name="Example: immunization doses by district x month (2024)",
            viz_type=VisualizationType.PIVOT_TABLE,
            data_elements=["YtbsuPPo010"],
            periods=MONTHS_2024,
            organisation_units=DISTRICTS,
            uid=PIVOT_UID,
        )
        created_pivot = await client.visualizations.create_from_spec(pivot)
        print(
            f"[pivot] {created_pivot.id}  rows={created_pivot.rowDimensions} "
            f"columns={created_pivot.columnDimensions} filters={created_pivot.filterDimensions}",
        )

        kpi = VisualizationSpec(
            name="Example: immunization doses — December 2024 (Sierra Leone)",
            viz_type=VisualizationType.SINGLE_VALUE,
            data_elements=["YtbsuPPo010"],
            periods=["202412"],
            organisation_units=["ImspTQPwCqd"],
            uid=KPI_UID,
        )
        created_kpi = await client.visualizations.create_from_spec(kpi)
        print(
            f"[kpi]   {created_kpi.id}  rows={created_kpi.rowDimensions} "
            f"columns={created_kpi.columnDimensions} filters={created_kpi.filterDimensions}",
        )

        for uid in (PIVOT_UID, KPI_UID):
            await client.visualizations.delete(uid)
        print("[deleted]")


if __name__ == "__main__":
    run_example(main)
