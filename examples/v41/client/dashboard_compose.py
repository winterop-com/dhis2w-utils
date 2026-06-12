"""Compose a dashboard from scratch — two KPI tiles + a line chart below.

Shows the full authoring loop when building automated dashboards (e.g.
"weekly KPI dashboard" jobs):

1. Create each visualization via `VisualizationSpec` + `create_from_spec`.
2. Create an empty `Dashboard` via the generated CRUD accessor.
3. Call `dashboards.add_item(dashboard_uid, viz_uid, slot=...)` for each
   item. Explicit `DashboardSlot` lets two KPI tiles sit side-by-side
   above a full-width chart.
4. (Optional) Screenshot via `d2w browser dashboard screenshot`.

Usage:
    uv run python examples/v41/client/dashboard_compose.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import DashboardSlot, VisualizationSpec
from dhis2w_client.generated.v42.enums import VisualizationType
from dhis2w_client.generated.v42.schemas import Dashboard
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

DASHBOARD_UID = "DashExCmp01"
KPI_PENTA1_UID = "VizExCmpKp1"
KPI_MEASLES_UID = "VizExCmpKp2"
LINE_UID = "VizExCmpLn1"


async def main() -> None:
    """Build three vizes + compose them into one dashboard."""
    async with open_client(profile_from_env()) as client:
        # ---- KPI: Penta1 doses given, 2024 annual total at Sierra Leone root ----
        kpi_penta1 = await client.visualizations.create_from_spec(
            VisualizationSpec(
                name="Example compose: Penta1 2024 total",
                viz_type=VisualizationType.SINGLE_VALUE,
                data_elements=["fClA2Erf6IO"],
                periods=["2024"],
                organisation_units=["ImspTQPwCqd"],
                uid=KPI_PENTA1_UID,
            ),
        )

        # ---- KPI: Measles doses given, 2024 annual total ----
        kpi_measles = await client.visualizations.create_from_spec(
            VisualizationSpec(
                name="Example compose: Measles 2024 total",
                viz_type=VisualizationType.SINGLE_VALUE,
                data_elements=["YtbsuPPo010"],
                periods=["2024"],
                organisation_units=["ImspTQPwCqd"],
                uid=KPI_MEASLES_UID,
            ),
        )

        # ---- LINE: Penta1 monthly by district for 2024 ----
        line = await client.visualizations.create_from_spec(
            VisualizationSpec(
                name="Example compose: Penta1 monthly by district",
                viz_type=VisualizationType.LINE,
                data_elements=["fClA2Erf6IO"],
                periods=[f"2024{m:02d}" for m in range(1, 13)],
                organisation_units=["jUb8gELQApl", "PMa2VCrupOd", "qhqAxPSTUXp", "kJq2mPyFEHo"],
                uid=LINE_UID,
            ),
        )
        print(f"[created vizes] {kpi_penta1.id}, {kpi_measles.id}, {line.id}")

        # ---- Create the empty dashboard shell via generated CRUD ----
        await client.resources.dashboards.create(
            Dashboard.model_validate(
                {
                    "id": DASHBOARD_UID,
                    "name": "Example composed dashboard",
                    "description": "Built by dashboard_compose.py — two KPI tiles + one line chart.",
                    "dashboardItems": [],
                },
            ),
        )
        print(f"[created dashboard] {DASHBOARD_UID}")

        # ---- Add items with explicit slots ----
        # Two KPI tiles across the top (each 30 wide × 15 tall).
        await client.dashboards.add_item(
            DASHBOARD_UID,
            kpi_penta1.id or KPI_PENTA1_UID,
            slot=DashboardSlot(x=0, y=0, width=30, height=15),
        )
        await client.dashboards.add_item(
            DASHBOARD_UID,
            kpi_measles.id or KPI_MEASLES_UID,
            slot=DashboardSlot(x=30, y=0, width=30, height=15),
        )
        # Line chart full width below (auto-stacks below y=15).
        await client.dashboards.add_item(
            DASHBOARD_UID,
            line.id or LINE_UID,
        )
        print("[composed] 3 items placed on the dashboard")

        # Fetch the final shape for verification.
        final = await client.dashboards.get(DASHBOARD_UID)
        items = list(final.dashboardItems or [])
        print(f"[verified] dashboard has {len(items)} items")
        for item in items:
            x = getattr(item, "x", None) if not isinstance(item, dict) else item.get("x")
            y = getattr(item, "y", None) if not isinstance(item, dict) else item.get("y")
            w = getattr(item, "width", None) if not isinstance(item, dict) else item.get("width")
            h = getattr(item, "height", None) if not isinstance(item, dict) else item.get("height")
            print(f"  item slot=(x={x}, y={y}, w={w}, h={h})")

        # Clean up so reruns stay idempotent.
        await client.resources.dashboards.delete(DASHBOARD_UID)
        for uid in (KPI_PENTA1_UID, KPI_MEASLES_UID, LINE_UID):
            await client.visualizations.delete(uid)
        print("[deleted]")


if __name__ == "__main__":
    run_example(main)
