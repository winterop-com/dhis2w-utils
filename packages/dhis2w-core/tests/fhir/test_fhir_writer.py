"""Unit tests for generated-file cleanup and writes."""

from pathlib import Path

from dhis2w_core.fhir_core.models import FshArtifact
from dhis2w_core.fhir_core.writer import GENERATED_HEADER, clean_generated_files, write_artifacts


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
