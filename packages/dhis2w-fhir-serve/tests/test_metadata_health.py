"""`GET /facade/metadata-health`: what a live run reports about the instance, and what a compiled run says instead.

Mocked (respx); no live stack. The instance behind the fixture is seeded with exactly the defects the
page exists to surface - a name carrying `<`, a form name carrying `<`, a code carrying a space, an
organisation unit with no code at all - plus translations in two locales that stop halfway, so the
coverage half has both a covered object and a gap to report.

What is asserted about the findings is that they arrive as `d2w fhir validate` graded them: the same
severity, the same scope, and the same sentence. This route reruns the validator rather than
re-implementing it, and a test that restated the wording here would be a second copy of it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile
from dhis2w_fhir.config import FhirProject, load_fhir_config
from dhis2w_fhir.validation.schemas import ValidationFinding
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.health import (
    COMPILED_RUN_REASON,
    TranslatedObject,
    field_at_fault,
    translation_coverage,
)
from dhis2w_fhir_serve.routes import FACADE_MOUNT_PATH
from dhis2w_fhir_serve.routes.metadata_health import METADATA_HEALTH_PATH
from dhis2w_fhir_serve.settings import ServeSettings
from fastapi import FastAPI

_HOST = "https://dhis2.example"

_BASE_URL = "http://serve.test"

#: Where the report is read. The router states the path relative to the mount it is included
#: under, and this is that path where a request has to be sent.
METADATA_HEALTH_ADDRESS = f"{FACADE_MOUNT_PATH}{METADATA_HEALTH_PATH}"

_SYSTEM_INFO = {"version": "2.42.0"}

_PROFILES_TOML = """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""

_FHIR_TOML = """
[ig]
id = "dhis2.fhir.example"
canonical = "http://example.org/fhir"
name = "Dhis2FhirExample"
title = "DHIS2 FHIR Example IG"
publisher = "Example Organisation"
"""

#: The data elements the seeded data set asks: one clean, one whose name and form name carry '<',
#: one whose code opens with a space.
_CLEAN_ELEMENT = "DeAncVisit1"
_HOSTILE_ELEMENT = "DeHostile01"
_SPACED_CODE_ELEMENT = "DeSpacedCd1"

_DATA_SET = "DsMonthly01"
_OPTION_SET = "OsSymptom01"
_CATEGORY = "CatSex00001"
_CATEGORY_OPTION = "CoFemale001"
_UNIT_WITH_CODE = "OuClinic001"
_UNIT_WITHOUT_CODE = "OuNoCode001"


def _metadata_sweep() -> dict[str, Any]:
    """The instance-wide sweep `d2w fhir validate` grades, seeded with one defect of each kind."""
    return {
        "dataElements": [
            {"id": _CLEAN_ELEMENT, "name": "ANC 1st visit", "formName": "ANC 1st visit", "code": "ANC_1"},
            {"id": _HOSTILE_ELEMENT, "name": "Weight < 50 kg", "formName": "Weight < 50 kg", "code": "WEIGHT_LOW"},
            {"id": _SPACED_CODE_ELEMENT, "name": "Blood pressure", "code": " BLOOD_PRESSURE"},
        ],
        "dataSets": [{"id": _DATA_SET, "name": "Monthly report", "code": "DS_MONTHLY"}],
        "optionSets": [{"id": _OPTION_SET, "name": "Symptom", "code": "SYMPTOM"}],
        "categories": [{"id": _CATEGORY, "name": "Sex", "code": "SEX"}],
        "categoryOptions": [{"id": _CATEGORY_OPTION, "name": "Female", "code": "FEMALE"}],
        "organisationUnits": [
            {"id": _UNIT_WITH_CODE, "name": "Ngelehun CHC", "code": "OU_CLINIC"},
            {"id": _UNIT_WITHOUT_CODE, "name": "Badjia"},
        ],
    }


def _translation(locale: str, property_name: str, value: str) -> dict[str, str]:
    """One DHIS2 translation entry, as the API sends it."""
    return {"locale": locale, "property": property_name, "value": value}


def _data_elements_with_translations() -> dict[str, Any]:
    """The data elements as the translation read sees them: one fully covered, two short of something."""
    return {
        "dataElements": [
            {
                "id": _CLEAN_ELEMENT,
                "name": "ANC 1st visit",
                "formName": "ANC 1st visit",
                "translations": [
                    _translation("fr", "NAME", "Visite CPN 1"),
                    _translation("lo", "NAME", "ກວດຄັ້ງທີ 1"),
                    _translation("fr", "FORM_NAME", "Visite CPN 1"),
                    _translation("lo", "FORM_NAME", "ກວດຄັ້ງທີ 1"),
                ],
            },
            {
                "id": _HOSTILE_ELEMENT,
                "name": "Weight < 50 kg",
                "formName": "Weight < 50 kg",
                "translations": [_translation("fr", "NAME", "Poids < 50 kg")],
            },
            {
                "id": _SPACED_CODE_ELEMENT,
                "name": "Blood pressure",
                "translations": [_translation("fr_CA", "NAME", "Tension arterielle")],
            },
        ]
    }


def _untranslated(resource_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    """One collection's translation read for objects nobody has translated."""
    return {resource_type: [{**entry, "translations": []} for entry in entries]}


def _mock_instance() -> None:
    """Mock every read the health route makes: the selection, the sweep, and the translations."""
    respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
    respx.get(f"{_HOST}/api/metadata").mock(return_value=httpx.Response(200, json=_metadata_sweep()))
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataSets": [
                    {
                        "id": _DATA_SET,
                        "name": "Monthly report",
                        "translations": [],
                        "dataSetElements": [
                            {"dataElement": {"id": _CLEAN_ELEMENT}},
                            {"dataElement": {"id": _HOSTILE_ELEMENT}},
                            {"dataElement": {"id": _SPACED_CODE_ELEMENT}},
                        ],
                    }
                ]
            },
        )
    )
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json={"programs": []}))
    respx.get(f"{_HOST}/api/optionSets").mock(
        return_value=httpx.Response(
            200, json=_untranslated("optionSets", [{"id": _OPTION_SET, "name": "Symptom", "options": []}])
        )
    )
    respx.get(f"{_HOST}/api/categories").mock(
        return_value=httpx.Response(
            200,
            json=_untranslated(
                "categories",
                [{"id": _CATEGORY, "name": "Sex", "categoryOptions": [{"id": _CATEGORY_OPTION, "name": "Female"}]}],
            ),
        )
    )
    respx.get(f"{_HOST}/api/categoryOptions").mock(
        return_value=httpx.Response(
            200, json=_untranslated("categoryOptions", [{"id": _CATEGORY_OPTION, "name": "Female"}])
        )
    )
    respx.get(f"{_HOST}/api/organisationUnits").mock(
        return_value=httpx.Response(
            200,
            json=_untranslated(
                "organisationUnits",
                [{"id": _UNIT_WITH_CODE, "name": "Ngelehun CHC"}, {"id": _UNIT_WITHOUT_CODE, "name": "Badjia"}],
            ),
        )
    )
    respx.get(f"{_HOST}/api/dataElements").mock(
        return_value=httpx.Response(200, json=_data_elements_with_translations())
    )


@pytest.fixture
def health_project(tmp_path: Path) -> FhirProject:
    """A project with a compiled guide on disk, whose selection names nothing and so selects everything."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(_FHIR_TOML, encoding="utf-8")
    compiled = tmp_path / "ig" / "fsh-generated" / "resources"
    compiled.mkdir(parents=True)
    (compiled / "Questionnaire-d2-ds-monthly-q.json").write_text(
        '{"resourceType": "Questionnaire", "id": "d2-ds-monthly-q", "status": "active"}\n', encoding="utf-8"
    )
    return FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())


@pytest.fixture
def health_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Profile:
    """A Basic profile against the mocked host, resolvable from a config home of this test's own."""
    config_directory = tmp_path / ".config" / "dhis2"
    config_directory.mkdir(parents=True)
    (config_directory / "profiles.toml").write_text(_PROFILES_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_directory.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    return Profile(base_url=_HOST, auth="basic", username="admin", password="district")


@pytest.fixture
async def live_health_client(health_project: FhirProject, health_profile: Profile) -> AsyncIterator[httpx.AsyncClient]:
    """The facade over the compiled guide, holding a DHIS2 client against the mocked instance."""
    with respx.mock:
        _mock_instance()
        app: FastAPI = create_app(ServeSettings(project_dir=health_project.project_root))
        async with (
            app.router.lifespan_context(app),
            open_client(health_profile) as dhis2,
        ):
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


@pytest.fixture
async def compiled_health_client(health_project: FhirProject) -> AsyncIterator[httpx.AsyncClient]:
    """The same facade with no instance behind it, which is what a compiled run is."""
    app: FastAPI = create_app(ServeSettings(project_dir=health_project.project_root))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
            yield http


def _finding(body: dict[str, Any], uid: str, category: str, field: str | None = None) -> dict[str, Any]:
    """The one finding of a kind about one object, so a test names what it is asserting about."""
    findings: list[dict[str, Any]] = body["findings"]
    matches = [
        item
        for item in findings
        if item["uid"] == uid and item["category"] == category and (field is None or item["field"] == field)
    ]
    assert len(matches) == 1, f"expected exactly one {category} finding for {uid}, got {len(matches)}"
    return matches[0]


async def test_a_compiled_run_says_there_is_no_instance_behind_it(
    compiled_health_client: httpx.AsyncClient,
) -> None:
    """The refusal is a body a screen renders, not a status code it has to interpret."""
    response = await compiled_health_client.get(METADATA_HEALTH_ADDRESS)
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"] == COMPILED_RUN_REASON
    assert body["findings"] == []


async def test_a_compiled_run_answers_plain_json_rather_than_a_fhir_media_type(
    compiled_health_client: httpx.AsyncClient,
) -> None:
    """The route is outside the FHIR group, so it answers `application/json` and never an OperationOutcome."""
    response = await compiled_health_client.get(METADATA_HEALTH_ADDRESS)
    assert response.headers["content-type"].startswith("application/json")


async def test_the_route_is_not_claimed_by_the_read_catch_all(
    compiled_health_client: httpx.AsyncClient,
) -> None:
    """A hyphen is not a path separator, so `/facade/metadata-health` is neither `/metadata` nor a resource type."""
    metadata = await compiled_health_client.get("/metadata")
    assert metadata.json()["resourceType"] == "CapabilityStatement"
    health = await compiled_health_client.get(METADATA_HEALTH_ADDRESS)
    assert "resourceType" not in health.json()


async def test_a_live_run_reports_the_findings_the_validator_graded(
    live_health_client: httpx.AsyncClient,
) -> None:
    """A name carrying '<' on a selected object is the error it is at the command line."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    assert body["available"] is True
    hostile = _finding(body, _HOSTILE_ELEMENT, "template-hostile-name", field="name")
    assert hostile["severity"] == "error"
    assert hostile["scope"] == "selection"
    assert "'<'" in hostile["message"]
    assert body["counts"]["errors"] >= 1


async def test_a_hostile_form_name_is_reported_as_the_form_name(
    live_health_client: httpx.AsyncClient,
) -> None:
    """The two spellings a question carries are graded under one category, and the row says which one."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    form_name = _finding(body, _HOSTILE_ELEMENT, "template-hostile-name", field="form name")
    assert form_name["message"].startswith("form name ")
    assert form_name["severity"] == "error"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("name Malaria\\x01cases contains the control character \\x01", "name"),
        ("form name Vitamin\\x01A contains the control character \\x01", "form name"),
    ],
    ids=["name", "form-name"],
)
def test_a_control_character_finding_names_the_spelling_it_is_about(message: str, expected: str) -> None:
    """A control character reaches either of a question's two spellings, and the row says which one."""
    finding = ValidationFinding(
        severity="error",
        scope="selection",
        category="control-character-name",
        resource_type="dataElements",
        uid="De1aaaaaaaa",
        name="Vitamin A",
        code="DE1",
        message=message,
    )
    assert field_at_fault(finding) == expected


async def test_a_code_carrying_a_space_is_reported_against_the_code(
    live_health_client: httpx.AsyncClient,
) -> None:
    """A DHIS2 code opening with a space is not a FHIR code, and the row names the code as the field."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    invalid = _finding(body, _SPACED_CODE_ELEMENT, "invalid-code")
    assert invalid["field"] == "code"
    assert invalid["code"] == " BLOOD_PRESSURE"
    assert invalid["severity"] == "warning"
    assert invalid["message"] == "code is not a valid FHIR code: code has leading whitespace"


async def test_an_organisation_unit_with_no_code_is_reported(live_health_client: httpx.AsyncClient) -> None:
    """A unit is expected to carry both identifiers, so a missing code is a finding of its own."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    missing = _finding(body, _UNIT_WITHOUT_CODE, "missing-code")
    assert missing["field"] == "code"
    assert missing["code"] is None


async def test_every_finding_states_what_the_grade_costs(live_health_client: httpx.AsyncClient) -> None:
    """A severity word answers nothing on its own, so each row carries the sentence behind it."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    assert body["findings"]
    assert all(item["cost"] != "" for item in body["findings"])


async def test_the_answer_states_the_posture_the_severities_were_graded_under(
    live_health_client: httpx.AsyncClient,
) -> None:
    """The same name is a blocker under one hostile-names posture and a note under the other."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    assert body["graded_under"].startswith("not set - ")
    assert body["object_count"] > 0


async def test_the_locales_in_use_are_the_ones_the_selection_carries(
    live_health_client: httpx.AsyncClient,
) -> None:
    """No system-settings read: an instance is being maintained in the languages written into it."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    assert body["translations"]["locales"] == ["fr", "fr-CA", "lo"]


async def test_coverage_is_counted_per_locale(live_health_client: httpx.AsyncClient) -> None:
    """Each locale states how many selected objects it covers, for the name and for the form name."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    per_locale = {row["locale"]: row for row in body["translations"]["per_locale"]}
    assert per_locale["fr"]["name_count"] == 2
    assert per_locale["fr"]["form_name_count"] == 1
    assert per_locale["lo"]["name_count"] == 1
    assert per_locale["fr-CA"]["form_name_count"] == 0


async def test_a_locale_few_objects_carry_states_the_objects_that_carry_it(
    live_health_client: httpx.AsyncClient,
) -> None:
    """Three translations out of a whole instance is a short list of carriers, not a wall of absence."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    per_locale = {row["locale"]: row for row in body["translations"]["per_locale"]}
    assert per_locale["fr"]["standing"] == "sparse"
    assert per_locale["fr"]["missing"] == []
    carriers = {carrier["uid"]: carrier for carrier in per_locale["fr"]["carriers"]}
    assert set(carriers) == {_CLEAN_ELEMENT, _HOSTILE_ELEMENT}
    assert carriers[_CLEAN_ELEMENT]["carries_form_name"] is True
    assert carriers[_HOSTILE_ELEMENT]["carries_form_name"] is False


async def test_the_form_named_denominator_counts_only_objects_dhis2_gives_a_form_name(
    live_health_client: httpx.AsyncClient,
) -> None:
    """Nothing to translate is nothing to be short of - a form name is a second string only where there is one."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    assert body["translations"]["form_named_count"] == 2


async def test_no_absent_translation_is_graded_as_a_finding(live_health_client: httpx.AsyncClient) -> None:
    """The severities are the validator's own, and the validator grades names and codes - never a translation."""
    body = (await live_health_client.get(METADATA_HEALTH_ADDRESS)).json()
    counted = body["counts"]["errors"] + body["counts"]["warnings"] + body["counts"]["infos"]
    assert counted == len(body["findings"])
    assert body["translations"]["locales"] != []
    assert not any("translat" in finding["category"] for finding in body["findings"])
    assert not any("translat" in finding["message"].lower() for finding in body["findings"])


async def test_the_uiconfig_says_a_live_run_can_report_on_its_instance(
    live_health_client: httpx.AsyncClient,
) -> None:
    """The navigation asks the settings rather than following a link to find out."""
    body = (await live_health_client.get("/facade/uiconfig")).json()
    assert body["metadata_health"] == {"enabled": True}


async def test_the_uiconfig_says_a_compiled_run_cannot(compiled_health_client: httpx.AsyncClient) -> None:
    """A compiled run has no instance to grade, and the settings say so before a page is offered."""
    body = (await compiled_health_client.get("/facade/uiconfig")).json()
    assert body["metadata_health"] == {"enabled": False}


def _object(
    uid: str,
    *,
    names: set[str],
    form_names: set[str] | None = None,
    form_named: bool = False,
) -> TranslatedObject:
    """One projected object, for the coverage arithmetic that needs no request behind it."""
    return TranslatedObject(
        resource_type="dataElements",
        uid=uid,
        name=uid,
        form_named=form_named,
        name_locales=frozenset(names),
        form_name_locales=frozenset(form_names or set()),
    )


def test_an_instance_nobody_has_translated_reports_no_locales_at_all() -> None:
    """One language is a whole state, not a page of everything being missing."""
    coverage = translation_coverage([_object("Aaa11111111", names=set()), _object("Bbb11111111", names=set())])
    assert coverage.locales == []
    assert coverage.per_locale == []
    assert coverage.object_count == 2


def test_a_locale_three_objects_out_of_many_carry_is_told_through_its_carriers() -> None:
    """A stray translation is what three objects hold, not what the other thousand are short of."""
    carried = [_object(f"Aaa1111111{index}", names={"es"}) for index in range(3)]
    rest = [_object(f"Bbb1111111{index}", names={"en"}) for index in range(9)]
    coverage = translation_coverage(carried + rest)
    assert [item.standing for item in coverage.per_locale] == ["majority", "sparse"]
    row = next(item for item in coverage.per_locale if item.locale == "es")
    assert row.name_count == 3
    assert [carrier.uid for carrier in row.carriers] == ["Aaa11111110", "Aaa11111111", "Aaa11111112"]
    assert row.missing == []


def test_a_locale_most_of_the_selection_carries_is_told_through_the_objects_short_of_it() -> None:
    """Past half the selection, the shorter list is the objects nobody has written the translation for."""
    coverage = translation_coverage(
        [
            _object("Aaa11111111", names={"fr"}),
            _object("Bbb11111111", names={"fr"}),
            _object("Ccc11111111", names=set()),
        ]
    )
    row = coverage.per_locale[0]
    assert row.standing == "majority"
    assert row.carriers == []
    assert [item.uid for item in row.missing] == ["Ccc11111111"]
    assert row.missing[0].name_untranslated is True
    assert row.missing[0].form_name_untranslated is False


def test_a_form_name_is_a_second_string_the_share_is_read_against() -> None:
    """A locale holding every name and no form name has done half the work, which is the boundary itself."""
    objects = [_object(f"Aaa1111111{index}", names={"lo"}, form_named=True) for index in range(4)]
    row = translation_coverage(objects).per_locale[0]
    assert row.standing == "majority"
    assert [item.form_name_untranslated for item in row.missing] == [True, True, True, True]
    assert [item.name_untranslated for item in row.missing] == [False, False, False, False]


def test_an_object_with_no_form_name_is_never_short_of_a_form_name_translation() -> None:
    """Nothing to translate is nothing to be short of, whichever side the locale is told through."""
    coverage = translation_coverage(
        [_object("Aaa11111111", names={"fr"}), _object("Bbb11111111", names={"fr"}, form_named=False)]
    )
    assert coverage.form_named_count == 0
    assert coverage.per_locale[0].standing == "majority"
    assert coverage.per_locale[0].missing == []


def test_listed_objects_are_ordered_by_resource_type_then_name() -> None:
    """Either list is read top to bottom, so it is ordered rather than left in the order DHIS2 answered."""
    coverage = translation_coverage(
        [
            _object("Ccc11111111", names={"fr"}),
            _object("Aaa11111111", names={"lo"}),
            _object("Bbb11111111", names={"fr", "lo"}),
        ]
    )
    french = next(row for row in coverage.per_locale if row.locale == "fr")
    assert french.standing == "majority"
    assert [item.uid for item in french.missing] == ["Aaa11111111"]
