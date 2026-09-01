"""`GET /facade/data-sets/{uid}/responses`: the wire read it holds DHIS2 to, and the forms it answers.

Mocked (respx); no live stack. The store is the compiled capture fixture, whose aggregate forms are
the very Questionnaires a served value is projected through - `BfMAe6Itzgt` on the default category
combo, and `TuL8IOPzpHh` on a non-default one, which is what makes "one document per attribute option
combo" a claim these tests can make rather than assert about a hypothetical instance.

What is asserted about the wire is the discipline the read is built on: the data set, the one
organisation unit, and the periods the request named, and nothing that would widen it - no
`children`, no date range.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile
from dhis2w_fhir.config import DataSetsConfig, FhirProject, ServeAuth, ServeJwtConfig, TrackedEntitiesConfig
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.capability import build_server_capability
from dhis2w_fhir_serve.capture.naming import CaptureNaming
from dhis2w_fhir_serve.passthrough import open_pass_through_client
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import load_compiled_store
from fastapi import FastAPI
from fixture_project import CAPTURE_CANONICAL, CAPTURE_IDENTIFIER_BASE
from joserfc.jwk import RSAKey

_HOST = "https://dhis2.example"
_BASE_URL = "http://serve.test"
_SYSTEM_INFO = {"version": "2.42.0"}

_DATA_VALUE_SETS_URL = f"{_HOST}/api/dataValueSets"

#: The two aggregate forms the fixture publishes: one on the default category combo, one on a
#: category combo whose responses have to name the attribute option combo they are filed under.
_DATA_SET_UID = "BfMAe6Itzgt"
_COMBO_DATA_SET_UID = "TuL8IOPzpHh"

_ORG_UNIT_UID = "ImspTQPwCqd"
_OTHER_ORG_UNIT_UID = "DiszpKrYNg8"
_PERIOD = "202607"
_EARLIER_PERIOD = "202606"

#: Two cells of the immunization section of `BfMAe6Itzgt`, and one of the section beneath it.
_BCG_ELEMENT = "s46m5MS0hxu"
_IMMUNIZED_ELEMENT = "UOlfIjgN8X6"
_FIXED_UNDER_ONE = "Prlt0C1RF0s"
_FIXED_OVER_ONE = "psbwp3CQEhs"

#: One cell of the non-default-combo form, and two combos its values may be filed under.
_COMBO_ELEMENT = "cZnQDuF3IDz"
_COMBO_CATEGORY_OPTION_COMBO = "fsFN9T4ck3E"
_EDUCATION_COMBO = "oawMLLH7OjA"
_WATER_COMBO = "pO5CEqK6c1s"

_DATA_SET_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/{_DATA_SET_UID}"
_AGGREGATE_PROFILE = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-aggregate-response"
_PERIOD_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-period"
_FORM_TYPE_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-form-type"
_ATTRIBUTE_OPTION_COMBO_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-attribute-option-combo"
_ATTRIBUTE_OPTION_COMBO_CODE_SYSTEM = f"{CAPTURE_CANONICAL}/CodeSystem/d2-aoc-idcDPkDtepR-cs"

_PROFILES_TOML = """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""


def _value(
    data_element: str,
    category_option_combo: str,
    value: str,
    *,
    org_unit: str | None = None,
    period: str | None = None,
    attribute_option_combo: str | None = None,
) -> dict[str, Any]:
    """One data value as `/api/dataValueSets` exports it, with the keys it states left off when absent."""
    stated: dict[str, Any] = {
        "dataElement": data_element,
        "categoryOptionCombo": category_option_combo,
        "value": value,
    }
    if org_unit is not None:
        stated["orgUnit"] = org_unit
    if period is not None:
        stated["period"] = period
    if attribute_option_combo is not None:
        stated["attributeOptionCombo"] = attribute_option_combo
    return stated


def _envelope(*values: dict[str, Any], **keys: str) -> dict[str, Any]:
    """One export envelope carrying the values, and whatever envelope-level keys the case is about."""
    return {"dataValues": list(values), **keys}


def _export(*values: dict[str, Any], **keys: str) -> respx.Route:
    """Mock the data value export one read comes off."""
    return respx.get(_DATA_VALUE_SETS_URL).mock(return_value=httpx.Response(200, json=_envelope(*values, **keys)))


@pytest.fixture
def data_sets() -> DataSetsConfig:
    """The `[serve.data_sets]` table the app under test was started with; override to change it."""
    return DataSetsConfig()


@pytest.fixture
def data_set_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Profile:
    """A Basic profile against the mocked host, resolvable from a config home of this test's own."""
    config_directory = tmp_path / ".config" / "dhis2"
    config_directory.mkdir(parents=True)
    (config_directory / "profiles.toml").write_text(_PROFILES_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_directory.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    return Profile(base_url=_HOST, auth="basic", username="admin", password="district")


@pytest.fixture
async def data_set_client(
    capture_project: FhirProject,
    data_set_profile: Profile,
    data_sets: DataSetsConfig,
) -> AsyncIterator[httpx.AsyncClient]:
    """The facade over the capture guide, holding a DHIS2 client against the mocked host."""
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(ServeSettings(project_dir=capture_project.project_root, data_sets=data_sets))
        async with (
            app.router.lifespan_context(app),
            open_client(data_set_profile) as dhis2,
        ):
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


@pytest.fixture
async def compiled_client(compiled_project: FhirProject) -> AsyncIterator[httpx.AsyncClient]:
    """The same facade with no instance behind it, which is what a compiled run is."""
    app: FastAPI = create_app(ServeSettings(project_dir=compiled_project.project_root))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
            yield http


def _responses_url(data_set_uid: str = _DATA_SET_UID, query: str = f"orgUnit={_ORG_UNIT_UID}&period={_PERIOD}") -> str:
    """The collection address one read is made at, with the bounds a read always carries."""
    return f"/facade/data-sets/{data_set_uid}/responses?{query}"


def _link(bundle: dict[str, Any], relation: str) -> str | None:
    """One relation's URL out of a Bundle's links, or None when the Bundle offers no such link."""
    return next((link["url"] for link in bundle.get("link", []) if link["relation"] == relation), None)


def _parameters(url: str) -> dict[str, list[str]]:
    """The query one link carries, as a client reading it would."""
    return parse_qs(urlsplit(url).query)


def _matches(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """The matched resources of a searchset, which is every entry but an `outcome` one."""
    return [entry["resource"] for entry in bundle.get("entry", []) if entry["search"]["mode"] == "match"]


def _extensions(response: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The extensions one document carries, keyed by url."""
    return {extension["url"]: extension for extension in response.get("extension", [])}


def _answers(response: dict[str, Any]) -> dict[str, Any]:
    """Every answered cell of one document, keyed by link id - the shape both directions are pinned on."""
    found: dict[str, Any] = {}

    def _walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            if item.get("answer"):
                found[item["linkId"]] = item["answer"]
            _walk(item.get("item", []))

    _walk(response.get("item", []))
    return found


def test_the_naming_states_the_system_a_data_set_form_is_published_under(capture_project: FhirProject) -> None:
    """The join key: a form is found by the DHIS2 data set UID it carries, under the guide's own system."""
    naming = CaptureNaming.from_project(capture_project)

    assert naming.data_set_identifier_system == f"{CAPTURE_IDENTIFIER_BASE}/id/data-set"


async def test_the_read_names_the_data_set_the_unit_and_the_periods_and_nothing_wider(
    data_set_client: httpx.AsyncClient,
) -> None:
    """The bounds the request stated are the bounds the instance is asked under - no subtree, no range."""
    read = _export(_value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "12", org_unit=_ORG_UNIT_UID, period=_PERIOD))

    response = await data_set_client.get(_responses_url())

    assert response.status_code == 200
    assert len(read.calls) == 1
    parameters = parse_qs(urlsplit(str(read.calls[0].request.url)).query)
    assert parameters["dataSet"] == [_DATA_SET_UID]
    assert parameters["orgUnit"] == [_ORG_UNIT_UID]
    assert parameters["period"] == [_PERIOD]
    assert "children" not in parameters
    assert "startDate" not in parameters


async def test_one_reporting_key_is_served_as_the_document_its_data_set_form_describes(
    data_set_client: httpx.AsyncClient,
) -> None:
    """The document is the capture contract's own: the data set's form, the unit, the period, the cells."""
    _export(
        _value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "12", org_unit=_ORG_UNIT_UID, period=_PERIOD),
        _value(_IMMUNIZED_ELEMENT, _FIXED_OVER_ONE, "57.5", org_unit=_ORG_UNIT_UID, period=_PERIOD),
    )

    body = (await data_set_client.get(_responses_url())).json()
    [response] = _matches(body)

    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    assert body["total"] == 1
    assert response["resourceType"] == "QuestionnaireResponse"
    assert response["id"] == f"{_ORG_UNIT_UID}-{_PERIOD}-default"
    assert response["questionnaire"] == _DATA_SET_QUESTIONNAIRE
    assert response["status"] == "completed"
    assert response["meta"]["profile"] == [_AGGREGATE_PROFILE]
    assert response["subject"] == {"reference": f"Location/{_ORG_UNIT_UID}"}
    assert _answers(response) == {
        f"{_BCG_ELEMENT}.{_FIXED_UNDER_ONE}": [{"valueInteger": 12}],
        f"{_IMMUNIZED_ELEMENT}.{_FIXED_OVER_ONE}": [{"valueDecimal": 57.5}],
    }


async def test_the_document_dates_itself_with_the_period_the_values_were_reported_for(
    data_set_client: httpx.AsyncClient,
) -> None:
    """The D2Period extension, in the one spelling `$generate` also writes: the ISO, the type, the range."""
    _export(_value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "12", org_unit=_ORG_UNIT_UID, period=_PERIOD))

    body = (await data_set_client.get(_responses_url())).json()
    extensions = _extensions(_matches(body)[0])
    period = {part["url"]: part for part in extensions[_PERIOD_EXTENSION]["extension"]}

    assert period["iso"]["valueString"] == _PERIOD
    assert period["type"]["valueCode"] == "Monthly"
    assert period["period"]["valuePeriod"] == {"start": "2026-07-01", "end": "2026-07-31"}
    assert extensions[_FORM_TYPE_EXTENSION]["valueCode"] == "aggregate"


async def test_a_value_naming_no_key_of_its_own_takes_the_envelopes(data_set_client: httpx.AsyncClient) -> None:
    """DHIS2 reads the envelope's keys as the default for a value that names none, and so does this."""
    _export(
        _value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "12"),
        _value(_IMMUNIZED_ELEMENT, _FIXED_OVER_ONE, "57.5"),
        orgUnit=_ORG_UNIT_UID,
        period=_PERIOD,
    )

    body = (await data_set_client.get(_responses_url())).json()
    [response] = _matches(body)

    assert body["total"] == 1
    assert response["id"] == f"{_ORG_UNIT_UID}-{_PERIOD}-default"
    assert len(_answers(response)) == 2


async def test_a_data_set_on_a_non_default_category_combo_answers_one_document_per_combo(
    data_set_client: httpx.AsyncClient,
) -> None:
    """The attribute option combo is the third reporting key, so two combos are two forms, each coded."""
    _export(
        _value(
            _COMBO_ELEMENT,
            _COMBO_CATEGORY_OPTION_COMBO,
            "76.8",
            org_unit=_ORG_UNIT_UID,
            period=_PERIOD,
            attribute_option_combo=_EDUCATION_COMBO,
        ),
        _value(
            _COMBO_ELEMENT,
            _COMBO_CATEGORY_OPTION_COMBO,
            "9.1",
            org_unit=_ORG_UNIT_UID,
            period=_PERIOD,
            attribute_option_combo=_WATER_COMBO,
        ),
    )

    body = (await data_set_client.get(_responses_url(_COMBO_DATA_SET_UID))).json()
    responses = _matches(body)

    assert body["total"] == 2
    assert [response["id"] for response in responses] == [
        f"{_ORG_UNIT_UID}-{_PERIOD}-{_EDUCATION_COMBO}",
        f"{_ORG_UNIT_UID}-{_PERIOD}-{_WATER_COMBO}",
    ]
    education = _extensions(responses[0])[_ATTRIBUTE_OPTION_COMBO_EXTENSION]
    assert education["valueCoding"] == {
        "system": _ATTRIBUTE_OPTION_COMBO_CODE_SYSTEM,
        "code": _EDUCATION_COMBO,
        "display": "Provide access to basic education",
    }
    assert all(response["meta"]["profile"] == [_AGGREGATE_PROFILE] for response in responses)


async def test_one_combo_can_be_asked_for_on_its_own(data_set_client: httpx.AsyncClient) -> None:
    """`attributeOptionCombo` narrows the answer to the values filed under one of them."""
    _export(
        _value(
            _COMBO_ELEMENT,
            _COMBO_CATEGORY_OPTION_COMBO,
            "76.8",
            org_unit=_ORG_UNIT_UID,
            period=_PERIOD,
            attribute_option_combo=_EDUCATION_COMBO,
        ),
        _value(
            _COMBO_ELEMENT,
            _COMBO_CATEGORY_OPTION_COMBO,
            "9.1",
            org_unit=_ORG_UNIT_UID,
            period=_PERIOD,
            attribute_option_combo=_WATER_COMBO,
        ),
    )

    query = f"orgUnit={_ORG_UNIT_UID}&period={_PERIOD}&attributeOptionCombo={_WATER_COMBO}"
    body = (await data_set_client.get(_responses_url(_COMBO_DATA_SET_UID, query))).json()

    assert body["total"] == 1
    assert [response["id"] for response in _matches(body)] == [f"{_ORG_UNIT_UID}-{_PERIOD}-{_WATER_COMBO}"]


async def test_several_periods_are_several_forms_ordered_by_the_reporting_key(
    data_set_client: httpx.AsyncClient,
) -> None:
    """The order is `(orgUnit, period, attributeOptionCombo)` ascending, so two reads answer the same bytes."""
    read = _export(
        _value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "12", org_unit=_OTHER_ORG_UNIT_UID, period=_PERIOD),
        _value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "9", org_unit=_ORG_UNIT_UID, period=_PERIOD),
        _value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "7", org_unit=_ORG_UNIT_UID, period=_EARLIER_PERIOD),
    )

    query = f"orgUnit={_ORG_UNIT_UID}&period={_PERIOD}&period={_EARLIER_PERIOD}"
    body = (await data_set_client.get(_responses_url(query=query))).json()

    assert parse_qs(urlsplit(str(read.calls[0].request.url)).query)["period"] == [_PERIOD, _EARLIER_PERIOD]
    assert [response["id"] for response in _matches(body)] == [
        f"{_OTHER_ORG_UNIT_UID}-{_PERIOD}-default",
        f"{_ORG_UNIT_UID}-{_EARLIER_PERIOD}-default",
        f"{_ORG_UNIT_UID}-{_PERIOD}-default",
    ]


async def test_a_page_is_a_slice_of_the_selection_and_the_links_carry_the_bounds(
    data_set_client: httpx.AsyncClient,
) -> None:
    """`_count` and `page` walk the ordered selection, and every link still names the read's own bounds."""
    _export(
        *[
            _value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "1", org_unit=unit, period=_PERIOD)
            for unit in ("AAaaaaaaaa1", "BBbbbbbbbb2", "CCcccccccc3")
        ]
    )

    first = (await data_set_client.get(f"{_responses_url()}&_count=2")).json()
    second = (await data_set_client.get(_link(first, "next") or "")).json()
    back = (await data_set_client.get(_link(second, "previous") or "")).json()

    assert [response["subject"]["reference"] for response in _matches(first)] == [
        "Location/AAaaaaaaaa1",
        "Location/BBbbbbbbbb2",
    ]
    assert [response["subject"]["reference"] for response in _matches(second)] == ["Location/CCcccccccc3"]
    assert [response["id"] for response in _matches(back)] == [response["id"] for response in _matches(first)]
    assert first["total"] == second["total"] == 3
    assert _link(first, "previous") is None
    assert _link(second, "next") is None
    assert _parameters(_link(second, "self") or "")["orgUnit"] == [_ORG_UNIT_UID]
    assert _parameters(_link(second, "self") or "")["period"] == [_PERIOD]


async def test_count_zero_asks_how_many_forms_the_selection_holds(data_set_client: httpx.AsyncClient) -> None:
    """R4's request for the total alone: how many forms were reported, and none of them."""
    _export(
        _value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "1", org_unit=_ORG_UNIT_UID, period=_PERIOD),
        _value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "2", org_unit=_OTHER_ORG_UNIT_UID, period=_PERIOD),
    )

    body = (await data_set_client.get(f"{_responses_url()}&_count=0")).json()

    assert body["total"] == 2
    assert "entry" not in body


async def test_a_count_above_the_limit_is_served_the_limit(data_set_client: httpx.AsyncClient) -> None:
    """A page is bounded by `[serve.data_sets] page_size_limit`, clamped rather than refused."""
    _export(_value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "1", org_unit=_ORG_UNIT_UID, period=_PERIOD))

    body = (await data_set_client.get(f"{_responses_url()}&_count=5000")).json()

    assert _parameters(_link(body, "self") or "")["_count"] == ["100"]


async def test_one_reported_form_is_read_at_the_url_its_entry_names(data_set_client: httpx.AsyncClient) -> None:
    """The id carries all three keys, so the item read needs no parameters and names its own bounds."""
    _export(_value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "12", org_unit=_ORG_UNIT_UID, period=_PERIOD))

    body = (await data_set_client.get(_responses_url())).json()
    entry_url = body["entry"][0]["fullUrl"]
    read = await data_set_client.get(entry_url)
    missing = await data_set_client.get(
        f"/facade/data-sets/{_DATA_SET_UID}/responses/{_OTHER_ORG_UNIT_UID}-{_PERIOD}-default"
    )

    assert entry_url == (f"{_BASE_URL}/facade/data-sets/{_DATA_SET_UID}/responses/{_ORG_UNIT_UID}-{_PERIOD}-default")
    assert read.status_code == 200
    assert read.json()["id"] == f"{_ORG_UNIT_UID}-{_PERIOD}-default"
    assert missing.status_code == 404


async def test_a_read_naming_no_period_is_refused_before_the_instance_is_asked(
    data_set_client: httpx.AsyncClient,
) -> None:
    """Ignoring it would answer every period the data set collects to a client that asked about one."""
    read = _export()

    response = await data_set_client.get(f"/facade/data-sets/{_DATA_SET_UID}/responses?orgUnit={_ORG_UNIT_UID}")

    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "invalid"
    assert "`period` is required" in response.json()["issue"][0]["diagnostics"]
    assert not read.called


async def test_a_read_naming_no_organisation_unit_is_refused_the_same_way(
    data_set_client: httpx.AsyncClient,
) -> None:
    """The other half of the same bound, and the refusal names both so one round trip states the whole rule."""
    read = _export()

    response = await data_set_client.get(f"/facade/data-sets/{_DATA_SET_UID}/responses?period={_PERIOD}")

    assert response.status_code == 400
    diagnostics = response.json()["issue"][0]["diagnostics"]
    assert "`orgUnit` is required" in diagnostics
    assert "at least one `period`" in diagnostics
    assert not read.called


@pytest.mark.parametrize("data_sets", [DataSetsConfig(period_limit=2)])
async def test_more_periods_than_the_project_answers_at_once_is_refused_with_both_numbers(
    data_set_client: httpx.AsyncClient,
) -> None:
    """Splitting the read is the client's move, and it cannot make it without the count and the limit."""
    read = _export()

    query = f"orgUnit={_ORG_UNIT_UID}&period=202601&period=202602&period=202603"
    response = await data_set_client.get(_responses_url(query=query))

    assert response.status_code == 400
    diagnostics = response.json()["issue"][0]["diagnostics"]
    assert "this request names 3 `period` values" in diagnostics
    assert "at most 2" in diagnostics
    assert "`[serve.data_sets] period_limit`" in diagnostics
    assert not read.called


async def test_a_period_this_server_cannot_read_is_refused_rather_than_asked_about(
    data_set_client: httpx.AsyncClient,
) -> None:
    """DHIS2 answers an unparseable period with an empty export, which reads as `nothing was reported`."""
    read = _export()

    response = await data_set_client.get(_responses_url(query=f"orgUnit={_ORG_UNIT_UID}&period=last-month"))

    assert response.status_code == 400
    assert "`period` was given `last-month`" in response.json()["issue"][0]["diagnostics"]
    assert not read.called


async def test_a_parameter_this_surface_cannot_apply_is_refused(data_set_client: httpx.AsyncClient) -> None:
    """Ignoring one would answer a narrower question with the whole selection."""
    read = _export()

    response = await data_set_client.get(f"{_responses_url()}&children=true")

    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "invalid"
    assert "`children`" in response.json()["issue"][0]["diagnostics"]
    assert not read.called


async def test_a_data_set_this_guide_publishes_no_form_for_is_a_404(data_set_client: httpx.AsyncClient) -> None:
    """There is nothing to serve the values as, and nothing else the request could have meant."""
    read = _export()

    response = await data_set_client.get(_responses_url("Zz00nOtHeRe"))

    assert response.status_code == 404
    assert response.json()["issue"][0]["diagnostics"] == "no data set with id `Zz00nOtHeRe` is served here"
    assert not read.called


@pytest.mark.parametrize("data_sets", [DataSetsConfig(data_sets=[_COMBO_DATA_SET_UID])])
async def test_a_data_set_outside_the_projects_own_list_is_answered_the_same_way(
    data_set_client: httpx.AsyncClient,
) -> None:
    """A project that named the data sets it answers for has said the others are not served here."""
    read = _export()

    response = await data_set_client.get(_responses_url())

    assert response.status_code == 404
    assert response.json()["issue"][0]["diagnostics"] == f"no data set with id `{_DATA_SET_UID}` is served here"
    assert not read.called


@pytest.mark.parametrize("data_sets", [DataSetsConfig(responses=False)])
async def test_a_project_serving_forms_alone_refuses_the_values_and_names_the_key(
    data_set_client: httpx.AsyncClient,
) -> None:
    """`[serve.data_sets] responses = false` is a decision the refusal states in the operator's words."""
    read = _export()

    response = await data_set_client.get(_responses_url())

    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-supported"
    assert "`[serve.data_sets] responses = true`" in response.json()["issue"][0]["diagnostics"]
    assert not read.called


async def test_a_compiled_run_answers_that_it_has_no_instance_to_read(compiled_client: httpx.AsyncClient) -> None:
    """A compiled guide has nothing to answer about, and says so rather than answering an empty selection."""
    response = await compiled_client.get(_responses_url())

    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-supported"
    assert "--live" in response.json()["issue"][0]["diagnostics"]


@pytest.mark.parametrize(
    ("data_sets", "declared"),
    [(DataSetsConfig(), True), (DataSetsConfig(responses=False), False)],
)
def test_the_capability_statement_states_where_a_data_sets_values_are_read(
    capture_project: FhirProject, data_sets: DataSetsConfig, declared: bool
) -> None:
    """`/metadata` names the address, on the resource type whose documents it answers with."""
    store = load_compiled_store(capture_project)
    settings = ServeSettings(project_dir=capture_project.project_root, live=True, data_sets=data_sets)
    statement = build_server_capability(
        project=capture_project,
        store_summary=store.summary(),
        settings=settings,
        register_surface=RegisterSurface.resolve(
            TrackedEntityIndex.from_store(capture_project, store), TrackedEntitiesConfig()
        ),
        server_version="9.9.9",
    )
    documentation = " ".join(
        resource.documentation or "" for rest in statement.rest or [] for resource in rest.resource or []
    )

    assert ("/facade/data-sets/{uid}/responses" in documentation) is declared


# ---------------------------------------------------------------------------------------------
# The credentials: DHIS2's verdict carried as it stands, and never a fall back to this facade's own.
# ---------------------------------------------------------------------------------------------

_ISSUER = "https://issuer.example/realms/facade"
_DISCOVERY_URL = f"{_ISSUER}/.well-known/openid-configuration"
_JWKS_URL = f"{_ISSUER}/protocol/openid-connect/certs"


@pytest.fixture
async def forwarding_client(capture_project: FhirProject) -> AsyncIterator[httpx.AsyncClient]:
    """A facade under `[serve] auth = "dhis2"`, reading the instance as whoever asked."""
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(
            ServeSettings(
                project_dir=capture_project.project_root,
                auth=ServeAuth.DHIS2,
                dhis2_base_url=_HOST,
            )
        )
        async with (
            app.router.lifespan_context(app),
            open_pass_through_client(_HOST, provenance="dhis2w-fhir-serve/9.9.9") as pool,
        ):
            app.state.live_client = pool
            app.state.caller_client = pool
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


async def test_the_read_carries_the_callers_own_credentials_to_the_instance(
    forwarding_client: httpx.AsyncClient,
) -> None:
    """Under the `dhis2` posture the values come back as the caller sees them, not as the facade does."""
    respx.get(f"{_HOST}/api/me").mock(return_value=httpx.Response(200, json={"username": "clerk"}))
    read = _export(_value(_BCG_ELEMENT, _FIXED_UNDER_ONE, "12", org_unit=_ORG_UNIT_UID, period=_PERIOD))

    response = await forwarding_client.get(_responses_url(), headers={"Authorization": "Basic Y2xlcms6cHc="})

    assert response.status_code == 200
    assert read.calls.last.request.headers["authorization"] == "Basic Y2xlcms6cHc="


async def test_a_refusal_the_instance_gave_the_caller_is_answered_as_it_stands(
    forwarding_client: httpx.AsyncClient,
) -> None:
    """A 403 about the caller is carried through rather than dressed as this server failing to read."""
    respx.get(f"{_HOST}/api/me").mock(return_value=httpx.Response(200, json={"username": "clerk"}))
    respx.get(_DATA_VALUE_SETS_URL).mock(return_value=httpx.Response(403, json={"message": "no data view access"}))

    response = await forwarding_client.get(_responses_url(), headers={"Authorization": "Basic Y2xlcms6cHc="})

    assert response.status_code == 403
    assert response.json()["issue"][0]["code"] == "forbidden"


async def test_a_request_with_no_credential_is_refused_rather_than_read_as_the_facade(
    forwarding_client: httpx.AsyncClient,
) -> None:
    """There is nobody to answer as, and answering as the facade's own profile is the read this prevents."""
    read = _export()

    response = await forwarding_client.get(_responses_url())

    assert response.status_code == 401
    assert "realm=" in response.headers["WWW-Authenticate"]
    assert not read.called


@pytest.fixture
async def unforwarded_client(capture_project: FhirProject) -> AsyncIterator[httpx.AsyncClient]:
    """A facade under `auth = "jwt"` with `[serve.jwt] forward_bearer` off, which forwards nothing."""
    with respx.mock:
        respx.get(_DISCOVERY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "issuer": _ISSUER,
                    "authorization_endpoint": f"{_ISSUER}/protocol/openid-connect/auth",
                    "token_endpoint": f"{_ISSUER}/protocol/openid-connect/token",
                    "jwks_uri": _JWKS_URL,
                },
            )
        )
        key = RSAKey.generate_key(2048, parameters={"kid": "rsa-1", "use": "sig", "alg": "RS256"})
        respx.get(_JWKS_URL).mock(return_value=httpx.Response(200, json={"keys": [key.as_dict(private=False)]}))
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(
            ServeSettings(
                project_dir=capture_project.project_root,
                auth=ServeAuth.JWT,
                dhis2_base_url=_HOST,
                jwt=ServeJwtConfig(issuer=_ISSUER, forward_bearer=False),
            )
        )
        async with (
            app.router.lifespan_context(app),
            open_pass_through_client(_HOST, provenance="dhis2w-fhir-serve/9.9.9") as pool,
        ):
            app.state.live_client = pool
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


async def test_a_posture_that_forwards_no_token_answers_no_values_at_all(
    unforwarded_client: httpx.AsyncClient,
) -> None:
    """501 and the two things that would make it answerable, never a read under the facade's own rights."""
    read = _export()

    response = await unforwarded_client.get(_responses_url())

    assert response.status_code == 501
    diagnostics = response.json()["issue"][0]["diagnostics"]
    assert "forward_bearer = true" in diagnostics
    assert "oidc.jwt.token.authentication.enabled" in diagnostics
    assert not read.called
