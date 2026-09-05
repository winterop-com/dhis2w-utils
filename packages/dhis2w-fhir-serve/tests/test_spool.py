"""The response spool: durable writes, the lifecycle states, quarantine, sweeping, and id minting."""

from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path

import pytest
from dhis2w_fhir.service import ForwardImportIssue, ForwardImportOutcome, WithdrawalRecord
from dhis2w_fhir_serve.spool import (
    IMPORT_REPORT_SUFFIX,
    ORPHAN_TEMPORARY_FILE_AGE_SECONDS,
    ResponseLifecycle,
    ResponseSpool,
    StoredResponseEnvelope,
    UnreadableReceiptError,
    current_instant,
    new_response_id,
)

FHIR_ID_RE = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")


def make_envelope(
    response_id: str = "aaa",
    received_at: str = "2026-08-07T10:00:00Z",
    form_kind: str = "aggregate",
    questionnaire: str = "http://example.org/fhir/Questionnaire/d2-ds-anc-q",
    warnings: tuple[str, ...] = (),
) -> StoredResponseEnvelope:
    """Build a receipt whose response carries the stamped id."""
    return StoredResponseEnvelope(
        response_id=response_id,
        received_at=received_at,
        form_kind=form_kind,
        questionnaire=questionnaire,
        warnings=warnings,
        response={
            "resourceType": "QuestionnaireResponse",
            "id": response_id,
            "questionnaire": questionnaire,
            "status": "completed",
        },
    )


def drain(spool: ResponseSpool, response_id: str, lifecycle: ResponseLifecycle) -> Path:
    """Move one receipt into another state exactly as `d2w fhir forward` does - a rename, nothing else."""
    destination = spool.directory_for(lifecycle)
    destination.mkdir(parents=True, exist_ok=True)
    source = spool.directory_for(ResponseLifecycle.RECEIVED) / f"{response_id}.json"
    moved = destination / source.name
    source.rename(moved)
    return moved


def test_save_then_get_round_trips(tmp_path: Path) -> None:
    """A saved receipt reads back off disk unchanged, as received."""
    spool = ResponseSpool.at(tmp_path)
    envelope = make_envelope(warnings=("code XYZ not in the served terminology",))

    spool.save(envelope)

    found = spool.get("aaa")
    assert found is not None
    assert found.lifecycle is ResponseLifecycle.RECEIVED
    assert StoredResponseEnvelope(**found.model_dump(include=set(StoredResponseEnvelope.model_fields))) == envelope
    assert spool.get("missing") is None


def test_at_creates_the_receiving_directory(tmp_path: Path) -> None:
    """Pointing a spool at a project creates the directory a first capture lands in, and starts empty."""
    spool = ResponseSpool.at(tmp_path / "deep")

    assert spool.directory_for(ResponseLifecycle.RECEIVED).is_dir()
    assert spool.count() == 0


def test_save_writes_a_parseable_file_named_for_the_response(tmp_path: Path) -> None:
    """The mirror file is `<response_id>.json` under `received/`, with no temporary files left behind."""
    spool = ResponseSpool.at(tmp_path)

    spool.save(make_envelope(response_id="bbb"))

    directory = spool.directory_for(ResponseLifecycle.RECEIVED)
    written = directory / "bbb.json"
    assert written.is_file()
    assert sorted(path.name for path in directory.iterdir()) == ["bbb.json"]
    parsed = json.loads(written.read_text(encoding="utf-8"))
    assert parsed["response_id"] == "bbb"
    assert parsed["response"]["resourceType"] == "QuestionnaireResponse"
    assert "lifecycle" not in parsed
    assert written.read_text(encoding="utf-8").endswith("\n")


def test_a_second_spool_over_the_same_project_reads_the_same_receipts(tmp_path: Path) -> None:
    """The directory is the index, so a fresh spool sees everything the previous one wrote."""
    ResponseSpool.at(tmp_path).save(make_envelope(response_id="ccc"))

    rebuilt = ResponseSpool.at(tmp_path)

    assert rebuilt.count() == 1
    found = rebuilt.get("ccc")
    assert found is not None
    assert found.questionnaire == "http://example.org/fhir/Questionnaire/d2-ds-anc-q"


def test_a_forwarded_receipt_is_still_read_and_carries_its_state(tmp_path: Path) -> None:
    """A drain renames the file; the receipt keeps reading back, now as `forwarded`.

    This is the case a startup-loaded index gets wrong: `d2w fhir forward` runs beside a live
    server, and a spool that answered from memory would still be calling this one `received`.
    """
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="drained"))

    drain(spool, "drained", ResponseLifecycle.FORWARDED)

    found = spool.get("drained")
    assert found is not None
    assert found.lifecycle is ResponseLifecycle.FORWARDED
    assert spool.count() == 1


def test_counts_split_by_lifecycle(tmp_path: Path) -> None:
    """The per-state counts are the queue depth beside what became of everything else."""
    spool = ResponseSpool.at(tmp_path)
    for response_id in ("queued", "sent", "refused", "retracted"):
        spool.save(make_envelope(response_id=response_id))
    drain(spool, "sent", ResponseLifecycle.FORWARDED)
    drain(spool, "refused", ResponseLifecycle.REJECTED)
    drain(spool, "retracted", ResponseLifecycle.WITHDRAWN)

    counts = spool.count_by_lifecycle()

    assert counts == {
        ResponseLifecycle.RECEIVED: 1,
        ResponseLifecycle.FORWARDED: 1,
        ResponseLifecycle.REJECTED: 1,
        ResponseLifecycle.WITHDRAWN: 1,
    }


def test_search_covers_every_lifecycle_state_newest_first(tmp_path: Path) -> None:
    """Receipts come back in received order whichever directory they now sit in."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="middle", received_at="2026-08-07T11:00:00Z"))
    spool.save(make_envelope(response_id="oldest", received_at="2026-08-07T09:00:00Z"))
    spool.save(make_envelope(response_id="newest", received_at="2026-08-07T13:00:00Z"))
    drain(spool, "middle", ResponseLifecycle.FORWARDED)
    drain(spool, "oldest", ResponseLifecycle.REJECTED)

    found = spool.search()

    assert [receipt.response_id for receipt in found.receipts] == ["newest", "middle", "oldest"]


def test_search_narrows_to_one_lifecycle_state(tmp_path: Path) -> None:
    """A lifecycle filter answers the queue on its own, which is what a drain is measured by."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="queued"))
    spool.save(make_envelope(response_id="sent"))
    drain(spool, "sent", ResponseLifecycle.FORWARDED)

    queued = spool.search(lifecycles=(ResponseLifecycle.RECEIVED,))

    assert [receipt.response_id for receipt in queued.receipts] == ["queued"]


def test_search_filters_by_questionnaire(tmp_path: Path) -> None:
    """A questionnaire filter narrows to the form that was answered."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="anc", questionnaire="http://example.org/fhir/Questionnaire/anc"))
    spool.save(make_envelope(response_id="epi", questionnaire="http://example.org/fhir/Questionnaire/epi"))

    found = spool.search(questionnaire="http://example.org/fhir/Questionnaire/epi")

    assert [receipt.response_id for receipt in found.receipts] == ["epi"]


def test_search_filters_by_form_kind(tmp_path: Path) -> None:
    """A form-kind filter separates aggregate captures from event ones."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="agg", form_kind="aggregate"))
    spool.save(make_envelope(response_id="evt", form_kind="event"))

    assert [receipt.response_id for receipt in spool.search(form_kind="event").receipts] == ["evt"]


def test_search_filters_by_ids(tmp_path: Path) -> None:
    """An id filter ORs within itself and ANDs with the other filters."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="one", received_at="2026-08-07T09:00:00Z", form_kind="aggregate"))
    spool.save(make_envelope(response_id="two", received_at="2026-08-07T10:00:00Z", form_kind="event"))
    spool.save(make_envelope(response_id="three", received_at="2026-08-07T11:00:00Z", form_kind="event"))

    both = spool.search(ids=("one", "three"))
    narrowed = spool.search(form_kind="event", ids=("one", "three"))

    assert [receipt.response_id for receipt in both.receipts] == ["three", "one"]
    assert [receipt.response_id for receipt in narrowed.receipts] == ["three"]


def test_count(tmp_path: Path) -> None:
    """The count is the number of receipts held, and re-saving an id replaces rather than duplicates."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="ddd"))
    spool.save(make_envelope(response_id="eee"))
    spool.save(make_envelope(response_id="ddd", form_kind="event"))

    assert spool.count() == 2


def test_a_rejection_report_is_read_back_beside_its_receipt(tmp_path: Path) -> None:
    """The sidecar `<id>.report.json` the forwarder leaves is what a rejection is explained by."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="refused"))
    drain(spool, "refused", ResponseLifecycle.REJECTED)
    report = ForwardImportOutcome(
        status="ERROR",
        message="Import failed",
        ignored=1,
        issues=(ForwardImportIssue(error_code="E1120", subject="ImspTQPwCqd", message="Data element not found"),),
    )
    (spool.directory_for(ResponseLifecycle.REJECTED) / f"refused{IMPORT_REPORT_SUFFIX}").write_text(
        report.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )

    found = spool.import_report("refused", ResponseLifecycle.REJECTED)

    assert found is not None
    assert found.status == "ERROR"
    assert found.issues[0].error_code == "E1120"


def _withdrawal_record(event_uid: str = "EvTsupVis01") -> WithdrawalRecord:
    """The sidecar `d2w fhir withdraw` writes into `withdrawn/` when DHIS2 takes the delete."""
    return WithdrawalRecord(
        status="OK",
        deleted=1,
        event_uid=event_uid,
        withdrawn_at="2026-08-09T12:00:00Z",
        received_at="2026-08-07T10:00:00Z",
    )


def test_a_withdrawn_receipt_reads_back_in_the_fourth_state(tmp_path: Path) -> None:
    """`d2w fhir withdraw` renames the receipt into `withdrawn/`, and the facade reads it there."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="retracted"))
    drain(spool, "retracted", ResponseLifecycle.WITHDRAWN)

    found = spool.get("retracted")

    assert found is not None
    assert found.lifecycle is ResponseLifecycle.WITHDRAWN
    assert [receipt.response_id for receipt in spool.search().receipts] == ["retracted"]


def test_a_withdrawal_record_is_read_back_beside_its_receipt(tmp_path: Path) -> None:
    """The record says what DHIS2 answered the delete, and what the instance keeps afterwards."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="retracted"))
    drain(spool, "retracted", ResponseLifecycle.WITHDRAWN)
    (spool.directory_for(ResponseLifecycle.WITHDRAWN) / f"retracted{IMPORT_REPORT_SUFFIX}").write_text(
        _withdrawal_record().model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )

    found = spool.withdrawal_record("retracted")

    assert found is not None
    assert found.event_uid == "EvTsupVis01"
    assert found.withdrawn_at == "2026-08-09T12:00:00Z"
    assert "hidden copy" in found.note


def test_a_withdrawn_receipt_with_no_record_answers_none(tmp_path: Path) -> None:
    """A receipt filed under `withdrawn/` with no sidecar is still withdrawn; it just says nothing more."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="retracted"))
    drain(spool, "retracted", ResponseLifecycle.WITHDRAWN)

    assert spool.withdrawal_record("retracted") is None


def test_an_unreadable_withdrawal_record_does_not_fail_the_listing(tmp_path: Path) -> None:
    """A corrupt record is a lost diagnostic rather than a lost receipt, so the read answers absent."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="retracted"))
    drain(spool, "retracted", ResponseLifecycle.WITHDRAWN)
    (spool.directory_for(ResponseLifecycle.WITHDRAWN) / f"retracted{IMPORT_REPORT_SUFFIX}").write_text(
        "{not json", encoding="utf-8"
    )

    assert spool.withdrawal_record("retracted") is None
    assert [receipt.response_id for receipt in spool.search().receipts] == ["retracted"]


def test_a_forwarded_receipt_has_no_withdrawal_record(tmp_path: Path) -> None:
    """The sidecar is read out of `withdrawn/` alone, so a forwarded receipt's import report is not one."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="sent"))
    drain(spool, "sent", ResponseLifecycle.FORWARDED)
    (spool.directory_for(ResponseLifecycle.FORWARDED) / f"sent{IMPORT_REPORT_SUFFIX}").write_text(
        ForwardImportOutcome(status="OK", created=1).model_dump_json(), encoding="utf-8"
    )

    assert spool.withdrawal_record("sent") is None
    assert spool.import_report("sent", ResponseLifecycle.FORWARDED) is not None


def test_a_report_file_is_not_mistaken_for_a_receipt(tmp_path: Path) -> None:
    """`<id>.report.json` sits in the same directory as the receipt and must never be listed as one."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="refused"))
    drain(spool, "refused", ResponseLifecycle.REJECTED)
    (spool.directory_for(ResponseLifecycle.REJECTED) / f"refused{IMPORT_REPORT_SUFFIX}").write_text(
        ForwardImportOutcome(status="ERROR").model_dump_json(), encoding="utf-8"
    )

    assert [receipt.response_id for receipt in spool.search().receipts] == ["refused"]


def test_a_receipt_with_no_report_answers_none(tmp_path: Path) -> None:
    """A rejection whose report is missing is still a rejection; it just says nothing about why."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="refused"))
    drain(spool, "refused", ResponseLifecycle.REJECTED)

    assert spool.import_report("refused", ResponseLifecycle.REJECTED) is None


def test_an_unreadable_report_does_not_fail_the_listing(tmp_path: Path) -> None:
    """A corrupt diagnostic is not a lost receipt, so the report reads as absent rather than raising."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="refused"))
    drain(spool, "refused", ResponseLifecycle.REJECTED)
    (spool.directory_for(ResponseLifecycle.REJECTED) / f"refused{IMPORT_REPORT_SUFFIX}").write_text(
        "{not json", encoding="utf-8"
    )

    assert spool.import_report("refused", ResponseLifecycle.REJECTED) is None
    assert [receipt.response_id for receipt in spool.search().receipts] == ["refused"]


def test_unparseable_json_is_quarantined_and_named(tmp_path: Path) -> None:
    """A corrupt receipt file is moved aside and named, and every receipt around it still reads."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="whole"))
    (spool.directory_for(ResponseLifecycle.RECEIVED) / "broken.json").write_text("{not json", encoding="utf-8")

    found = spool.search()

    assert [receipt.response_id for receipt in found.receipts] == ["whole"]
    assert [entry.file_name for entry in found.quarantined] == ["broken.json"]
    assert "not readable as JSON" in found.quarantined[0].reason
    assert (spool.malformed_directory / "broken.json").is_file()
    assert not (spool.directory_for(ResponseLifecycle.RECEIVED) / "broken.json").exists()


def test_a_file_that_is_not_an_envelope_is_quarantined_and_named(tmp_path: Path) -> None:
    """Valid JSON that is not a receipt is moved aside with the reason it is not one."""
    spool = ResponseSpool.at(tmp_path)
    (spool.directory_for(ResponseLifecycle.RECEIVED) / "stray.json").write_text(
        '{"resourceType": "QuestionnaireResponse"}', encoding="utf-8"
    )

    found = spool.search()

    assert found.receipts == ()
    assert [entry.file_name for entry in found.quarantined] == ["stray.json"]
    assert "not a stored response envelope" in found.quarantined[0].reason


def test_a_quarantined_file_keeps_its_reason_for_every_later_listing(tmp_path: Path) -> None:
    """The reason is written beside the file as it moves, so a listing an hour later still states it."""
    spool = ResponseSpool.at(tmp_path)
    (spool.directory_for(ResponseLifecycle.RECEIVED) / "broken.json").write_text("{not json", encoding="utf-8")
    spool.search()

    quarantined = ResponseSpool.at(tmp_path).malformed()

    assert [entry.file_name for entry in quarantined] == ["broken.json"]
    assert "not readable as JSON" in quarantined[0].reason


def test_an_unreadable_spool_directory_is_raised(tmp_path: Path) -> None:
    """One bad file is quarantined; a directory this process cannot read fails the whole read."""
    spool = ResponseSpool.at(tmp_path)
    received = spool.directory_for(ResponseLifecycle.RECEIVED)
    received.chmod(0o000)
    try:
        with pytest.raises(UnreadableReceiptError, match="cannot be read"):
            spool.search()
    finally:
        received.chmod(0o755)


def test_an_orphan_temporary_file_is_swept_once_it_is_old_enough(tmp_path: Path) -> None:
    """An abandoned write is deleted; one young enough to still be in flight is left exactly alone."""
    spool = ResponseSpool.at(tmp_path)
    received = spool.directory_for(ResponseLifecycle.RECEIVED)
    abandoned = received / ".abandoned.json.tmp"
    abandoned.write_text("half a rec", encoding="utf-8")
    in_flight = received / ".in-flight.json.tmp"
    in_flight.write_text("half a rec", encoding="utf-8")
    stale = time.time() - 2 * ORPHAN_TEMPORARY_FILE_AGE_SECONDS
    os.utime(abandoned, (stale, stale))

    swept = spool.sweep_orphan_temporary_files()

    assert swept == (".abandoned.json.tmp",)
    assert not abandoned.exists()
    assert in_flight.is_file()


def test_saving_a_receipt_flushes_it_and_its_directory_entry_to_the_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A capture is durable before it is acknowledged: the file is fsynced, then the directory naming it."""
    synced: list[str] = []
    real_fsync = os.fsync

    def _record(descriptor: int) -> None:
        synced.append("directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", _record)
    spool = ResponseSpool.at(tmp_path)

    spool.save(make_envelope(response_id="durable"))

    assert synced == ["file", "directory"]


def test_new_response_id_is_a_fhir_safe_id() -> None:
    """Minted ids are 32 hex characters, unique, and legal as a FHIR id and a file name."""
    first = new_response_id()
    second = new_response_id()

    assert len(first) == 32
    assert FHIR_ID_RE.match(first)
    assert first != second


def test_current_instant_is_a_fhir_instant() -> None:
    """The receipt timestamp is UTC with a Z suffix and millisecond precision, which is what orders a drain."""
    instant = current_instant()

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", instant)
