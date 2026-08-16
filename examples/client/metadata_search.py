"""Cross-resource metadata search via `client.metadata.search`.

One verb, three match axes (UID, code, name), every DHIS2 resource type
hit in parallel. Useful workflow: you have *some* identifier — a log
line UID, a partial code, or a name fragment — and want to know which
resource owns it before drilling into the typed accessor.

`MetadataAccessor.search` fans out three concurrent `/api/metadata`
requests (one per `<field>:ilike:<q>` axis) and merges the bundles into
a `SearchResults` model grouped by resource type, deduplicated by UID.

Usage:
    uv run python examples/client/metadata_search.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import NoProfileError, open_client, profile_from_env_raw


async def main() -> None:
    """Demonstrate UID / partial-UID / code / name searches against the seed."""
    profile = profile_from_env_raw()
    if profile is None:
        raise NoProfileError("set DHIS2_URL + DHIS2_PAT (or DHIS2_USERNAME + DHIS2_PASSWORD)")
    async with open_client(profile) as client:
        # 1. Name fragment — the broadest pattern, matches across every resource.
        results = await client.metadata.search("measles")
        print(f"'measles' matched {results.total} objects across {len(results.hits)} resources")
        for resource, hits in results.hits.items():
            print(f"  {resource}: {len(hits)}")

        # 2. Full UID — id:ilike:<uid> hits exactly one object.
        results = await client.metadata.search("s46m5MS0hxu")
        flat = results.flat()
        if flat:
            hit = flat[0]
            print(f"\ns46m5MS0hxu -> {hit.resource}/{hit.uid}: {hit.name}")

        # 3. Partial UID — id:ilike:<prefix> works as a substring match.
        results = await client.metadata.search("s46m")
        print(f"\n's46m' (partial UID) matched {results.total} object(s)")

        # 4. Business code — code:ilike:<fragment> for interop / mapping tables.
        results = await client.metadata.search("DE_3597")
        print(f"\n'DE_3597' (code) matched {results.total} data element(s)")

        # 5. Narrow per-resource page size to avoid huge result sets.
        results = await client.metadata.search("imm", page_size=5)
        print(f"\n'imm' (page_size=5) matched {results.total} object(s)")


if __name__ == "__main__":
    run_example(main)
