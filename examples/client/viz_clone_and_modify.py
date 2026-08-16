"""Clone an existing Visualization, confirm the clone is independent.

Admin workflows often iterate by cloning a chart that's 90% right,
giving it a new name, and tweaking one or two fields. `clone()`
duplicates every data dimension / period / org-unit selection with a
fresh UID so the clone renders identically out of the gate.

Server-owned fields (`created`, `lastUpdated`, `createdBy`, `user`,
`access`, display-computed shortcuts) are stripped off the clone
payload so DHIS2 treats it as a net-new create rather than an update
of the source.

Usage:
    uv run python examples/client/viz_clone_and_modify.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import VisualizationSpec

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.enums import VisualizationType
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

SOURCE_UID = "VizExClSrc1"
CLONE_UID = "VizExClCpy1"


async def main() -> None:
    """Create a source chart, clone it, verify independence, clean up."""
    async with open_client(profile_from_env()) as client:
        source_spec = VisualizationSpec(
            name="Example: source chart (clone template)",
            viz_type=VisualizationType.LINE,
            data_elements=["fClA2Erf6IO"],
            periods=[f"2024{m:02d}" for m in range(1, 13)],
            organisation_units=["jUb8gELQApl", "PMa2VCrupOd", "qhqAxPSTUXp", "kJq2mPyFEHo"],
            uid=SOURCE_UID,
        )
        source = await client.visualizations.create_from_spec(source_spec)
        print(f"[source] {source.id}  name={source.name!r}")

        clone = await client.visualizations.clone(
            source.id or SOURCE_UID,
            new_name="Example: cloned chart (renamed)",
            new_uid=CLONE_UID,
            new_description="Cloned from viz_clone_and_modify.py; independent of source.",
        )
        print(f"[clone]  {clone.id}  name={clone.name!r}")

        # Independence check: deleting the source must not break the clone.
        await client.visualizations.delete(SOURCE_UID)
        still_there = await client.visualizations.get(CLONE_UID)
        assert still_there.id == CLONE_UID, "clone should survive source deletion"
        print("[verified] clone survives source deletion")

        await client.visualizations.delete(CLONE_UID)
        print("[deleted]")


if __name__ == "__main__":
    run_example(main)
