"""Simplest Visualization creation path — `VisualizationSpec` + create_from_spec.

Covers the 80% case: pick a chart type, name a data element + periods +
org units, let the spec pick sensible dimensional placement, POST via
`/api/metadata`, get back a fully-populated typed `Visualization`.

Usage:
    uv run python examples/client/viz_create_basic.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import VisualizationSpec

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.enums import VisualizationType
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

VIZ_UID = "VizExBasic1"


async def main() -> None:
    """Create one COLUMN chart of Penta1 doses given by district for 2024."""
    async with open_client(profile_from_env()) as client:
        spec = VisualizationSpec(
            name="Example: Penta1 doses given by district (2024)",
            viz_type=VisualizationType.COLUMN,
            data_elements=["fClA2Erf6IO"],
            periods=["2025"],
            organisation_units=["jUb8gELQApl", "PMa2VCrupOd", "qhqAxPSTUXp", "kJq2mPyFEHo"],
            description="Seeded via examples/client/viz_create_basic.py",
            uid=VIZ_UID,
        )
        viz = await client.visualizations.create_from_spec(spec)
        print(f"[created] {viz.id}  type={viz.type}  name={viz.name!r}")
        print(f"  rows={viz.rowDimensions}  columns={viz.columnDimensions}  filters={viz.filterDimensions}")

        # Round-trip check — fetch it back to confirm the axes populated.
        fetched = await client.visualizations.get(VIZ_UID)
        assert fetched.id == VIZ_UID
        print("[verified] axes survived the metadata round-trip")

        # Clean up so reruns stay idempotent.
        await client.visualizations.delete(VIZ_UID)
        print("[deleted]")


if __name__ == "__main__":
    run_example(main)
