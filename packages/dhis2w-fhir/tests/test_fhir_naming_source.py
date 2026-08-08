"""Tests for the identity-stem threading on the W-2 surfaces: org units, questionnaires, examples, pages.

The id mode is pinned by the untouched golden and parity suites - every stem is the DHIS2 id
there, byte for byte. These tests cover the other two sources: `code-or-id` picks the code where
it can serve and falls back with a note (underscore codes like the demo database's `OU_525` are
the expected reality - R4 ids forbid `_`), and `code` refuses the run through `CodeStemError`.
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
from dhis2w_fhir import (
    AttributeCodeIndex,
    CodeStemError,
    ExampleAnswerIn,
    ExampleResponseIn,
    GenerateConfig,
    InitOptions,
    NamingSource,
    OrganisationUnitIn,
    PagesIn,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
    StemResolution,
    build_example_artifacts,
    build_example_documents,
    build_organisation_unit_instances,
    build_page_artifacts,
    build_questionnaire_artifacts,
    build_questionnaire_documents,
    load_project,
    option_set_identities,
    organisation_unit_stem_subjects,
    plan_organisation_unit_stems,
    plan_questionnaire_stems,
    service,
)
from dhis2w_fhir.resources.questionnaires.schemas import ProgramContextIn

_CANONICAL = "http://example.org/fhir"
_HOST = "https://dhis2.example"

#: The demo database's real data-set code shape: the underscore R4 ids forbid.
_UNDERSCORE_CODE = "DS_359711"


def _config(source: NamingSource) -> GenerateConfig:
    """A generate config under one naming source, everything else at its default."""
    return GenerateConfig.model_validate({"naming": {"source": source}})


def _organisation_units() -> list[OrganisationUnitIn]:
    """A three-unit hierarchy: a coded root, an underscore-coded district, an uncoded chiefdom."""
    return [
        OrganisationUnitIn(uid="ImspTQPwCqd", name="Sierra Leone", code="SL", level=1, path="/ImspTQPwCqd"),
        OrganisationUnitIn(
            uid="O6uvpzGd5pu",
            name="Bo",
            code="OU_525",
            level=2,
            path="/ImspTQPwCqd/O6uvpzGd5pu",
            parent_uid="ImspTQPwCqd",
        ),
        OrganisationUnitIn(
            uid="YuQRtpLP10I",
            name="Badjia",
            level=3,
            path="/ImspTQPwCqd/O6uvpzGd5pu/YuQRtpLP10I",
            parent_uid="O6uvpzGd5pu",
        ),
    ]


def _registry_documents(source: NamingSource) -> tuple[dict[str, Any], list[str]]:
    """Build the registry under one source: the parsed documents keyed by file stem, plus the notes."""
    build = build_organisation_unit_instances(
        _organisation_units(), _config(source), _CANONICAL, attribute_codes=AttributeCodeIndex()
    )
    documents = {
        artifact.relative_path.removeprefix("registry/").removesuffix(".json"): json.loads(artifact.content)
        for artifact in build.artifacts
    }
    return documents, build.notes


def test_code_or_id_names_org_unit_files_ids_and_references_by_the_code_stem() -> None:
    """A usable code becomes the file name, both resource ids, and every reference targeting the unit."""
    documents, _ = _registry_documents("code-or-id")

    assert "Organization-SL" in documents
    assert "Location-SL" in documents
    assert documents["Organization-SL"]["id"] == "SL"
    assert documents["Location-SL"]["id"] == "SL"
    assert documents["Location-SL"]["managingOrganization"]["reference"] == "Organization/SL"
    # The identifier slices keep the DHIS2 id and code as the data they are.
    assert documents["Organization-SL"]["identifier"][0]["value"] == "ImspTQPwCqd"
    assert documents["Organization-SL"]["identifier"][1]["value"] == "SL"


def test_an_underscore_code_falls_back_to_the_id_with_the_aggregate_note() -> None:
    """The owner's real data: `OU_525` carries an underscore, which an R4 id forbids, so the id serves.

    The child of the fallen-back unit still resolves its `partOf` through the same resolution,
    so the hierarchy references the file that really exists.
    """
    documents, notes = _registry_documents("code-or-id")

    assert "Organization-O6uvpzGd5pu" in documents
    assert "Organization-OU_525" not in documents
    assert documents["Organization-O6uvpzGd5pu"]["partOf"]["reference"] == "Organization/SL"
    assert documents["Location-YuQRtpLP10I"]["partOf"]["reference"] == "Location/O6uvpzGd5pu"
    fallback_notes = [note for note in notes if "unusable as identity stems; fell back to the id" in note]
    assert len(fallback_notes) == 1
    assert "2 organisation unit codes" in fallback_notes[0]
    assert "Bo (O6uvpzGd5pu)" in fallback_notes[0]
    assert "Badjia (YuQRtpLP10I)" in fallback_notes[0]


def test_id_mode_resolves_every_org_unit_stem_to_the_id_without_notes() -> None:
    """Under the default source the stems are the DHIS2 ids and resolution stays silent."""
    resolution = plan_organisation_unit_stems(organisation_unit_stem_subjects(_organisation_units()), "id")

    assert resolution.stems == {
        "ImspTQPwCqd": "ImspTQPwCqd",
        "O6uvpzGd5pu": "O6uvpzGd5pu",
        "YuQRtpLP10I": "YuQRtpLP10I",
    }
    assert resolution.notes == []


def test_a_code_shared_by_two_units_falls_back_on_both() -> None:
    """A colliding code would merge two files into one, so both subjects keep their ids."""
    units = [
        OrganisationUnitIn(uid="AaaaaaaaaaA", name="One", code="DUP", level=1, path="/AaaaaaaaaaA"),
        OrganisationUnitIn(uid="BbbbbbbbbbB", name="Two", code="DUP", level=1, path="/BbbbbbbbbbB"),
    ]
    resolution = plan_organisation_unit_stems(organisation_unit_stem_subjects(units), "code-or-id")

    assert resolution.stems == {"AaaaaaaaaaA": "AaaaaaaaaaA", "BbbbbbbbbbB": "BbbbbbbbbbB"}
    assert len(resolution.notes) == 1


def test_code_mode_refuses_the_org_unit_surface_by_name() -> None:
    """`source = "code"` raises before anything is built, naming the surface and the offenders."""
    with pytest.raises(CodeStemError, match="organisation unit") as caught:
        build_organisation_unit_instances(
            _organisation_units(), _config("code"), _CANONICAL, attribute_codes=AttributeCodeIndex()
        )
    assert "OU_525" in str(caught.value)


def _questionnaire_sources() -> list[QuestionnaireSourceIn]:
    """Three forms: an underscore-coded data set, a coded event program, and a coded tracker stage."""
    return [
        QuestionnaireSourceIn(uid="BfMAe6Itzgt", name="Child Health", code=_UNDERSCORE_CODE, kind="aggregate"),
        QuestionnaireSourceIn(uid="VBqh0ynB2wv", name="Malaria case registration", code="EVT-CR", kind="event"),
        QuestionnaireSourceIn(
            uid="A03MvHHogjR",
            name="Birth",
            code="STG-BIRTH",
            kind="tracker-event",
            program=ProgramContextIn(uid="IpHINAT79UW", name="Child Programme", code="CHILD"),
        ),
    ]


def _built_fsh(source: NamingSource) -> dict[str, str]:
    """Build the questionnaire FSH under one source, keyed by relative path."""
    config = _config(source)
    build = build_questionnaire_artifacts(
        _questionnaire_sources(),
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )
    return {artifact.relative_path: artifact.content for artifact in build.artifacts}


def test_code_or_id_threads_the_questionnaire_stem_through_file_id_url_and_name() -> None:
    """One resolved stem names the file, the instance, the `id`, the canonical URL, and the FSH name."""
    files = _built_fsh("code-or-id")

    content = files["event-programs/EVT-CR.fsh"]
    assert "Instance: Questionnaire-EVT-CR\n" in content
    assert '* id = "EVT-CR"\n' in content
    assert f'* url = "{_CANONICAL}/Questionnaire/EVT-CR"\n' in content
    # The FSH-name segment pascal-collapses the code stem: hyphens cannot ride in a name.
    assert '* name = "D2PR_EVTCR"\n' in content
    # The identifier slice still carries the DHIS2 id as data.
    assert '* identifier[=].value = "VBqh0ynB2wv"\n' in content


def test_the_underscore_coded_data_set_falls_back_and_the_build_says_so() -> None:
    """`DS_359711` cannot serve as a stem, so the data set keeps its id and the note names it."""
    config = _config("code-or-id")
    build = build_questionnaire_artifacts(
        _questionnaire_sources(),
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )
    paths = [artifact.relative_path for artifact in build.artifacts]

    assert "data-sets/BfMAe6Itzgt.fsh" in paths
    fallback_notes = [note for note in build.notes if "unusable as identity stems; fell back to the id" in note]
    assert len(fallback_notes) == 1
    assert "1 questionnaire target codes" in fallback_notes[0]
    assert "Child Health (BfMAe6Itzgt)" in fallback_notes[0]


def test_a_tracker_stage_files_under_its_program_stem() -> None:
    """The stage's file nests under the program's stem, both resolved by the same plan."""
    files = _built_fsh("code-or-id")

    assert "tracker-programs/CHILD/STG-BIRTH.fsh" in files


def test_code_mode_refuses_the_questionnaire_surface_by_name() -> None:
    """`source = "code"` raises `CodeStemError` naming the questionnaire surface and the offender."""
    config = _config("code")
    with pytest.raises(CodeStemError, match="questionnaire target") as caught:
        build_questionnaire_artifacts(
            _questionnaire_sources(),
            config,
            _CANONICAL,
            ig_status="draft",
            option_set_plan=option_set_identities([], config),
            attribute_codes=AttributeCodeIndex(),
        )
    assert _UNDERSCORE_CODE in str(caught.value)


def test_the_fsh_and_json_questionnaire_paths_agree_on_every_identity_under_code_or_id() -> None:
    """Both emitters resolve stems through the same plan, so id, url, name, and file stem line up."""
    config = _config("code-or-id")
    sources = _questionnaire_sources()
    plan = plan_questionnaire_stems(sources, config.naming.source)
    fsh = build_questionnaire_artifacts(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )
    documents = build_questionnaire_documents(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )

    by_id = {str(questionnaire.id): questionnaire for questionnaire in documents.questionnaires}
    questionnaire_files = {
        artifact.fsh_name: artifact for artifact in fsh.artifacts if artifact.fsh_name.startswith("Questionnaire-")
    }
    assert len(by_id) == len(sources)
    for source in sources:
        stem = plan.targets.stem_for(source.uid)
        document = by_id[stem]
        artifact = questionnaire_files[f"Questionnaire-{stem}"]
        assert artifact.relative_path.endswith(f"/{stem}.fsh")
        assert f'* id = "{stem}"\n' in artifact.content
        assert f'* url = "{document.url}"\n' in artifact.content
        assert f'* name = "{document.name}"\n' in artifact.content


def test_the_parity_fixtures_agree_across_both_paths_under_code_or_id() -> None:
    """The committed parity projections rebuilt under code-or-id: both emitters name every identity alike.

    The SUSHI goldens themselves are id-mode output, so this run compares the two builders to
    each other over the same real fixtures - the demo data sets carry underscore codes
    (`DS_359711`) and every program carries none, so this selection resolves entirely to id
    fall-backs, with the aggregate note raised once by each path.
    """
    fixtures = Path(__file__).parent / "data" / "questionnaire-sources"
    sources = [
        QuestionnaireSourceIn.model_validate(entry)
        for entry in json.loads((fixtures / "sources.json").read_text(encoding="utf-8"))
    ]
    config = _config("code-or-id")
    plan = plan_questionnaire_stems(sources, config.naming.source)
    fsh = build_questionnaire_artifacts(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )
    documents = build_questionnaire_documents(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )

    by_id = {str(questionnaire.id): questionnaire for questionnaire in documents.questionnaires}
    questionnaire_files = {
        artifact.fsh_name: artifact for artifact in fsh.artifacts if artifact.fsh_name.startswith("Questionnaire-")
    }
    for source in sources:
        stem = plan.targets.stem_for(source.uid)
        assert stem == source.uid
        artifact = questionnaire_files[f"Questionnaire-{stem}"]
        assert f'* id = "{stem}"\n' in artifact.content
        assert f'* url = "{by_id[stem].url}"\n' in artifact.content
        assert f'* name = "{by_id[stem].name}"\n' in artifact.content
    # The FSH build reports both of its surfaces - the form targets and the tracker programs the
    # stage files nest under - while the document build uses (and reports) the targets alone.
    fsh_fallbacks = [note for note in fsh.notes if "unusable as identity stems; fell back to the id" in note]
    document_fallbacks = [note for note in documents.notes if "unusable as identity stems" in note]
    assert [note for note in fsh_fallbacks if "questionnaire target" in note] == document_fallbacks
    assert len([note for note in fsh_fallbacks if "tracker program" in note]) == 1


_EXAMPLE_TARGET = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt",
    name="Child Health",
    code="DSCH",
    kind="aggregate",
    flat_items=[QuestionnaireItemIn(uid="De1aaaaaaaa", name="Referred to", value_type="ORGANISATION_UNIT")],
)

_EXAMPLE_RESPONSE = ExampleResponseIn(
    instance_id="BfMAe6Itzgt-202401-ImspTQPwCqd",
    target_uid="BfMAe6Itzgt",
    kind="aggregate",
    organisation_unit_uid="ImspTQPwCqd",
    status_code="completed",
    answers=[ExampleAnswerIn(data_element_uid="De1aaaaaaaa", value="O6uvpzGd5pu")],
)

_EXAMPLE_ORGANISATION_UNIT_STEMS = StemResolution(stems={"ImspTQPwCqd": "SL", "O6uvpzGd5pu": "BO"})


def test_example_files_and_references_follow_the_stems_while_instance_ids_stay_data() -> None:
    """The file and the questionnaire canonical follow the target stem, Location refs follow the registry,
    and the instance id keeps the DHIS2 data identifiers it embeds."""
    config = _config("code-or-id")
    build = build_example_artifacts(
        [_EXAMPLE_TARGET],
        [_EXAMPLE_RESPONSE],
        [],
        config,
        _CANONICAL,
        option_set_plan=option_set_identities([], config),
        published_organisation_unit_uids=frozenset({"ImspTQPwCqd", "O6uvpzGd5pu"}),
        organisation_unit_stems=_EXAMPLE_ORGANISATION_UNIT_STEMS,
    )

    assert [artifact.relative_path for artifact in build.artifacts] == ["examples/DSCH-1.fsh"]
    content = build.artifacts[0].content
    assert "Instance: QuestionnaireResponse-BfMAe6Itzgt-202401-ImspTQPwCqd\n" in content
    assert f'* questionnaire = "{_CANONICAL}/Questionnaire/DSCH"\n' in content
    assert "* subject = Reference(Location/SL)\n" in content
    assert "Reference(Location/BO)" in content


def test_example_documents_follow_the_same_stems_as_the_fsh_path() -> None:
    """The served response references the stem-named Questionnaire and Locations, id staying the data id."""
    config = _config("code-or-id")
    build = build_example_documents(
        [_EXAMPLE_TARGET],
        [_EXAMPLE_RESPONSE],
        [],
        config,
        _CANONICAL,
        option_set_plan=option_set_identities([], config),
        published_organisation_unit_uids=frozenset({"ImspTQPwCqd", "O6uvpzGd5pu"}),
        organisation_unit_stems=_EXAMPLE_ORGANISATION_UNIT_STEMS,
    )

    (response,) = build.responses
    assert response.id == "BfMAe6Itzgt-202401-ImspTQPwCqd"
    assert response.questionnaire == f"{_CANONICAL}/Questionnaire/DSCH"
    assert response.subject is not None
    assert response.subject.reference == "Location/SL"
    document = json.loads(response.model_dump_json(exclude_none=True, by_alias=True))
    assert '"Location/BO"' in json.dumps(document)


def test_pages_links_and_intro_file_names_follow_the_stems() -> None:
    """The forms catalog, the questionnaire intros, and the organization intros all name the stems."""
    units = [
        OrganisationUnitIn(
            uid="ImspTQPwCqd", name="Sierra Leone", code="SL", description="The root.", level=1, path="/ImspTQPwCqd"
        ),
    ]
    pages = PagesIn(forms=[_EXAMPLE_TARGET], organisation_units=units)
    build = build_page_artifacts(pages, _config("code-or-id"), _CANONICAL)
    paths = [artifact.relative_path for artifact in build.artifacts]
    forms_page = next(artifact for artifact in build.artifacts if artifact.relative_path.endswith("forms.md"))

    assert "pagecontent/Questionnaire-DSCH-intro.md" in paths
    assert "pagecontent/Organization-SL-intro.md" in paths
    assert "(Questionnaire-DSCH.html)" in forms_page.content
    # The catalog still shows the DHIS2 id as data.
    assert "BfMAe6Itzgt" in forms_page.content


_ORGANISATION_UNITS_PAYLOAD = {
    "organisationUnits": [
        {"id": "ImspTQPwCqd", "name": "Sierra Leone", "code": "SL", "level": 1, "path": "/ImspTQPwCqd"},
        {
            "id": "O6uvpzGd5pu",
            "name": "Bo",
            "code": "OU_525",
            "level": 2,
            "path": "/ImspTQPwCqd/O6uvpzGd5pu",
            "parent": {"id": "ImspTQPwCqd"},
        },
    ]
}

_DATA_SETS_PAYLOAD = {
    "dataSets": [
        {
            "id": "BfMAe6Itzgt",
            "name": "Child Health",
            "code": _UNDERSCORE_CODE,
            "dataSetElements": [
                {
                    "dataElement": {
                        "id": "De1aaaaaaaa",
                        "name": "BCG doses given",
                        "valueType": "INTEGER",
                        "categoryCombo": {"id": "bjDvmb4bfuf", "name": "default", "isDefault": True},
                    }
                }
            ],
        }
    ]
}

_PROGRAMS_PAYLOAD = {
    "programs": [
        {
            "id": "VBqh0ynB2wv",
            "name": "Malaria case registration",
            "code": "EVT-CR",
            "programType": "WITHOUT_REGISTRATION",
            "programStages": [
                {
                    "id": "pTo4uMt3xur",
                    "programStageSections": [],
                    "programStageDataElements": [
                        {
                            "compulsory": True,
                            "dataElement": {"id": "qrur9Dvnyt5", "name": "Age in years", "valueType": "INTEGER"},
                        }
                    ],
                }
            ],
        }
    ]
}


async def _scaffold_project(directory: Path, source: NamingSource) -> None:
    """Scaffold a project and pin its `[generate.naming] source`."""
    options = InitOptions(
        ig_id="dhis2.fhir.naming",
        canonical=_CANONICAL,
        name="Dhis2FhirNaming",
        title="Naming IG",
        publisher="Naming Org",
    )
    await service.init_project(directory, options)
    config_path = directory / "fhir.toml"
    body = config_path.read_text(encoding="utf-8")
    config_path.write_text(f'{body}\n[generate.naming]\nsource = "{source}"\n', encoding="utf-8")


def _mock_instance(mock_system_info: Callable[..., None], mock_attributes: Callable[..., None]) -> None:
    """Mock every endpoint a generate run over the coded fixture instance reads."""
    mock_system_info("v42")
    mock_attributes()
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json={"optionSets": []}))
    respx.get(f"{_HOST}/api/categories").mock(return_value=httpx.Response(200, json={"categories": []}))
    respx.get(f"{_HOST}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/programs").mock(return_value=httpx.Response(200, json=_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ORGANISATION_UNITS_PAYLOAD))


@respx.mock
async def test_the_generate_report_carries_the_code_or_id_fallback_notes(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A questionnaire run under code-or-id reports every code that could not serve as a stem."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path, "code-or-id")

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    fallback_notes = [note for note in report.notes if "unusable as identity stems; fell back to the id" in note]
    assert len(fallback_notes) == 1
    assert f"Child Health (BfMAe6Itzgt) - code {_UNDERSCORE_CODE!r}" not in fallback_notes[0]
    assert "Child Health (BfMAe6Itzgt)" in fallback_notes[0]
    written = [path for path in report.written_files if path.startswith("data-sets/")]
    assert written == ["data-sets/BfMAe6Itzgt.fsh"]
    event_files = [path for path in report.written_files if path.startswith("event-programs/")]
    assert event_files == ["event-programs/EVT-CR.fsh"]


@respx.mock
async def test_the_org_unit_report_notes_the_underscore_fallback_and_writes_code_stem_files(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The registry names its files by the resolved stems and reports the underscore fall-back."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path, "code-or-id")

    report = await service.generate_organisation_units(resolve_profile("probe"), load_project(tmp_path))

    registry = sorted(path for path in report.written_files if path.startswith("registry/"))
    assert registry == [
        "registry/Location-O6uvpzGd5pu.json",
        "registry/Location-SL.json",
        "registry/Organization-O6uvpzGd5pu.json",
        "registry/Organization-SL.json",
    ]
    fallback_notes = [note for note in report.notes if "unusable as identity stems; fell back to the id" in note]
    assert len(fallback_notes) == 1
    assert "Bo (O6uvpzGd5pu)" in fallback_notes[0]


@respx.mock
async def test_code_mode_refuses_the_run_before_writing_anything(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`source = "code"` raises `CodeStemError` at the plan level, leaving the target directories untouched."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path, "code")

    with pytest.raises(CodeStemError, match="questionnaire target"):
        await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))
    with pytest.raises(CodeStemError, match="organisation unit"):
        await service.generate_organisation_units(resolve_profile("probe"), load_project(tmp_path))

    assert not list((tmp_path / "ig" / "input" / "fsh").glob("data-sets/*"))
    assert not list((tmp_path / "ig" / "input" / "resources").glob("registry/*"))


@respx.mock
async def test_generate_full_under_code_or_id_matches_the_solo_targets(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The plans the full run passes down equal the ones each solo target resolves for itself."""
    _mock_instance(mock_system_info, mock_attributes)
    full_root = tmp_path / "full"
    solo_root = tmp_path / "solo"
    await _scaffold_project(full_root, "code-or-id")
    await _scaffold_project(solo_root, "code-or-id")
    profile = resolve_profile("probe")

    await service.generate_full(profile, load_project(full_root))
    await service.generate_foundation(load_project(solo_root))
    await service.generate_option_sets(profile, load_project(solo_root))
    await service.generate_categories(profile, load_project(solo_root))
    await service.generate_questionnaires(profile, load_project(solo_root))
    await service.generate_examples(profile, load_project(solo_root))
    await service.generate_organisation_units(profile, load_project(solo_root))
    await service.generate_pages(profile, load_project(solo_root))

    assert _tree(full_root) == _tree(solo_root)


def _tree(root: Path) -> dict[str, bytes]:
    """Every generated file under one project root, keyed by its path relative to that root."""
    return {
        str(path.relative_to(root)): path.read_bytes() for path in sorted((root / "ig").rglob("*")) if path.is_file()
    }
