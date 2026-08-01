"""Unit tests for generated-file cleanup and writes."""

from pathlib import Path

from dhis2w_fhir.writer import (
    GENERATED_HEADER,
    FshArtifact,
    clean_generated_files,
    sync_artifacts,
    write_artifacts,
)


def _artifact(relative_path: str, content: str = "CodeSystem: X\n") -> FshArtifact:
    """Build a small artifact for writer tests."""
    return FshArtifact(relative_path=relative_path, kind="terminology-pair", fsh_name="X", content=content)


def test_write_prepends_header(tmp_path: Path) -> None:
    """Written files start with the generated header and land under nested directories."""
    written = write_artifacts(tmp_path, [_artifact("terminology/sample.fsh")])
    assert written == ["terminology/sample.fsh"]
    text = (tmp_path / "terminology" / "sample.fsh").read_text(encoding="utf-8")
    assert text.startswith(f"{GENERATED_HEADER}\n\n")


def test_clean_deletes_only_generated(tmp_path: Path) -> None:
    """Cleanup removes header-bearing files and leaves hand-authored FSH untouched."""
    directory = tmp_path / "terminology"
    write_artifacts(tmp_path, [_artifact("terminology/generated.fsh")])
    (directory / "hand-authored.fsh").write_text("CodeSystem: Manual\n", encoding="utf-8")
    deleted = clean_generated_files(directory)
    assert deleted == ["generated.fsh"]
    assert (directory / "hand-authored.fsh").exists()
    assert not (directory / "generated.fsh").exists()


def test_clean_missing_directory_is_noop(tmp_path: Path) -> None:
    """Cleaning a directory that does not exist returns an empty list."""
    assert clean_generated_files(tmp_path / "nowhere") == []


def test_write_clean_write_is_idempotent(tmp_path: Path) -> None:
    """A write -> clean -> write cycle converges to the same single file."""
    artifact = _artifact("terminology/sample.fsh")
    write_artifacts(tmp_path, [artifact])
    clean_generated_files(tmp_path / "terminology")
    written = write_artifacts(tmp_path, [artifact])
    assert written == ["terminology/sample.fsh"]
    assert sorted(path.name for path in (tmp_path / "terminology").glob("*.fsh")) == ["sample.fsh"]


def test_sync_reports_written_unchanged_deleted(tmp_path: Path) -> None:
    """Sync writes new files, leaves identical ones untouched, and deletes stale generated files."""
    first = [_artifact("terminology/keep.fsh"), _artifact("terminology/stale.fsh")]
    report = sync_artifacts(tmp_path, "terminology", first)
    assert report.written == ["terminology/keep.fsh", "terminology/stale.fsh"]

    keep_stat = (tmp_path / "terminology" / "keep.fsh").stat().st_mtime_ns
    second = [_artifact("terminology/keep.fsh"), _artifact("terminology/new.fsh")]
    report = sync_artifacts(tmp_path, "terminology", second)
    assert report.written == ["terminology/new.fsh"]
    assert report.unchanged == ["terminology/keep.fsh"]
    assert report.deleted == ["stale.fsh"]
    assert (tmp_path / "terminology" / "keep.fsh").stat().st_mtime_ns == keep_stat


def test_sync_never_deletes_hand_authored(tmp_path: Path) -> None:
    """Hand-authored .fsh files in the target subdirectory survive a sync."""
    (tmp_path / "terminology").mkdir()
    (tmp_path / "terminology" / "manual.fsh").write_text("CodeSystem: Manual\n", encoding="utf-8")
    report = sync_artifacts(tmp_path, "terminology", [_artifact("terminology/generated.fsh")])
    assert report.deleted == []
    assert (tmp_path / "terminology" / "manual.fsh").exists()
