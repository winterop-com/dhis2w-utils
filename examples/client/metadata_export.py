"""Pull a metadata bundle off an instance — `service.export_metadata`.

The service layer does the DHIS2 parameter mapping (`resources`, `fields`,
per-resource filters) and hands back a typed `MetadataBundle` rather than a
dict, so the resource keys are walked through `bundle.resources()` and the whole
thing serialises with `model_dump_json`.

`:owner` is the default field selector and the lossless one: every field the
object owns, which is what makes the bundle re-importable somewhere else.
Pushing one back is `metadata_bulk_import.py`.

Usage:
    uv run python examples/client/metadata_export.py
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from _runner import run_example
from dhis2w_core.profile import profile_from_env

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_core.v42.plugins.metadata import service


async def main() -> None:
    """Export a narrow slice, summarise it per resource, then a filtered one."""
    profile = profile_from_env()

    with TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"

        bundle = await service.export_metadata(
            profile,
            resources=["dataElements", "indicatorTypes"],
            fields=":owner",
        )
        bundle_path.write_text(
            bundle.model_dump_json(indent=2, exclude_none=True, by_alias=True),
            encoding="utf-8",
        )
        print(f"exported -> {bundle_path}")
        for resource, items in bundle.resources():
            print(f"  {resource}: {len(items)} objects")

        # `per_resource_filters` narrows the slice — one filter list per resource,
        # in the same `property:operator:value` DSL the CLI takes.
        narrowed = await service.export_metadata(
            profile,
            resources=["dataElements"],
            per_resource_filters={"dataElements": ["name:like:Penta"]},
        )
        print("\nfiltered to name like Penta:")
        for resource, items in narrowed.resources():
            print(f"  {resource}: {len(items)} objects")


if __name__ == "__main__":
    run_example(main)
