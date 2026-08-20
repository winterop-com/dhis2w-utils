"""Tests for handing an already-open `Dhis2Client` to the capabilities that read DHIS2.

Every capability here takes a `Profile` and opens its own connection, or takes the connection the
caller already holds. The two forms have to agree about two things: the report they produce, and how
many connections the process paid for. Opening a client costs one `/api/system/info` read on the way
up, so counting that path across the mocked calls is how a second connection announces itself.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import respx
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import FhirProject, InitOptions, load_project, service

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client

_HOST = "https://dhis2.example"

#: The instance every capability here reads: one data set with one question, one option set, one
#: category, one organisation unit. Small enough that the reports are readable when they disagree.
_INSTANCE: dict[str, list[dict[str, Any]]] = {
    "dataSets": [
        {
            "id": "DsCli000001",
            "name": "Child care",
            "code": "CHILD_CARE",
            "periodType": "Monthly",
            "dataSetElements": [{"dataElement": {"id": "DeCli000001", "name": "Weight", "valueType": "NUMBER"}}],
        }
    ],
    "programs": [],
    "trackedEntityTypes": [],
    "optionSets": [{"id": "OsCli000001", "name": "Bednet distribution", "code": "BEDNETS", "options": []}],
    "categories": [{"id": "CaCli000001", "name": "Sex", "code": "SEX", "categoryOptions": []}],
    "organisationUnits": [
        {"id": "OuCli000001", "name": "Sierra Leone", "code": "SL", "level": 1, "path": "/OuCli000001"}
    ],
    "programRules": [],
    "attributes": [],
}


async def _project(directory: Path) -> FhirProject:
    """Scaffold a project that selects everything the mocked instance holds and generates no examples."""
    await service.init_project(
        directory,
        InitOptions(
            ig_id="dhis2.fhir.clientarg",
            canonical="http://example.org/fhir",
            name="Dhis2FhirClientArgument",
            title="Client Argument IG",
            publisher="Client Org",
        ),
    )
    config_path = directory / "fhir.toml"
    config_path.write_text(
        f"{config_path.read_text(encoding='utf-8')}\n[generate.examples]\nper_target = 0\n",
        encoding="utf-8",
    )
    return load_project(directory)


def _mock_instance() -> None:
    """Answer every endpoint these capabilities read, the validate sweep included."""
    respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json={"version": "2.42.0"}))
    for resource, items in _INSTANCE.items():
        respx.get(f"{_HOST}/api/{resource}").mock(return_value=httpx.Response(200, json={resource: items}))
    respx.get(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataSets": [{"id": "DsCli000001", "name": "Child care", "code": "CHILD_CARE"}],
                "dataElements": [{"id": "DeCli000001", "name": "Weight", "code": None}],
                "optionSets": [{"id": "OsCli000001", "name": "Bednet distribution", "code": "BEDNETS"}],
                "categories": [{"id": "CaCli000001", "name": "Sex", "code": "SEX"}],
                "organisationUnits": [{"id": "OuCli000001", "name": "Sierra Leone", "code": "SL"}],
            },
        )
    )


#: The generate targets that read DHIS2, named the way `d2w fhir generate <target>` names them.
_GENERATE_TARGETS: dict[str, Callable[..., Awaitable[Any]]] = {
    "option-sets": service.generate_option_sets,
    "categories": service.generate_categories,
    "questionnaires": service.generate_questionnaires,
    "examples": service.generate_examples,
    "organisation-units": service.generate_organisation_units,
    "pages": service.generate_pages,
    "full": service.generate_full,
}


@respx.mock
@pytest.mark.parametrize("target", list(_GENERATE_TARGETS))
async def test_a_target_driven_by_a_caller_supplied_client_opens_no_second_connection(
    probe_profile: None,  # noqa: ARG001
    tmp_path: Path,
    target: str,
) -> None:
    """The same report either way, and the handed-in form pays for no connection of its own."""
    _mock_instance()
    generate = _GENERATE_TARGETS[target]
    profile = resolve_profile("probe")
    from_profile = await generate(profile, await _project(tmp_path / "profile"))

    async with open_client(profile) as client:
        opened = _connections()
        from_client = await generate(profile, await _project(tmp_path / "handed-in"), client=client)
        assert _connections() == opened, "the target opened a second connection instead of using the caller's"
        assert await _still_answering(client)

    assert _comparable(from_client) == _comparable(from_profile)


@respx.mock
async def test_validate_driven_by_a_caller_supplied_client_opens_no_second_connection(
    probe_profile: None,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    """`validate_codes` reads through the caller's connection and reports what the profile form reports."""
    _mock_instance()
    profile = resolve_profile("probe")
    project = await _project(tmp_path / "project")
    from_profile = await service.validate_codes(profile, project.config.generate)

    async with open_client(profile) as client:
        opened = _connections()
        from_client = await service.validate_codes(profile, project.config.generate, client=client)
        assert _connections() == opened, "validate opened a second connection instead of using the caller's"
        assert await _still_answering(client)

    assert from_client.model_dump() == from_profile.model_dump()


@respx.mock
async def test_the_profile_form_still_opens_and_closes_its_own_connection(
    probe_profile: None,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    """With no client handed in the profile is the convenience wrapper, so each call connects once."""
    _mock_instance()
    profile = resolve_profile("probe")
    project = await _project(tmp_path / "project")
    before = _connections()

    await service.generate_option_sets(profile, project)
    await service.generate_categories(profile, project)

    assert _connections() == before + 2


def _connections() -> int:
    """How many DHIS2 connections this test has paid for - every `open_client` reads `/api/system/info` once."""
    return sum(1 for call in respx.calls if call.request.url.path == "/api/system/info")


async def _still_answering(client: Dhis2Client) -> bool:
    """Whether the caller's client is still usable after the call - its lifetime is the caller's, not the call's."""
    return await client.resources.option_sets.list(fields="id", paging=False) is not None


def _comparable(report: Any) -> dict[str, Any]:
    """One report as the value two runs of the same project must agree on, with the project path dropped."""
    dumped: dict[str, Any] = report.model_dump()
    return _without_project_root(dumped)


def _without_project_root(value: dict[str, Any]) -> dict[str, Any]:
    """Drop `project_root` wherever it appears, so two identically scaffolded projects compare equal."""
    return {
        key: _without_project_root(item) if isinstance(item, dict) else item
        for key, item in value.items()
        if key != "project_root"
    }
