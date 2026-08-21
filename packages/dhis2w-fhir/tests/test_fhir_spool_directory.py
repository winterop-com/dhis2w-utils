"""`[serve] spool_dir` on the draining side: which tree a forward reads, and what an empty one is refused with.

The key sits in `[serve]` because the server writes the tree; the forwarder follows the project's
declaration rather than carrying a location of its own. So everything a drain touches - the queue it
reads, the states it files into, the lock it holds, the listing `d2w fhir spool` prints - is resolved
off that one key, and a project that moved its spool moved it for both halves of the loop at once.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dhis2w_fhir.config import FHIR_CONFIG_FILENAME, ServeConfig, load_fhir_config, load_project
from dhis2w_fhir.service import ForwardImportRecord, read_spool_state, spool_layout
from dhis2w_fhir.spool import (
    REFUSAL_RECORD_SUFFIX,
    SPOOL_RELATIVE_PATH,
    ForwardRefusalRecord,
    RefusalReason,
    SpoolLayout,
    SpoolState,
    drain_lock,
    move_to_forwarded,
    read_received_responses,
    read_refusal_record,
    read_spooled_receipts,
    record_refusal,
    resolve_spool_root,
)
from pydantic import ValidationError

_CANONICAL = "http://example.org/fhir"

_IG_TABLE = """
[ig]
id = "dhis2.fhir.spooldir"
canonical = "http://example.org/fhir"
name = "SpoolDir"
title = "SpoolDir"
publisher = "Winterop"
"""


def _write_project(root: Path, spool_dir: str | None = None) -> Path:
    """A project whose `[serve]` table states the spool directory, or states none at all."""
    root.mkdir(parents=True, exist_ok=True)
    table = "" if spool_dir is None else f'\n[serve]\nspool_dir = "{spool_dir}"\n'
    (root / FHIR_CONFIG_FILENAME).write_text(f"{_IG_TABLE}{table}", encoding="utf-8")
    return root


def _write_receipt(directory: Path, response_id: str) -> None:
    """One receipt envelope, written the way `d2w fhir serve` writes what it accepted."""
    directory.mkdir(parents=True, exist_ok=True)
    envelope = {
        "response_id": response_id,
        "received_at": "2026-08-01T09:00:00Z",
        "form_kind": "aggregate",
        "questionnaire": f"{_CANONICAL}/Questionnaire/BfMAe6Itzgt",
        "warnings": [],
        "response": {
            "resourceType": "QuestionnaireResponse",
            "id": response_id,
            "questionnaire": f"{_CANONICAL}/Questionnaire/BfMAe6Itzgt",
            "status": "completed",
        },
    }
    (directory / f"{response_id}.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")


def test_a_relative_directory_is_resolved_against_the_project(tmp_path: Path) -> None:
    """The ordinary case, and the one the scaffold's .gitignore covers when it is left unstated."""
    assert resolve_spool_root(tmp_path, "receipts") == tmp_path / "receipts"
    assert resolve_spool_root(tmp_path) == tmp_path / SPOOL_RELATIVE_PATH


def test_an_absolute_directory_is_taken_as_written(tmp_path: Path) -> None:
    """A spool on a volume the operator chose sits where they put it, project or no project."""
    assert resolve_spool_root(tmp_path, "/srv/dhis2w/receipts") == Path("/srv/dhis2w/receipts")


def test_the_project_is_what_the_layout_is_resolved_from(tmp_path: Path) -> None:
    """One helper, so a drain, a listing, and a requeue of one project cannot read three directories."""
    project = load_project(_write_project(tmp_path / "project", "receipts"))

    layout = spool_layout(project)

    assert layout.root == project.project_root / "receipts"
    assert layout.directory_for(SpoolState.RECEIVED) == project.project_root / "receipts" / "received"
    assert layout.malformed_directory == project.project_root / "receipts" / "malformed"


def test_a_drain_reads_the_queue_the_project_named(tmp_path: Path) -> None:
    """What a forward run starts from: the receipts in the directory this project says it writes to."""
    project = load_project(_write_project(tmp_path / "project", "receipts"))
    _write_receipt(project.project_root / "receipts" / "received", "moved-1")

    reading = read_received_responses(spool_layout(project))

    assert [response.response_id for response in reading.responses] == ["moved-1"]


def test_a_drain_reads_nothing_out_of_the_directory_the_project_is_not_using(tmp_path: Path) -> None:
    """The other half: a receipt under the default tree of a project that moved its spool is not this queue.

    Nothing is lost by it - the file is where somebody put it - but a drain that read both directories
    would be a drain with two opinions about where this project's receipts live.
    """
    project = load_project(_write_project(tmp_path / "project", "receipts"))
    _write_receipt(project.project_root / SPOOL_RELATIVE_PATH / "received", "left-behind")

    assert read_received_responses(spool_layout(project)).responses == ()


def test_an_absolute_spool_is_drained_and_named_absolutely(tmp_path: Path) -> None:
    """A spool outside the project still drains, and a listing names it as the absolute path it is."""
    elsewhere = tmp_path / "volume" / "receipts"
    project = load_project(_write_project(tmp_path / "project", str(elsewhere)))
    _write_receipt(elsewhere / "received", "outside-1")

    report = read_spool_state(project)

    assert report.counts.received == 1
    assert report.receipts[0].response_id == "outside-1"


def test_the_listing_counts_the_directory_the_project_named(tmp_path: Path) -> None:
    """`d2w fhir spool` answers about the same tree the drain would, since it resolves the same key."""
    project = load_project(_write_project(tmp_path / "project", "receipts"))
    _write_receipt(project.project_root / "receipts" / "received", "moved-1")
    _write_receipt(project.project_root / SPOOL_RELATIVE_PATH / "received", "left-behind")

    report = read_spool_state(project)

    assert [row.response_id for row in report.receipts] == ["moved-1"]


def test_the_drain_lock_is_held_inside_the_directory_the_project_named(tmp_path: Path) -> None:
    """One drain at a time is one lock per spool, so the lock moves with the tree it guards."""
    project = load_project(_write_project(tmp_path / "project", "receipts"))

    with drain_lock(spool_layout(project)) as path:
        assert path.parent == project.project_root / "receipts"
        assert path.is_file()


def test_a_project_that_states_nothing_uses_the_tree_inside_it(tmp_path: Path) -> None:
    """The default is the same directory the scaffold ignores and every other page names."""
    project = load_project(_write_project(tmp_path / "project"))

    assert spool_layout(project).root == project.project_root / SPOOL_RELATIVE_PATH


def test_an_empty_directory_is_refused_where_it_is_written(tmp_path: Path) -> None:
    """An empty name points at nothing, and a project that states one has to mean a directory.

    Refused at parse rather than resolved to the project root: a spool root that is also the project
    root would put `received/` beside `fhir.toml` on the strength of two quotation marks.
    """
    with pytest.raises(ValidationError) as refused:
        ServeConfig(spool_dir="")

    assert "spool_dir is empty" in str(refused.value)

    _write_project(tmp_path / "project", "")

    with pytest.raises(ValidationError):
        load_fhir_config(tmp_path / "project" / FHIR_CONFIG_FILENAME)


def test_the_layout_carries_the_project_a_report_names_paths_against(tmp_path: Path) -> None:
    """A report states a spool file relative to the project, which stays true of a root outside it."""
    layout = SpoolLayout.resolve(tmp_path / "project", "/srv/receipts")

    assert layout.project_root == tmp_path / "project"
    assert layout.root == Path("/srv/receipts")


def _queued_with_refusal(tmp_path: Path, record: ForwardRefusalRecord | None = None) -> SpoolLayout:
    """One project holding a queued receipt `stuck-1`, with a refusal record beside it when given."""
    project = load_project(_write_project(tmp_path / "project"))
    layout = spool_layout(project)
    _write_receipt(layout.directory_for(SpoolState.RECEIVED), "stuck-1")
    if record is not None:
        record_refusal(read_received_responses(layout).responses[0], record)
    return layout


def _refusal() -> ForwardRefusalRecord:
    """The record a committing drain writes when it refuses a receipt for the second time."""
    return ForwardRefusalRecord(
        refused_at="2026-08-17T12:00:00Z",
        attempt_count=2,
        reasons=(RefusalReason(category="no-form-type", reason="the form declares no kind"),),
    )


def test_a_refusal_record_rides_the_listing_and_never_reads_as_a_receipt(tmp_path: Path) -> None:
    """The marker is a sidecar: the listing states it on the receipt's row, and no read mistakes it for one."""
    layout = _queued_with_refusal(tmp_path, _refusal())

    contents = read_spooled_receipts(layout)

    assert [receipt.response_id for receipt in contents.receipts] == ["stuck-1"]
    refusal = contents.receipts[0].refusal
    assert refusal is not None
    assert refusal.attempt_count == 2
    assert refusal.line == "the form declares no kind"
    assert [response.response_id for response in read_received_responses(layout).responses] == ["stuck-1"]


def test_a_receipt_no_drain_has_refused_carries_no_refusal(tmp_path: Path) -> None:
    """Nothing on disk means nothing stated: the row reads exactly as it did before any drain ran."""
    layout = _queued_with_refusal(tmp_path)

    contents = read_spooled_receipts(layout)

    assert contents.receipts[0].refusal is None


def test_a_corrupt_refusal_record_answers_none_and_the_receipt_still_lists(tmp_path: Path) -> None:
    """It is the marker that got corrupted, not the receipt that got lost."""
    layout = _queued_with_refusal(tmp_path)
    directory = layout.directory_for(SpoolState.RECEIVED)
    (directory / f"stuck-1{REFUSAL_RECORD_SUFFIX}").write_text("{not json", encoding="utf-8")

    contents = read_spooled_receipts(layout)

    assert [receipt.response_id for receipt in contents.receipts] == ["stuck-1"]
    assert contents.receipts[0].refusal is None
    assert read_refusal_record(directory, "stuck-1") is None


def test_the_move_that_drains_a_receipt_deletes_its_refusal_record(tmp_path: Path) -> None:
    """The marker records the queue; a receipt leaving the queue leaves nothing stale behind it."""
    layout = _queued_with_refusal(tmp_path, _refusal())
    spooled = read_received_responses(layout).responses[0]

    move_to_forwarded(spooled, ForwardImportRecord(status="OK"))

    received = layout.directory_for(SpoolState.RECEIVED)
    assert not (received / f"stuck-1{REFUSAL_RECORD_SUFFIX}").exists()
    assert (layout.directory_for(SpoolState.FORWARDED) / "stuck-1.json").is_file()


def test_the_spool_state_report_counts_the_refused_still_queued(tmp_path: Path) -> None:
    """`d2w fhir spool` states the fact on the receipt's own row and in the counts."""
    layout = _queued_with_refusal(tmp_path, _refusal())
    project = load_project(layout.project_root)

    report = read_spool_state(project)

    assert report.counts.refused_in_queue == 1
    row = report.receipts[0]
    assert row.reason is not None
    assert "the form declares no kind" in row.reason
    assert "2 drains" in row.reason
    assert "2026-08-17T12:00:00Z" in row.reason
    assert "1 of the received refused by a drain" in report.counts_line
