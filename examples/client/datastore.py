"""DHIS2 key-value data store — namespaced get/set/delete via the client.

`/api/dataStore` is DHIS2's instance-wide key/value store for app/instance state; the per-user
`/api/userDataStore` is the same shape (pass `user=True`). Stored values are arbitrary JSON.

This rounds a value through a demo namespace — set, read back, list, then delete the namespace so
nothing is left behind.

Usage:
    uv run python examples/client/datastore.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.profile import profile_from_env

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_core.v42.plugins.datastore import service

NAMESPACE = "dhis2w_utils_demo"  # demo namespace — created + deleted by this script.
KEY = "example"


async def main() -> None:
    """Round-trip a value through the data store, then clean up the demo namespace."""
    profile = profile_from_env()

    await service.set_value(profile, NAMESPACE, KEY, {"hello": "world", "count": 42})
    print(f"set {NAMESPACE}/{KEY}")

    value = await service.get_value(profile, NAMESPACE, KEY)
    print(f"get {NAMESPACE}/{KEY} -> {value}")

    keys = await service.list_keys(profile, NAMESPACE)
    print(f"keys in {NAMESPACE}: {keys}")

    namespaces = await service.list_namespaces(profile)
    print(f"store currently has {len(namespaces)} namespaces")

    await service.delete_namespace(profile, NAMESPACE)
    print(f"cleaned up namespace {NAMESPACE}")


if __name__ == "__main__":
    run_example(main)
