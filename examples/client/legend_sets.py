"""LegendSet authoring via `client.legend_sets` + application to a visualization.

Walks the canonical legend-set flow:

1. Build a `LegendSetSpec` from typed `LegendSpec` rows (one per colour
   range). DHIS2's own vocabulary is LegendSet + Legend — the spec
   names mirror that.
2. POST it via `client.legend_sets.create_from_spec(spec)` — one atomic
   `/api/metadata` call for the LegendSet + its inline Legend children.
3. Read it back via `client.legend_sets.get(uid)` + list every set on
   the instance via `client.legend_sets.list_all()`.
4. Attach the new set to an ad-hoc column viz via
   `VisualizationSpec(legend_set=<uid>)` — DHIS2 colours each bar by
   the matching legend at render time.
5. Clean up: delete the viz + the legend set.

Usage:
    uv run python examples/client/legend_sets.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import LegendSetSpec, LegendSpec, VisualizationSpec

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.enums import VisualizationType
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Build a LegendSet, apply it to a viz, print verification lines."""
    spec = LegendSetSpec(
        name="Demo coverage bands",
        code="DEMO_COVERAGE_BANDS",
        legends=[
            LegendSpec(start=0, end=50, color="#d73027", name="Low"),
            LegendSpec(start=50, end=80, color="#fdae61", name="Medium"),
            LegendSpec(start=80, end=120, color="#1a9850", name="High"),
        ],
    )

    async with open_client(profile_from_env()) as client:
        legend_set = await client.legend_sets.create_from_spec(spec)
        print(f"created legendSet {legend_set.id} name={legend_set.name!r} legends={len(legend_set.legends or [])}")

        # Round-trip check — fetch and show the legends we just wrote.
        fetched = await client.legend_sets.get(legend_set.id or "")
        for legend in fetched.legends or []:
            if isinstance(legend, dict):
                print(
                    f"  legend {legend.get('name')}: "
                    f"{legend.get('startValue')} – {legend.get('endValue')}  "
                    f"color={legend.get('color')}",
                )

        # Build a throw-away COLUMN viz that references the new legend set.
        viz_spec = VisualizationSpec(
            name="Demo: BCG doses 2024 with legend",
            viz_type=VisualizationType.COLUMN,
            data_elements=["s46m5MS0hxu"],  # BCG doses given (seeded DE)
            periods=[f"2024{m:02d}" for m in range(1, 13)],
            organisation_units=["ImspTQPwCqd"],  # Sierra Leone root
            category_dimension="pe",
            legend_set=legend_set.id,
        )
        viz = await client.visualizations.create_from_spec(viz_spec)
        print(f"created viz {viz.id} with legend_set={legend_set.id}")

        # Cleanup — keep the instance tidy after the demo runs.
        await client.visualizations.delete(viz.id or "")
        await client.legend_sets.delete(legend_set.id or "")
        print("cleaned up demo viz + legend set")


if __name__ == "__main__":
    run_example(main)
