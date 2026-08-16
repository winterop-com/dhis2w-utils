"""Apply RFC 6902 JSON Patch ops to a metadata object — library-level usage.

Two entry points into the same feature:

1. `client.resources.<resource>.patch(uid, ops)` — the generated accessor.
   Lowest-level, no service layer, typed per-resource. Returns the raw
   DHIS2 payload (dict at the HTTP boundary).
2. `service.patch_metadata(profile, resource, uid, ops)` — plugin service.
   Accepts resource name as a string (so you can parameterise without
   imports), and returns a typed `WebMessageResponse`.

Both accept typed `AddOp` / `ReplaceOp` / `RemoveOp` / ... variants or raw
`{op, path, ...}` dicts interchangeably — dicts route through
`JsonPatchOpAdapter` at the wire boundary.

Usage:
    uv run python examples/client/metadata_patch.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import (
    AddOp,
    JsonPatchOpAdapter,
    RemoveOp,
    ReplaceOp,
    WebMessageResponse,
)
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_core.v42.plugins.metadata import service


async def main() -> None:
    """Walk through the two patch entry points against a seeded dataElement."""
    profile = profile_from_env()

    async with open_client(profile) as client:
        # Pick the first dataElement from the seeded fixture as our target.
        elements = await client.resources.data_elements.list(page_size=1, fields="id,name,description")
        if not elements:
            print("no dataElements available; seed the stack first")
            return
        target = elements[0]
        uid = target.id
        assert uid is not None
        print(f"target: dataElements/{uid}  (name={target.name!r})")

        # 1. Generated accessor path — typed ops, raw dict return. Multiple ops in one call.
        print("\n--- 1. Generated accessor: client.resources.data_elements.patch(...)")
        await client.resources.data_elements.patch(
            uid,
            [
                ReplaceOp(path="/description", value="Patched via generated accessor"),
                AddOp(path="/formName", value="Antenatal Visit 1"),
            ],
        )
        readback = await client.resources.data_elements.get(uid, fields="id,name,description,formName")
        print(f"  description after: {readback.description!r}")
        print(f"  formName after: {readback.formName!r}")

        # 2. Service path — typed WebMessageResponse return; accepts mixed typed + dict ops.
        print("\n--- 2. Service: patch_metadata(..., ops=[...]) — typed + dict ops mixed freely")
        response: WebMessageResponse = await service.patch_metadata(
            profile,
            "dataElements",
            uid,
            [
                ReplaceOp(path="/description", value="Patched via service"),
                # Raw dict form — goes through JsonPatchOpAdapter to pick the right variant.
                {"op": "add", "path": "/code", "value": "PATCH_EXAMPLE"},
            ],
        )
        print(f"  WebMessageResponse.status={response.status!r}")
        readback = await client.resources.data_elements.get(uid, fields="id,name,description,code")
        print(f"  description after: {readback.description!r}")
        print(f"  code after: {readback.code!r}")

        # 3. Validate an op from an untrusted dict source (JSON on disk, agent input, ...).
        print("\n--- 3. `JsonPatchOpAdapter.validate_python` — safe dict→typed op")
        untrusted = {"op": "remove", "path": "/code"}
        op = JsonPatchOpAdapter.validate_python(untrusted)
        print(f"  parsed to: {type(op).__name__}({op})")
        await service.patch_metadata(profile, "dataElements", uid, [op])

        # Revert the fields we touched so the example is idempotent.
        print("\n--- cleanup: revert the fixture so the example can re-run cleanly")
        await client.resources.data_elements.patch(
            uid,
            [
                ReplaceOp(path="/description", value=target.description or ""),
                RemoveOp(path="/code"),
                RemoveOp(path="/formName"),
            ],
        )
        final = await client.resources.data_elements.get(uid, fields="id,description,code,formName")
        print(f"  final description: {final.description!r}")
        print(f"  final code: {final.code!r}")
        print(f"  final formName: {final.formName!r}")


if __name__ == "__main__":
    run_example(main)
