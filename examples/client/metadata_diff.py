"""Client-level example — use the `metadata` plugin service directly for diff workflows.

Mirrors the CLI's `d2w metadata diff` but calls `service.diff_bundles` /
`service.diff_bundle_against_instance` directly, so you can wire a diff into
a Python pipeline (CI drift detection, pre-import safety checks, etc.).

Usage:
    uv run python examples/client/metadata_diff.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _runner import run_example
from dhis2w_core.profile import profile_from_env

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_core.v42.plugins.metadata import service
from dhis2w_core.v42.plugins.metadata.models import MetadataBundle


async def main() -> None:
    """Compare a fresh live export against a synthetic baseline + surface per-resource deltas."""
    profile = profile_from_env()

    # In real use the baseline would come from git / an artefact store. Here we
    # export the live catalog, deep-copy it, mutate the copy, and diff to show
    # how the machinery reports structural changes.
    live_bundle = await service.export_metadata(
        profile,
        resources=["dataElements"],
        fields=":owner",
    )
    # Serialise -> parse to get an independent bundle we can mutate safely.
    baseline_raw = json.loads(live_bundle.model_dump_json(exclude_none=True, by_alias=True))
    if baseline_raw.get("dataElements"):
        baseline_raw["dataElements"][0]["name"] = "BASELINE DRIFT"
    baseline = MetadataBundle.from_raw(baseline_raw)

    diff = service.diff_bundles(
        baseline,
        live_bundle,
        left_label="baseline.json",
        right_label="instance",
    )
    print(f"diff {diff.left_label} -> {diff.right_label}")
    for resource in diff.resources:
        print(
            f"  {resource.resource}: "
            f"+{len(resource.created)} ~{len(resource.updated)} "
            f"-{len(resource.deleted)} ={resource.unchanged_count}"
        )
        for change in resource.updated[:3]:
            fields = ", ".join(change.changed_fields)
            print(f"    updated {change.id} ({change.name or '-'}): {fields}")

    # Convenience: compare a file-on-disk against the live instance in one call.
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        tmp.write(baseline.model_dump_json(indent=2, exclude_none=True, by_alias=True))
        baseline_path = Path(tmp.name)
    baseline_from_disk = MetadataBundle.from_raw(json.loads(baseline_path.read_text(encoding="utf-8")))
    live_diff = await service.diff_bundle_against_instance(
        profile,
        baseline_from_disk,
        bundle_label=baseline_path.name,
    )
    print(
        f"\nlive vs {baseline_path.name}: "
        f"+{live_diff.total_created} ~{live_diff.total_updated} -{live_diff.total_deleted}"
    )


if __name__ == "__main__":
    run_example(main)
