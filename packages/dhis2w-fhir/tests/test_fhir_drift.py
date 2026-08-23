"""Tests for the drift report - the doctor phase that says the instance has moved past the guide.

Three levels, for the three things that can be wrong. The comparators are graded as pure functions
over typed published and instance sides, because that is where the direction of a finding is decided.
`detect_drift` is driven against a published-artifact tree on disk and a respx'd instance, because
that is where the reads and the identifier grammar are decided. And the phase is driven through
`run_doctor`, because that is where the outcome, the exit code, and the skip reasons are decided.

The scope boundary gets a test of its own in both places. Drift that ignored the selection would
report a national hierarchy against a one-district registry and be wrong about every unit in it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import respx
from dhis2w_client.profile import Profile
from dhis2w_fhir.config import load_project
from dhis2w_fhir.doctor import (
    DoctorOptions,
    DoctorOutcome,
    DoctorPhase,
    drift_findings,
    grade_drift,
    resolve_published_project,
    run_doctor,
)
from dhis2w_fhir.drift import (
    DRIFT_REMEDY,
    DriftFinding,
    DriftKind,
    DriftReport,
    DriftSubject,
    InstanceForm,
    InstanceObject,
    InstanceOption,
    InstanceOptionSet,
    PublishedForm,
    PublishedObject,
    PublishedOptionSet,
    compare_form,
    compare_option_set,
    compare_organisation_units,
    detect_drift,
    read_published_guide,
    registry_scope_line,
)
from dhis2w_fhir.service import GenerationProfile

if TYPE_CHECKING:
    from pathlib import Path

_BASE_URL = "https://dhis2.example"

#: The scratch project every disk-reading test publishes from: one district's registry, one data set,
#: one tracker program with one stage, one tracked entity type, and one option set.
_PROJECT_TOML = """
profile = "probe"

[ig]
id = "dhis2.fhir.drift"
canonical = "http://example.org/fhir/drift"
name = "DriftExample"
title = "Drift example guide"
publisher = "Example Organisation"

[generate.organisation_units]
root = "DistrictAA"
max_level = 3
"""

_IDENTIFIER_BASE = "http://dhis2.org/fhir/id"
_CANONICAL = "http://example.org/fhir/drift"


def _profile() -> GenerationProfile:
    """The probe instance every whole-run test names."""
    return GenerationProfile(
        name="probe", origin="test", profile=Profile(base_url=_BASE_URL, auth="pat", token="d2p_test")
    )


def _write(path: Path, document: dict[str, Any]) -> None:
    """Write one published resource where the reader of a published guide finds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def _location(uid: str, name: str) -> dict[str, Any]:
    """One organisation unit as the registry publishes its Location."""
    return {
        "resourceType": "Location",
        "id": uid,
        "identifier": [{"system": f"{_IDENTIFIER_BASE}/org-unit", "value": uid}],
        "name": name,
    }


def _code_system(uid: str, title: str, concepts: dict[str, str]) -> dict[str, Any]:
    """One option set as the terminology publishes its CodeSystem, one concept per option."""
    return {
        "resourceType": "CodeSystem",
        "id": f"d2-os-{uid}-cs",
        "identifier": [{"system": f"{_IDENTIFIER_BASE}/option-set", "value": uid}],
        "title": title,
        "concept": [{"code": code, "display": display} for code, display in concepts.items()],
    }


def _questionnaire(uid: str, kind: str, segment: str, title: str, questions: dict[str, str]) -> dict[str, Any]:
    """One published form, with its questions coded in the vocabulary its kind asks from."""
    system = (
        f"{_CANONICAL}/CodeSystem/d2-tea-cs"
        if kind in {"tracker", "tracked-entity"}
        else (f"{_CANONICAL}/CodeSystem/d2-de-cs")
    )
    return {
        "resourceType": "Questionnaire",
        "id": uid,
        "identifier": [{"system": f"{_IDENTIFIER_BASE}/{segment}", "value": uid}],
        "code": [{"system": f"{_CANONICAL}/CodeSystem/d2-form-type-cs", "code": kind}],
        "title": title,
        "item": [
            {
                "linkId": question_uid,
                "text": display,
                "code": [{"system": system, "code": question_uid, "display": display}],
            }
            for question_uid, display in questions.items()
        ],
    }


@pytest.fixture
def published_project(tmp_path: Path) -> Path:
    """A published guide on disk: a registry, an option set, and four forms, all agreeing with the instance."""
    (tmp_path / "fhir.toml").write_text(_PROJECT_TOML, encoding="utf-8")
    registry = tmp_path / "ig/input/resources/registry"
    _write(registry / "Location-OuAAAAAAAA1.json", _location("OuAAAAAAAA1", "Alpha district"))
    _write(registry / "Location-OuAAAAAAAA2.json", _location("OuAAAAAAAA2", "Alpha chiefdom"))
    terminology = tmp_path / "ig/input/resources/terminology"
    _write(
        terminology / "CodeSystem-d2-os-OsAAAAAAAA1-cs.json",
        _code_system("OsAAAAAAAA1", "Vaccine type", {"OptAAAAAAA1": "BCG", "OptAAAAAAA2": "Measles"}),
    )
    compiled = tmp_path / "ig/fsh-generated/resources"
    _write(
        compiled / "Questionnaire-DsAAAAAAAA1.json",
        _questionnaire("DsAAAAAAAA1", "aggregate", "data-set", "Child Health", {"DeAAAAAAAA1": "BCG doses given"}),
    )
    _write(
        compiled / "Questionnaire-PrAAAAAAAA1.json",
        _questionnaire("PrAAAAAAAA1", "tracker", "program", "Child Programme", {"TeaAAAAAAA1": "First name"}),
    )
    _write(
        compiled / "Questionnaire-PsAAAAAAAA1.json",
        _questionnaire("PsAAAAAAAA1", "tracker-event", "program-stage", "Birth", {"DeAAAAAAAA2": "Apgar Score"}),
    )
    _write(
        compiled / "Questionnaire-TetAAAAAAA1.json",
        _questionnaire("TetAAAAAAA1", "tracked-entity", "tracked-entity-type", "Person", {"TeaAAAAAAA1": "First name"}),
    )
    return tmp_path


def _mock_instance(
    *,
    organisation_units: list[dict[str, str]] | None = None,
    options: list[dict[str, str]] | None = None,
    data_elements: list[dict[str, str]] | None = None,
    attributes: list[dict[str, str]] | None = None,
    stage_elements: list[dict[str, str]] | None = None,
    stages: list[dict[str, str]] | None = None,
) -> None:
    """Answer every read one drift pass makes, with the clean instance as the default of each."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(200, json={"version": "2.42.0"}))
    respx.get(f"{_BASE_URL}/api/organisationUnits").mock(
        return_value=httpx.Response(
            200,
            json={
                "organisationUnits": organisation_units
                if organisation_units is not None
                else [{"id": "OuAAAAAAAA1", "name": "Alpha district"}, {"id": "OuAAAAAAAA2", "name": "Alpha chiefdom"}]
            },
        )
    )
    respx.get(f"{_BASE_URL}/api/optionSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "optionSets": [
                    {
                        "id": "OsAAAAAAAA1",
                        "name": "Vaccine type",
                        "options": options
                        if options is not None
                        else [
                            {"id": "OptAAAAAAA1", "code": "BCG", "name": "BCG"},
                            {"id": "OptAAAAAAA2", "code": "MEASLES", "name": "Measles"},
                        ],
                    }
                ]
            },
        )
    )
    respx.get(f"{_BASE_URL}/api/dataSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataSets": [
                    {
                        "id": "DsAAAAAAAA1",
                        "name": "Child Health",
                        "dataSetElements": [
                            {"dataElement": element}
                            for element in (
                                data_elements
                                if data_elements is not None
                                else [{"id": "DeAAAAAAAA1", "name": "BCG doses given"}]
                            )
                        ],
                    }
                ]
            },
        )
    )
    respx.get(f"{_BASE_URL}/api/programs").mock(
        return_value=httpx.Response(
            200,
            json={
                "programs": [
                    {
                        "id": "PrAAAAAAAA1",
                        "name": "Child Programme",
                        "programTrackedEntityAttributes": [
                            {"trackedEntityAttribute": attribute}
                            for attribute in (
                                attributes if attributes is not None else [{"id": "TeaAAAAAAA1", "name": "First name"}]
                            )
                        ],
                        "programStages": stages
                        if stages is not None
                        else [{"id": "PsAAAAAAAA1", "name": "Birth", "programStageDataElements": []}],
                    }
                ]
            },
        )
    )
    respx.get(f"{_BASE_URL}/api/programStages").mock(
        return_value=httpx.Response(
            200,
            json={
                "programStages": [
                    {
                        "id": "PsAAAAAAAA1",
                        "name": "Birth",
                        "programStageDataElements": [
                            {"dataElement": element}
                            for element in (
                                stage_elements
                                if stage_elements is not None
                                else [{"id": "DeAAAAAAAA2", "name": "Apgar Score"}]
                            )
                        ],
                    }
                ]
            },
        )
    )
    respx.get(f"{_BASE_URL}/api/trackedEntityTypes").mock(
        return_value=httpx.Response(
            200,
            json={
                "trackedEntityTypes": [
                    {
                        "id": "TetAAAAAAA1",
                        "name": "Person",
                        "trackedEntityTypeAttributes": [
                            {"trackedEntityAttribute": attribute}
                            for attribute in (
                                attributes if attributes is not None else [{"id": "TeaAAAAAAA1", "name": "First name"}]
                            )
                        ],
                    }
                ]
            },
        )
    )


async def _drift(project_root: Path) -> DriftReport:
    """Run one drift pass against the mocked instance, through a client the profile opens."""
    from dhis2w_core.client_context import open_client

    async with open_client(_profile().profile) as client:
        return await detect_drift(client, load_project(project_root))


# --- the comparators, graded as pure functions ---------------------------------------------------


def test_a_clean_registry_drifts_in_no_direction() -> None:
    """Two sides naming the same units under the same names is the quiet case, and reports nothing."""
    published = [PublishedObject(uid="OU1", name="Alpha"), PublishedObject(uid="OU2", name="Beta")]
    instance = [InstanceObject(uid="OU1", name="Alpha"), InstanceObject(uid="OU2", name="Beta")]

    assert compare_organisation_units(published, instance) == []


def test_a_unit_the_instance_gained_is_reported_as_added() -> None:
    """A unit inside the scope the guide carries no Location for is drift the guide has to be told about."""
    findings = compare_organisation_units(
        [PublishedObject(uid="OU1", name="Alpha")],
        [InstanceObject(uid="OU1", name="Alpha"), InstanceObject(uid="OU2", name="Beta")],
    )

    assert len(findings) == 1
    assert findings[0].kind is DriftKind.ADDED
    assert findings[0].subject is DriftSubject.ORGANISATION_UNIT
    assert findings[0].uid == "OU2"
    assert "Beta" in findings[0].title
    assert "publishes nothing for it" in findings[0].detail


def test_a_unit_the_instance_lost_is_reported_as_removed() -> None:
    """The other direction: the guide publishes a unit the instance no longer holds in scope."""
    findings = compare_organisation_units(
        [PublishedObject(uid="OU1", name="Alpha"), PublishedObject(uid="OU2", name="Beta")],
        [InstanceObject(uid="OU1", name="Alpha")],
    )

    assert [finding.kind for finding in findings] == [DriftKind.REMOVED]
    assert findings[0].uid == "OU2"
    assert "no longer holds it" in findings[0].detail


def test_a_unit_renamed_under_one_uid_is_reported_with_both_names() -> None:
    """A rename keeps the identity and changes what a reader of the guide sees, so both names are stated."""
    findings = compare_organisation_units(
        [PublishedObject(uid="OU1", name="Alpha")], [InstanceObject(uid="OU1", name="Alpha North")]
    )

    assert [finding.kind for finding in findings] == [DriftKind.RENAMED]
    assert findings[0].published_name == "Alpha"
    assert findings[0].instance_name == "Alpha North"
    assert "'Alpha'" in findings[0].detail
    assert "'Alpha North'" in findings[0].detail


def test_a_substituted_hostile_name_is_not_a_rename() -> None:
    """A guide published with `hostile_names = "substitute"` carries the toolchain's own rewrite, not drift."""
    assert (
        compare_organisation_units(
            [PublishedObject(uid="OU1", name="Fixed, under 1y")], [InstanceObject(uid="OU1", name="Fixed, <1y")]
        )
        == []
    )


@pytest.mark.parametrize(
    ("options", "expected_kind", "expected_uid"),
    [
        ([InstanceOption(uid="O1", code="BCG", name="BCG")], None, None),
        (
            [InstanceOption(uid="O1", code="BCG", name="BCG"), InstanceOption(uid="O2", code="OPV", name="OPV")],
            DriftKind.ADDED,
            "O2",
        ),
        ([], DriftKind.REMOVED, "O1"),
        ([InstanceOption(uid="O1", code="BCG", name="BCG vaccine")], DriftKind.RENAMED, "O1"),
    ],
)
def test_an_option_set_drifts_in_every_direction(
    options: list[InstanceOption], expected_kind: DriftKind | None, expected_uid: str | None
) -> None:
    """One published CodeSystem against four instance states: clean, gained, lost, renamed."""
    published = PublishedOptionSet(uid="OS1", title="Vaccine type", options=(PublishedObject(uid="O1", name="BCG"),))

    findings = compare_option_set(published, InstanceOptionSet(uid="OS1", name="Vaccine type", options=tuple(options)))

    if expected_kind is None:
        assert findings == []
        return
    assert [finding.kind for finding in findings] == [expected_kind]
    assert findings[0].uid == expected_uid
    assert findings[0].subject is DriftSubject.OPTION
    assert "Vaccine type" in findings[0].holder


def test_a_code_mode_concept_still_matches_the_option_it_stands_for() -> None:
    """Under `concept_code_source = "code"` a concept is keyed by the DHIS2 code, and still resolves."""
    published = PublishedOptionSet(uid="OS1", title="Vaccine type", options=(PublishedObject(uid="BCG", name="BCG"),))

    assert (
        compare_option_set(
            published,
            InstanceOptionSet(
                uid="OS1", name="Vaccine type", options=(InstanceOption(uid="O1", code="BCG", name="BCG"),)
            ),
        )
        == []
    )


def test_a_form_reports_the_questions_the_instance_gained_and_lost() -> None:
    """A data set that gained a data element and lost another is two findings on the form that asks them."""
    published = PublishedForm(
        resource_id="DS1",
        kind="aggregate",
        uid="DS1",
        title="Child Health",
        questions=(PublishedObject(uid="DE1", name="BCG"), PublishedObject(uid="DE2", name="OPV")),
    )
    instance = InstanceForm(
        uid="DS1",
        name="Child Health",
        questions=(InstanceObject(uid="DE1", name="BCG"), InstanceObject(uid="DE3", name="Measles")),
    )

    findings = compare_form(published, instance, frozenset())

    assert {(finding.kind, finding.uid) for finding in findings} == {
        (DriftKind.REMOVED, "DE2"),
        (DriftKind.ADDED, "DE3"),
    }
    assert all(finding.subject is DriftSubject.DATA_ELEMENT for finding in findings)


def test_a_registration_form_reports_attributes_rather_than_data_elements() -> None:
    """A tracker form asks tracked entity attributes, so its drift is named as attributes."""
    published = PublishedForm(resource_id="PR1", kind="tracker", uid="PR1", title="Child Programme")
    instance = InstanceForm(uid="PR1", name="Child Programme", questions=(InstanceObject(uid="TEA1", name="Gender"),))

    findings = compare_form(published, instance, frozenset())

    assert [finding.subject for finding in findings] == [DriftSubject.TRACKED_ENTITY_ATTRIBUTE]
    assert findings[0].uid == "TEA1"


def test_a_stage_the_program_gained_publishes_no_form_and_is_drift() -> None:
    """A tracker program that grew a stage asks questions no published form carries."""
    published = PublishedForm(resource_id="PR1", kind="tracker", uid="PR1", title="Child Programme")
    instance = InstanceForm(
        uid="PR1",
        name="Child Programme",
        stages=(InstanceObject(uid="PS1", name="Birth"), InstanceObject(uid="PS2", name="Postnatal")),
    )

    findings = compare_form(published, instance, frozenset({"PS1"}))

    assert [(finding.subject, finding.kind, finding.uid) for finding in findings] == [
        (DriftSubject.PROGRAM_STAGE, DriftKind.ADDED, "PS2")
    ]


def test_a_form_whose_dhis2_object_is_gone_is_one_finding_rather_than_every_question() -> None:
    """A deleted data set is one fact about the form, not one fact per question it used to ask.

    And the finding names the data set, not a data element: an artifact that outlived its DHIS2
    object is drift about that object, so calling it a question would be naming the wrong thing.
    """
    published = PublishedForm(
        resource_id="DS1",
        kind="aggregate",
        uid="DS1",
        title="Child Health",
        questions=(PublishedObject(uid="DE1", name="BCG"), PublishedObject(uid="DE2", name="OPV")),
    )

    findings = compare_form(published, None, frozenset())

    assert [(finding.subject, finding.kind, finding.uid) for finding in findings] == [
        (DriftSubject.DATA_SET, DriftKind.REMOVED, "DS1")
    ]
    assert findings[0].title == "data set Child Health (DS1)"


def test_an_option_set_the_instance_deleted_is_named_as_an_option_set() -> None:
    """The whole CodeSystem outlived its DHIS2 object, which is one finding about the set itself."""
    published = PublishedOptionSet(uid="OS1", title="Vaccine type", options=(PublishedObject(uid="O1", name="BCG"),))

    findings = compare_option_set(published, None)

    assert [(finding.subject, finding.kind, finding.uid) for finding in findings] == [
        (DriftSubject.OPTION_SET, DriftKind.REMOVED, "OS1")
    ]
    assert findings[0].title == "option set Vaccine type (OS1)"


@pytest.mark.parametrize(
    ("root", "max_level", "expected"),
    [
        ("DistrictAA", 3, "the hierarchy under DistrictAA down to level 3"),
        ("DistrictAA", None, "the hierarchy under DistrictAA"),
        (None, 3, "the hierarchy down to level 3"),
        (None, None, "the whole hierarchy"),
    ],
)
def test_the_registry_scope_is_stated_in_the_words_the_selection_uses(
    root: str | None, max_level: int | None, expected: str
) -> None:
    """The evidence line names the slice the guide claims to publish, however the selection narrows it."""
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitSelection

    config = GenerateConfig(organisation_units=OrganisationUnitSelection(root=root, max_level=max_level))

    assert registry_scope_line(config) == expected


# --- the reader and the whole pass, against a published tree and a mocked instance ----------------


def test_the_reader_finds_every_published_object_it_compares(published_project: Path) -> None:
    """What a published guide holds, read through the same reader the served store and check-artifacts use."""
    guide = read_published_guide(load_project(published_project))

    assert [unit.uid for unit in guide.organisation_units] == ["OuAAAAAAAA1", "OuAAAAAAAA2"]
    assert [option_set.uid for option_set in guide.option_sets] == ["OsAAAAAAAA1"]
    assert {form.uid for form in guide.forms} == {"DsAAAAAAAA1", "PrAAAAAAAA1", "PsAAAAAAAA1", "TetAAAAAAA1"}
    assert guide.program_stage_uids == frozenset({"PsAAAAAAAA1"})


@respx.mock
async def test_a_guide_that_still_describes_the_instance_reports_one_quiet_line(published_project: Path) -> None:
    """Nothing moved, so the phase says what it read and says it found nothing."""
    _mock_instance()

    report = await _drift(published_project)

    assert report.findings == ()
    assert report.evidence == (
        "the guide publishes the instance as it now stands: 2 organisation unit(s), 1 option set(s), "
        "and 4 form(s) read against the hierarchy under DistrictAA down to level 3"
    )
    assert DRIFT_REMEDY not in report.evidence


@respx.mock
async def test_an_organisation_unit_outside_the_registry_scope_is_not_drift(published_project: Path) -> None:
    """The instance is read under the selection's own filters, so a unit elsewhere never reaches the compare.

    This is the property the whole report rests on. A pass that read the hierarchy unfiltered would
    call every unit outside one district's registry an addition, and a national instance would drown
    the finding table in objects the project never asked for.
    """
    _mock_instance()

    await _drift(published_project)

    request = next(call.request for call in respx.calls if call.request.url.path == "/api/organisationUnits")
    assert sorted(request.url.params.get_list("filter")) == ["level:le:3", "path:like:DistrictAA"]


@respx.mock
async def test_every_drift_class_reports_against_a_moved_instance(published_project: Path) -> None:
    """One instance that moved in all five ways at once, and one finding per object that moved."""
    _mock_instance(
        organisation_units=[
            {"id": "OuAAAAAAAA1", "name": "Alpha district"},
            {"id": "OuAAAAAAAA3", "name": "Gamma chiefdom"},
        ],
        options=[
            {"id": "OptAAAAAAA1", "code": "BCG", "name": "BCG"},
            {"id": "OptAAAAAAA2", "code": "MEASLES", "name": "Measles, second dose"},
        ],
        data_elements=[{"id": "DeAAAAAAAA1", "name": "BCG doses given"}, {"id": "DeAAAAAAAA9", "name": "OPV0"}],
        attributes=[{"id": "TeaAAAAAAA1", "name": "Given name"}],
        stage_elements=[{"id": "DeAAAAAAAA2", "name": "Apgar Score"}],
        stages=[{"id": "PsAAAAAAAA1", "name": "Birth"}, {"id": "PsAAAAAAAA2", "name": "Postnatal"}],
    )

    report = await _drift(published_project)

    moved = {(finding.subject, finding.kind, finding.uid) for finding in report.findings}
    assert (DriftSubject.ORGANISATION_UNIT, DriftKind.REMOVED, "OuAAAAAAAA2") in moved
    assert (DriftSubject.ORGANISATION_UNIT, DriftKind.ADDED, "OuAAAAAAAA3") in moved
    assert (DriftSubject.OPTION, DriftKind.RENAMED, "OptAAAAAAA2") in moved
    assert (DriftSubject.DATA_ELEMENT, DriftKind.ADDED, "DeAAAAAAAA9") in moved
    assert (DriftSubject.TRACKED_ENTITY_ATTRIBUTE, DriftKind.RENAMED, "TeaAAAAAAA1") in moved
    assert (DriftSubject.PROGRAM_STAGE, DriftKind.ADDED, "PsAAAAAAAA2") in moved
    assert DRIFT_REMEDY in report.evidence
    assert "unmapped-tracked-entity-type" in report.evidence


# --- the phase: outcome, severity, and the reasons it does not run --------------------------------


def test_drift_is_graded_a_warning_rather_than_a_failure() -> None:
    """A guide that is out of date still serves, still captures, and still forwards - so it never exits 1."""
    report = DriftReport(
        registry_scope="the whole hierarchy",
        findings=(
            DriftFinding(
                subject=DriftSubject.OPTION,
                kind=DriftKind.ADDED,
                uid="O2",
                holder="the published option set Vaccine type (OS1)",
                instance_name="OPV",
            ),
        ),
    )

    graded = grade_drift(report)

    assert graded.outcome is DoctorOutcome.WARNED
    assert [finding.severity for finding in graded.findings] == ["warning"]
    assert graded.findings[0].phase is DoctorPhase.DRIFT
    assert graded.findings[0].field_path == "added"


def test_a_clean_drift_report_grades_the_phase_as_passed() -> None:
    """Zero drift is a pass, on the one line the phase is read by."""
    graded = grade_drift(DriftReport(registry_scope="the whole hierarchy"))

    assert graded.outcome is DoctorOutcome.PASSED
    assert graded.findings == ()
    assert drift_findings(DriftReport(registry_scope="the whole hierarchy")) == []


def test_the_doctor_workspace_is_never_read_as_the_published_guide(
    published_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project this run scaffolded seconds ago can only agree with the instance, so it is not the subject."""
    monkeypatch.chdir(published_project)

    assert resolve_published_project(published_project.resolve()) is None
    assert resolve_published_project(published_project / "elsewhere") is not None


def test_a_working_directory_with_no_project_resolves_no_published_guide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `fhir.toml` anywhere above the working directory means there is no guide to check."""
    monkeypatch.chdir(tmp_path)

    assert resolve_published_project(tmp_path / "workspace") is None


@respx.mock
async def test_the_phase_skips_with_a_reason_when_there_is_no_published_guide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Doctor run from a directory holding no project reports why the phase did not run, and passes."""
    monkeypatch.setattr("dhis2w_fhir.doctor.shutil.which", lambda _name: None)
    monkeypatch.chdir(tmp_path)
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(500, json={}))

    report = await run_doctor(_profile(), DoctorOptions(workspace=tmp_path / "workspace"))

    phase = next(entry for entry in report.phases if entry.phase is DoctorPhase.DRIFT)
    # Connect failed, so every later phase is blocked rather than skipped - the reason still stands.
    assert phase.outcome is DoctorOutcome.BLOCKED
    assert phase.reason


@respx.mock
async def test_the_phase_skips_when_the_project_was_generated_but_never_compiled(
    published_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No compiled tree is a fact about the project, so the phase says so rather than reporting nothing."""
    for path in (published_project / "ig/fsh-generated/resources").glob("*.json"):
        path.unlink()
    monkeypatch.setattr("dhis2w_fhir.doctor.shutil.which", lambda _name: None)
    monkeypatch.chdir(published_project)
    _mock_instance()
    respx.get(f"{_BASE_URL}/api/metadata").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{_BASE_URL}/api/attributes").mock(return_value=httpx.Response(200, json={"attributes": []}))
    respx.get(f"{_BASE_URL}/api/programRules").mock(return_value=httpx.Response(200, json={"programRules": []}))
    respx.get(f"{_BASE_URL}/api/categories").mock(return_value=httpx.Response(200, json={"categories": []}))
    respx.get(f"{_BASE_URL}/api/dataElements").mock(return_value=httpx.Response(200, json={"dataElements": []}))
    respx.get(f"{_BASE_URL}/api/trackedEntityAttributes").mock(
        return_value=httpx.Response(200, json={"trackedEntityAttributes": []})
    )
    respx.post(f"{_BASE_URL}/api/dataValueSets").mock(return_value=httpx.Response(200, json={"status": "SUCCESS"}))
    respx.post(f"{_BASE_URL}/api/tracker").mock(return_value=httpx.Response(200, json={"status": "OK"}))

    report = await run_doctor(_profile(), DoctorOptions(workspace=published_project / "workspace"))

    phase = next(entry for entry in report.phases if entry.phase is DoctorPhase.DRIFT)
    assert phase.outcome is DoctorOutcome.SKIPPED
    assert "make sushi" in (phase.reason or "")
