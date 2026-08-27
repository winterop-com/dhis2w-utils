"""A SINGLE_VALUE visualization — the KPI tile and why its grid is empty.

A KPI tile renders one big number, so the spec collapses the grid to exactly one
cell: `rows=[]`, `columns=[dx]`, `filters=[pe, ou]`. Everything that would spread
the answer across a table becomes a filter instead.

Usage:
    uv run python examples/client/viz_single_value.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import VisualizationSpec

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.enums import VisualizationType
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

KPI_UID = "VizExKpi001"


async def main() -> None:
    """Build a KPI tile for one data element, one period, one organisation unit."""
    async with open_client(profile_from_env()) as client:
        spec = VisualizationSpec(
            name="Example: immunization doses — December 2024 (Sierra Leone)",
            viz_type=VisualizationType.SINGLE_VALUE,
            data_elements=["YtbsuPPo010"],
            periods=["202412"],
            organisation_units=["ImspTQPwCqd"],
            uid=KPI_UID,
        )
        created = await client.visualizations.create_from_spec(spec)
        print(
            f"[kpi] {created.id}  rows={created.rowDimensions} "
            f"columns={created.columnDimensions} filters={created.filterDimensions}",
        )

        await client.visualizations.delete(KPI_UID)
        print("[deleted]")


if __name__ == "__main__":
    run_example(main)
