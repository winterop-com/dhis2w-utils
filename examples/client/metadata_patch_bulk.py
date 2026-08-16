"""Bulk RFC 6902 patch across many UIDs on one resource — client-side fan-out.

DHIS2 does not expose a single bulk-PATCH endpoint. The library fans
out concurrent `PATCH /api/<resource>/<uid>` calls and merges the
results into one typed `BulkPatchResult`. Per-UID failures land in
`.failures` instead of raising, so callers see row-level detail
without exception handling.

Usage:
    uv run python examples/client/metadata_patch_bulk.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import ReplaceOp
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Rename the first two DataElements found, then rename them back."""
    async with open_client(profile_from_env()) as client:
        data_elements = await client.data_elements.list_all(page_size=2)
        if len(data_elements) < 2:
            print("need at least two data elements on the instance to run this example")
            return
        first, second = data_elements[0], data_elements[1]
        original_first = first.shortName or ""
        original_second = second.shortName or ""
        print(f"original shortNames: {first.id}={original_first!r}  {second.id}={original_second!r}")

        # Bulk-patch shortName on both DEs in parallel.
        result = await client.metadata.patch_bulk(
            "dataElements",
            [
                (first.id or "", [ReplaceOp(op="replace", path="/shortName", value="BulkPatched1")]),
                (second.id or "", [ReplaceOp(op="replace", path="/shortName", value="BulkPatched2")]),
            ],
        )
        print(f"patched: {len(result.successful_uids)} ok, {len(result.failures)} failed")
        assert result.ok, f"unexpected failures: {result.failures}"

        # Verify the new names stuck.
        refreshed = await client.data_elements.get(first.id or "")
        print(f"refreshed first.shortName={refreshed.shortName!r}")

        # Revert in one bulk call.
        await client.metadata.patch_bulk(
            "dataElements",
            [
                (first.id or "", [ReplaceOp(op="replace", path="/shortName", value=original_first)]),
                (second.id or "", [ReplaceOp(op="replace", path="/shortName", value=original_second)]),
            ],
        )
        print("reverted both DEs to original shortNames")


if __name__ == "__main__":
    run_example(main)
