"""The disaggregation a data set holds its cells over: `dataSetElements[].categoryCombo` over the element's own.

DHIS2 holds a category combo in two places for one aggregate cell. The data element carries its own,
and the data set element - the join between a data set and an element it carries - carries the combo
that data set holds that element's values over. The join wins: a data element on the default combo,
carried by a data set that states a four-way age split, holds four cells in that data set and one
everywhere else. `service._effective_category_combo` is the single point that resolves the pair, and
every reader of a data-set cell's combo is downstream of it - the questionnaire's per-option-combo
child items, the `D2COC_CS` concepts, the compulsory operands, and the conversion that writes each
answer back under its own `categoryOptionCombo`.

The fixture is the shape play dev-2-43 carries on "Mortality under 5 years by age group"
(`ce7DSxx5H2I`): every data element on `default`, every join on `Morbidity Age`. The names are
spelled "under 5" rather than "< 5" because the generate gate refuses a `<` in any name it emits,
question names included.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import InitOptions, load_project, service

_HOST = "https://dhis2.example"
_CANONICAL = "http://example.org/fhir"

#: The default combo every data element of the fixture carries - one cell, no disaggregation.
_DEFAULT_COMBO: dict[str, Any] = {
    "id": "bjDvmb4bfuf",
    "name": "default",
    "isDefault": True,
    "categories": [{"id": "GLevLNI9wkl"}],
    "categoryOptionCombos": [{"id": "HllvX50cXC0", "name": "default", "categoryOptions": [{"id": "xYerKDKCefk"}]}],
}

#: The combo the data set states over its elements instead - a four-way age split.
_AGE_COMBO: dict[str, Any] = {
    "id": "pbvcDRasDav",
    "name": "Morbidity Age",
    "isDefault": False,
    "categories": [{"id": "Ca1aaaaaaaa"}],
    "categoryOptionCombos": [
        {"id": "Coc0to11moo", "name": "0-11m", "code": "AGE_0_11M", "categoryOptions": [{"id": "Opt0to11moo"}]},
        {"id": "Coc12to59mo", "name": "12-59m", "code": "AGE_12_59M", "categoryOptions": [{"id": "Opt12to59mo"}]},
        {"id": "Coc5to14yrs", "name": "5-14y", "code": "AGE_5_14Y", "categoryOptions": [{"id": "Opt5to14yrs"}]},
        {"id": "Coc15yrsplu", "name": "15y+", "code": "AGE_15Y_PLUS", "categoryOptions": [{"id": "Opt15yrsplu"}]},
    ],
}

#: The one category the age combo splits over, as the decomposition reads it.
_CATEGORIES_PAYLOAD: dict[str, object] = {
    "categories": [
        {
            "id": "Ca1aaaaaaaa",
            "name": "Morbidity Age",
            "categoryOptions": [
                {"id": "Opt0to11moo", "name": "0-11m"},
                {"id": "Opt12to59mo", "name": "12-59m"},
                {"id": "Opt5to14yrs", "name": "5-14y"},
                {"id": "Opt15yrsplu", "name": "15y+"},
            ],
        }
    ]
}

#: The two data elements the fixture data set carries, both on the default combo.
_CHOLERA: dict[str, Any] = {
    "id": "eY5ehpbEsB7",
    "name": "Cholera (Deaths under 5 yrs)",
    "valueType": "INTEGER_ZERO_OR_POSITIVE",
    "categoryCombo": _DEFAULT_COMBO,
}
_DYSENTERY: dict[str, Any] = {
    "id": "Ix2HsbDMLea",
    "name": "Dysentery (Deaths under 5 yrs)",
    "valueType": "INTEGER_ZERO_OR_POSITIVE",
    "categoryCombo": _DEFAULT_COMBO,
}

#: Every option-combo UID the age split holds, in the order the emitter writes its cells.
_AGE_OPTION_COMBO_UIDS = ["Coc0to11moo", "Coc12to59mo", "Coc15yrsplu", "Coc5to14yrs"]


#: The organisation unit the fixture data set is reported for, and the root the example walk starts at.
_ROOT_ORG_UNIT = "ImspTQPwCqd"
_REPORTING_UNIT = "DiszpKrYNg8"

#: The registry both the assignment read and the example walk are answered with.
_ORG_UNITS_PAYLOAD: dict[str, object] = {
    "organisationUnits": [
        {"id": _ROOT_ORG_UNIT, "name": "Sierra Leone"},
        {"id": _REPORTING_UNIT, "name": "Ngelehun CHC"},
    ]
}

#: One month of values the instance holds for the fixture, keyed by the option combos of the override.
_DATA_VALUE_SET: dict[str, object] = {
    "dataSet": "ce7DSxx5H2I",
    "period": "202606",
    "dataValues": [
        {
            "dataElement": "eY5ehpbEsB7",
            "period": "202606",
            "orgUnit": _REPORTING_UNIT,
            "categoryOptionCombo": "Coc0to11moo",
            "attributeOptionCombo": "HllvX50cXC0",
            "value": "7",
        },
        {
            "dataElement": "eY5ehpbEsB7",
            "period": "202606",
            "orgUnit": _REPORTING_UNIT,
            "categoryOptionCombo": "Coc12to59mo",
            "attributeOptionCombo": "HllvX50cXC0",
            "value": "3",
        },
    ],
}


def _data_sets_payload(
    *, override: dict[str, Any] | None, operands: list[dict[str, object]] | None = None
) -> dict[str, object]:
    """The fixture data set, its two joins carrying `override` as their own combo when one is given."""
    element_join: dict[str, Any] = {} if override is None else {"categoryCombo": override}
    return {
        "dataSets": [
            {
                # The real data set's name carries '<', which the generate gate now refuses outright;
                # these tests are about the combo override join, so the fixture keeps a survivable name.
                "id": "ce7DSxx5H2I",
                "name": "Mortality under 5 years by age group",
                "periodType": "Monthly",
                "organisationUnits": [{"id": _REPORTING_UNIT}],
                "sections": [],
                "compulsoryDataElementOperands": operands or [],
                "dataSetElements": [
                    {"dataElement": _CHOLERA, **element_join},
                    {"dataElement": _DYSENTERY, **element_join},
                ],
            }
        ]
    }


async def _scaffold_project(directory: Path, *, examples_source: str = "synthetic") -> None:
    """Scaffold a project selecting the fixture data set alone, its examples drawn from `examples_source`."""
    options = InitOptions(
        ig_id="dhis2.fhir.overrides",
        canonical=_CANONICAL,
        name="Dhis2FhirOverrides",
        title="Override IG",
        publisher="Override Org",
    )
    await service.init_project(directory, options)
    config_path = directory / "fhir.toml"
    body = config_path.read_text(encoding="utf-8")
    body += '\n[generate.data_sets]\ninclude_ids = ["ce7DSxx5H2I"]\n'
    body += "\n[generate.event_programs]\ninclude_ids = []\n"
    body += "\n[generate.tracker_programs]\ninclude_ids = []\n"
    body += f'\n[generate.examples]\nper_target = 1\nsource = "{examples_source}"\n'
    config_path.write_text(body, encoding="utf-8")


def _mock_metadata(*, override: dict[str, Any] | None, operands: list[dict[str, object]] | None = None) -> respx.Route:
    """Mock every metadata endpoint a run over the fixture reads, answering with the data-set route."""
    data_sets = respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(200, json=_data_sets_payload(override=override, operands=operands))
    )
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))
    respx.get(f"{_HOST}/api/programRules").mock(return_value=httpx.Response(200, json={"programRules": []}))
    respx.get(f"{_HOST}/api/trackedEntityTypes").mock(return_value=httpx.Response(200, json={"trackedEntityTypes": []}))
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json={"optionSets": []}))
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json=_CATEGORIES_PAYLOAD))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ORG_UNITS_PAYLOAD))
    return data_sets


async def _generate(
    tmp_path: Path, *, override: dict[str, Any] | None, operands: list[dict[str, object]] | None = None
) -> dict[str, str]:
    """Generate the questionnaire target over the fixture and read the emitted FSH back by relative path."""
    await _scaffold_project(tmp_path)
    _mock_metadata(override=override, operands=operands)
    await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))
    fsh_root = tmp_path / "ig" / "input" / "fsh"
    return {
        str(path.relative_to(fsh_root)): path.read_text(encoding="utf-8") for path in sorted(fsh_root.rglob("*.fsh"))
    }


@respx.mock
async def test_the_data_set_fetch_asks_for_the_join_category_combo(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    mock_organisation_unit_levels: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The override rides the projection the elements ride, so knowing it costs no second request."""
    mock_system_info("v42")
    mock_attributes()
    mock_organisation_unit_levels()
    await _scaffold_project(tmp_path)
    data_sets = _mock_metadata(override=_AGE_COMBO)

    await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    combo = (
        "categoryCombo[id,name,isDefault,categories[id,categoryOptions[id]],"
        "categoryOptionCombos[id,name,code,categoryOptions[id]]]"
    )
    element = (
        "dataElement[id,code,name,formName,description,valueType,domainType,optionSet[id],"
        f"translations[locale,property,value],{combo}]"
    )
    projections = [str(call.request.url.params["fields"]) for call in data_sets.calls]
    carrying_elements = [fields for fields in projections if "dataSetElements[" in fields]
    assert len(carrying_elements) == 1
    assert f"dataSetElements[{element},{combo}]" in carrying_elements[0]


@respx.mock
async def test_an_override_disaggregates_the_question_into_its_own_cells(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    mock_organisation_unit_levels: Callable[..., None],
    wire_version: str,
    tmp_path: Path,
) -> None:
    """A data set that states a four-way split over a default-combo element publishes four cells per question."""
    mock_system_info(wire_version)
    mock_attributes()
    mock_organisation_unit_levels()

    content = (await _generate(tmp_path, override=_AGE_COMBO))["data-sets/ce7DSxx5H2I.fsh"]

    for uid in ("eY5ehpbEsB7", "Ix2HsbDMLea"):
        assert f'* item[+].linkId = "{uid}"' in content
        assert "* item[=].type = #group" in content
        for option_combo_uid in _AGE_OPTION_COMBO_UIDS:
            assert f'* item[=].item[+].linkId = "{uid}.{option_combo_uid}"' in content
    assert content.count("linkId") == 2 + 2 * len(_AGE_OPTION_COMBO_UIDS)


@respx.mock
async def test_without_an_override_the_data_elements_own_combo_stands(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    mock_organisation_unit_levels: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A data set that restates nothing holds the element's own cells - here the default combo's single one."""
    mock_system_info("v42")
    mock_attributes()
    mock_organisation_unit_levels()

    content = (await _generate(tmp_path, override=None))["data-sets/ce7DSxx5H2I.fsh"]

    assert '* item[+].linkId = "eY5ehpbEsB7"' in content
    assert "#group" not in content
    for option_combo_uid in _AGE_OPTION_COMBO_UIDS:
        assert option_combo_uid not in content


@respx.mock
async def test_an_override_naming_the_elements_own_combo_changes_nothing(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    mock_organisation_unit_levels: Callable[..., None],
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Restating the combo an element already carries is a no-op, byte for byte across every file."""
    mock_system_info("v42")
    mock_attributes()
    mock_organisation_unit_levels()

    restated = await _generate(tmp_path, override=_DEFAULT_COMBO)
    plain = await _generate(tmp_path_factory.mktemp("plain"), override=None)

    assert restated == plain


@respx.mock
async def test_the_option_combos_of_an_override_reach_the_category_option_combo_vocabulary(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    mock_organisation_unit_levels: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Every cell the forms hold is a concept of `D2COC_CS`, decomposed into the category it splits over."""
    mock_system_info("v42")
    mock_attributes()
    mock_organisation_unit_levels()

    artifacts = await _generate(tmp_path, override=_AGE_COMBO)

    content = artifacts["data-dictionary/category-option-combos.fsh"]
    for option_combo_uid in _AGE_OPTION_COMBO_UIDS:
        assert f"* #{option_combo_uid}" in content
    assert '* #Coc0to11moo "0-11m"' in content
    assert (
        "* #Coc0to11moo ^property[=].valueCoding = "
        'http://example.org/fhir/CodeSystem/d2-cat-Ca1aaaaaaaa-cs#Opt0to11moo "0-11m"' in content
    )
    assert "HllvX50cXC0" not in content


@respx.mock
async def test_a_compulsory_operand_requires_a_cell_of_the_override(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    mock_organisation_unit_levels: Callable[..., None],
    tmp_path: Path,
) -> None:
    """An operand names the cell by the option combo the data set holds it over, so the override grades it."""
    mock_system_info("v42")
    mock_attributes()
    mock_organisation_unit_levels()
    operands: list[dict[str, object]] = [
        {"dataElement": {"id": "eY5ehpbEsB7"}, "categoryOptionCombo": {"id": "Coc0to11moo"}}
    ]

    content = (await _generate(tmp_path, override=_AGE_COMBO, operands=operands))["data-sets/ce7DSxx5H2I.fsh"]

    required = content.split('* item[=].item[+].linkId = "eY5ehpbEsB7.Coc0to11moo"')[1]
    assert required.split("linkId")[0].count("* item[=].item[=].required = true") == 1
    assert content.count("required = true") == 1


@respx.mock
async def test_an_example_answers_the_cell_of_the_override_it_holds_a_value_for(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    mock_organisation_unit_levels: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A live value is keyed by the option combo of the override, so the example answers that cell."""
    mock_system_info("v42")
    mock_attributes()
    mock_organisation_unit_levels()
    await _scaffold_project(tmp_path, examples_source="instance")
    _mock_metadata(override=_AGE_COMBO)
    respx.get(f"{_HOST}/api/dataValueSets").mock(return_value=httpx.Response(200, json=_DATA_VALUE_SET))
    respx.get(f"{_HOST}/api/tracker/events").mock(return_value=httpx.Response(200, json={"instances": []}))

    await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))
    report = await service.generate_examples(resolve_profile("probe"), load_project(tmp_path))

    assert report.example_count == 1
    content = (tmp_path / "ig" / "input" / "fsh" / "examples" / "ce7DSxx5H2I-1.fsh").read_text(encoding="utf-8")
    assert '* item[=].item[+].linkId = "eY5ehpbEsB7.Coc0to11moo"' in content
    assert "* item[=].item[=].answer[+].valueInteger = 7" in content
    assert '* item[=].item[+].linkId = "eY5ehpbEsB7.Coc12to59mo"' in content
    assert "* item[=].item[=].answer[+].valueInteger = 3" in content


@respx.mock
async def test_a_load_set_response_answers_the_cells_of_the_override(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A synthetic response is drawn against the form the data set really holds, cell for cell."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    _mock_metadata(override=_AGE_COMBO)

    report = await service.generate_load_set(resolve_profile("probe"), load_project(tmp_path), per_target=1)

    assert report.response_count == 1
    document = json.loads((tmp_path / "load" / "ce7DSxx5H2I-example-1.json").read_text(encoding="utf-8"))
    link_ids = {child["linkId"] for item in document["item"] for child in item.get("item", [])}
    assert link_ids == {
        f"{data_element_uid}.{option_combo_uid}"
        for data_element_uid in ("eY5ehpbEsB7", "Ix2HsbDMLea")
        for option_combo_uid in _AGE_OPTION_COMBO_UIDS
    }
