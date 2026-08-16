"""Pull DHIS2 org units as GeoJSON, validate with geojson-pydantic.

Demonstrates `/api/organisationUnits.geojson`. Parses the response
through `geojson_pydantic.FeatureCollection` so coordinates, geometry
types, and properties are all typed — no manual `dict.get(...)` chains.

By default the seeded Sierra Leone fixture has no geometries, so this
example falls back to showing the feature-free FeatureCollection. Against
a real instance (or after PATCH /api/organisationUnits/{uid} with a
geometry) you'll see real coordinates.

Usage:
    uv run python examples/client/geojson_org_units.py [level]

Env: same as 01_whoami.py.
"""

from __future__ import annotations

import sys

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env
from geojson_pydantic import FeatureCollection


async def main() -> None:
    """Fetch org-unit GeoJSON at `level` and print a typed summary."""
    level = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    async with open_client(profile_from_env()) as client:
        payload = await client.get_raw(
            "/api/organisationUnits.geojson",
            params={"level": level, "includeCoordinates": "true"},
        )
    # Validate through geojson-pydantic — gives us .features typed as
    # list[Feature[Geometry, Properties]] with real coordinate types.
    collection: FeatureCollection = FeatureCollection.model_validate(payload)
    print(f"level {level}: {len(collection.features)} feature(s)")
    for feature in collection.features[:5]:
        props = feature.properties or {}
        geom_type = feature.geometry.type if feature.geometry else "(none)"
        print(f"  {str(props.get('id', '?')):<12} {str(props.get('name', '?')):<28} geometry_type={geom_type}")
    if not collection.features:
        print("  (no geometries on the seeded fixture — PATCH a geometry onto an OU to see coordinates)")


if __name__ == "__main__":
    run_example(main)
