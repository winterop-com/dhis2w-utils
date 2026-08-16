"""List every installed app + the configured App Hub catalog via `Dhis2Client.apps`.

Pairs with `examples/cli/apps.sh` (CLI path). Demonstrates the three
read verbs on the library surface: `list_apps()`, `hub_list()`, and the
`update_all()` logic reused from `dhis2w_core.plugins.apps.service`.

Usage:
    uv run python examples/client/apps.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Connect, list installed apps, then list the App Hub catalog — no writes."""
    async with open_client(profile_from_env()) as client:
        installed = await client.apps.list_apps()
        print(f"installed apps ({len(installed)}):")
        for app in installed:
            hub_marker = f"hub={app.app_hub_id}" if app.app_hub_id else "side-loaded"
            bundle_marker = "bundled" if app.bundled else hub_marker
            print(f"  {app.key:30s} {app.version or '-':10s}  {bundle_marker}")

        print()
        print("App Hub catalog (first 5 rows):")
        hub = await client.apps.hub_list()
        for row in hub[:5]:
            version_count = len(row.versions)
            print(f"  {row.id:40s} {row.name or '-':30s} {version_count} versions")


if __name__ == "__main__":
    run_example(main)
