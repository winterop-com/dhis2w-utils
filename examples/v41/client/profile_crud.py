"""Profile CRUD from Python — both in-memory and on-disk paths.

Every `d2w profile ...` CLI command maps 1:1 onto a function in
`dhis2w_core.plugins.profile.service`. This example walks both paths:

1. **In-memory** — construct a `Profile(...)` and hand it straight to
   `open_client`. Nothing gets written anywhere; the profile exists only
   for the duration of the `async with`. Ideal for tests, multi-tenant
   services, throwaway sessions, anywhere you don't want disk state.

2. **On-disk** — `add_profile` / `rename_profile` / `set_default_profile` /
   `remove_profile`. These edit the TOML files the CLI reads. The demo
   uses a temp working directory with `scope="project"` so it writes to
   `<tmp>/.dhis2/profiles.toml`, not your real `~/.config/dhis2/profiles.toml`.

Usage:
    uv run python examples/v41/client/profile_crud.py

Requires `DHIS2_PAT` in env (the seeded local PAT is fine; sourcing
`infra/home/credentials/.env.auth` sets it).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile, load_catalog
from dhis2w_core.v42.plugins.profile import service


async def demo_in_memory() -> None:
    """In-memory profile — `Profile(...)` handed to `open_client`, never persisted."""
    print("--- 1. In-memory Profile(...) — no disk touch ---")

    profile = Profile(
        base_url="http://localhost:8080",
        auth="pat",
        token=os.environ["DHIS2_PAT"],
    )
    # `open_client` takes any Profile — it doesn't care where it came from.
    async with open_client(profile) as client:
        me = await client.system.me()
        print(f"  connected via ephemeral Profile; user={me.username}, version={client.raw_version}")

    # The profile instance is a plain pydantic model — inspect, diff, or serialise freely.
    print(f"  model_dump (secrets masked manually in real code): {profile.model_dump(exclude={'token'})}")


def demo_on_disk(start: Path) -> None:
    """On-disk CRUD — `add` / `show` / `list` / `rename` / `set-default` / `remove`.

    Scopes every write to `<start>/.dhis2/profiles.toml` so the real
    `~/.config/dhis2/profiles.toml` is untouched. `service.*_profile` calls
    are what the `d2w profile` CLI commands wrap, so anything you can do
    from the shell you can do from Python.
    """
    print("\n--- 2. On-disk CRUD via dhis2w_core.plugins.profile.service ---")

    tmp_profiles = start / ".dhis2" / "profiles.toml"
    print(f"  scope=project, target file: {tmp_profiles}")

    # CREATE / upsert. `make_default=True` writes `default = "demo_a"` alongside.
    result_a = service.add_profile(
        "demo_a",
        Profile(base_url="http://localhost:8080", auth="pat", token=os.environ["DHIS2_PAT"]),
        scope="project",
        make_default=True,
        start=start,
    )
    print(f"  added 'demo_a'      -> wrote {result_a.path.name}")

    # Second profile, same scope.
    service.add_profile(
        "demo_b",
        Profile(base_url="http://localhost:8080", auth="basic", username="admin", password="district"),
        scope="project",
        start=start,
    )
    print("  added 'demo_b'      -> (basic auth, not default)")

    # LIST — both in the project file we just wrote.
    summaries = service.list_profiles(start=start)
    for summary in summaries:
        default_marker = " [default]" if summary.is_default else ""
        print(f"  list: {summary.name:10}  auth={summary.auth}  source={summary.source}{default_marker}")

    # SHOW — full view of one profile (secrets masked unless `include_secrets=True`).
    shown = service.show_profile("demo_a", start=start)
    print(f"  show 'demo_a': base_url={shown.base_url}  auth={shown.auth}  token={shown.token!r}  (masked)")

    # RENAME in place.
    service.rename_profile("demo_a", "demo_a_renamed", start=start)
    print("  renamed 'demo_a' -> 'demo_a_renamed'")

    # SET DEFAULT — move the default flag to demo_b.
    service.set_default_profile("demo_b", scope="project", start=start)
    print("  set default = 'demo_b'")

    # Inspect the catalog programmatically (same data the CLI's `profile list` prints).
    # `catalog.project` is the raw ProfilesFile for the scope we wrote to.
    catalog = load_catalog(start=start)
    print(f"  catalog after rename+set-default: {sorted(catalog.project.profiles)}; default={catalog.project.default}")

    # REMOVE — clean up, back to an empty file.
    for name in ("demo_a_renamed", "demo_b"):
        service.remove_profile(name, scope="project", start=start)
    print("  removed both demo profiles")


async def main() -> None:
    """Run the in-memory demo, then the on-disk CRUD demo in an isolated temp dir."""
    await demo_in_memory()
    with tempfile.TemporaryDirectory() as tmp:
        demo_on_disk(Path(tmp))
    print("\n--- done; real ~/.config/dhis2/profiles.toml was untouched ---")


if __name__ == "__main__":
    run_example(main)
