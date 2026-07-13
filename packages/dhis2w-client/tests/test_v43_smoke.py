"""Smoke matrix for the v43 client tree — broad-not-deep guardrails.

Covers the structural surface that lives in `dhis2w_client.v43.*`:
import-time correctness, the connect/version-handshake happy path,
one accessor read, and the auth-provider construction. Pairs with
the equivalent `test_v41_smoke.py` so divergent v41/v43 surfaces
both have a basic regression gate. Deeper accessor / wire-shape
behaviour is exercised by `test_v43_*` divergence + setter files.
"""

from __future__ import annotations

import httpx
import respx
from dhis2w_client.generated import Dhis2
from dhis2w_client.v43 import (
    BasicAuth,
    Dhis2Client,
    PatAuth,
    Profile,
    build_auth_provider,
    open_client,
)


def test_v43_top_level_imports_resolve() -> None:
    """v43 top-level imports resolve."""
    assert Dhis2Client.__module__ == "dhis2w_client.v43.client"
    assert PatAuth.__module__ == "dhis2w_client.v43.auth.pat"
    assert BasicAuth.__module__ == "dhis2w_client.v43.auth.basic"


def test_v43_build_auth_provider_pat() -> None:
    """v43 build auth for basic pat."""
    provider = build_auth_provider(Profile(base_url="http://x", auth="pat", token="d2p_x"))
    assert isinstance(provider, PatAuth)


def test_v43_build_auth_provider_basic() -> None:
    """v43 build auth for basic basic."""
    provider = build_auth_provider(Profile(base_url="http://x", auth="basic", username="admin", password="district"))
    assert isinstance(provider, BasicAuth)


@respx.mock
async def test_v43_open_client_runs_handshake_and_binds_v43_tree() -> None:
    """v43 open client runs handshake and binds v43 tree."""
    base_url = "http://mocked.v43.example"
    respx.get(f"{base_url}/").mock(return_value=httpx.Response(200, text=""))
    respx.get(f"{base_url}/api/system/info").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"version": "2.43.0", "revision": "abc"},
        ),
    )
    respx.get(f"{base_url}/api/me").mock(
        return_value=httpx.Response(200, json={"id": "u1", "username": "admin", "displayName": "Admin"}),
    )
    profile = Profile(base_url=base_url, auth="pat", token="d2pat_x", version=Dhis2.V43)
    async with open_client(profile, system_cache_ttl=None) as client:
        me = await client.system.me()
        assert me.username == "admin"
        assert client.version_key == "v43"
