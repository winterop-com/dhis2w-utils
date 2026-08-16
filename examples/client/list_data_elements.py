"""List data elements via the generated typed resources — pure `dhis2w-client`.

Demonstrates `Dhis2Client.resources` — the version-aware auto-generated
surface. After `connect()` binds the right version's module,
`client.resources.data_elements` is a typed accessor with pagination,
field selection, and a pydantic model return type.

This example uses **only `dhis2w-client`** (no `dhis2w-core` install
needed). It builds a `Profile` from `DHIS2_URL` + `DHIS2_PAT` /
`DHIS2_USERNAME` env vars and calls `dhis2w_client.open_client(profile)`
directly. For the full TOML profile resolution chain, see the
`dhis2w-core` examples that use `profile_from_env()`.

Usage:
    uv run python examples/client/list_data_elements.py [limit]

Env:
    DHIS2_URL  — base URL of your DHIS2 instance
    DHIS2_PAT  — Personal Access Token (or DHIS2_USERNAME + DHIS2_PASSWORD)
"""

from __future__ import annotations

import sys

from _runner import run_example
from dhis2w_client import NoProfileError, open_client, profile_from_env_raw


async def main() -> None:
    """Fetch up to `limit` data elements and print their uid + name."""
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    profile = profile_from_env_raw()
    if profile is None:
        raise NoProfileError("set DHIS2_URL + DHIS2_PAT (or DHIS2_USERNAME + DHIS2_PASSWORD)")
    async with open_client(profile) as client:
        elements = await client.resources.data_elements.list(
            fields="id,name,valueType,domainType",
            page_size=limit,
        )
        print(f"{len(elements)} data element(s) (DHIS2 {client.raw_version}):")
        for element in elements:
            print(
                f"  {element.id or '?':<12} "
                f"{element.name or '?':<40} "
                f"{str(element.valueType or '?'):<20} "
                f"{element.domainType or '?'}"
            )


if __name__ == "__main__":
    run_example(main)
