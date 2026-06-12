"""Contract test: every taxonomy authority string exists in the live inventory.

The dangerous-authority taxonomy in `dhis2w_core.security_core.authorities`
hardcodes authority names. A name the running DHIS2 version does not define
can never be granted by current-version role editing and most likely gates
nothing -- matching on it gives false confidence. This test pins every
taxonomy string to the live `/api/authorities` inventory on the play
instances for v42 and v43.

v41 is exempt: its `/api/authorities` endpoint returns 500 (BUGS.md #45).

Marked `@pytest.mark.contract` so it runs in the dedicated CI job
(`.github/workflows/contract.yml`) and not as part of `make test`. Play
being unreachable skips rather than fails.
"""

from __future__ import annotations

import httpx
import pytest
from dhis2w_core.security_core import AUTHORITY_CATEGORIES

PLAY_URLS = {
    "v42": "https://play.im.dhis2.org/dev-2-42",
    "v43": "https://play.im.dhis2.org/dev-2-43",
}

TAXONOMY_STRINGS: frozenset[str] = frozenset().union(*(category.authorities for category in AUTHORITY_CATEGORIES))


async def _fetch_inventory(base_url: str) -> set[str]:
    """Return the authority id inventory from a live instance, skipping only if unreachable.

    Only network-level failures (`httpx.RequestError`) skip; an HTTP error
    status fails the test — a 401/500 from the endpoint must not turn into
    a green run that validated nothing.
    """
    try:
        async with httpx.AsyncClient(auth=("admin", "district"), timeout=30.0) as client:
            response = await client.get(f"{base_url}/api/authorities")
    except httpx.RequestError as exc:
        pytest.skip(f"play instance {base_url} unreachable: {exc}")
    response.raise_for_status()
    body = response.json()
    return {entry["id"] for entry in body.get("systemAuthorities", [])}


@pytest.mark.contract
@pytest.mark.parametrize("version", sorted(PLAY_URLS))
async def test_taxonomy_strings_exist_in_live_inventory(version: str) -> None:
    """Every authority string in the taxonomy is defined by the live instance."""
    inventory = await _fetch_inventory(PLAY_URLS[version])
    assert inventory, f"{version}: live inventory came back empty"
    unknown = sorted(TAXONOMY_STRINGS - inventory)
    assert not unknown, f"{version}: taxonomy strings not in the live /api/authorities inventory: {unknown}"
