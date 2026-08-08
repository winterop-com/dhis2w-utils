"""Unit tests for the response spool: atomic writes, index rebuild on scan, search, and id minting."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from dhis2w_fhir_serve.spool import (
    ResponseSpool,
    StoredResponseEnvelope,
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


def test_save_then_get_round_trips(tmp_path: Path) -> None:
    """A saved receipt reads back from memory unchanged."""
    spool = ResponseSpool.scan(tmp_path / "received")
    envelope = make_envelope(warnings=("code XYZ not in the served terminology",))

    spool.save(envelope)

    assert spool.get("aaa") == envelope
    assert spool.get("missing") is None


def test_scan_creates_the_directory(tmp_path: Path) -> None:
    """Scanning a directory that does not exist yet creates it and starts empty."""
    directory = tmp_path / "deep" / "received"

    spool = ResponseSpool.scan(directory)

    assert directory.is_dir()
    assert spool.count() == 0


def test_save_writes_a_parseable_file_named_for_the_response(tmp_path: Path) -> None:
    """The mirror file is `<response_id>.json` and holds the envelope, with no temporary files left behind."""
    directory = tmp_path / "received"
    spool = ResponseSpool.scan(directory)

    spool.save(make_envelope(response_id="bbb"))

    written = directory / "bbb.json"
    assert written.is_file()
    assert sorted(path.name for path in directory.iterdir()) == ["bbb.json"]
    parsed = json.loads(written.read_text(encoding="utf-8"))
    assert parsed["response_id"] == "bbb"
    assert parsed["response"]["resourceType"] == "QuestionnaireResponse"
    assert written.read_text(encoding="utf-8").endswith("\n")


def test_scan_rebuilds_the_index_from_the_mirror(tmp_path: Path) -> None:
    """A fresh spool over the same directory reads back everything the previous one wrote."""
    directory = tmp_path / "received"
    ResponseSpool.scan(directory).save(make_envelope(response_id="ccc"))

    rebuilt = ResponseSpool.scan(directory)

    assert rebuilt.count() == 1
    found = rebuilt.get("ccc")
    assert found is not None
    assert found.questionnaire == "http://example.org/fhir/Questionnaire/d2-ds-anc-q"


def test_search_returns_newest_first(tmp_path: Path) -> None:
    """Receipts come back in received order, newest first, whatever order they were saved in."""
    spool = ResponseSpool.scan(tmp_path / "received")
    spool.save(make_envelope(response_id="middle", received_at="2026-08-07T11:00:00Z"))
    spool.save(make_envelope(response_id="oldest", received_at="2026-08-07T09:00:00Z"))
    spool.save(make_envelope(response_id="newest", received_at="2026-08-07T13:00:00Z"))

    found = spool.search()

    assert [envelope.response_id for envelope in found] == ["newest", "middle", "oldest"]


def test_search_filters_by_questionnaire(tmp_path: Path) -> None:
    """A questionnaire filter narrows to the form that was answered."""
    spool = ResponseSpool.scan(tmp_path / "received")
    spool.save(make_envelope(response_id="anc", questionnaire="http://example.org/fhir/Questionnaire/anc"))
    spool.save(make_envelope(response_id="epi", questionnaire="http://example.org/fhir/Questionnaire/epi"))

    found = spool.search(questionnaire="http://example.org/fhir/Questionnaire/epi")

    assert [envelope.response_id for envelope in found] == ["epi"]


def test_search_filters_by_form_kind(tmp_path: Path) -> None:
    """A form-kind filter separates aggregate captures from event ones."""
    spool = ResponseSpool.scan(tmp_path / "received")
    spool.save(make_envelope(response_id="agg", form_kind="aggregate"))
    spool.save(make_envelope(response_id="evt", form_kind="event"))

    assert [envelope.response_id for envelope in spool.search(form_kind="event")] == ["evt"]


def test_search_filters_by_ids(tmp_path: Path) -> None:
    """An id filter ORs within itself and ANDs with the other filters."""
    spool = ResponseSpool.scan(tmp_path / "received")
    spool.save(make_envelope(response_id="one", received_at="2026-08-07T09:00:00Z", form_kind="aggregate"))
    spool.save(make_envelope(response_id="two", received_at="2026-08-07T10:00:00Z", form_kind="event"))
    spool.save(make_envelope(response_id="three", received_at="2026-08-07T11:00:00Z", form_kind="event"))

    both = spool.search(ids=("one", "three"))
    narrowed = spool.search(form_kind="event", ids=("one", "three"))

    assert [envelope.response_id for envelope in both] == ["three", "one"]
    assert [envelope.response_id for envelope in narrowed] == ["three"]


def test_count(tmp_path: Path) -> None:
    """The count is the number of receipts held, and re-saving an id replaces rather than duplicates."""
    spool = ResponseSpool.scan(tmp_path / "received")
    spool.save(make_envelope(response_id="ddd"))
    spool.save(make_envelope(response_id="eee"))
    spool.save(make_envelope(response_id="ddd", form_kind="event"))

    assert spool.count() == 2


def test_scan_fails_loudly_on_unparseable_json(tmp_path: Path) -> None:
    """A corrupt mirror file names itself rather than being skipped."""
    directory = tmp_path / "received"
    directory.mkdir()
    (directory / "broken.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match=r"broken\.json: not valid JSON"):
        ResponseSpool.scan(directory)


def test_scan_fails_loudly_on_a_file_that_is_not_an_envelope(tmp_path: Path) -> None:
    """Valid JSON that is not a receipt names the file."""
    directory = tmp_path / "received"
    directory.mkdir()
    (directory / "stray.json").write_text('{"resourceType": "QuestionnaireResponse"}', encoding="utf-8")

    with pytest.raises(ValueError, match=r"stray\.json: not a stored response envelope"):
        ResponseSpool.scan(directory)


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
