"""Smoke matrix for the v41 client tree — broad-not-deep guardrails.

Covers the structural surface that lives in `dhis2w_client.v41.*`:
import-time correctness, the connect/version-handshake happy path,
one accessor read, and the auth-provider construction. Pairs with
the equivalent `test_v43_smoke.py` so divergent v41/v43 surfaces
both have a basic regression gate. Deeper accessor / wire-shape
behaviour is exercised by `test_v41_*_retargeted.py` files.
"""

from __future__ import annotations

import httpx
import respx
from dhis2w_client.generated import Dhis2
from dhis2w_client.v41 import (
    BasicAuth,
    Dhis2Client,
    PatAuth,
    Profile,
    build_auth_provider,
    open_client,
)


def test_v41_top_level_imports_resolve() -> None:
    """v41 top-level imports resolve."""
    # If any of these are mis-bound, the import line would already have raised.
    assert Dhis2Client.__module__ == "dhis2w_client.v41.client"
    assert PatAuth.__module__ == "dhis2w_client.v41.auth.pat"
    assert BasicAuth.__module__ == "dhis2w_client.v41.auth.basic"


def test_v41_build_auth_provider_pat() -> None:
    """v41 build auth for basic pat."""
    provider = build_auth_provider(Profile(base_url="http://x", auth="pat", token="d2p_x"))
    assert isinstance(provider, PatAuth)


def test_v41_build_auth_provider_basic() -> None:
    """v41 build auth for basic basic."""
    provider = build_auth_provider(Profile(base_url="http://x", auth="basic", username="admin", password="district"))
    assert isinstance(provider, BasicAuth)


@respx.mock
async def test_v41_open_client_runs_handshake_and_binds_v41_tree() -> None:
    """v41 open client runs handshake and binds v41 tree."""
    base_url = "http://mocked.v41.example"
    respx.get(f"{base_url}/").mock(return_value=httpx.Response(200, text=""))
    respx.get(f"{base_url}/api/system/info").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"version": "2.41.4", "revision": "abc"},
        ),
    )
    respx.get(f"{base_url}/api/me").mock(
        return_value=httpx.Response(200, json={"id": "u1", "username": "admin", "displayName": "Admin"}),
    )
    profile = Profile(base_url=base_url, auth="pat", token="d2pat_x", version=Dhis2.V41)
    async with open_client(profile, system_cache_ttl=None) as client:
        me = await client.system.me()
        assert me.username == "admin"
        # client.version_key should pin to v41 because Profile.version is set.
        assert client.version_key == "v41"
