"""Live read-parity against the DHIS2 play servers (v41 / v42 / v43).

Where the mocked accessor tests prove the v41/v43 code *runs* against a known wire shape,
these prove it parses the **real** wire each major actually returns — catching behaviour
divergences a copied accessor can hide. Reads only; the live tier never writes to play.

`@pytest.mark.slow` (network) — run with `make test-slow`; skips when a play server is down.
"""

from __future__ import annotations

import pytest
from dhis2w_client import BasicAuth, Dhis2Client

pytestmark = pytest.mark.slow


def _auth() -> BasicAuth:
    """Play's default admin credentials (read-only use)."""
    return BasicAuth(username="admin", password="district")


async def test_connect_binds_the_reported_major(play_target: tuple[str, str]) -> None:
    """Connecting to each play server binds that major's tree and reports its version."""
    url, version_key = play_target
    async with Dhis2Client(url, auth=_auth()) as client:
        assert client.version_key == version_key
        info = await client.system.info()
        assert (info.version or "").startswith(f"2.{version_key[1:]}")
        assert (await client.system.me()).username


async def test_identical_accessors_parse_real_wire(play_target: tuple[str, str]) -> None:
    """Identical-across-versions accessors parse the live wire into typed models on every major."""
    url, _ = play_target
    async with Dhis2Client(url, auth=_auth()) as client:
        data_elements = await client.data_elements.list_all(page_size=5)
        assert data_elements and type(data_elements[0]).__name__ == "DataElement"
        assert data_elements[0].id and data_elements[0].valueType is not None

        categories = await client.categories.list_all(page_size=5)
        assert categories and type(categories[0]).__name__ == "Category"

        indicators = await client.indicators.list_all(page_size=5)
        assert indicators and type(indicators[0]).__name__ == "Indicator"

        data_sets = await client.data_sets.list_all(page_size=5)
        assert data_sets and type(data_sets[0]).__name__ == "DataSet"

        program_indicators = await client.program_indicators.list_all(page_size=5)
        assert program_indicators and type(program_indicators[0]).__name__ == "ProgramIndicator"


async def test_diverged_accessors_parse_real_wire(play_target: tuple[str, str]) -> None:
    """Diverged accessors parse each major's real wire — the high-value parity check."""
    url, _ = play_target
    async with Dhis2Client(url, auth=_auth()) as client:
        combos = await client.category_combos.list_all(page_size=5)
        assert combos and type(combos[0]).__name__ == "CategoryCombo"
        assert combos[0].id and combos[0].dataDimensionType is not None

        org_units = await client.organisation_units.list_all(page_size=5)
        assert org_units and type(org_units[0]).__name__ == "OrganisationUnit"
        assert org_units[0].id and org_units[0].level is not None

        programs = await client.programs.list_all(page_size=5)
        assert programs and type(programs[0]).__name__ == "Program"
        assert programs[0].id

        option_sets = await client.option_sets.list_all(page_size=5)
        assert option_sets and type(option_sets[0]).__name__ == "OptionSet"
        assert option_sets[0].id

        results = await client.metadata.search("anc")
        assert results.total >= 0
        assert isinstance(results.flat(), list)
