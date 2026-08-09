"""The response spool: atomic writes, the three lifecycle states, per-call directory reads, and id minting."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from dhis2w_fhir.service import ForwardImportIssue, ForwardImportOutcome
from dhis2w_fhir_serve.spool import (
    REJECTION_REPORT_SUFFIX,
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
    for response_id in ("queued", "sent", "refused"):
        spool.save(make_envelope(response_id=response_id))
    drain(spool, "sent", ResponseLifecycle.FORWARDED)
    drain(spool, "refused", ResponseLifecycle.REJECTED)

    counts = spool.count_by_lifecycle()

    assert counts == {
        ResponseLifecycle.RECEIVED: 1,
        ResponseLifecycle.FORWARDED: 1,
        ResponseLifecycle.REJECTED: 1,
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

    assert [receipt.response_id for receipt in found] == ["newest", "middle", "oldest"]


def test_search_narrows_to_one_lifecycle_state(tmp_path: Path) -> None:
    """A lifecycle filter answers the queue on its own, which is what a drain is measured by."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="queued"))
    spool.save(make_envelope(response_id="sent"))
    drain(spool, "sent", ResponseLifecycle.FORWARDED)

    queued = spool.search(lifecycles=(ResponseLifecycle.RECEIVED,))

    assert [receipt.response_id for receipt in queued] == ["queued"]


def test_search_filters_by_questionnaire(tmp_path: Path) -> None:
    """A questionnaire filter narrows to the form that was answered."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="anc", questionnaire="http://example.org/fhir/Questionnaire/anc"))
    spool.save(make_envelope(response_id="epi", questionnaire="http://example.org/fhir/Questionnaire/epi"))

    found = spool.search(questionnaire="http://example.org/fhir/Questionnaire/epi")

    assert [receipt.response_id for receipt in found] == ["epi"]


def test_search_filters_by_form_kind(tmp_path: Path) -> None:
    """A form-kind filter separates aggregate captures from event ones."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="agg", form_kind="aggregate"))
    spool.save(make_envelope(response_id="evt", form_kind="event"))

    assert [receipt.response_id for receipt in spool.search(form_kind="event")] == ["evt"]


def test_search_filters_by_ids(tmp_path: Path) -> None:
    """An id filter ORs within itself and ANDs with the other filters."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="one", received_at="2026-08-07T09:00:00Z", form_kind="aggregate"))
    spool.save(make_envelope(response_id="two", received_at="2026-08-07T10:00:00Z", form_kind="event"))
    spool.save(make_envelope(response_id="three", received_at="2026-08-07T11:00:00Z", form_kind="event"))

    both = spool.search(ids=("one", "three"))
    narrowed = spool.search(form_kind="event", ids=("one", "three"))

    assert [receipt.response_id for receipt in both] == ["three", "one"]
    assert [receipt.response_id for receipt in narrowed] == ["three"]


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
    (spool.directory_for(ResponseLifecycle.REJECTED) / f"refused{REJECTION_REPORT_SUFFIX}").write_text(
        report.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )

    found = spool.rejection("refused")

    assert found is not None
    assert found.status == "ERROR"
    assert found.issues[0].error_code == "E1120"


def test_a_report_file_is_not_mistaken_for_a_receipt(tmp_path: Path) -> None:
    """`<id>.report.json` sits in the same directory as the receipt and must never be listed as one."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="refused"))
    drain(spool, "refused", ResponseLifecycle.REJECTED)
    (spool.directory_for(ResponseLifecycle.REJECTED) / f"refused{REJECTION_REPORT_SUFFIX}").write_text(
        ForwardImportOutcome(status="ERROR").model_dump_json(), encoding="utf-8"
    )

    assert [receipt.response_id for receipt in spool.search()] == ["refused"]


def test_a_receipt_with_no_report_answers_none(tmp_path: Path) -> None:
    """A rejection whose report is missing is still a rejection; it just says nothing about why."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="refused"))
    drain(spool, "refused", ResponseLifecycle.REJECTED)

    assert spool.rejection("refused") is None


def test_an_unreadable_report_does_not_fail_the_listing(tmp_path: Path) -> None:
    """A corrupt diagnostic is not a lost receipt, so the report reads as absent rather than raising."""
    spool = ResponseSpool.at(tmp_path)
    spool.save(make_envelope(response_id="refused"))
    drain(spool, "refused", ResponseLifecycle.REJECTED)
    (spool.directory_for(ResponseLifecycle.REJECTED) / f"refused{REJECTION_REPORT_SUFFIX}").write_text(
        "{not json", encoding="utf-8"
    )

    assert spool.rejection("refused") is None
    assert [receipt.response_id for receipt in spool.search()] == ["refused"]


def test_reading_fails_loudly_on_unparseable_json(tmp_path: Path) -> None:
    """A corrupt receipt file names itself rather than being skipped."""
    spool = ResponseSpool.at(tmp_path)
    (spool.directory_for(ResponseLifecycle.RECEIVED) / "broken.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(UnreadableReceiptError, match=r"broken\.json: not readable as JSON"):
        spool.search()


def test_reading_fails_loudly_on_a_file_that_is_not_an_envelope(tmp_path: Path) -> None:
    """Valid JSON that is not a receipt names the file."""
    spool = ResponseSpool.at(tmp_path)
    (spool.directory_for(ResponseLifecycle.RECEIVED) / "stray.json").write_text(
        '{"resourceType": "QuestionnaireResponse"}', encoding="utf-8"
    )

    with pytest.raises(UnreadableReceiptError, match=r"stray\.json: not a stored response envelope"):
        spool.search()


def test_new_response_id_is_a_fhir_safe_id() -> None:
    """Minted ids are 32 hex characters, unique, and legal as a FHIR id and a file name."""
    first = new_response_id()
    second = new_response_id()

    assert len(first) == 32
    assert FHIR_ID_RE.match(first)
    assert first != second


def test_current_instant_is_a_fhir_instant() -> None:
    """The receipt timestamp is UTC with a Z suffix and second precision."""
    instant = current_instant()

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", instant)
