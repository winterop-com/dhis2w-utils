"""DashboardItem.user (v42) -> users (v43) — rename + reshape from Reference to list[User].

In v42 each `DashboardItem` carries a singular `user: Reference | None`.
In v43 the same wire field was renamed to `users` and reshaped to
`list[User]`. The hand-written `client.dashboards` accessor parses
against the v42 model, so on v43 wire data the new collection lands
under `model_extra` rather than as a typed attribute.

Two access paths are shown:

1. Branch on `client.version_key` and read v43 extras off
   `model_extra` (works without changing imports).
2. Bypass the v42-pinned helper via a direct
   `dhis2w_client.generated.v43.*` import for a typed v43 model.

Run this script on a v42 *and* a v43 instance — the output makes the
difference obvious.

Usage:
    uv run python examples/client/v43/dashboard_item_users.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client.generated.v43.schemas.dashboard import Dashboard as DashboardV43
from dhis2w_client.generated.v43.schemas.dashboard_item import DashboardItem as DashboardItemV43
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Read one dashboard's items and print the owner field per version."""
    async with open_client(profile_from_env()) as client:
        dashboards = await client.dashboards.list_all()
        if not dashboards:
            print("no dashboards on this instance — nothing to demonstrate")
            return
        dashboard = dashboards[0]
        print(f"version={client.version_key} dashboard={dashboard.id} name={dashboard.name!r}")

        # Path 1: read via the v42-typed helper, branching on version.
        for item in (dashboard.dashboardItems or [])[:3]:
            if client.version_key == "v43":
                users = (item.model_extra or {}).get("users") or []
                owners = [u.get("id") for u in users]
                print(f"  [extras] item {item.id} type={item.type} v43 users={owners}")
            else:
                owner = item.user.id if item.user else None
                print(f"  [typed v42] item {item.id} type={item.type} user={owner!r}")

        # Path 2: bypass the helper for typed v43 access. v43 declares
        # `Dashboard.dashboardItems: list[Any]` and `DashboardItem.users:
        # list[Any]`, so neither layer auto-converts to the nested model;
        # parse each item with `DashboardItemV43.model_validate(...)` and
        # treat its users as plain dicts (use `.get("id")`).
        if client.version_key == "v43":
            raw = await client.get_raw(f"/api/dashboards/{dashboard.id}")
            typed = DashboardV43.model_validate(raw)
            for item_raw in (typed.dashboardItems or [])[:3]:
                item_v43 = DashboardItemV43.model_validate(item_raw)
                owner_ids = [u.get("id") for u in (item_v43.users or [])]
                print(f"  [typed v43] item {item_v43.id} users={owner_ids}")


if __name__ == "__main__":
    run_example(main)
