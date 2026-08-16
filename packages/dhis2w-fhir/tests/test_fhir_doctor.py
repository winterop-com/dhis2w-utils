"""Tests for `d2w fhir doctor` - phase orchestration, the graders, the oracle, and the rendering.

The graders are tested as the pure functions they are: what a phase concluded is a separate contract
from how it did the work, and a run that has to reach a real instance to prove "a rejection fails the
phase" would be testing DHIS2 rather than doctor.

The orchestration is tested at both ends of its range. A connect that never answers leaves every
later phase BLOCKED, which is the short path; and a whole small instance, mocked collection by
collection, is driven from connect through to the oracle with nothing BLOCKED at all, which is the
only proof that the chain each phase hands to the next actually holds all the way along. The compiler
is monkeypatched out of existence in that run, so compile is SKIPPED deterministically whatever the
machine happens to have on its PATH.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_client.profile import Profile
from dhis2w_core.client_context import open_client
from dhis2w_fhir.conversion import (
    CodedAnswerMode,
    ConversionRefusal,
    ConversionRefusalCategory,
    ConversionTargetKind,
)
from dhis2w_fhir.doctor import (
    _ORACLE_FAMILIES,
    DOCTOR_PHASE_ORDER,
    DoctorFinding,
    DoctorOptions,
    DoctorOutcome,
    DoctorPhase,
    DoctorPhaseResult,
    DoctorReport,
    _capture_one,
    _capture_order,
    _CaptureOutcome,
    _FamilyOutcome,
    _judge_family,
    _OracleFamily,
    _ProbeAssignment,
    _ProbeTarget,
    _registry_root,
    _sample_uids,
    _ServedResource,
    _sushi_command,
    generate_findings,
    grade_capture,
    grade_forward,
    grade_oracle,
    phase_evidence,
    render_doctor_markdown,
    run_doctor,
)
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory
from dhis2w_fhir.service import (
    ForwardImportIssue,
    ForwardImportOutcome,
    ForwardOutcome,
    ForwardOutcomeKind,
    ForwardReport,
    GenerationProfile,
)
from fastapi import FastAPI
from starlette.responses import JSONResponse
from typer.testing import CliRunner

_runner = CliRunner()

_BASE_URL = "https://dhis2.example"

_IDENTIFIER_BASE = "http://dhis2.org/fhir/id"

#: The organisation-unit family, which is the one every oracle test judges through.
_ORGANISATION_UNIT_FAMILY = _ORACLE_FAMILIES[0]


def _profile() -> GenerationProfile:
    """A resolved profile pointing at the respx-mocked instance."""
    return GenerationProfile(
        name="probe",
        origin="test",
        profile=Profile(base_url=_BASE_URL, auth="pat", token="d2p_test"),
    )


def _phase(
    phase: DoctorPhase,
    outcome: DoctorOutcome,
    evidence: str = "",
    reason: str | None = None,
    findings: tuple[DoctorFinding, ...] = (),
) -> DoctorPhaseResult:
    """One phase result, as a report is assembled from."""
    return DoctorPhaseResult(phase=phase, outcome=outcome, evidence=evidence, reason=reason, findings=findings)


def _report(*phases: DoctorPhaseResult) -> DoctorReport:
    """One report over the given phases, with the invocation fields a run fills in."""
    return DoctorReport(
        profile_name="probe",
        profile_origin="test",
        base_url=_BASE_URL,
        dhis2_version="2.42.0",
        version_tree="v42",
        workspace=Path("/tmp/doctor"),
        workspace_kept=False,
        generated_at=datetime(2026, 8, 11, tzinfo=UTC),
        options=DoctorOptions(),
        phases=phases,
    )


def _forward_report(*outcomes: ForwardOutcome) -> ForwardReport:
    """One forward report over the given per-response outcomes."""
    return ForwardReport(
        project_root=Path("/tmp/doctor"),
        dry_run=True,
        coded_answer_mode=CodedAnswerMode.LENIENT,
        spooled=len(outcomes),
        outcomes=outcomes,
    )


def _rejected(response_id: str, error_code: str, reason: str) -> ForwardOutcome:
    """One response DHIS2 was given and refused, carrying the row it refused it on."""
    return ForwardOutcome(
        response_id=response_id,
        spool_path=f".serve/responses/received/{response_id}.json",
        kind=ForwardOutcomeKind.REJECTED,
        target_kind=ConversionTargetKind.TRACKER_EVENT,
        import_outcome=ForwardImportOutcome(
            status="ERROR",
            message="import failed",
            issues=(ForwardImportIssue(error_code=error_code, message=reason),),
        ),
    )


def test_report_round_trips_through_json() -> None:
    """A report dumps to JSON and validates back, counts, verdict, and findings intact."""
    finding = DoctorFinding(
        phase=DoctorPhase.ORACLE,
        severity="error",
        subject="Organization/OU1",
        detail="the instance says the name is 'Bo District'",
        field_path="name",
    )
    report = _report(
        _phase(DoctorPhase.CONNECT, DoctorOutcome.PASSED, "DHIS2 2.42.0"),
        _phase(DoctorPhase.ORACLE, DoctorOutcome.FAILED, "1 mismatch", findings=(finding,)),
    )
    restored = DoctorReport.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.findings == (finding,)
    assert [phase.phase for phase in restored.failed_phases] == [DoctorPhase.ORACLE]
    assert restored.counts_by_outcome["pass"] == 1
    assert restored.counts_by_outcome["fail"] == 1
    assert restored.verdict_line.startswith("BROKEN")


def test_a_run_without_failures_reads_as_usable() -> None:
    """Warnings and skips do not break the verdict - only a failure does."""
    report = _report(
        _phase(DoctorPhase.CONNECT, DoctorOutcome.PASSED),
        _phase(DoctorPhase.GENERATE, DoctorOutcome.WARNED, "2 note(s)"),
        _phase(DoctorPhase.COMPILE, DoctorOutcome.SKIPPED, reason="no compiler"),
    )
    assert report.failed_phases == ()
    assert report.verdict_line.startswith("USABLE")


def test_phase_evidence_folds_the_reason_into_a_phase_that_did_not_run() -> None:
    """A skipped phase reads as its reason, and a phase that ran reads as its evidence."""
    skipped = _phase(DoctorPhase.COMPILE, DoctorOutcome.SKIPPED, reason="no FSH compiler on this machine")
    ran = _phase(DoctorPhase.CONNECT, DoctorOutcome.PASSED, "DHIS2 2.42.0")
    assert phase_evidence(skipped) == "no FSH compiler on this machine"
    assert phase_evidence(ran) == "DHIS2 2.42.0"


def test_markdown_report_carries_the_phase_table_and_every_finding() -> None:
    """The written report holds one row per phase and one row per finding, pipes escaped."""
    finding = DoctorFinding(
        phase=DoctorPhase.FORWARD,
        severity="error",
        subject="E1029",
        detail="OrganisationUnit | Program do not match",
    )
    markdown = render_doctor_markdown(
        _report(
            _phase(DoctorPhase.CONNECT, DoctorOutcome.PASSED, "DHIS2 2.42.0"),
            _phase(DoctorPhase.FORWARD, DoctorOutcome.FAILED, "1 rejected", findings=(finding,)),
        )
    )
    assert "| connect | pass | DHIS2 2.42.0 |" in markdown
    assert "| forward | fail | 1 rejected |" in markdown
    assert "OrganisationUnit \\| Program do not match" in markdown
    assert "Verdict: BROKEN" in markdown


def test_markdown_report_states_a_clean_run_rather_than_an_empty_table() -> None:
    """A run that found nothing says so in words, not as a findings table with no rows."""
    markdown = render_doctor_markdown(_report(_phase(DoctorPhase.CONNECT, DoctorOutcome.PASSED, "DHIS2 2.42.0")))
    assert "No phase found anything to report against this instance." in markdown


@respx.mock
async def test_a_connect_failure_blocks_every_later_phase() -> None:
    """Bad credentials stop the run at connect, and every phase after it says what stopped it."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(401, json={"message": "Unauthorized"}))
    report = await run_doctor(_profile(), DoctorOptions())
    assert [phase.phase for phase in report.phases] == list(DOCTOR_PHASE_ORDER)
    connect = report.phases[0]
    assert connect.outcome is DoctorOutcome.FAILED
    assert connect.evidence
    assert all(phase.outcome is DoctorOutcome.BLOCKED for phase in report.phases[1:])
    assert all(phase.reason for phase in report.phases[1:])
    assert report.verdict_line.startswith("BROKEN")


@respx.mock
async def test_a_connect_failure_leaves_no_workspace_behind() -> None:
    """The minted workspace is removed on every exit path, including the one that failed first."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(401, json={"message": "Unauthorized"}))
    report = await run_doctor(_profile(), DoctorOptions())
    assert not report.workspace_kept
    assert not report.workspace.exists()


@respx.mock
def test_cli_exits_one_when_a_phase_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`d2w fhir doctor` renders the phase table and exits 1 when the instance never answers."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        f"""
default = "probe"

[profiles.probe]
base_url = "{_BASE_URL}"
auth = "pat"
token = "d2p_test"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(401, json={"message": "Unauthorized"}))

    result = _runner.invoke(build_app(), ["fhir", "doctor", "--no-progress"])

    assert result.exit_code == 1
    assert "connect" in result.output
    assert "blocked" in result.output
    assert (tmp_path / "reports" / "fhir-doctor-report.md").exists()


#: A whole small instance, in the shapes the generate reads project. One data set, one event program,
#: one option set, one category, and a two-level registry - enough that every phase after connect has
#: something real to do, and small enough that the whole run is a couple of seconds.
_OPTION_SETS_PAYLOAD = {
    "optionSets": [
        {
            "id": "Xa1b2c3d4e5",
            "name": "Birth type",
            "options": [
                {"id": "kRRUtYaGett", "code": "NB", "name": "Natural Birth", "sortOrder": 1},
                {"id": "EBE0c8sZazS", "code": "CS", "name": "Scheduled Cesarean", "sortOrder": 2},
            ],
        }
    ]
}

_CATEGORIES_PAYLOAD = {
    "categories": [
        {
            "id": "O5P6e8yu1T6",
            "name": "Sex",
            "categoryOptions": [
                {"id": "TNYQzTHdoxL", "code": "F", "name": "Female"},
                {"id": "apsOixVZlf1", "code": "M", "name": "Male"},
            ],
        }
    ]
}

_ORGANISATION_UNITS_PAYLOAD = {
    "organisationUnits": [
        {"id": "ImspTQPwCqd", "name": "Sierra Leone", "level": 1, "path": "/ImspTQPwCqd", "code": "SL"},
        {
            "id": "O6uvpzGd5pu",
            "name": "Bo",
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
            "code": "DS_359711",
            "periodType": "Monthly",
            "sections": [{"id": "Sec1aaaaaaa", "name": "Immunization", "dataElements": [{"id": "De1aaaaaaaa"}]}],
            "dataSetElements": [
                {
                    "dataElement": {
                        "id": "De1aaaaaaaa",
                        "name": "BCG doses given",
                        "valueType": "INTEGER_ZERO_OR_POSITIVE",
                        "optionSet": {"id": "Xa1b2c3d4e5"},
                        "categoryCombo": {"id": "bjDvmb4bfuf", "name": "default", "isDefault": True},
                    }
                }
            ],
            "organisationUnits": [{"id": "ImspTQPwCqd"}, {"id": "O6uvpzGd5pu"}],
        }
    ]
}

_PROGRAMS_PAYLOAD = {
    "programs": [
        {
            "id": "VBqh0ynB2wv",
            "name": "Malaria case registration",
            "code": "MAL_CASE",
            "programType": "WITHOUT_REGISTRATION",
            "organisationUnits": [{"id": "ImspTQPwCqd"}, {"id": "O6uvpzGd5pu"}],
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

#: What a value-type read answers for whichever uids it asked about. A uid names exactly one object,
#: so the same shape serves the data-element read and the tracked-entity-attribute one.
_VALUE_TYPES = {"De1aaaaaaaa": "INTEGER_ZERO_OR_POSITIVE", "qrur9Dvnyt5": "INTEGER"}


def _requested_uids(request: httpx.Request) -> list[str]:
    """The uids one id-only read asked about, off its `id:in:[...]` filter."""
    inside = request.url.params.get("filter", "").partition("[")[2].rpartition("]")[0]
    return [uid for uid in inside.split(",") if uid]


def _typed(collection: str) -> Any:
    """A side effect answering one value-type read with a type for every uid it named."""

    def _answer(request: httpx.Request) -> httpx.Response:
        entries = [{"id": uid, "valueType": _VALUE_TYPES.get(uid, "TEXT")} for uid in _requested_uids(request)]
        return httpx.Response(200, json={collection: entries})

    return _answer


def _programs(request: httpx.Request) -> httpx.Response:
    """Answer the programs read, honouring the `programType` filter the scaffold probe asks each kind with.

    The probe asks twice - once for the first event program, once for the first tracker one - and an
    instance that answered both with the same object would have the scaffold select a
    WITHOUT_REGISTRATION program as a tracker program, which generate rightly refuses. This instance
    holds no tracker program at all, so the run's forms are the aggregate one and the event one.
    """
    filters = request.url.params.get_list("filter")
    if any("programType:eq:WITH_REGISTRATION" in value for value in filters):
        return httpx.Response(200, json={"programs": []})
    return httpx.Response(200, json=_PROGRAMS_PAYLOAD)


def _mock_whole_instance() -> None:
    """Mock every endpoint a whole doctor run touches, across all nine phases.

    The routes answer repeatedly on purpose: generate, validate, the live store, and forward each open
    a client of their own, so a route that answered once would fail the phase that asked second.
    """
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(200, json={"version": "2.42.0"}))
    respx.get(f"{_BASE_URL}/api/attributes").mock(return_value=httpx.Response(200, json={"attributes": []}))
    respx.get(f"{_BASE_URL}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    respx.get(f"{_BASE_URL}/api/categories").mock(return_value=httpx.Response(200, json=_CATEGORIES_PAYLOAD))
    respx.get(f"{_BASE_URL}/api/dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    respx.get(f"{_BASE_URL}/api/programs").mock(side_effect=_programs)
    respx.get(f"{_BASE_URL}/api/programRules").mock(return_value=httpx.Response(200, json={"programRules": []}))
    respx.get(f"{_BASE_URL}/api/trackedEntityTypes").mock(
        return_value=httpx.Response(200, json={"trackedEntityTypes": []})
    )
    respx.get(f"{_BASE_URL}/api/organisationUnits").mock(
        return_value=httpx.Response(200, json=_ORGANISATION_UNITS_PAYLOAD)
    )
    respx.get(f"{_BASE_URL}/api/dataElements").mock(side_effect=_typed("dataElements"))
    respx.get(f"{_BASE_URL}/api/trackedEntityAttributes").mock(side_effect=_typed("trackedEntityAttributes"))
    # The validate sweep reads the whole metadata document at once, and answers off its own keys.
    respx.get(f"{_BASE_URL}/api/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [{"id": uid, "name": uid, "code": None} for uid in _VALUE_TYPES],
                "optionSets": _OPTION_SETS_PAYLOAD["optionSets"],
                "categories": _CATEGORIES_PAYLOAD["categories"],
                "organisationUnits": _ORGANISATION_UNITS_PAYLOAD["organisationUnits"],
                "dataSets": _DATA_SETS_PAYLOAD["dataSets"],
                "programs": _PROGRAMS_PAYLOAD["programs"],
            },
        )
    )
    # The forward phase is a dry run, so both endpoints answer as validate-only acceptances.
    respx.post(f"{_BASE_URL}/api/dataValueSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "response": {
                    "responseType": "ImportSummary",
                    "status": "SUCCESS",
                    "importCount": {"imported": 1, "updated": 0, "ignored": 0, "deleted": 0},
                },
            },
        )
    )
    respx.post(f"{_BASE_URL}/api/tracker").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "stats": {"created": 1, "updated": 0, "deleted": 0, "ignored": 0, "total": 1},
                "validationReport": {"errorReports": [], "warningReports": []},
            },
        )
    )


@respx.mock
async def test_a_whole_run_reaches_a_verdict_with_no_phase_left_blocked(
    probe_profile: None,  # noqa: ARG001
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every phase runs against a mocked instance, and each one concludes something of its own.

    BLOCKED is the outcome that means a phase never ran because an earlier one left it nothing to run
    on, so a run with none of them is the only proof that the orchestration actually walks the whole
    chain - connect through to the oracle - rather than falling over somewhere in the middle.
    """
    # No compiler on the machine under test, so the compile phase is SKIPPED deterministically and
    # the serve phase builds its store off the instance rather than off fsh-generated resources.
    monkeypatch.setattr("dhis2w_fhir.doctor.shutil.which", lambda _name: None)
    _mock_whole_instance()

    report = await run_doctor(_profile(), DoctorOptions(workspace=tmp_path / "workspace", live=True, samples=5))

    assert [phase.phase for phase in report.phases] == list(DOCTOR_PHASE_ORDER)
    assert len(report.phases) == 9
    blocked = [phase.phase for phase in report.phases if phase.outcome is DoctorOutcome.BLOCKED]
    assert blocked == [], f"phases that never ran: {blocked}"
    assert all(phase.evidence or phase.reason for phase in report.phases)

    outcomes = {phase.phase: phase.outcome for phase in report.phases}
    assert outcomes[DoctorPhase.CONNECT] is DoctorOutcome.PASSED
    assert outcomes[DoctorPhase.SCAFFOLD] is DoctorOutcome.PASSED
    # No `sushi` and no docker image is a machine with no compiler, which is skipped rather than failed.
    assert outcomes[DoctorPhase.COMPILE] is DoctorOutcome.SKIPPED
    # The oracle was asked, rather than skipped for want of `--live`.
    assert outcomes[DoctorPhase.ORACLE] is not DoctorOutcome.SKIPPED

    assert report.dhis2_version == "2.42.0"
    assert report.version_tree == "v42"
    assert report.verdict_line.startswith(("USABLE", "BROKEN"))
    assert report.workspace_kept


@respx.mock
async def test_a_whole_run_judges_every_oracle_family_it_served(
    probe_profile: None,  # noqa: ARG001
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The oracle phase's evidence names each of the four families, so none is silently skipped."""
    monkeypatch.setattr("dhis2w_fhir.doctor.shutil.which", lambda _name: None)
    _mock_whole_instance()

    report = await run_doctor(_profile(), DoctorOptions(workspace=tmp_path / "workspace", live=True))

    oracle = next(phase for phase in report.phases if phase.phase is DoctorPhase.ORACLE)
    for family in _ORACLE_FAMILIES:
        assert f"{family.label}:" in oracle.evidence, family.label


@respx.mock
def test_the_cli_writes_a_report_of_a_run_that_reached_every_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A whole run leaves the markdown handover behind, with the phase table filled in."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        f"""
default = "probe"

[profiles.probe]
base_url = "{_BASE_URL}"
auth = "pat"
token = "d2p_test"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dhis2w_fhir.doctor.shutil.which", lambda _name: None)
    _mock_whole_instance()
    workspace = tmp_path / "workspace"

    result = _runner.invoke(build_app(), ["fhir", "doctor", "--no-progress", "--live", "--workspace", str(workspace)])

    assert result.exit_code == 0, result.output
    written = workspace / "reports" / "fhir-doctor-report.md"
    assert written.exists(), result.output
    markdown = written.read_text(encoding="utf-8")
    assert "# fhir doctor report" in markdown
    assert "## Phases" in markdown
    for phase in DOCTOR_PHASE_ORDER:
        assert f"| {phase.value} |" in markdown
    # No phase was left unrun, which is the whole claim of a run that reached the oracle.
    assert "0 blocked" in markdown
    assert "Verdict: USABLE" in markdown


def test_no_compiler_on_the_machine_offers_no_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither `sushi` nor docker means the compile phase has nothing to run, which is what SKIPPED means."""
    monkeypatch.setattr("dhis2w_fhir.doctor.shutil.which", lambda _name: None)
    assert _sushi_command() is None


def test_docker_without_the_scaffold_image_offers_no_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Doctor never builds the compiler image - a docker that does not hold it is a machine without a compiler."""
    monkeypatch.setattr("dhis2w_fhir.doctor.shutil.which", lambda name: None if name == "sushi" else "/usr/bin/docker")
    monkeypatch.setattr("dhis2w_fhir.doctor._docker_image_present", lambda _docker: False)
    assert _sushi_command() is None


def test_a_present_sushi_is_run_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `sushi` on PATH is the compiler, run over the IG directory as the scaffold's Makefile runs it."""
    monkeypatch.setattr("dhis2w_fhir.doctor.shutil.which", lambda name: "/usr/bin/sushi" if name == "sushi" else None)
    assert _sushi_command() == ["sushi", "."]


def _capture_app(*, accept: bool) -> FastAPI:
    """A stand-in capture endpoint: `$generate` answers a response, and the POST takes it or refuses it."""
    app = FastAPI()

    @app.get("/Questionnaire/{resource_id}/$generate")
    async def generate(resource_id: str) -> JSONResponse:
        return JSONResponse({"resourceType": "QuestionnaireResponse", "questionnaire": resource_id})

    @app.post("/QuestionnaireResponse")
    async def create() -> JSONResponse:
        if accept:
            return JSONResponse(status_code=201, content={"resourceType": "OperationOutcome"})
        return JSONResponse(
            status_code=422,
            content={"resourceType": "OperationOutcome", "issue": [{"diagnostics": "answer 3 is out of bounds"}]},
        )

    return app


def _form(resource_id: str, form_kind: str = "aggregate") -> _ServedResource:
    """One served Questionnaire as the capture phase reads it."""
    return _ServedResource(resource_type="Questionnaire", resource_id=resource_id, form_kind=form_kind)


async def test_capture_accepts_what_the_endpoint_generated() -> None:
    """The 201 invariant holding is what a passing capture phase means."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_capture_app(accept=True)), base_url="http://serve.test"
    ) as http:
        outcome = await _capture_one(http, _form("DS1"), 0)
    assert outcome.generated
    assert outcome.accepted
    assert outcome.findings == ()
    assert grade_capture([outcome]).outcome is DoctorOutcome.PASSED


async def test_capture_fails_when_the_endpoint_refuses_its_own_output() -> None:
    """An endpoint refusing what it just generated is broken, and the diagnostics say why."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_capture_app(accept=False)), base_url="http://serve.test"
    ) as http:
        outcome = await _capture_one(http, _form("DS1"), 0)
    assert outcome.generated
    assert not outcome.accepted
    assert len(outcome.findings) == 1
    assert outcome.findings[0].severity == "error"
    assert "answer 3 is out of bounds" in outcome.findings[0].detail
    graded = grade_capture([outcome])
    assert graded.outcome is DoctorOutcome.FAILED
    assert graded.evidence == "1 form(s), 1 generated, 0 accepted as 201"


def test_one_note_is_one_finding_however_many_targets_raised_it() -> None:
    """Targets share their source notes, so the same note reaching three of them is still one row."""
    greyed_cells = GenerateNote(
        category=GenerateNoteCategory.FORM_STRUCTURE,
        message="data set 'Child Health' (BfMAe6Itzgt) greys out 8 disaggregated cells",
    )
    gap = GenerateNote(
        category=GenerateNoteCategory.SELECTION_GAP,
        message="1 organisation units have a parent outside the selection",
    )

    findings = generate_findings([greyed_cells, gap, greyed_cells, greyed_cells])

    assert [finding.detail for finding in findings] == [greyed_cells.message, gap.message]


def test_a_note_two_targets_word_differently_stays_two_findings() -> None:
    """Dedup is by value, so two genuinely different notes of one category both keep their row."""
    findings = generate_findings(
        [
            GenerateNote(category=GenerateNoteCategory.FORM_STRUCTURE, message="data set 'A' greys out 8 cells"),
            GenerateNote(category=GenerateNoteCategory.FORM_STRUCTURE, message="data set 'B' greys out 2 cells"),
        ]
    )

    assert len(findings) == 2


def test_capture_order_puts_a_registration_before_its_stages() -> None:
    """A stage response answers against a spooled registration, so the registration is captured first."""
    forms = [_form("STAGE", "tracker-event"), _form("DS", "aggregate"), _form("PROG", "tracker")]
    assert [form.resource_id for form in _capture_order(forms)] == ["PROG", "DS", "STAGE"]


def test_forward_rejections_fail_the_phase_and_roll_up_by_cause() -> None:
    """Two responses refused for one reason are one finding, and the phase they belong to is broken."""
    report = _forward_report(
        _rejected("r1", "E1029", "Event OrganisationUnit `abc` and Program `def`, do not match."),
        _rejected("r2", "E1029", "Event OrganisationUnit `ghi` and Program `jkl`, do not match."),
    )
    graded = grade_forward(report)
    assert graded.outcome is DoctorOutcome.FAILED
    assert len(graded.findings) == 1
    assert graded.findings[0].subject == "E1029"
    assert graded.findings[0].detail.startswith("2 response(s):")


def test_a_translator_refusal_only_degrades_the_forward_phase() -> None:
    """A response the translator would not read whole is a note, not a broken instance."""
    refused = ForwardOutcome(
        response_id="r3",
        spool_path=".serve/responses/received/r3.json",
        kind=ForwardOutcomeKind.REFUSED,
        refusals=(
            ConversionRefusal(
                category=ConversionRefusalCategory.UNKNOWN_LINK_ID,
                reason="link id `zzz` is not a question of this form",
            ),
        ),
    )
    graded = grade_forward(_forward_report(refused))
    assert graded.outcome is DoctorOutcome.WARNED
    assert graded.findings[0].severity == "warning"


def test_a_clean_drain_passes_the_forward_phase() -> None:
    """A clean instance shows nothing rejected and nothing refused, which is a passing phase."""
    accepted = ForwardOutcome(
        response_id="r4",
        spool_path=".serve/responses/received/r4.json",
        kind=ForwardOutcomeKind.ACCEPTED,
        import_outcome=ForwardImportOutcome(status="OK"),
    )
    unverifiable = ForwardOutcome(
        response_id="r5",
        spool_path=".serve/responses/received/r5.json",
        kind=ForwardOutcomeKind.UNVERIFIABLE,
    )
    graded = grade_forward(_forward_report(accepted, unverifiable))
    assert graded.outcome is DoctorOutcome.PASSED
    assert graded.findings == ()


def test_registry_root_takes_the_probe_level_ancestor_of_the_first_deep_enough_assignment() -> None:
    """The subtree published is the one the selected forms are actually assigned inside."""
    samples = [
        _ProbeAssignment(target=_ProbeTarget(kind="data set", uid="DS", name="ART"), path="/COUNTRY", level=1),
        _ProbeAssignment(
            target=_ProbeTarget(kind="event program", uid="PR", name="ANC"),
            path="/COUNTRY/DISTRICT/CHIEFDOM/FACILITY",
            level=4,
        ),
    ]
    assert _registry_root(samples) == "DISTRICT"


def test_a_hierarchy_with_no_deep_assignment_publishes_by_level_instead() -> None:
    """A flat hierarchy names no subtree, which is how the registry falls back to a level cap."""
    samples = [_ProbeAssignment(target=_ProbeTarget(kind="data set", uid="DS", name="ART"), path="/ROOT", level=1)]
    assert _registry_root(samples) is None


def test_the_oracle_sample_is_deterministic() -> None:
    """Two runs against one unchanged instance judge the same objects, so a mismatch replays."""
    uids = [f"OU{index:03d}" for index in range(50)]
    assert _sample_uids(uids, 5) == _sample_uids(uids, 5)
    assert len(_sample_uids(uids, 5)) == 5
    assert _sample_uids(uids[:3], 5) == uids[:3]


def _served_organisation_unit(uid: str, name: str) -> _ServedResource:
    """One served Organization, indexed the way the store indexes it."""
    return _ServedResource(
        resource_type="Organization",
        resource_id=uid.lower(),
        identity_system=f"{_IDENTIFIER_BASE}/org-unit",
        identity_value=uid,
        code_system=f"{_IDENTIFIER_BASE}/org-unit-code",
        code_value=uid,
        name=name,
    )


def _mock_organisation_units(entries: list[dict[str, Any]]) -> None:
    """Answer the oracle's organisation-unit read with the given wire objects."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(200, json={"version": "2.42.0"}))
    respx.get(f"{_BASE_URL}/api/organisationUnits").mock(
        return_value=httpx.Response(200, json={"organisationUnits": entries})
    )


@respx.mock
async def test_the_instance_judges_a_served_name_and_names_the_field_path() -> None:
    """The instance is the authority: a served name it disagrees with is a finding on `name`."""
    _mock_organisation_units([{"id": "OU1", "name": "Bo District", "code": "BO"}])
    async with open_client(_profile().profile) as client:
        outcome = await _judge_family(
            client, _ORGANISATION_UNIT_FAMILY, [_served_organisation_unit("OU1", "Bo")], _IDENTIFIER_BASE, 5
        )
    paths = {finding.field_path for finding in outcome.findings}
    assert "name" in paths
    assert "identifier[1].value" in paths
    assert grade_oracle([outcome]).outcome is DoctorOutcome.FAILED


@respx.mock
async def test_a_served_resource_naming_an_object_the_instance_lost_is_a_finding() -> None:
    """A resource whose DHIS2 object the instance no longer holds is broken, on `identifier[0].value`."""
    _mock_organisation_units([])
    async with open_client(_profile().profile) as client:
        outcome = await _judge_family(
            client, _ORGANISATION_UNIT_FAMILY, [_served_organisation_unit("OU1", "Bo")], _IDENTIFIER_BASE, 5
        )
    assert len(outcome.findings) == 1
    assert outcome.findings[0].field_path == "identifier[0].value"
    assert "does not hold" in outcome.findings[0].detail


@respx.mock
async def test_a_served_resource_the_instance_agrees_with_raises_nothing() -> None:
    """A resource that still derives from current instance state is what a passing oracle means."""
    _mock_organisation_units([{"id": "OU1", "name": "Bo", "code": "OU1"}])
    async with open_client(_profile().profile) as client:
        outcome = await _judge_family(
            client, _ORGANISATION_UNIT_FAMILY, [_served_organisation_unit("OU1", "Bo")], _IDENTIFIER_BASE, 5
        )
    assert outcome.findings == ()
    assert "1 resource(s) over 1 DHIS2 object(s), 1 resolved, 1 deep-compared" in outcome.summary
    assert grade_oracle([outcome]).outcome is DoctorOutcome.PASSED


def test_an_oracle_family_nothing_was_served_for_says_so() -> None:
    """A family the project publishes nothing of is stated rather than counted as agreement."""
    assert grade_oracle([_FamilyOutcome(summary="programs: nothing served")]).outcome is DoctorOutcome.PASSED


#: The four families by their label, so a failure names the family rather than an index.
_FAMILIES_BY_LABEL = {family.label: family for family in _ORACLE_FAMILIES}


def _served_member(family: _OracleFamily, uid: str, human_name: str, code: str) -> _ServedResource:
    """One served resource of the given family, carrying the human name in the element that family reads.

    `Organization` states its human name on `name` and both `Questionnaire` families and `CodeSystem`
    state theirs on `title`, which is the divergence a single-family test never exercises.
    """
    on_name = family.resource_type == "Organization"
    return _ServedResource(
        resource_type=family.resource_type,
        resource_id=uid.lower(),
        identity_system=f"{_IDENTIFIER_BASE}/{family.identifier_segment}",
        identity_value=uid,
        code_system=f"{_IDENTIFIER_BASE}/{family.identifier_segment}-code",
        code_value=code,
        name=human_name if on_name else None,
        title=None if on_name else human_name,
        concept_count=2 if family.child_key else 0,
    )


def _mock_family(family: _OracleFamily, entries: list[dict[str, Any]]) -> None:
    """Answer one family's own collection read with the given wire objects."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(200, json={"version": "2.42.0"}))
    respx.get(f"{_BASE_URL}{family.api_path}").mock(
        return_value=httpx.Response(200, json={family.collection_key: entries})
    )


def _instance_object(family: _OracleFamily, uid: str, human_name: str, code: str) -> dict[str, Any]:
    """One wire object as the family's own read returns it, with the children that family counts."""
    wire: dict[str, Any] = {"id": uid, "name": human_name, "code": code}
    if family.child_key:
        wire[family.child_key] = [{"id": f"{uid}-c1"}, {"id": f"{uid}-c2"}]
    return wire


@pytest.mark.parametrize("label", list(_FAMILIES_BY_LABEL))
@respx.mock
async def test_every_oracle_family_agrees_with_an_instance_it_still_derives_from(label: str) -> None:
    """Each of the four families reads its own endpoint, its own collection key, and its own name element."""
    family = _FAMILIES_BY_LABEL[label]
    _mock_family(family, [_instance_object(family, "Ob1", "Gender", "GENDER")])
    async with open_client(_profile().profile) as client:
        outcome = await _judge_family(
            client, family, [_served_member(family, "Ob1", "Gender", "GENDER")], _IDENTIFIER_BASE, 5
        )
    assert outcome.findings == ()
    assert f"{family.label}: 1 resource(s) over 1 DHIS2 object(s), 1 resolved, 1 deep-compared" in outcome.summary
    assert grade_oracle([outcome]).outcome is DoctorOutcome.PASSED


@pytest.mark.parametrize("label", list(_FAMILIES_BY_LABEL))
@respx.mock
async def test_every_oracle_family_reports_a_name_and_a_code_the_instance_disagrees_with(label: str) -> None:
    """The human name and the code are judged in every family, on the field path that family carries them."""
    family = _FAMILIES_BY_LABEL[label]
    _mock_family(family, [_instance_object(family, "Ob1", "Gender", "GENDER")])
    async with open_client(_profile().profile) as client:
        outcome = await _judge_family(
            client, family, [_served_member(family, "Ob1", "Sex", "SEX")], _IDENTIFIER_BASE, 5
        )
    paths = {finding.field_path for finding in outcome.findings}
    assert paths == {"name" if family.resource_type == "Organization" else "title", "identifier[1].value"}
    assert grade_oracle([outcome]).outcome is DoctorOutcome.FAILED


@pytest.mark.parametrize("label", list(_FAMILIES_BY_LABEL))
@respx.mock
async def test_every_oracle_family_reports_an_object_the_instance_no_longer_holds(label: str) -> None:
    """A served resource naming a UID the family's endpoint does not answer for is broken, in every family."""
    family = _FAMILIES_BY_LABEL[label]
    _mock_family(family, [])
    async with open_client(_profile().profile) as client:
        outcome = await _judge_family(
            client, family, [_served_member(family, "Ob1", "Gender", "GENDER")], _IDENTIFIER_BASE, 5
        )
    assert [finding.field_path for finding in outcome.findings] == ["identifier[0].value"]
    assert f"names DHIS2 {family.label[:-1]} Ob1" in outcome.findings[0].detail


@respx.mock
async def test_only_the_option_set_family_counts_the_children_it_published() -> None:
    """`child_key` is what makes a concept count judgeable, and option sets are the family that has one."""
    family = _FAMILIES_BY_LABEL["option sets"]
    _mock_family(family, [_instance_object(family, "Ob1", "Gender", "GENDER")])
    served = _served_member(family, "Ob1", "Gender", "GENDER").model_copy(update={"concept_count": 1})
    async with open_client(_profile().profile) as client:
        outcome = await _judge_family(client, family, [served], _IDENTIFIER_BASE, 5)
    assert [finding.field_path for finding in outcome.findings] == ["concept"]
    # A concept count that drifted is a warning: the guide is stale, not wrong about what it names.
    assert grade_oracle([outcome]).outcome is DoctorOutcome.WARNED


@respx.mock
async def test_the_two_questionnaire_families_are_separated_by_their_identifier_system() -> None:
    """Data sets and programs are both `Questionnaire`, so only the identifier system tells them apart."""
    data_sets = _FAMILIES_BY_LABEL["data sets"]
    programs = _FAMILIES_BY_LABEL["programs"]
    _mock_family(data_sets, [_instance_object(data_sets, "Ds1", "Child Health", "CH")])
    served = [
        _served_member(data_sets, "Ds1", "Child Health", "CH"),
        _served_member(programs, "Pr1", "Antenatal care", "ANC"),
    ]
    async with open_client(_profile().profile) as client:
        outcome = await _judge_family(client, data_sets, served, _IDENTIFIER_BASE, 5)
    # The program-identified Questionnaire was not judged here, so its absent object raised nothing.
    assert outcome.findings == ()
    assert "data sets: 1 resource(s) over 1 DHIS2 object(s)" in outcome.summary


def test_capture_grading_of_an_ungeneratable_form_only_degrades_the_phase() -> None:
    """A form the server cannot generate against is a note; only a refused 201 breaks the phase."""
    outcome = _CaptureOutcome(
        generated=False,
        accepted=False,
        findings=(
            DoctorFinding(
                phase=DoctorPhase.CAPTURE,
                severity="warning",
                subject="Questionnaire/DS1",
                detail="$generate answered 422",
            ),
        ),
    )
    assert grade_capture([outcome]).outcome is DoctorOutcome.WARNED


def test_the_json_payload_is_the_typed_report(tmp_path: Path) -> None:
    """`--json` emits the report itself, so a caller pipes stdout into jq without filtering."""
    payload = json.loads(_report(_phase(DoctorPhase.CONNECT, DoctorOutcome.PASSED, "ok")).model_dump_json())
    assert payload["phases"][0]["phase"] == "connect"
    assert payload["phases"][0]["outcome"] == "pass"
    assert payload["options"]["samples"] == 5
    del tmp_path
