"""End-to-end tests against the local DHIS2 stack using typed resources and system module."""

from __future__ import annotations

import pytest
from dhis2w_client import BasicAuth, Dhis2Client

pytestmark = pytest.mark.slow


async def test_connected_client_system_and_typed_resources(
    local_url: str,
    local_username: str,
    local_password: str,
    local_available: bool,
) -> None:
    """Connected client system and typed resources."""
    if not local_available:
        pytest.skip(f"local DHIS2 not reachable at {local_url}")
    auth = BasicAuth(username=local_username, password=local_password)
    async with Dhis2Client(local_url, auth=auth) as client:
        info = await client.system.info()
        assert info.version is not None
        assert client.version_key.startswith("v")

        me = await client.system.me()
        assert me.username == local_username

        if hasattr(client.resources, "data_elements"):
            items = await client.resources.data_elements.list(fields="id,name")
            assert isinstance(items, list)
            if items:
                first = items[0]
                assert first.id is not None
                fetched = await client.resources.data_elements.get(first.id, fields="id,name")
                assert fetched.id == first.id
