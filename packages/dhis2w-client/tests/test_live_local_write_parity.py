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


async def test_composite_data_set_with_elements(local_url: str, local_pat: str) -> None:
    """The hard write: create N data elements, a data set, wire them together, verify, tear down.

    This is the multi-object write small local models stall on (correlating freshly-created
    UIDs). Here it validates the accessor wiring against the live stack end-to-end.
    """
    if not local_pat:
        pytest.skip("no local PAT — run `make dhis2-run` to populate")
    tag = secrets.token_hex(3)
    element_count = 3
    async with Dhis2Client(local_url, auth=PatAuth(token=local_pat)) as client:
        element_ids: list[str] = []
        data_set_id: str | None = None
        try:
            for index in range(element_count):
                element = await client.data_elements.create(
                    name=f"zz-composite-{tag}-de{index}",
                    short_name=f"zz{tag}de{index}",
                    value_type="NUMBER",
                )
                assert element.id
                element_ids.append(element.id)

            data_set = await client.data_sets.create(
                name=f"zz-composite-{tag}-set",
                short_name=f"zz{tag}set",
                period_type="Monthly",
            )
            data_set_id = data_set.id
            assert data_set_id

            for element_id in element_ids:
                await client.data_sets.add_element(data_set_id, element_id)

            fetched = await client.data_sets.get(data_set_id)
            assert len(fetched.dataSetElements or []) == element_count
            wired = {(entry.dataElement.id if entry.dataElement else None) for entry in (fetched.dataSetElements or [])}
            assert wired == set(element_ids)
        finally:
            if data_set_id:
                await client.data_sets.delete(data_set_id)
            for element_id in element_ids:
                await client.data_elements.delete(element_id)


async def test_composite_program_with_stages(local_url: str, local_pat: str) -> None:
    """The second hard write: an event program + N stages, verified and torn down.

    Uses WITHOUT_REGISTRATION so no tracked-entity-type dependency is needed.
    """
    if not local_pat:
        pytest.skip("no local PAT — run `make dhis2-run` to populate")
    tag = secrets.token_hex(3)
    stage_count = 2
    async with Dhis2Client(local_url, auth=PatAuth(token=local_pat)) as client:
        stage_ids: list[str] = []
        program_id: str | None = None
        try:
            program = await client.programs.create(
                name=f"zz-program-{tag}",
                short_name=f"zz{tag}prog",
                program_type="WITHOUT_REGISTRATION",
            )
            program_id = program.id
            assert program_id

            for index in range(stage_count):
                stage = await client.program_stages.create(
                    name=f"zz-program-{tag}-stage{index}",
                    program_uid=program_id,
                    sort_order=index + 1,
                )
                assert stage.id
                stage_ids.append(stage.id)

            stages = await client.program_stages.list_for(program_id)
            assert {stage.id for stage in stages} == set(stage_ids)
        finally:
            for stage_id in stage_ids:
                await client.program_stages.delete(stage_id)
            if program_id:
                await client.programs.delete(program_id)
