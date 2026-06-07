"""Regression tests for the version-pin mismatch guard on Dhis2Client.connect().

A caller that pins `Dhis2Client(version=Dhis2.V43)` but connects to a v42
server used to bind the v43 generated tree against a v42 wire, silently
round-tripping renamed/added fields. connect() now refuses to bind in that
case unless `allow_version_mismatch=True` is set.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from dhis2w_client import (
    BasicAuth,
    Dhis2,
    Dhis2Client,
)
from dhis2w_client.errors import VersionPinMismatchError


@respx.mock
async def test_pinning_matching_version_succeeds() -> None:
    """Pinning matching version succeeds."""
    base_url = "http://mocked.matching.example"
    respx.get(f"{base_url}/").mock(return_value=httpx.Response(200, text=""))
    respx.get(f"{base_url}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4", "revision": "abc"}),
    )
    client = Dhis2Client(
        base_url,
        auth=BasicAuth(username="admin", password="district"),
        version=Dhis2.V42,
        system_cache_ttl=None,
    )
    async with client as c:
        assert c.version_key == "v42"


@respx.mock
async def test_pinning_mismatched_version_raises() -> None:
    """Pinning mismatched version raises."""
    base_url = "http://mocked.mismatch.example"
    respx.get(f"{base_url}/").mock(return_value=httpx.Response(200, text=""))
    respx.get(f"{base_url}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4", "revision": "abc"}),
    )
    client = Dhis2Client(
        base_url,
        auth=BasicAuth(username="admin", password="district"),
        version=Dhis2.V43,
        system_cache_ttl=None,
    )
    with pytest.raises(VersionPinMismatchError) as exc:
        async with client:
            pass
    assert exc.value.pinned == "v43"
    assert exc.value.reported == "2.42.4"
    assert "allow_version_mismatch" in str(exc.value)


@respx.mock
async def test_pinning_mismatched_version_allowed_via_opt_in() -> None:
    """Pinning mismatched version allowed via opt in."""
    base_url = "http://mocked.optin.example"
    respx.get(f"{base_url}/").mock(return_value=httpx.Response(200, text=""))
    respx.get(f"{base_url}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4", "revision": "abc"}),
    )
    client = Dhis2Client(
        base_url,
        auth=BasicAuth(username="admin", password="district"),
        version=Dhis2.V43,
        allow_version_mismatch=True,
        system_cache_ttl=None,
    )
    # Opt-in path: client binds the pinned v43 tree even though server reports v42.
    async with client as c:
        assert c.version_key == "v43"


@respx.mock
async def test_unparseable_server_version_does_not_block_pin() -> None:
    """Unparseable server version does not block pin."""
    base_url = "http://mocked.unparseable.example"
    respx.get(f"{base_url}/").mock(return_value=httpx.Response(200, text=""))
    respx.get(f"{base_url}/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "weird-build-string", "revision": "abc"}),
    )
    client = Dhis2Client(
        base_url,
        auth=BasicAuth(username="admin", password="district"),
        version=Dhis2.V42,
        system_cache_ttl=None,
    )
    # When the server didn't report a parseable version we trust the explicit
    # pin — better than blocking on a 'server didn't report version' error.
    async with client as c:
        assert c.version_key == "v42"
