"""Multi-line time-series — one line per org unit, months on the x-axis.

This is the canonical "trend by region" chart shape. `LINE`'s default
placement (`rows=[pe]`, `columns=[ou]`, `filters=[dx]`) already maps
time to the x-axis and districts to the series, so the spec stays
tiny.

Usage:
    uv run python examples/v41/client/viz_multiline_by_province.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import VisualizationSpec
from dhis2w_client.generated.v42.enums import VisualizationType
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

VIZ_UID = "VizExMulti1"
DISTRICTS = ["jUb8gELQApl", "PMa2VCrupOd", "qhqAxPSTUXp", "kJq2mPyFEHo"]
MONTHS = [f"2025{m:02d}" for m in range(1, 13)]


async def main() -> None:
    """Multi-line Penta1 chart: 4 districts × 12 months."""
    async with open_client(profile_from_env()) as client:
        # First sanity-check: analytics must return non-zero values before
        # a chart will render anything useful. Pull one period as a probe.
        probe = await client.get_raw(
            "/api/analytics",
            params={
                "dimension": ["dx:fClA2Erf6IO", "pe:202506", f"ou:{';'.join(DISTRICTS)}"],
                "skipMeta": "true",
            },
        )
        rows = probe.get("rows") or []
        if not rows:
            raise RuntimeError("analytics returned zero rows — run `d2w maintenance refresh-analytics`")
        print(f"[analytics probe] 202506 rows={len(rows)} (non-zero, safe to render)")

        spec = VisualizationSpec(
            name="Example: Penta1 doses monthly by district (2025)",
            viz_type=VisualizationType.LINE,
            data_elements=["fClA2Erf6IO"],
            periods=MONTHS,
            organisation_units=DISTRICTS,
            uid=VIZ_UID,
        )
        viz = await client.visualizations.create_from_spec(spec)
        print(f"[created] {viz.id}  series={viz.columnDimensions}  category={viz.rowDimensions}")

        await client.visualizations.delete(VIZ_UID)
        print("[deleted]")


if __name__ == "__main__":
    run_example(main)
