"""Bulk metadata patch — apply a CSV of `uid,path,value` to many objects concurrently.

Real-world pattern: a domain user ships a CSV of "change these fields on these
UIDs" and you want to apply it across a DHIS2 instance quickly. Each row
becomes one RFC 6902 `replace` op wrapped in a one-op patch call; all patches
run concurrently via `asyncio.gather`.

CSV format (header required):
    uid,resource,path,value
    fClA2Erf6IO,dataElements,/description,Updated via CSV
    UOlfIjgN8X6,dataElements,/shortName,FullyImm
    indIndicator01,indicators,/denominatorDescription,Denominator

Empty values translate to an RFC 6902 `remove` op. Values that parse as JSON
(`true`, `42`, `{"k":1}`) are decoded so booleans / numbers / nested objects
type through correctly.

Usage:
    uv run python examples/client/bulk_patch_from_csv.py patches.csv
    (no argument: generates + patches + reverts a tiny demo CSV)
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
import tempfile
from io import StringIO
from pathlib import Path

from _runner import run_example
from dhis2w_client import JsonPatchOp, JsonPatchOpAdapter, WebMessageResponse
from dhis2w_core.profile import Profile, profile_from_env

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_core.v42.plugins.metadata import service

_DEMO_CSV = """uid,resource,path,value
fClA2Erf6IO,dataElements,/description,Updated via bulk CSV
UOlfIjgN8X6,dataElements,/shortName,FullyImm
"""


def _row_to_op(path: str, raw_value: str) -> JsonPatchOp:
    """Convert a `path,value` CSV row into the matching RFC 6902 op.

    Empty value -> `remove`. Non-empty value -> `replace`; values that parse
    as JSON (booleans, numbers, nested objects) are decoded, strings pass through.
    """
    if raw_value == "":
        return JsonPatchOpAdapter.validate_python({"op": "remove", "path": path})
    try:
        value: object = json.loads(raw_value)
    except json.JSONDecodeError:
        value = raw_value
    return JsonPatchOpAdapter.validate_python({"op": "replace", "path": path, "value": value})


async def apply_csv(profile: Profile, reader: csv.DictReader[str]) -> list[WebMessageResponse]:
    """Read rows and fire one concurrent `patch_metadata` call per row."""
    tasks: list[asyncio.Task[WebMessageResponse]] = []
    seen: list[tuple[str, str, str]] = []  # (resource, uid, path) for summary
    for row in reader:
        uid = row["uid"].strip()
        resource = row["resource"].strip()
        path = row["path"].strip()
        value = row.get("value", "").strip()
        op = _row_to_op(path, value)
        tasks.append(asyncio.create_task(service.patch_metadata(profile, resource, uid, [op])))
        seen.append((resource, uid, path))
    print(f"dispatching {len(tasks)} patch calls concurrently ...")
    responses = await asyncio.gather(*tasks)
    for (resource, uid, path), response in zip(seen, responses, strict=False):
        print(f"  {resource}/{uid} {path}: status={response.status}")
    return responses


async def main() -> None:
    """Run the bulk-patch workflow; revert the demo fixture if no CSV was passed."""
    profile = profile_from_env()

    # Positional arg = path to CSV. Omit for the self-contained demo.
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
        print(f"reading {csv_path}")
        with csv_path.open(newline="", encoding="utf-8") as f:
            await apply_csv(profile, csv.DictReader(f))
        return

    # Self-contained demo: patch the seeded immunization data elements, then revert.
    print("--- no CSV supplied; using built-in demo (immunization data elements) ---")
    print(_DEMO_CSV)
    reader = csv.DictReader(StringIO(_DEMO_CSV))
    await apply_csv(profile, reader)

    print("\n--- reverting demo state so the example is idempotent ---")
    revert_csv = (
        "uid,resource,path,value\n"
        "fClA2Erf6IO,dataElements,/description,\n"  # empty -> remove
        "UOlfIjgN8X6,dataElements,/shortName,Fully Immunized\n"  # DHIS2's seeded default
    )
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as tmp:
        tmp.write(revert_csv)
        revert_path = Path(tmp.name)
    with revert_path.open(newline="", encoding="utf-8") as f:
        await apply_csv(profile, csv.DictReader(f))


if __name__ == "__main__":
    run_example(main)
