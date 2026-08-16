"""Create a thematic choropleth Map from flags — `MapSpec` + `MapLayerSpec`.

The seeded immunization stack has four districts with rough bounding
polygons in OU `geometry` — enough for a Sierra Leone-scoped choropleth
to render cleanly in the DHIS2 Maps app.

Usage:
    uv run python examples/client/map_create_choropleth.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import MapLayerSpec, MapSpec
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

MAP_UID = "MapExCh0001"


async def main() -> None:
    """Choropleth over four Sierra Leone districts for 2024 immunization doses."""
    async with open_client(profile_from_env()) as client:
        spec = MapSpec(
            name="Example: immunization doses 2024 choropleth",
            description="Seeded via examples/client/map_create_choropleth.py",
            uid=MAP_UID,
            longitude=15.0,
            latitude=64.5,
            zoom=4,
            basemap="openStreetMap",
            layers=[
                MapLayerSpec(
                    layer_kind="thematic",
                    name="Immunization doses (2024)",
                    data_elements=["YtbsuPPo010"],
                    periods=["2024"],
                    organisation_units=["ImspTQPwCqd"],
                    organisation_unit_levels=[2],
                    classes=5,
                    color_low="#fef0d9",
                    color_high="#b30000",
                ),
            ],
        )
        created = await client.maps.create_from_spec(spec)
        layer_count = len(created.mapViews or [])
        print(f"[created] {created.id}  name={created.name!r}  layers={layer_count}")
        print(f"  viewport: lon={created.longitude}  lat={created.latitude}  zoom={created.zoom}")

        # Clean up so reruns stay idempotent.
        await client.maps.delete(MAP_UID)
        print("[deleted]")


if __name__ == "__main__":
    run_example(main)
