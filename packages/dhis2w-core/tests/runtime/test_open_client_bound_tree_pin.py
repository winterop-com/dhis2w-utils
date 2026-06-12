"""Regression test: open_client threads the bound version tree as a pin.

When MCP has called `bind_version_tree()`, `open_client` passes that key
as `version=Dhis2(...)` to `Dhis2Client`. The client's on-connect
`/api/system/info` check then raises `VersionPinMismatchError` against
a wrong-major server even for per-call profiles that have no `.version`
field of their own — which is the realistic case: most profiles in the
wild won't bother to declare a `version` field.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_client.errors import VersionPinMismatchError
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile, bind_version_tree


@pytest.fixture(autouse=True)
def _reset_bound_tree() -> object:
    """Always clear the binding around each test so process-wide state can't leak."""
    bind_version_tree(None)
    yield None
    bind_version_tree(None)


@respx.mock
async def test_unpinned_profile_bound_tree_matches_server() -> None:
    """Unpinned profile bound tree matches server."""
    base_url = "http://mocked.match.example"
    respx.get(f"{base_url}/").mock(return_value=httpx.Response(200, text=""))
    respx.get(f"{base_url}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4", "revision": "abc"}),
    )
    bind_version_tree("v42")
    profile = Profile(base_url=base_url, auth="pat", token="d2pat_x")
    async with open_client(profile, system_cache_ttl=None) as client:
        assert client.version_key == "v42"


@respx.mock
async def test_unpinned_profile_bound_tree_mismatches_server_raises() -> None:
    """Unpinned profile bound tree mismatches server raises."""
    base_url = "http://mocked.mismatch.example"
    respx.get(f"{base_url}/").mock(return_value=httpx.Response(200, text=""))
    respx.get(f"{base_url}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.43.0", "revision": "abc"}),
    )
    bind_version_tree("v42")
    profile = Profile(base_url=base_url, auth="pat", token="d2pat_x")
    # Profile has no `.version` field — pre-fix, this would silently bind the
    # v42 plugin tree on top of v43 wire payloads. With the bound-tree pin
    # threaded into the client, connect() now raises VersionPinMismatchError.
    with pytest.raises(VersionPinMismatchError) as exc:
        async with open_client(profile, system_cache_ttl=None):
            pass
    assert exc.value.pinned == "v42"
    assert "2.43.0" in str(exc.value)


@respx.mock
async def test_unbound_path_unchanged_for_cli_usage() -> None:
    """Unbound path unchanged for cli usage."""
    base_url = "http://mocked.unbound.example"
    respx.get(f"{base_url}/").mock(return_value=httpx.Response(200, text=""))
    respx.get(f"{base_url}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.43.0", "revision": "abc"}),
    )
    # No bind_version_tree() call — the CLI's regular usage path. open_client
    # passes version=None so Dhis2Client auto-detects. v43 server → v43 tree.
    profile = Profile(base_url=base_url, auth="pat", token="d2pat_x")
    async with open_client(profile, system_cache_ttl=None) as client:
        assert client.version_key == "v43"
