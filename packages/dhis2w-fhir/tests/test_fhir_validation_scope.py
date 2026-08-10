"""Tests for scope-aware validation: severity means build impact on the configured IG, not instance alarm."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import InitOptions, load_project, service
from dhis2w_fhir.config import GenerateConfig
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.validation import build_code_validation, render_validation_markdown, usable_code_stem
from dhis2w_fhir.validation.pdf import render_validation_pdf
from dhis2w_fhir.validation.report import render_validation_csv
from dhis2w_fhir.validation.schemas import (
    MetadataCollectionIn,
    MetadataItemIn,
    ValidationScope,
)

_HOST = "https://dhis2.example"
_CONFIG = GenerateConfig()
_CODE_MODE = GenerateConfig(concept_code_source="code")
_GENERATED_AT = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

#: The option-set code that aborts the publisher on a real national instance.
_ABORTING_CODE = "ENTO - IRS < 6 Months"


def _collection(resource: str, *items: MetadataItemIn) -> MetadataCollectionIn:
    """Build one sweep collection."""
    return MetadataCollectionIn(resource=resource, items=list(items))


def test_scope_contains_maps_the_sweep_collections_to_their_surfaces() -> None:
    """Each surface answers for its sweep collection; a collection with no surface is never in scope."""
    scope = ValidationScope(
        option_sets=frozenset({"Os1aaaaaaaa"}),
        categories=frozenset({"Ca1aaaaaaaa"}),
        organisation_units=frozenset({"Ou1aaaaaaaa"}),
        data_sets=frozenset({"Ds1aaaaaaaa"}),
        programs=frozenset({"Pr1aaaaaaaa"}),
        program_stages=frozenset({"Ps1aaaaaaaa"}),
        data_elements=frozenset({"De1aaaaaaaa"}),
    )
    assert scope.contains("optionSets", "Os1aaaaaaaa")
    assert scope.contains("categories", "Ca1aaaaaaaa")
    assert scope.contains("organisationUnits", "Ou1aaaaaaaa")
    assert scope.contains("dataSets", "Ds1aaaaaaaa")
    assert scope.contains("programs", "Pr1aaaaaaaa")
    assert scope.contains("programStages", "Ps1aaaaaaaa")
    assert scope.contains("dataElements", "De1aaaaaaaa")
    assert not scope.contains("optionSets", "Os2aaaaaaaa")
    assert not scope.contains("dashboards", "Os1aaaaaaaa")
    assert not scope.contains("visualizations", "De1aaaaaaaa")


def test_an_in_scope_invalid_code_is_a_warning_and_out_of_scope_is_info() -> None:
    """The same sweep defect grades by whether the configured build emits the object."""
    scope = ValidationScope(data_elements=frozenset({"De1aaaaaaaa"}))
    report = build_code_validation(
        [],
        [
            _collection(
                "dataElements",
                MetadataItemIn(uid="De1aaaaaaaa", name="Selected", code=" X "),
                MetadataItemIn(uid="De2aaaaaaaa", name="Unselected", code=" Y "),
            )
        ],
        _CONFIG,
        scope=scope,
    )
    by_uid = {finding.uid: finding for finding in report.findings}
    assert (by_uid["De1aaaaaaaa"].severity, by_uid["De1aaaaaaaa"].scope) == ("warning", "selection")
    assert (by_uid["De2aaaaaaaa"].severity, by_uid["De2aaaaaaaa"].scope) == ("info", "instance")
    assert report.selection_warning_count == 1
    assert report.selection_info_count == 0


def test_an_in_scope_aborting_code_is_the_only_error() -> None:
    """A '<' code on a selected identifier surface is the one finding that grades error."""
    scope = ValidationScope(option_sets=frozenset({"Os1aaaaaaaa"}))
    report = build_code_validation(
        [],
        [
            _collection(
                "optionSets",
                MetadataItemIn(uid="Os1aaaaaaaa", name="Selected", code=_ABORTING_CODE),
            )
        ],
        _CONFIG,
        scope=scope,
    )
    assert [(finding.severity, finding.category) for finding in report.findings] == [("error", "template-hostile-code")]
    assert report.findings[0].scope == "selection"
    assert "`make build` aborts" in report.findings[0].message


def test_an_out_of_scope_aborting_code_is_info_but_still_names_the_stakes() -> None:
    """An unselected '<' code cannot abort this project's build, and the message says when it would."""
    report = build_code_validation(
        [],
        [_collection("optionSets", MetadataItemIn(uid="Os1aaaaaaaa", name="Unselected", code=_ABORTING_CODE))],
        _CONFIG,
        scope=ValidationScope(),
    )
    assert [(finding.severity, finding.scope) for finding in report.findings] == [("info", "instance")]
    assert "aborts `make build` the moment the object is selected" in report.findings[0].message


def test_an_unconfirmed_hostile_code_character_grades_warning_in_scope_and_info_out() -> None:
    """'>' and '&' never abort a build, so they top out at warning even on a selected object."""
    scope = ValidationScope(organisation_units=frozenset({"Ou1aaaaaaaa"}))
    report = build_code_validation(
        [],
        [
            _collection(
                "organisationUnits",
                MetadataItemIn(uid="Ou1aaaaaaaa", name="Selected", code="A&E"),
                MetadataItemIn(uid="Ou2aaaaaaaa", name="Unselected", code="OVER>5"),
            )
        ],
        _CONFIG,
        scope=scope,
    )
    by_uid = {finding.uid: finding for finding in report.findings}
    assert (by_uid["Ou1aaaaaaaa"].severity, by_uid["Ou1aaaaaaaa"].scope) == ("warning", "selection")
    assert (by_uid["Ou2aaaaaaaa"].severity, by_uid["Ou2aaaaaaaa"].scope) == ("info", "instance")


def test_an_organisation_unit_missing_code_grades_by_scope() -> None:
    """The registry's missing-code finding is a warning on published units and hygiene on the rest."""
    scope = ValidationScope(organisation_units=frozenset({"Ou1aaaaaaaa"}))
    report = build_code_validation(
        [],
        [
            _collection(
                "organisationUnits",
                MetadataItemIn(uid="Ou1aaaaaaaa", name="Published"),
                MetadataItemIn(uid="Ou2aaaaaaaa", name="Outside"),
            )
        ],
        _CONFIG,
        scope=scope,
    )
    by_uid = {finding.uid: finding for finding in report.findings}
    assert (by_uid["Ou1aaaaaaaa"].severity, by_uid["Ou1aaaaaaaa"].scope) == ("warning", "selection")
    assert (by_uid["Ou2aaaaaaaa"].severity, by_uid["Ou2aaaaaaaa"].scope) == ("info", "instance")


def test_a_template_hostile_name_on_a_never_emitted_collection_is_info() -> None:
    """A visualization never reaches an IG page, so its hostile name is hygiene even with a rich scope."""
    scope = ValidationScope(data_sets=frozenset({"Ds1aaaaaaaa"}))
    report = build_code_validation(
        [],
        [
            _collection(
                "visualizations",
                MetadataItemIn(uid="Vi1aaaaaaaa", name="Cases < 5", code="VIS1"),
            ),
            _collection(
                "dataSets",
                MetadataItemIn(uid="Ds1aaaaaaaa", name="Mortality < 5 years", code="DS1"),
            ),
        ],
        _CONFIG,
        scope=scope,
    )
    by_uid = {finding.uid: finding for finding in report.findings}
    assert (by_uid["Vi1aaaaaaaa"].severity, by_uid["Vi1aaaaaaaa"].scope) == ("info", "instance")
    assert (by_uid["Ds1aaaaaaaa"].severity, by_uid["Ds1aaaaaaaa"].scope) == ("warning", "selection")


def test_option_findings_inherit_their_option_sets_scope() -> None:
    """An option of an unselected set is instance hygiene whatever mode the run is in."""
    selected = OptionSetIn(
        uid="Os1aaaaaaaa", name="Selected", options=[OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Bad")]
    )
    unselected = OptionSetIn(
        uid="Os2aaaaaaaa", name="Unselected", options=[OptionIn(uid="Op2aaaaaaaa", code=" F ", name="Bad")]
    )
    scope = ValidationScope(option_sets=frozenset({"Os1aaaaaaaa"}))
    report = build_code_validation([selected, unselected], [], _CODE_MODE, scope=scope)
    by_uid = {finding.uid: finding for finding in report.findings}
    assert (by_uid["Op1aaaaaaaa"].severity, by_uid["Op1aaaaaaaa"].scope) == ("warning", "selection")
    assert (by_uid["Op2aaaaaaaa"].severity, by_uid["Op2aaaaaaaa"].scope) == ("info", "instance")


def test_attribute_findings_stay_instance_scoped() -> None:
    """An attribute applies per-object across every emitted type, so its finding keeps instance scope."""
    report = build_code_validation(
        [],
        [_collection("attributes", MetadataItemIn(uid="At1aaaaaaaa", name="Uncoded"))],
        _CONFIG,
        scope=ValidationScope(),
    )
    assert [(finding.severity, finding.scope) for finding in report.findings] == [("info", "instance")]


def test_usable_code_stem_takes_the_fhir_id_bar_not_the_code_bar() -> None:
    """A spaced code is a valid R4 code but no artifact stem; the stem bar is the R4 id datatype."""
    assert usable_code_stem("ANC-01")
    assert usable_code_stem("birth.type")
    assert not usable_code_stem("TWO WORDS")
    assert not usable_code_stem(_ABORTING_CODE)
    assert not usable_code_stem(None)
    assert not usable_code_stem("")
    assert not usable_code_stem("x" * 65)


def test_code_coverage_counts_usable_codes_per_in_scope_surface() -> None:
    """Coverage counts in-scope objects alone, per surface, and rolls the fraction up."""
    scope = ValidationScope(
        data_sets=frozenset({"Ds1aaaaaaaa", "Ds2aaaaaaaa"}),
        option_sets=frozenset({"Os1aaaaaaaa"}),
    )
    report = build_code_validation(
        [],
        [
            _collection(
                "dataSets",
                MetadataItemIn(uid="Ds1aaaaaaaa", name="Coded", code="DS1"),
                MetadataItemIn(uid="Ds2aaaaaaaa", name="Spaced", code="DS 2"),
                MetadataItemIn(uid="Ds3aaaaaaaa", name="Outside", code="DS3"),
            ),
            _collection("optionSets", MetadataItemIn(uid="Os1aaaaaaaa", name="Uncoded")),
            _collection("dashboards", MetadataItemIn(uid="Db1aaaaaaaa", name="Never", code="DB1")),
        ],
        _CONFIG,
        scope=scope,
    )
    assert report.code_coverage is not None
    by_surface = {surface.surface: surface for surface in report.code_coverage.surfaces}
    assert set(by_surface) == {"dataSets", "optionSets"}
    assert (by_surface["dataSets"].usable_count, by_surface["dataSets"].object_count) == (1, 2)
    assert (by_surface["optionSets"].usable_count, by_surface["optionSets"].object_count) == (0, 1)
    assert report.code_coverage.usable_count == 1
    assert report.code_coverage.object_count == 3
    assert report.code_coverage.line == "1/3"


def test_code_coverage_is_absent_without_a_resolved_scope() -> None:
    """The scope-less unit path computes no coverage, so a renderer can tell the two reports apart."""
    report = build_code_validation([], [_collection("dataSets", MetadataItemIn(uid="Ds1aaaaaaaa"))], _CONFIG)
    assert report.code_coverage is None


def test_the_markdown_report_carries_scope_and_coverage() -> None:
    """The scope column and the selection summary lines land in the rendered Markdown."""
    scope = ValidationScope(data_elements=frozenset({"De1aaaaaaaa"}))
    report = build_code_validation(
        [],
        [
            _collection(
                "dataElements",
                MetadataItemIn(uid="De1aaaaaaaa", name="Selected", code=" X "),
                MetadataItemIn(uid="De2aaaaaaaa", name="Unselected", code=" Y "),
            )
        ],
        _CONFIG,
        scope=scope,
    )
    markdown = render_validation_markdown(report, "probe", _GENERATED_AT)
    assert "| Severity | Scope | Category | Object | Code | Detail |" in markdown
    assert "| warning | selection | invalid-code |" in markdown
    assert "| info | instance | invalid-code |" in markdown
    assert "selection findings: 0 errors, 1 warnings, 0 infos" in markdown
    assert "code coverage (selection): 0/1" in markdown


def test_the_markdown_summary_omits_the_selection_lines_without_a_scope() -> None:
    """A scope-less report renders no selection split and no coverage line."""
    report = build_code_validation([], [], _CONFIG)
    markdown = render_validation_markdown(report, "probe", _GENERATED_AT)
    assert "selection findings" not in markdown
    assert "code coverage" not in markdown


def test_the_csv_and_pdf_carry_the_scope() -> None:
    """Both machine and print renderings carry the scope of every finding."""
    scope = ValidationScope()
    report = build_code_validation(
        [],
        [_collection("dataElements", MetadataItemIn(uid="De1aaaaaaaa", name="Unselected", code=" X "))],
        _CONFIG,
        scope=scope,
    )
    csv_text = render_validation_csv(report)
    assert "info,instance,invalid-code" in csv_text
    assert render_validation_pdf(report, "probe", _GENERATED_AT).startswith(b"%PDF")


def _mock_scope_endpoints(
    data_sets: list[dict[str, object]] | None = None,
    programs: list[dict[str, object]] | None = None,
    option_sets: list[dict[str, object]] | None = None,
    categories: list[dict[str, object]] | None = None,
    organisation_units: list[dict[str, object]] | None = None,
) -> dict[str, respx.Route]:
    """Mock the five id-only endpoints scope resolution reads, returning each route for inspection."""
    payloads: dict[str, list[dict[str, object]]] = {
        "dataSets": data_sets or [],
        "programs": programs or [],
        "optionSets": option_sets or [],
        "categories": categories or [],
        "organisationUnits": organisation_units or [],
    }
    return {
        resource: respx.get(f"{_HOST}/api/{resource}").mock(return_value=httpx.Response(200, json={resource: items}))
        for resource, items in payloads.items()
    }


@respx.mock
async def test_scope_resolution_mirrors_the_generate_selection(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
) -> None:
    """Selected containers pull their data elements in, the data elements pull their option sets in."""
    mock_system_info("v42")
    _mock_scope_endpoints(
        data_sets=[
            {
                "id": "Ds1aaaaaaaa",
                "dataSetElements": [{"dataElement": {"id": "De1aaaaaaaa", "optionSet": {"id": "OsXaaaaaaaa"}}}],
            }
        ],
        programs=[
            {
                "id": "Pr1aaaaaaaa",
                "programType": "WITHOUT_REGISTRATION",
                "programStages": [
                    {
                        "id": "Ps1aaaaaaaa",
                        "programStageDataElements": [
                            {"dataElement": {"id": "De2aaaaaaaa", "optionSet": {"id": "OsWaaaaaaaa"}}}
                        ],
                    }
                ],
            },
            {
                "id": "Pr2aaaaaaaa",
                "programType": "WITH_REGISTRATION",
                "programStages": [
                    {
                        "id": "Ps2aaaaaaaa",
                        "programStageDataElements": [
                            {"dataElement": {"id": "De3aaaaaaaa", "optionSet": {"id": "OsZaaaaaaaa"}}}
                        ],
                    },
                    {"id": "Ps3aaaaaaaa", "programStageDataElements": []},
                ],
                "programTrackedEntityAttributes": [
                    {"trackedEntityAttribute": {"id": "Tea1aaaaaaa", "optionSet": {"id": "OsVaaaaaaaa"}}}
                ],
            },
        ],
        option_sets=[
            {"id": "OsXaaaaaaaa"},
            {"id": "OsYaaaaaaaa"},
            {"id": "OsZaaaaaaaa"},
            {"id": "OsWaaaaaaaa"},
            {"id": "OsVaaaaaaaa"},
            {"id": "OsUaaaaaaaa"},
        ],
        categories=[{"id": "Ca1aaaaaaaa"}],
        organisation_units=[{"id": "Ou1aaaaaaaa"}],
    )
    config = GenerateConfig.model_validate(
        {"data_sets": {"include_ids": ["Ds1aaaaaaaa"]}, "option_sets": {"include_ids": ["OsYaaaaaaaa"]}}
    )

    async with open_client(resolve_profile("probe")) as client:
        scope = await service.resolve_validation_scope(client, config)

    assert scope.data_sets == frozenset({"Ds1aaaaaaaa"})
    assert scope.programs == frozenset({"Pr1aaaaaaaa", "Pr2aaaaaaaa"})
    # Only a tracker stage emits its own Questionnaire; the event program's stage is not a surface.
    assert scope.program_stages == frozenset({"Ps2aaaaaaaa", "Ps3aaaaaaaa"})
    # A tracked entity attribute is a question but not a data element, so it joins the option-set
    # closure without joining the surface `dataElements` answers for.
    assert scope.data_elements == frozenset({"De1aaaaaaaa", "De2aaaaaaaa", "De3aaaaaaaa"})
    # Configured set plus the closure the selected forms bind - the registration form's attribute
    # binding included; the unbound, unconfigured set stays out.
    assert scope.option_sets == frozenset({"OsYaaaaaaaa", "OsXaaaaaaaa", "OsWaaaaaaaa", "OsZaaaaaaaa", "OsVaaaaaaaa"})
    assert scope.categories == frozenset({"Ca1aaaaaaaa"})
    assert scope.organisation_units == frozenset({"Ou1aaaaaaaa"})


@respx.mock
async def test_the_default_category_leaves_the_scope_unless_asked_back(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
) -> None:
    """Validate must not grade an artifact the guide will not publish - and the asks that publish it win."""
    mock_system_info("v42")
    routes = _mock_scope_endpoints(
        categories=[{"id": "GLevLNI9wkl", "name": "default"}, {"id": "Ca1aaaaaaaa", "name": "Sex"}]
    )

    async with open_client(resolve_profile("probe")) as client:
        skipped = await service.resolve_validation_scope(client, GenerateConfig())
        opted_in = await service.resolve_validation_scope(
            client, GenerateConfig.model_validate({"categories": {"include_default": True}})
        )
        named = await service.resolve_validation_scope(
            client, GenerateConfig.model_validate({"categories": {"include_ids": ["GLevLNI9wkl"]}})
        )

    assert skipped.categories == frozenset({"Ca1aaaaaaaa"})
    assert opted_in.categories == frozenset({"GLevLNI9wkl", "Ca1aaaaaaaa"})
    # The narrowed fetch filters server-side (the mock answers everything regardless), so the
    # named default stays in scope and the request itself states the include_ids filter.
    assert "GLevLNI9wkl" in named.categories
    request_url = str(routes["categories"].calls.last.request.url)
    assert "GLevLNI9wkl" in request_url


def test_code_coverage_counts_follow_the_categories_scope() -> None:
    """A default category out of scope leaves the categories coverage denominator with the others."""
    scope = ValidationScope(categories=frozenset({"Ca1aaaaaaaa"}))
    report = build_code_validation(
        [],
        [
            _collection(
                "categories",
                MetadataItemIn(uid="Ca1aaaaaaaa", name="Sex", code="SEX"),
                MetadataItemIn(uid="GLevLNI9wkl", name="default"),
            )
        ],
        _CONFIG,
        scope=scope,
    )
    assert report.code_coverage is not None
    by_surface = {surface.surface: surface for surface in report.code_coverage.surfaces}
    assert (by_surface["categories"].usable_count, by_surface["categories"].object_count) == (1, 1)


@respx.mock
async def test_scope_resolution_applies_the_shared_organisation_unit_filters(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
) -> None:
    """The org-unit read goes through the same selection filters the registry walk applies."""
    mock_system_info("v42")
    routes = _mock_scope_endpoints(organisation_units=[{"id": "Ou1aaaaaaaa"}, {"id": "Ou2aaaaaaaa"}])
    config = GenerateConfig.model_validate({"organisation_units": {"root": "/Ou0aaaaaaaa", "max_level": 2}})

    async with open_client(resolve_profile("probe")) as client:
        scope = await service.resolve_validation_scope(client, config)

    assert scope.organisation_units == frozenset({"Ou1aaaaaaaa", "Ou2aaaaaaaa"})
    request_url = str(routes["organisationUnits"].calls.last.request.url)
    assert "path%3Alike%3A%2FOu0aaaaaaaa" in request_url or "path:like:/Ou0aaaaaaaa" in request_url
    assert "level%3Ale%3A2" in request_url or "level:le:2" in request_url


@respx.mock
async def test_a_program_named_under_the_wrong_table_contributes_nothing(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
) -> None:
    """A tracker program listed under event_programs is generate's refusal, not a scope surface."""
    mock_system_info("v42")
    _mock_scope_endpoints(
        programs=[
            {"id": "Pr1aaaaaaaa", "programType": "WITH_REGISTRATION", "programStages": [{"id": "Ps1aaaaaaaa"}]},
            {"id": "Pr2aaaaaaaa", "programType": "WITHOUT_REGISTRATION", "programStages": []},
        ]
    )
    config = GenerateConfig.model_validate(
        {"event_programs": {"include_ids": ["Pr1aaaaaaaa"]}, "tracker_programs": {"include_ids": ["Pr2aaaaaaaa"]}}
    )

    async with open_client(resolve_profile("probe")) as client:
        scope = await service.resolve_validation_scope(client, config)

    assert scope.programs == frozenset()
    assert scope.program_stages == frozenset()


async def _scaffold_project(directory: Path) -> None:
    """Scaffold a minimal project so the parity test can run generate against it."""
    await service.init_project(
        directory,
        InitOptions(
            ig_id="dhis2.fhir.scope",
            canonical="http://example.org/fhir",
            name="Dhis2FhirScope",
            title="Scope IG",
            publisher="Scope Org",
        ),
    )


@respx.mock
async def test_validate_error_and_the_generate_gate_refuse_the_same_object(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Parity: the one validate error on an in-scope '<' code is exactly the object generate refuses."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    hostile: dict[str, object] = {
        "id": "Os1aaaaaaaa",
        "name": "Bednet distribution",
        "code": _ABORTING_CODE,
        "options": [],
    }
    _mock_scope_endpoints(option_sets=[hostile])
    respx.get(f"{_HOST}/api/attributes").mock(return_value=httpx.Response(200, json={"attributes": []}))
    respx.get(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(200, json={"optionSets": [hostile]}),
    )

    report = await service.validate_codes(resolve_profile("probe"), GenerateConfig())
    errors = [finding for finding in report.findings if finding.severity == "error"]
    assert [(finding.resource_type, finding.uid, finding.scope) for finding in errors] == [
        ("optionSets", "Os1aaaaaaaa", "selection")
    ]

    with pytest.raises(service.BuildAbortingCodeError) as raised:
        await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))
    assert "Os1aaaaaaaa" in str(raised.value)
    assert _ABORTING_CODE in str(raised.value)


@respx.mock
async def test_an_out_of_scope_aborting_code_passes_validate_and_generate_alike(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Parity in the other direction: an unselected '<' code neither errors validate nor refuses generate."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(
        f'{config_path.read_text(encoding="utf-8")}\n[generate.option_sets]\ninclude_ids = ["Os2aaaaaaaa"]\n',
        encoding="utf-8",
    )
    hostile: dict[str, object] = {
        "id": "Os1aaaaaaaa",
        "name": "Bednet distribution",
        "code": _ABORTING_CODE,
        "options": [],
    }
    clean: dict[str, object] = {"id": "Os2aaaaaaaa", "name": "Birth type", "code": "BIRTH_TYPE", "options": []}
    _mock_scope_endpoints(option_sets=[hostile, clean])
    respx.get(f"{_HOST}/api/attributes").mock(return_value=httpx.Response(200, json={"attributes": []}))
    respx.get(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(200, json={"optionSets": [hostile, clean]}),
    )

    project = load_project(tmp_path)
    report = await service.validate_codes(resolve_profile("probe"), project.config.generate)
    assert report.error_count == 0
    hostile_finding = next(finding for finding in report.findings if finding.uid == "Os1aaaaaaaa")
    assert (hostile_finding.severity, hostile_finding.scope) == ("info", "instance")

    generated = await service.generate_option_sets(resolve_profile("probe"), project)
    assert generated.option_set_count == 1
