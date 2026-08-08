"""Tests for DHIS2 attribute values reaching the projections, and the attribute code index they join against."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client.generated.v42.schemas import DataSet, OptionSet, OrganisationUnit, Program
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import InitOptions, load_project, service
from dhis2w_fhir.attributes import AttributeCodeIndex, AttributeValueIn
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn

_HOST = "https://dhis2.example"
_TODAY = date(2026, 8, 1)

#: The live wire shape, confirmed on play 2.43 and on the Lao instance: the attribute UID and the value alone.
_WIRE_ATTRIBUTE_VALUES = [
    {"attribute": {"id": "ihn1wb9eho8"}, "value": "KE03"},
    {"attribute": {"id": "n2xYlNbsfko"}, "value": "Facility register"},
]

_MAPPED_ATTRIBUTE_VALUES = [
    AttributeValueIn(attribute_uid="ihn1wb9eho8", value="KE03"),
    AttributeValueIn(attribute_uid="n2xYlNbsfko", value="Facility register"),
]

_GEOJSON_VALUE = json.dumps({"type": "Point", "coordinates": [102.6, 17.97]})


def _organisation_unit(**extra: Any) -> OrganisationUnit:
    """Build a generated OrganisationUnit for the mapper."""
    payload: dict[str, Any] = {"id": "O6uvpzGd5pu", "name": "Bo", "level": 2, "path": "/ImspTQPwCqd/O6uvpzGd5pu"}
    payload.update(extra)
    return OrganisationUnit.model_validate(payload)


def _option_set(**extra: Any) -> OptionSet:
    """Build a generated OptionSet for the mapper."""
    payload: dict[str, Any] = {"id": "Xa1b2c3d4e5", "name": "Birth type", "options": []}
    payload.update(extra)
    return OptionSet.model_validate(payload)


def _data_set(**extra: Any) -> DataSet:
    """Build a generated DataSet for the mapper."""
    payload: dict[str, Any] = {"id": "BfMAe6Itzgt", "name": "Child Health", "periodType": "Monthly"}
    payload.update(extra)
    return DataSet.model_validate(payload)


def _event_program(**extra: Any) -> Program:
    """Build a generated single-stage event Program for the mapper."""
    payload: dict[str, Any] = {
        "id": "VBqh0ynB2wv",
        "name": "Malaria case registration",
        "programType": "WITHOUT_REGISTRATION",
        "programStages": [{"id": "pTo4uMt3xur", "name": "Stage", "programStageDataElements": []}],
    }
    payload.update(extra)
    return Program.model_validate(payload)


def _mapped_organisation_unit(model: OrganisationUnit) -> OrganisationUnitIn:
    """Map one organisation unit, asserting it survived the mapper."""
    mapped = service._organisation_unit_input(model, service.GeometryTally(), _TODAY)
    assert mapped is not None
    return mapped


def test_organisation_unit_attribute_values_reach_the_projection() -> None:
    """An organisation unit's attribute values arrive on the projection, in wire order."""
    mapped = _mapped_organisation_unit(_organisation_unit(attributeValues=_WIRE_ATTRIBUTE_VALUES))
    assert mapped.attribute_values == _MAPPED_ATTRIBUTE_VALUES


def test_option_set_attribute_values_reach_the_projection() -> None:
    """An option set's attribute values arrive on the projection, in wire order."""
    mapped = service._option_set_input(_option_set(attributeValues=_WIRE_ATTRIBUTE_VALUES))
    assert mapped.attribute_values == _MAPPED_ATTRIBUTE_VALUES


def test_data_set_attribute_values_reach_the_projection() -> None:
    """A data set's attribute values arrive on the questionnaire projection, in wire order."""
    mapped = service._data_set_source(_data_set(attributeValues=_WIRE_ATTRIBUTE_VALUES), [])
    assert mapped.attribute_values == _MAPPED_ATTRIBUTE_VALUES


def test_event_program_attribute_values_reach_the_projection() -> None:
    """An event program's attribute values arrive on the questionnaire projection, in wire order."""
    mapped = service._event_program_source(_event_program(attributeValues=_WIRE_ATTRIBUTE_VALUES), [])
    assert mapped.attribute_values == _MAPPED_ATTRIBUTE_VALUES


def test_objects_without_attribute_values_project_an_empty_list() -> None:
    """Every projection defaults to no attribute values - most DHIS2 objects carry none."""
    assert _mapped_organisation_unit(_organisation_unit()).attribute_values == []
    assert service._option_set_input(_option_set()).attribute_values == []
    assert service._data_set_source(_data_set(), []).attribute_values == []
    assert service._event_program_source(_event_program(), []).attribute_values == []


def test_an_attribute_value_carries_a_whole_geojson_document() -> None:
    """DHIS2 sends every value as a string whatever its value type, a GeoJSON document included."""
    mapped = service._option_set_input(
        _option_set(attributeValues=[{"attribute": {"id": "ihn1wb9eho8"}, "value": _GEOJSON_VALUE}])
    )
    assert mapped.attribute_values == [AttributeValueIn(attribute_uid="ihn1wb9eho8", value=_GEOJSON_VALUE)]


@pytest.mark.parametrize(
    "entry",
    [
        {"value": "KE03"},
        {"attribute": {}, "value": "KE03"},
        {"attribute": {"id": "ihn1wb9eho8"}},
        {"attribute": {"id": "ihn1wb9eho8"}, "value": 7},
        {"attribute": "ihn1wb9eho8", "value": "KE03"},
        "not-an-object",
    ],
)
def test_an_incomplete_attribute_value_is_dropped(entry: object) -> None:
    """An entry missing either half of the pair is dropped rather than projected half-formed."""
    mapped = service._option_set_input(_option_set(attributeValues=[entry]))
    assert mapped.attribute_values == []


async def _scaffold_project(directory: Path) -> None:
    """Scaffold a minimal project so the generate targets have a fhir.toml + ig tree."""
    options = InitOptions(
        ig_id="dhis2.fhir.attributes",
        canonical="http://example.org/fhir",
        name="Dhis2FhirAttributes",
        title="Attributes IG",
        publisher="Attributes Org",
    )
    await service.init_project(directory, options)


@respx.mock
async def test_every_metadata_fetch_asks_for_the_attribute_values(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """All four fetches request the attribute values - an omitted field list silently empties the projections."""
    mock_system_info("v42")
    mock_attributes()
    await _scaffold_project(tmp_path)
    option_sets = respx.get(f"{_HOST}/api/optionSets").mock(
        return_value=httpx.Response(200, json={"optionSets": []}),
    )
    organisation_units = respx.get(f"{_HOST}/api/organisationUnits").mock(
        return_value=httpx.Response(200, json={"organisationUnits": []}),
    )
    data_sets = respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json={"dataSets": []}))
    programs = respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))

    profile = resolve_profile("probe")
    await service.generate_option_sets(profile, load_project(tmp_path))
    await service.generate_organisation_units(profile, load_project(tmp_path))
    await service.generate_questionnaires(profile, load_project(tmp_path))

    for route in (option_sets, organisation_units, data_sets, programs):
        # The option-set identity plan fetches `id,name` alone, so it is the projection fetch that has to ask.
        assert any("attributeValues[attribute[id],value]" in call.request.url.params["fields"] for call in route.calls)


@respx.mock
async def test_attribute_values_survive_the_whole_fetch_path(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A wire payload carrying attribute values arrives populated at the far end of the fetch."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataSets": [{"id": "BfMAe6Itzgt", "name": "Child Health", "attributeValues": _WIRE_ATTRIBUTE_VALUES}]
            },
        )
    )
    respx.get(f"{_HOST}/api/programs").mock(
        return_value=httpx.Response(
            200,
            json={
                "programs": [
                    {
                        "id": "VBqh0ynB2wv",
                        "name": "Malaria case registration",
                        "programType": "WITHOUT_REGISTRATION",
                        "attributeValues": [{"attribute": {"id": "n2xYlNbsfko"}, "value": "Facility register"}],
                    }
                ]
            },
        )
    )

    async with open_client(resolve_profile("probe")) as client:
        sources = await service._fetch_questionnaire_sources(client, load_project(tmp_path).config.generate, [])

    by_uid = {source.uid: source for source in sources}
    assert by_uid["BfMAe6Itzgt"].attribute_values == _MAPPED_ATTRIBUTE_VALUES
    assert by_uid["VBqh0ynB2wv"].attribute_values == [
        AttributeValueIn(attribute_uid="n2xYlNbsfko", value="Facility register")
    ]


@respx.mock
async def test_organisation_unit_attribute_values_survive_the_paged_fetch(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The org-unit fetch pages the hierarchy, and each page's attribute values reach the projections."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    respx.get(f"{_HOST}/api/organisationUnits").mock(
        return_value=httpx.Response(
            200,
            json={
                "organisationUnits": [
                    {
                        "id": "O6uvpzGd5pu",
                        "name": "Bo",
                        "level": 2,
                        "path": "/ImspTQPwCqd/O6uvpzGd5pu",
                        "attributeValues": _WIRE_ATTRIBUTE_VALUES,
                    }
                ]
            },
        )
    )

    async with open_client(resolve_profile("probe")) as client:
        units = await service._fetch_organisation_units(
            client, load_project(tmp_path).config.generate, service.GeometryTally(), _TODAY, service._StepAnnouncer()
        )

    assert [unit.attribute_values for unit in units] == [_MAPPED_ATTRIBUTE_VALUES]


async def _resolve_index(route: respx.Route) -> AttributeCodeIndex:
    """Resolve the attribute code index against a mocked instance."""
    async with open_client(resolve_profile("probe")) as client:
        index = await service.resolve_attribute_code_index(client)
    assert route.called
    return index


@respx.mock
async def test_the_attribute_fetch_is_unpaged(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
) -> None:
    """DHIS2 answers 50 attributes to a page by default, so the join has to ask for every one of them."""
    mock_system_info(wire_version)
    attributes = respx.get(f"{_HOST}/api/attributes").mock(
        return_value=httpx.Response(200, json={"attributes": []}),
    )

    await _resolve_index(attributes)

    params = attributes.calls.last.request.url.params
    assert params["paging"] == "false"
    assert "page" not in params
    assert "pageSize" not in params
    assert params["fields"] == "id,code"


@respx.mock
async def test_the_index_holds_the_coded_attributes_and_omits_the_rest(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
) -> None:
    """Attributes DHIS2 left without a code are absent from the index; `code_for` answers None for them."""
    mock_system_info(wire_version)
    attributes = respx.get(f"{_HOST}/api/attributes").mock(
        return_value=httpx.Response(
            200,
            json={
                "attributes": [
                    {"id": "ihn1wb9eho8", "code": "FACILITY_CODE"},
                    {"id": "n2xYlNbsfko"},
                    {"id": "SWfdB5lX0fk", "code": ""},
                    {"code": "NO_UID"},
                ]
            },
        )
    )

    index = await _resolve_index(attributes)

    assert index.codes == {"ihn1wb9eho8": "FACILITY_CODE"}
    assert index.code_for("ihn1wb9eho8") == "FACILITY_CODE"
    assert index.code_for("n2xYlNbsfko") is None
    assert index.code_for("SWfdB5lX0fk") is None


def test_an_empty_index_answers_no_code() -> None:
    """An instance that codes none of its attributes yields an index every lookup misses."""
    assert AttributeCodeIndex().code_for("ihn1wb9eho8") is None
