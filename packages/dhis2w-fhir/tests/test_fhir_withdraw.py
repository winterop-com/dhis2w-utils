"""`d2w fhir withdraw` - the fourth spool state, and the one dial that has to be on before it works.

Two slices meet in this file. `[forward] corrections` and `[forward] withdrawals` are the deployment's
posture towards a submission that names what it amends or retracts, and they default to off; a
withdrawal is what the second of them gates. The whole path needs no guide and no translation - an
event's DHIS2 UID is derived from the receipt's own logical id - so the fixture here is a receipt
envelope in `forwarded/` and a mocked `/api/tracker`, and nothing else a drain would read.

The spool doctrine is what most of these assert: the receipt file is never rewritten, the import
report that recorded what it landed stays in `forwarded/`, and the record of the delete lands beside
the receipt in `withdrawn/` before the receipt moves in after it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import resolve
from dhis2w_fhir import load_project, service
from dhis2w_fhir.config import WithdrawalPosture
from dhis2w_fhir.conversion import receipt_event_uid
from dhis2w_fhir.spool import (
    FORWARDED_RESPONSES_RELATIVE_PATH,
    IMPORT_REPORT_SUFFIX,
    RECEIVED_RESPONSES_RELATIVE_PATH,
    WITHDRAWN_RESPONSES_RELATIVE_PATH,
    SpoolReadError,
)
from typer.testing import CliRunner

_runner = CliRunner()

_BASE_URL = "https://dhis2.example"
_QUESTIONNAIRE = "http://example.org/fhir/Questionnaire/d2-pr-case-surveillance"
_RECEIVED_AT = "2026-08-08T09:00:00Z"
_EVENT_RECEIPT = "e1f0aa11223344556677889900aabbcc"

_IG_TABLE = """
[ig]
id = "dhis2.fhir.withdraw"
canonical = "http://example.org/fhir"
name = "Withdraw"
title = "Withdraw"
publisher = "Winterop"
"""


def _write_probe_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point profile resolution at a `probe` profile whose base url is the mocked instance."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        f'default = "probe"\n\n[profiles.probe]\nbase_url = "{_BASE_URL}"\nauth = "pat"\ntoken = "d2p_test"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("COLUMNS", "300")


def _write_receipt(directory: Path, response_id: str, *, form_kind: str = "event") -> Path:
    """Write the receipt envelope `d2w fhir serve` leaves behind for one accepted submission."""
    directory.mkdir(parents=True, exist_ok=True)
    envelope = {
        "response_id": response_id,
        "received_at": _RECEIVED_AT,
        "form_kind": form_kind,
        "questionnaire": _QUESTIONNAIRE,
        "warnings": [],
        "response": {"resourceType": "QuestionnaireResponse", "id": response_id, "status": "completed"},
    }
    path = directory / f"{response_id}.json"
    path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return path


def _write_import_report(directory: Path, response_id: str) -> Path:
    """Write the sidecar a drain left when DHIS2 took this receipt's event."""
    path = directory / f"{response_id}{IMPORT_REPORT_SUFFIX}"
    path.write_text(
        json.dumps({"status": "OK", "message": "Import was successful.", "created": 1, "target_kind": "event"}),
        encoding="utf-8",
    )
    return path


def _write_project(root: Path, *, forward_table: str = "") -> None:
    """A project whose `[forward]` table each test writes for itself, with no compiled guide at all."""
    table = f"\n[forward]\n{forward_table}\n" if forward_table else ""
    (root / "fhir.toml").write_text(f"{_IG_TABLE}{table}", encoding="utf-8")


@pytest.fixture
def withdraw_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project holding one forwarded event receipt, its import report, and a retracting posture."""
    _write_probe_profile(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    _write_project(root, forward_table='withdrawals = "retract"')
    forwarded = root / FORWARDED_RESPONSES_RELATIVE_PATH
    _write_receipt(forwarded, _EVENT_RECEIPT)
    _write_import_report(forwarded, _EVENT_RECEIPT)
    monkeypatch.chdir(root)
    return root


def _deleted_tracker() -> httpx.Response:
    """What `/api/tracker` answers when it took the delete: one object gone, no error reported."""
    return httpx.Response(
        200,
        json={
            "httpStatus": "OK",
            "httpStatusCode": 200,
            "status": "OK",
            "message": "Import was successful.",
            "response": {
                "status": "OK",
                "stats": {"created": 0, "updated": 0, "deleted": 1, "ignored": 0, "total": 1},
                "validationReport": {"errorReports": [], "warningReports": []},
            },
        },
    )


def _already_deleted_tracker(event_uid: str) -> httpx.Response:
    """`E1082`, verbatim in shape: the UID is burned, and every strategy answers the same refusal."""
    return httpx.Response(
        409,
        json={
            "status": "ERROR",
            "stats": {"created": 0, "updated": 0, "deleted": 0, "ignored": 1, "total": 1},
            "validationReport": {
                "errorReports": [
                    {
                        "uid": event_uid,
                        "trackerType": "EVENT",
                        "errorCode": "E1082",
                        "message": f"Event: `{event_uid}` is already deleted and cannot be modified.",
                    }
                ],
                "warningReports": [],
            },
        },
    )


def _mock_instance(tracker_response: httpx.Response | None = None) -> dict[str, respx.Route]:
    """Mock what a withdrawal touches, which is the version probe and one tracker post - no guide read."""
    respx.get(f"{_BASE_URL}/api/system/info").mock(return_value=httpx.Response(200, json={"version": "2.42.6"}))
    tracker = respx.post(f"{_BASE_URL}/api/tracker").mock(return_value=tracker_response or _deleted_tracker())
    return {"tracker": tracker}


async def _withdraw(root: Path, response_ids: list[str], **keyword_arguments: Any) -> service.WithdrawReport:
    """One withdrawal run against the fixture project with the resolved probe profile."""
    return await service.withdraw_responses(
        resolve(None).profile, load_project(root), response_ids, **keyword_arguments
    )


# --- the dial ---------------------------------------------------------------------------------


async def test_a_project_that_states_no_posture_withdraws_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Off is the default, and the refusal names the key rather than the command that hit it."""
    _write_probe_profile(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    _write_project(root)
    _write_receipt(root / FORWARDED_RESPONSES_RELATIVE_PATH, _EVENT_RECEIPT)
    monkeypatch.chdir(root)

    with pytest.raises(service.WithdrawalNotEnabledError) as refusal:
        await _withdraw(root, [_EVENT_RECEIPT])

    assert "`[forward] withdrawals` is `off`" in str(refusal.value)
    assert 'withdrawals = "retract"' in str(refusal.value)


@respx.mock
async def test_a_stated_posture_outranks_the_table_for_one_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A flag is one run's decision and the table is the project's, and the run's wins - the sibling order."""
    _write_probe_profile(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    _write_project(root, forward_table='withdrawals = "off"')
    _write_receipt(root / FORWARDED_RESPONSES_RELATIVE_PATH, _EVENT_RECEIPT)
    _mock_instance()
    monkeypatch.chdir(root)

    report = await _withdraw(root, [_EVENT_RECEIPT], withdrawals=WithdrawalPosture.RETRACT)

    assert report.withdrawal_posture is WithdrawalPosture.RETRACT
    assert [receipt.kind for receipt in report.receipts] == [service.WithdrawalKind.WOULD_RETRACT]


@respx.mock
async def test_a_retracting_project_needs_no_flag(withdraw_project: Path) -> None:
    """The table is the project's posture, so a deployment that retracts states it once."""
    _mock_instance()

    report = await _withdraw(withdraw_project, [_EVENT_RECEIPT])

    assert report.withdrawal_posture is WithdrawalPosture.RETRACT


# --- what goes on the wire --------------------------------------------------------------------


@respx.mock
async def test_the_delete_names_the_event_the_receipt_id_derives(withdraw_project: Path) -> None:
    """The identity is recomputed off the receipt's own id, never looked up - no guide, no metadata read."""
    routes = _mock_instance()

    await _withdraw(withdraw_project, [_EVENT_RECEIPT], import_responses=True)

    body = json.loads(routes["tracker"].calls.last.request.content)
    assert body == {"events": [{"event": receipt_event_uid(_EVENT_RECEIPT)}]}


@respx.mock
async def test_a_dry_run_validates_the_delete_and_moves_nothing(withdraw_project: Path) -> None:
    """A terminal act gets a rehearsal: the real endpoint answers, and nothing is written or moved."""
    routes = _mock_instance()

    report = await _withdraw(withdraw_project, [_EVENT_RECEIPT])

    assert dict(routes["tracker"].calls.last.request.url.params) == {
        "importStrategy": "DELETE",
        "async": "false",
        "importMode": "VALIDATE",
    }
    assert report.dry_run is True
    assert report.receipts[0].kind is service.WithdrawalKind.WOULD_RETRACT
    assert report.receipts[0].spool_path is None
    assert (withdraw_project / FORWARDED_RESPONSES_RELATIVE_PATH / f"{_EVENT_RECEIPT}.json").is_file()
    assert not (withdraw_project / WITHDRAWN_RESPONSES_RELATIVE_PATH).exists()


@respx.mock
async def test_an_import_run_drops_the_validate_only_parameter(withdraw_project: Path) -> None:
    """`--import` is the same post with the validate-only dial off, and nothing else added."""
    routes = _mock_instance()

    await _withdraw(withdraw_project, [_EVENT_RECEIPT], import_responses=True)

    assert dict(routes["tracker"].calls.last.request.url.params) == {
        "importStrategy": "DELETE",
        "async": "false",
    }


# --- the fourth state -------------------------------------------------------------------------


@respx.mock
async def test_the_receipt_moves_to_withdrawn_with_the_record_of_the_delete_beside_it(
    withdraw_project: Path,
) -> None:
    """The fourth state, and the sidecar that says what remains in the instance rather than "deleted"."""
    _mock_instance()
    before = (withdraw_project / FORWARDED_RESPONSES_RELATIVE_PATH / f"{_EVENT_RECEIPT}.json").read_bytes()

    report = await _withdraw(withdraw_project, [_EVENT_RECEIPT], import_responses=True)

    withdrawn = withdraw_project / WITHDRAWN_RESPONSES_RELATIVE_PATH
    assert report.receipts[0].kind is service.WithdrawalKind.RETRACTED
    assert report.receipts[0].spool_path == f"{WITHDRAWN_RESPONSES_RELATIVE_PATH}/{_EVENT_RECEIPT}.json"
    assert not (withdraw_project / FORWARDED_RESPONSES_RELATIVE_PATH / f"{_EVENT_RECEIPT}.json").exists()
    assert (withdrawn / f"{_EVENT_RECEIPT}.json").read_bytes() == before
    record = service.WithdrawalRecord.model_validate_json(
        (withdrawn / f"{_EVENT_RECEIPT}{IMPORT_REPORT_SUFFIX}").read_text(encoding="utf-8")
    )
    assert record.event_uid == receipt_event_uid(_EVENT_RECEIPT)
    assert record.deleted == 1
    assert record.received_at == _RECEIVED_AT
    assert "keeps a hidden copy" in record.note
    assert "no longer appears in reports" in record.note


@respx.mock
async def test_the_import_report_of_the_forward_stays_where_it_recorded_the_import(withdraw_project: Path) -> None:
    """Two answers to two questions, and neither is rewritten - what it landed, and what letting go did."""
    _mock_instance()
    forwarded = withdraw_project / FORWARDED_RESPONSES_RELATIVE_PATH
    before = (forwarded / f"{_EVENT_RECEIPT}{IMPORT_REPORT_SUFFIX}").read_bytes()

    await _withdraw(withdraw_project, [_EVENT_RECEIPT], import_responses=True)

    assert (forwarded / f"{_EVENT_RECEIPT}{IMPORT_REPORT_SUFFIX}").read_bytes() == before


@respx.mock
async def test_the_spool_listing_counts_the_withdrawn_receipt_and_reads_its_record(withdraw_project: Path) -> None:
    """A withdrawn receipt is a row a listing states, off the one sidecar that is not an import report."""
    _mock_instance()
    await _withdraw(withdraw_project, [_EVENT_RECEIPT], import_responses=True)

    state = service.read_spool_state(load_project(withdraw_project))

    assert state.counts.withdrawn == 1
    assert state.counts.forwarded == 0
    assert state.counts.total == 1
    row = next(row for row in state.receipts if row.response_id == _EVENT_RECEIPT)
    assert row.state.value == "withdrawn"
    assert row.reason is not None
    assert receipt_event_uid(_EVENT_RECEIPT) in row.reason
    assert "no longer appears in reports" in row.reason


# --- refusals ---------------------------------------------------------------------------------


@respx.mock
async def test_dhis2_refusing_the_delete_leaves_the_receipt_where_it_landed(withdraw_project: Path) -> None:
    """`E1082` is DHIS2 saying the UID is already burned, and the receipt's own record is still true."""
    _mock_instance(_already_deleted_tracker(receipt_event_uid(_EVENT_RECEIPT)))

    report = await _withdraw(withdraw_project, [_EVENT_RECEIPT], import_responses=True)

    assert [receipt.kind for receipt in report.receipts] == [service.WithdrawalKind.REFUSED]
    assert report.refused[0].outcome.issues[0].error_code == "E1082"
    assert (withdraw_project / FORWARDED_RESPONSES_RELATIVE_PATH / f"{_EVENT_RECEIPT}.json").is_file()
    assert not (withdraw_project / WITHDRAWN_RESPONSES_RELATIVE_PATH).exists()


async def test_a_receipt_that_never_landed_is_refused_by_name(withdraw_project: Path) -> None:
    """Only what reached DHIS2 can be taken back, and a queued receipt is refused before anything posts."""
    _write_receipt(withdraw_project / RECEIVED_RESPONSES_RELATIVE_PATH, "queued-1")

    with pytest.raises(SpoolReadError) as refusal:
        await _withdraw(withdraw_project, ["queued-1"], import_responses=True)

    assert "`queued-1` is not a forwarded receipt" in str(refusal.value)


@respx.mock
async def test_a_receipt_that_landed_something_other_than_an_event_is_refused_before_anything_posts(
    withdraw_project: Path,
) -> None:
    """The aggregate and registration legs each need a guard this one does not, so neither is guessed at."""
    routes = _mock_instance()
    _write_receipt(withdraw_project / FORWARDED_RESPONSES_RELATIVE_PATH, "aggregate-1", form_kind="aggregate")

    with pytest.raises(service.WithdrawalUnsupportedError) as refusal:
        await _withdraw(withdraw_project, [_EVENT_RECEIPT, "aggregate-1"], import_responses=True)

    assert "`aggregate-1` (aggregate)" in str(refusal.value)
    assert routes["tracker"].call_count == 0
    assert (withdraw_project / FORWARDED_RESPONSES_RELATIVE_PATH / f"{_EVENT_RECEIPT}.json").is_file()


# --- the command ------------------------------------------------------------------------------


@respx.mock
def test_the_command_refuses_when_the_project_states_no_posture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate is the first thing the command reaches, so a project that withdraws nothing posts nothing."""
    _write_probe_profile(tmp_path, monkeypatch)
    _write_project(tmp_path)
    _write_receipt(tmp_path / FORWARDED_RESPONSES_RELATIVE_PATH, _EVENT_RECEIPT)
    routes = _mock_instance()
    monkeypatch.chdir(tmp_path)

    result = _runner.invoke(build_app(), ["fhir", "withdraw", _EVENT_RECEIPT])

    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, service.WithdrawalNotEnabledError)
    assert "[forward] withdrawals" in str(result.exception)
    assert routes["tracker"].call_count == 0


@respx.mock
def test_the_command_answers_json_on_stdout_and_names_what_remains(
    withdraw_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `--json` payload is stdout alone, and it carries the whole report the terminal narrated."""
    _mock_instance()
    monkeypatch.chdir(withdraw_project)

    result = _runner.invoke(build_app(), ["--json", "fhir", "withdraw", "--import", _EVENT_RECEIPT])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is False
    assert payload["withdrawal_posture"] == "retract"
    assert payload["receipts"][0]["event_uid"] == receipt_event_uid(_EVENT_RECEIPT)
    assert payload["receipts"][0]["kind"] == "retracted"


@respx.mock
def test_the_command_exits_one_when_dhis2_would_not_delete(
    withdraw_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal is a run that did not do what it was asked, so it exits 1 rather than reporting quietly."""
    _mock_instance(_already_deleted_tracker(receipt_event_uid(_EVENT_RECEIPT)))
    monkeypatch.chdir(withdraw_project)

    result = _runner.invoke(build_app(), ["fhir", "withdraw", "--import", _EVENT_RECEIPT])

    assert result.exit_code == 1, result.output
    assert "E1082" in result.output
