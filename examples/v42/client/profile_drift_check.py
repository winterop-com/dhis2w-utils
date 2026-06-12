"""Profile drift check — diff metadata between two profiles (e.g. staging vs prod).

Useful as a CI guard: export the same resource slice from two profiles, run a
structural diff, exit non-zero when the diff isn't empty. Catches configuration
drift before it causes production surprises.

This demo uses the same profile twice to guarantee a clean `0 changed` diff.
In a real pipeline, swap `profile_a` / `profile_b` for two different profiles
(e.g. `resolve_profile("staging")` + `resolve_profile("prod")`) and pipe the
result into whatever alerting you already have.

For a CLI equivalent of this pattern, see:

    d2w metadata diff-profiles <a> <b> -r dataElements -r indicators \
        --filter dataElements:name:like:Penta --exit-on-drift

Exit code:
    0  -> no drift
    1  -> drift detected (prints per-resource counts on stderr)

Usage:
    uv run python examples/v42/client/profile_drift_check.py
"""

from __future__ import annotations

import sys

from _runner import run_example
from dhis2w_core.profile import Profile, profile_from_env, resolve_profile
from dhis2w_core.v42.plugins.metadata import service


async def drift(resource_types: list[str], profile_a: Profile, profile_b: Profile, *, fields: str = ":owner") -> int:
    """Export + diff two profiles; return 0 on clean, 1 on any structural change."""
    print(f"exporting {resource_types} from {profile_a.base_url} ...")
    bundle_a = await service.export_metadata(profile_a, resources=resource_types, fields=fields)
    print(f"exporting {resource_types} from {profile_b.base_url} ...")
    bundle_b = await service.export_metadata(profile_b, resources=resource_types, fields=fields)

    diff = service.diff_bundles(
        bundle_a,
        bundle_b,
        left_label=f"A ({profile_a.base_url})",
        right_label=f"B ({profile_b.base_url})",
    )
    if diff.total_created + diff.total_updated + diff.total_deleted == 0:
        print(f"no drift across {len(diff.resources)} resource collections.")
        return 0

    print(
        f"DRIFT: +{diff.total_created} / ~{diff.total_updated} / -{diff.total_deleted}",
        file=sys.stderr,
    )
    for resource in diff.resources:
        if resource.total_changed == 0:
            continue
        print(
            f"  {resource.resource}: +{len(resource.created)} ~{len(resource.updated)} -{len(resource.deleted)}",
            file=sys.stderr,
        )
    return 1


async def main() -> None:
    """Compare a resource slice between two profiles. Demo uses the active profile twice."""
    default_profile = profile_from_env()

    # CI usage: replace these two lines with `resolve_profile("staging")` and
    # `resolve_profile("prod")` — or any two profiles you've registered.
    profile_a = default_profile
    profile_b = resolve_profile(None)

    exit_code = await drift(["dataElements", "indicators"], profile_a, profile_b)
    sys.exit(exit_code)


if __name__ == "__main__":
    run_example(main)
