"""Export + import a metadata bundle — typed round-trip via the service layer.

Shows the cross-instance dev workflow: pull a slice from the source, optionally
transform it in Python, then push the bundle to a target. The service layer
(`export_metadata` / `import_metadata`) does the full DHIS2 parameter mapping
(`importStrategy`, `atomicMode`, `dryRun`, `skipSharing`, ...) and returns a
typed `WebMessageResponse` with the full import report.

Usage:
    uv run python examples/client/metadata_export_import.py
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from _runner import run_example

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.oas import AtomicMode, ImportStrategy
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v42.plugins.metadata import service


async def main() -> None:
    """Export a narrow bundle, summarise, dry-run re-import, print the report."""
    profile = profile_from_env()

    with TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"

        # 1. Export a dataElements + indicatorTypes slice with lossless `:owner` fields.
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

        # 2. Print a per-resource count summary.
        for resource, items in bundle.resources():
            print(f"  {resource}: {len(items)} objects")

        # 3. Dry-run import against the same instance — validates + preheats without committing.
        #    Typed enums from OAS codegen (`ImportStrategy`, `AtomicMode`, ...) — raw strings
        #    also work on the wire since StrEnum members ARE strings.
        report = await service.import_metadata(
            profile,
            bundle,
            import_strategy=ImportStrategy.CREATE_AND_UPDATE,
            atomic_mode=AtomicMode.ALL,
            dry_run=True,
        )
        print(f"\ndry-run import: status={report.status or report.httpStatus or '?'}")
        counts = report.import_count()
        if counts is not None:
            print(
                f"  imported={counts.imported} updated={counts.updated} "
                f"ignored={counts.ignored} deleted={counts.deleted}"
            )
        for conflict in report.conflicts()[:5]:
            print(f"  conflict: {conflict.property} = {conflict.value} [{conflict.errorCode}]")


if __name__ == "__main__":
    run_example(main)
