"""A PIVOT_TABLE visualization — `VisualizationSpec` and its default placement.

A pivot puts organisation units down the side, periods across the top, and the
data element in a filter: `rows=[ou]`, `columns=[pe]`, `filters=[dx]`. The spec
fills those three dimension lists itself, so a caller states what data it wants
and reads back where each dimension landed.

Usage:
    uv run python examples/client/viz_pivot_table.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import VisualizationSpec

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.enums import VisualizationType
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

PIVOT_UID = "VizExPivot1"
DISTRICTS = ["jUb8gELQApl", "PMa2VCrupOd", "qhqAxPSTUXp", "kJq2mPyFEHo"]
MONTHS_2024 = [f"2024{m:02d}" for m in range(1, 13)]


async def main() -> None:
    """Build a pivot of immunization doses by district and month, then clean up."""
    async with open_client(profile_from_env()) as client:
        spec = VisualizationSpec(
            name="Example: immunization doses by district x month (2024)",
            viz_type=VisualizationType.PIVOT_TABLE,
            data_elements=["YtbsuPPo010"],
            periods=MONTHS_2024,
            organisation_units=DISTRICTS,
            uid=PIVOT_UID,
        )
        created = await client.visualizations.create_from_spec(spec)
        print(
            f"[pivot] {created.id}  rows={created.rowDimensions} "
            f"columns={created.columnDimensions} filters={created.filterDimensions}",
        )

        await client.visualizations.delete(PIVOT_UID)
        print("[deleted]")


if __name__ == "__main__":
    run_example(main)
