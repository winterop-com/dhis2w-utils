"""Map.basemaps — v43 adds a collection of Basemap to every Map.

v42 had no `basemaps` field on `Map`. v43 adds `basemaps: list[Basemap]`,
plus a new top-level `Basemap` model in the OAS tree
(`dhis2w_client.generated.v43.oas.basemap.Basemap`).

Usage:
    uv run python examples/client/v43/map_basemaps.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client.generated.v43.oas.basemap import Basemap
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Read one Map and surface the v43-only `basemaps` collection."""
    async with open_client(profile_from_env()) as client:
        maps = await client.maps.list_all()
        if not maps:
            print("no maps on this instance")
            return
        map_obj = maps[0]
        print(f"version={client.version_key} map={map_obj.id} name={map_obj.name!r}")

        if client.version_key != "v43":
            print("  v42: Map.basemaps does not exist")
            return

        # Path 1: read the v43 collection off model_extra on the v42-typed helper.
        extras = map_obj.model_extra or {}
        raw_basemaps = extras.get("basemaps") or []
        print(f"  [extras] count={len(raw_basemaps)}")

        # Path 2: typed access via the new v43 Basemap model.
        if raw_basemaps:
            typed = [Basemap.model_validate(bm) for bm in raw_basemaps]
            for basemap in typed:
                print(f"  [typed] basemap id={basemap.id} hidden={basemap.hidden} opacity={basemap.opacity}")


if __name__ == "__main__":
    run_example(main)
