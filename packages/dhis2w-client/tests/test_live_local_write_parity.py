"""Live write-parity against a local DHIS2 stack — writes never go to the shared play demo.

create -> verify -> delete round-trips on the hand-written accessors, against whatever major
the local stack runs. To cover v41/v43, restart the stack on that version and re-run; the
test is version-agnostic (the client dispatches to whatever the stack reports). Every object
is prefixed and torn down in a finally, so nothing lingers.

`@pytest.mark.slow` — run with `make test-slow`; skips when no local stack / PAT is available.
"""

from __future__ import annotations

import secrets

import pytest
from dhis2w_client import Dhis2Client, PatAuth

pytestmark = pytest.mark.slow


def _name() -> str:
    """A collision-proof, clearly-test-owned object name."""
    return f"zz-utils-write-parity-{secrets.token_hex(4)}"


async def test_data_element_create_verify_rename_delete(local_url: str, local_pat: str) -> None:
    """data_elements create -> get -> rename -> delete round-trips against the live stack."""
    if not local_pat:
        pytest.skip("no local PAT — run `make dhis2-run` to populate")
    name = _name()
    async with Dhis2Client(local_url, auth=PatAuth(token=local_pat)) as client:
        created = await client.data_elements.create(name=name, short_name=name[:50], value_type="NUMBER")
        assert created.id and created.name == name
        try:
            fetched = await client.data_elements.get(created.id)
            assert fetched.id == created.id
            assert fetched.valueType == "NUMBER"

            renamed = await client.data_elements.rename(created.id, short_name="zz-renamed")
            assert renamed.shortName == "zz-renamed"
            assert (await client.data_elements.get(created.id)).shortName == "zz-renamed"
        finally:
            await client.data_elements.delete(created.id)
