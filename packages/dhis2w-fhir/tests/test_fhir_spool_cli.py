"""CliRunner tests for `d2w fhir spool` and `d2w fhir requeue` - the two operator verbs over the queue.

Nothing is mocked here and no profile is configured, which is the point: both commands are directory
work, and an operator asking what is queued or putting a refused receipt back has to be able to do it
while the DHIS2 instance is down - which is exactly when they will.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from dhis2w_cli.main import build_app
from dhis2w_fhir.service import OVERWRITE_REFUSAL_CATEGORY, ForwardImportRecord
from dhis2w_fhir.spool import (
    IMPORT_REPORT_SUFFIX,
    MALFORMED_RESPONSES_RELATIVE_PATH,
    RECEIVED_RESPONSES_RELATIVE_PATH,
    REFUSAL_RECORD_SUFFIX,
    REJECTED_RESPONSES_RELATIVE_PATH,
    ForwardRefusalRecord,
    RefusalReason,
)
from typer.testing import CliRunner

_runner = CliRunner()

_FHIR_TOML = """
[ig]
id = "dhis2.fhir.test"
canonical = "http://example.org/fhir"
name = "Dhis2FhirTest"
title = "DHIS2 FHIR Test IG"
publisher = "Test Organisation"
"""

_QUESTIONNAIRE = "http://example.org/fhir/Questionnaire/d2-ds-child-health"


def _write_receipt(directory: Path, response_id: str, received_at: str = "2026-08-08T09:00:00Z") -> None:
    """Write the receipt envelope `d2w fhir serve` leaves behind for one accepted submission."""
    directory.mkdir(parents=True, exist_ok=True)
    envelope = {
        "response_id": response_id,
        "received_at": received_at,
        "form_kind": "aggregate",
        "questionnaire": _QUESTIONNAIRE,
        "warnings": [],
        "response": {"resourceType": "QuestionnaireResponse", "id": response_id, "status": "completed"},
    }
    (directory / f"{response_id}.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")


@pytest.fixture
def spooled_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project holding one queued receipt, one DHIS2 refused, and one file that is not a receipt.

    No profiles.toml anywhere: a command that opened a client would fail here, which is the assertion
    every test in this module is making without stating it.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("COLUMNS", "300")
    (tmp_path / "fhir.toml").write_text(_FHIR_TOML, encoding="utf-8")
    _write_receipt(tmp_path / RECEIVED_RESPONSES_RELATIVE_PATH, "queued-1")
    rejected = tmp_path / REJECTED_RESPONSES_RELATIVE_PATH
    _write_receipt(rejected, "refused-1", received_at="2026-08-08T10:00:00Z")
    record = ForwardImportRecord(status="ERROR", message="Import failed")
    (rejected / f"refused-1{IMPORT_REPORT_SUFFIX}").write_text(
        record.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )
    (tmp_path / RECEIVED_RESPONSES_RELATIVE_PATH / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_spool_listing_counts_each_state(spooled_project: Path) -> None:
    """The three states and the holding pen, in the words an operator reads rather than directory names."""
    result = _runner.invoke(build_app(), ["fhir", "spool"])

    assert result.exit_code == 0, result.output
    assert "not yet sent to DHIS2" in result.output
    assert "accepted by DHIS2" in result.output
    assert "refused by DHIS2" in result.output
    assert "unreadable files" in result.output


def test_the_spool_listing_names_every_receipt_under_details(spooled_project: Path) -> None:
    """`--details` is the row-per-receipt view, and a refused row carries the reason off its report."""
    result = _runner.invoke(build_app(), ["fhir", "spool", "--details"])

    assert result.exit_code == 0, result.output
    assert "queued-1" in result.output
    assert "refused-1" in result.output
    assert "Import failed" in result.output
    assert "broken.json" in result.output


def _write_refusal_record(project_root: Path, response_id: str) -> None:
    """The marker a committing drain leaves beside a receipt it refused to translate."""
    record = ForwardRefusalRecord(
        refused_at="2026-08-17T12:00:00Z",
        attempt_count=3,
        reasons=(RefusalReason(category="no-form-type", reason="the form declares no kind"),),
    )
    destination = project_root / RECEIVED_RESPONSES_RELATIVE_PATH / f"{response_id}{REFUSAL_RECORD_SUFFIX}"
    destination.write_text(record.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")


def test_the_spool_listing_states_a_translator_refused_receipt(spooled_project: Path) -> None:
    """A refused-but-queued receipt no longer reads like one no drain has touched."""
    _write_refusal_record(spooled_project, "queued-1")

    result = _runner.invoke(build_app(), ["fhir", "spool", "--details"])

    assert result.exit_code == 0, result.output
    assert "refused by a drain, still queued" in result.output
    assert "the form declares no kind" in result.output
    assert "3 drains" in result.output
    assert "queued receipt(s) were refused on the last run that posted" in result.output


def test_the_spool_listing_states_an_overwrite_refused_receipt(spooled_project: Path) -> None:
    """The listing reads the same sidecar whichever refusal filled it, so both refusals are one row shape."""
    record = ForwardRefusalRecord(
        refused_at="2026-08-17T12:00:00Z",
        reasons=(
            RefusalReason(
                category=OVERWRITE_REFUSAL_CATEGORY,
                element="De2aaaaaaaa",
                reason="De2aaaaaaaa / 202607 / ImspTQPwCqd (sent by 0c81a28f, received 2026-08-08T09:00:00Z)",
            ),
        ),
    )
    destination = spooled_project / RECEIVED_RESPONSES_RELATIVE_PATH / f"queued-1{REFUSAL_RECORD_SUFFIX}"
    destination.write_text(record.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")

    result = _runner.invoke(build_app(), ["fhir", "spool", "--details"])

    assert result.exit_code == 0, result.output
    assert "refused by a drain, still queued" in result.output
    assert "sent by 0c81a28f" in result.output
    assert "1 drain," in result.output


def test_the_spool_listing_answers_json_on_stdout(spooled_project: Path) -> None:
    """The `--json` payload is stdout alone, so a caller pipes it into `jq` without filtering."""
    result = _runner.invoke(build_app(), ["--json", "fhir", "spool"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["counts"] == {
        "received": 1,
        "forwarded": 0,
        "rejected": 1,
        "withdrawn": 0,
        "malformed": 1,
        "refused_in_queue": 0,
    }
    assert [entry["file_name"] for entry in payload["quarantined"]] == ["broken.json"]


def test_the_unreadable_file_is_moved_to_the_holding_pen_by_the_listing(spooled_project: Path) -> None:
    """Reading the spool is what finds a file that is no longer a receipt, so reading is what files it."""
    _runner.invoke(build_app(), ["fhir", "spool"])

    assert (spooled_project / MALFORMED_RESPONSES_RELATIVE_PATH / "broken.json").is_file()
    assert not (spooled_project / RECEIVED_RESPONSES_RELATIVE_PATH / "broken.json").exists()


def test_requeue_moves_one_named_receipt_back_into_the_queue(spooled_project: Path) -> None:
    """The one reverse move the spool has, and it names what it moved."""
    result = _runner.invoke(build_app(), ["fhir", "requeue", "refused-1"])

    assert result.exit_code == 0, result.output
    assert "refused-1" in result.output
    assert (spooled_project / RECEIVED_RESPONSES_RELATIVE_PATH / "refused-1.json").is_file()
    assert not (spooled_project / REJECTED_RESPONSES_RELATIVE_PATH / "refused-1.json").exists()


def test_requeue_leaves_the_import_report_behind_as_history(spooled_project: Path) -> None:
    """What DHIS2 answered about that payload is still true of that post, so the report stays where it is."""
    _runner.invoke(build_app(), ["fhir", "requeue", "refused-1"])

    assert (spooled_project / REJECTED_RESPONSES_RELATIVE_PATH / f"refused-1{IMPORT_REPORT_SUFFIX}").is_file()


def test_requeue_all_rejected_moves_everything_dhis2_refused(spooled_project: Path) -> None:
    """The usual case is "the instance is fixed, try all of them again"."""
    result = _runner.invoke(build_app(), ["fhir", "requeue", "--all-rejected"])

    assert result.exit_code == 0, result.output
    assert (spooled_project / RECEIVED_RESPONSES_RELATIVE_PATH / "refused-1.json").is_file()


def _through_the_funnel(
    arguments: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> str:
    """Run one command end to end through `run_app`, and answer with what stderr said."""
    from dhis2w_core.cli_errors import run_app

    monkeypatch.setattr(sys, "argv", ["d2w", *arguments])
    with pytest.raises(SystemExit) as exit_info:
        run_app(build_app())
    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err + captured.out
    return captured.err


def test_requeue_refuses_an_id_that_is_not_rejected(
    spooled_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A command reporting success for a receipt it never found would be worse than a clean refusal."""
    stderr = _through_the_funnel(["fhir", "requeue", "queued-1"], monkeypatch, capsys)

    assert "queued-1" in stderr
    # The directory as it is on this machine, since a project that moved its spool is exactly the
    # one where a relative name would send the operator to a directory that holds nothing.
    assert str(spooled_project / REJECTED_RESPONSES_RELATIVE_PATH) in stderr
    assert (spooled_project / RECEIVED_RESPONSES_RELATIVE_PATH / "queued-1.json").is_file()


def test_requeue_naming_nothing_at_all_says_what_it_needs(
    spooled_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bare `requeue` is ambiguous between one receipt and all of them, so it asks rather than guesses."""
    stderr = _through_the_funnel(["fhir", "requeue"], monkeypatch, capsys)

    assert "--all-rejected" in stderr


def _write_attributed_receipt(directory: Path, response_id: str, submitted_by: str) -> None:
    """One receipt the facade captured under `[serve] auth = "dhis2"`, stamped with who submitted it."""
    directory.mkdir(parents=True, exist_ok=True)
    envelope = {
        "response_id": response_id,
        "received_at": "2026-08-08T11:00:00Z",
        "form_kind": "aggregate",
        "questionnaire": _QUESTIONNAIRE,
        "submitted_by": submitted_by,
        "warnings": [],
        "response": {"resourceType": "QuestionnaireResponse", "id": response_id, "status": "completed"},
    }
    (directory / f"{response_id}.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")


def test_the_listing_names_who_captured_a_receipt_when_one_names_anybody(spooled_project: Path) -> None:
    """A DHIS2-posture facade records the submitter, and the listing is where an operator reads it back."""
    _write_attributed_receipt(spooled_project / RECEIVED_RESPONSES_RELATIVE_PATH, "attributed-1", "clerk")

    result = _runner.invoke(build_app(), ["fhir", "spool", str(spooled_project), "--details"])

    assert result.exit_code == 0, result.output
    assert "Captured by" in result.output
    assert "clerk" in result.output


def test_the_listing_leaves_the_column_out_where_no_receipt_names_anybody(spooled_project: Path) -> None:
    """Every receipt a no-authentication facade wrote carries none, and a column of blanks says nothing."""
    result = _runner.invoke(build_app(), ["fhir", "spool", str(spooled_project), "--details"])

    assert result.exit_code == 0, result.output
    assert "Captured by" not in result.output
