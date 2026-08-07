"""Unit tests for generated-file cleanup and writes."""

from pathlib import Path

from dhis2w_fhir.writer import (
    GENERATED_HEADER,
    GENERATED_MARKDOWN_HEADER,
    FshArtifact,
    JsonArtifact,
    clean_generated_files,
    sync_artifacts,
    sync_json_artifacts,
    write_artifacts,
)


def _artifact(relative_path: str, content: str = "CodeSystem: X\n") -> FshArtifact:
    """Build a small artifact for writer tests."""
    return FshArtifact(relative_path=relative_path, kind="terminology-pair", fsh_name="X", content=content)


def _page(relative_path: str, content: str = "# Forms\n") -> FshArtifact:
    """Build a small markdown page artifact for writer tests."""
    return FshArtifact(relative_path=relative_path, kind="page", fsh_name="forms.md", content=content)


def _json(relative_path: str, content: str = '{"resourceType": "Organization"}\n') -> JsonArtifact:
    """Build a small JSON artifact for writer tests."""
    return JsonArtifact(relative_path=relative_path, content=content)


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


def test_sync_writes_nested_artifacts_under_their_own_subdirectory(tmp_path: Path) -> None:
    """A nested target creates the subdirectory on the way down and reports the full relative path."""
    report = sync_artifacts(tmp_path, "tracker-programs", [_artifact("tracker-programs/IpHINAT79UW/A03MvHHogjR.fsh")])
    assert report.written == ["tracker-programs/IpHINAT79UW/A03MvHHogjR.fsh"]
    assert (tmp_path / "tracker-programs" / "IpHINAT79UW" / "A03MvHHogjR.fsh").is_file()


def test_sync_sweeps_stale_generated_files_out_of_nested_subdirectories(tmp_path: Path) -> None:
    """A generated file the build dropped is deleted however deep it sits, reported relative to the target."""
    first = [
        _artifact("tracker-programs/IpHINAT79UW/A03MvHHogjR.fsh"),
        _artifact("tracker-programs/IpHINAT79UW/ZzYYXq4fJie.fsh"),
    ]
    sync_artifacts(tmp_path, "tracker-programs", first)
    report = sync_artifacts(tmp_path, "tracker-programs", [_artifact("tracker-programs/IpHINAT79UW/A03MvHHogjR.fsh")])
    assert report.deleted == ["IpHINAT79UW/ZzYYXq4fJie.fsh"]
    assert not (tmp_path / "tracker-programs" / "IpHINAT79UW" / "ZzYYXq4fJie.fsh").exists()
    assert (tmp_path / "tracker-programs" / "IpHINAT79UW" / "A03MvHHogjR.fsh").exists()


def test_sync_never_deletes_a_hand_authored_nested_file(tmp_path: Path) -> None:
    """The header is what marks a file generated, so a hand-authored file deep in the tree survives."""
    sync_artifacts(tmp_path, "tracker-programs", [_artifact("tracker-programs/IpHINAT79UW/A03MvHHogjR.fsh")])
    manual = tmp_path / "tracker-programs" / "IpHINAT79UW" / "manual.fsh"
    manual.write_text("Instance: Questionnaire-Manual\n", encoding="utf-8")
    report = sync_artifacts(tmp_path, "tracker-programs", [_artifact("tracker-programs/IpHINAT79UW/A03MvHHogjR.fsh")])
    assert report.deleted == []
    assert manual.exists()


def test_sync_prunes_a_subdirectory_it_empties(tmp_path: Path) -> None:
    """A program whose every stage left the selection leaves no empty directory behind; the target itself stays."""
    sync_artifacts(tmp_path, "tracker-programs", [_artifact("tracker-programs/IpHINAT79UW/A03MvHHogjR.fsh")])
    report = sync_artifacts(tmp_path, "tracker-programs", [_artifact("tracker-programs/uy2gU8kT1jF/oRySG82BKE6.fsh")])
    assert report.deleted == ["IpHINAT79UW/A03MvHHogjR.fsh"]
    assert not (tmp_path / "tracker-programs" / "IpHINAT79UW").exists()
    assert (tmp_path / "tracker-programs" / "uy2gU8kT1jF" / "oRySG82BKE6.fsh").is_file()


def test_sync_keeps_a_subdirectory_holding_a_hand_authored_file(tmp_path: Path) -> None:
    """Pruning removes empty directories only, so a directory left holding hand-authored work stays."""
    sync_artifacts(tmp_path, "tracker-programs", [_artifact("tracker-programs/IpHINAT79UW/A03MvHHogjR.fsh")])
    manual = tmp_path / "tracker-programs" / "IpHINAT79UW" / "manual.fsh"
    manual.write_text("Instance: Questionnaire-Manual\n", encoding="utf-8")
    sync_artifacts(tmp_path, "tracker-programs", [])
    assert manual.exists()


def test_sync_tells_same_named_files_in_different_subdirectories_apart(tmp_path: Path) -> None:
    """Two programs may hold a same-named file, so the produced set is keyed by path rather than by name."""
    sync_artifacts(
        tmp_path,
        "tracker-programs",
        [_artifact("tracker-programs/IpHINAT79UW/shared.fsh"), _artifact("tracker-programs/uy2gU8kT1jF/shared.fsh")],
    )
    report = sync_artifacts(tmp_path, "tracker-programs", [_artifact("tracker-programs/IpHINAT79UW/shared.fsh")])
    assert report.deleted == ["uy2gU8kT1jF/shared.fsh"]
    assert (tmp_path / "tracker-programs" / "IpHINAT79UW" / "shared.fsh").exists()


def test_markdown_pages_take_the_markdown_header(tmp_path: Path) -> None:
    """A `.md` artifact is headed by the HTML comment; a `.fsh` one keeps the FSH line comment."""
    write_artifacts(tmp_path, [_page("pagecontent/forms.md"), _artifact("terminology/sample.fsh")])
    page = (tmp_path / "pagecontent" / "forms.md").read_text(encoding="utf-8")
    assert page.startswith(f"{GENERATED_MARKDOWN_HEADER}\n\n")
    fsh = (tmp_path / "terminology" / "sample.fsh").read_text(encoding="utf-8")
    assert fsh.startswith(f"{GENERATED_HEADER}\n\n")


def test_clean_deletes_generated_pages_but_never_the_hand_authored_index(tmp_path: Path) -> None:
    """Cleanup removes header-bearing markdown and leaves the scaffolded index.md beside it untouched."""
    directory = tmp_path / "pagecontent"
    write_artifacts(tmp_path, [_page("pagecontent/forms.md")])
    (directory / "index.md").write_text("# My IG\n\nHand-authored.\n", encoding="utf-8")
    deleted = clean_generated_files(directory)
    assert deleted == ["forms.md"]
    assert (directory / "index.md").read_text(encoding="utf-8") == "# My IG\n\nHand-authored.\n"


def test_sync_sweeps_stale_pages_and_spares_the_hand_authored_index(tmp_path: Path) -> None:
    """A page dropped from the build is deleted on the next sync; index.md survives every cycle."""
    directory = tmp_path / "pagecontent"
    directory.mkdir()
    (directory / "index.md").write_text("# My IG\n", encoding="utf-8")
    sync_artifacts(tmp_path, "pagecontent", [_page("pagecontent/forms.md"), _page("pagecontent/stale.md")])
    report = sync_artifacts(tmp_path, "pagecontent", [_page("pagecontent/forms.md")])
    assert report.unchanged == ["pagecontent/forms.md"]
    assert report.deleted == ["stale.md"]
    assert (directory / "index.md").exists()


def test_page_sync_is_byte_stable_on_a_second_run(tmp_path: Path) -> None:
    """Regenerating unchanged pages writes nothing at all - the second run reports only unchanged files."""
    pages = [_page("pagecontent/forms.md"), _page("pagecontent/registry.md", "# Registry\n")]
    first = sync_artifacts(tmp_path, "pagecontent", pages)
    assert first.written == ["pagecontent/forms.md", "pagecontent/registry.md"]
    second = sync_artifacts(tmp_path, "pagecontent", pages)
    assert second.written == []
    assert second.deleted == []
    assert second.unchanged == ["pagecontent/forms.md", "pagecontent/registry.md"]


def test_json_sync_writes_new_files_verbatim(tmp_path: Path) -> None:
    """A new JSON artifact is reported in written and lands on disk with no header prepended."""
    report = sync_json_artifacts(tmp_path, "registry", [_json("registry/Organization-abc123.json")])
    assert report.written == ["registry/Organization-abc123.json"]
    destination = tmp_path / "registry" / "Organization-abc123.json"
    assert destination.read_text(encoding="utf-8") == '{"resourceType": "Organization"}\n'


def test_json_sync_is_byte_stable_on_a_second_run(tmp_path: Path) -> None:
    """Byte-identical content on a second run reports unchanged and leaves the file's timestamp alone."""
    artifacts = [_json("registry/Organization-abc123.json")]
    sync_json_artifacts(tmp_path, "registry", artifacts)
    written_stat = (tmp_path / "registry" / "Organization-abc123.json").stat().st_mtime_ns
    report = sync_json_artifacts(tmp_path, "registry", artifacts)
    assert report.written == []
    assert report.deleted == []
    assert report.unchanged == ["registry/Organization-abc123.json"]
    assert (tmp_path / "registry" / "Organization-abc123.json").stat().st_mtime_ns == written_stat


def test_json_sync_rewrites_changed_content(tmp_path: Path) -> None:
    """Content that differs from disk is rewritten and reported in written."""
    sync_json_artifacts(tmp_path, "registry", [_json("registry/Organization-abc123.json")])
    changed = _json("registry/Organization-abc123.json", '{"resourceType": "Organization", "id": "abc123"}\n')
    report = sync_json_artifacts(tmp_path, "registry", [changed])
    assert report.written == ["registry/Organization-abc123.json"]
    assert report.unchanged == []
    destination = tmp_path / "registry" / "Organization-abc123.json"
    assert destination.read_text(encoding="utf-8") == '{"resourceType": "Organization", "id": "abc123"}\n'


def test_json_sync_deletes_stale_json_by_name(tmp_path: Path) -> None:
    """A JSON file the build no longer produces is deleted and its name appears in deleted."""
    first = [_json("registry/keep.json"), _json("registry/stale.json")]
    sync_json_artifacts(tmp_path, "registry", first)
    report = sync_json_artifacts(tmp_path, "registry", [_json("registry/keep.json")])
    assert report.deleted == ["stale.json"]
    assert not (tmp_path / "registry" / "stale.json").exists()
    assert (tmp_path / "registry" / "keep.json").exists()


def test_json_sync_leaves_other_extensions_alone(tmp_path: Path) -> None:
    """A non-JSON file in the owned directory survives the sweep."""
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "notes.txt").write_text("Keep me.\n", encoding="utf-8")
    report = sync_json_artifacts(tmp_path, "registry", [_json("registry/keep.json")])
    assert report.deleted == []
    assert (tmp_path / "registry" / "notes.txt").read_text(encoding="utf-8") == "Keep me.\n"


def test_json_sync_sweeps_only_the_target_subdirectory(tmp_path: Path) -> None:
    """A JSON file in a different subdirectory is outside the owned directory and survives."""
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "other.json").write_text('{"resourceType": "Patient"}\n', encoding="utf-8")
    report = sync_json_artifacts(tmp_path, "registry", [_json("registry/keep.json")])
    assert report.deleted == []
    assert (tmp_path / "elsewhere" / "other.json").exists()


def test_json_sync_creates_nested_parent_directories(tmp_path: Path) -> None:
    """A nested relative path creates every parent directory on the way down."""
    report = sync_json_artifacts(tmp_path, "registry", [_json("registry/organizations/Organization-abc123.json")])
    assert report.written == ["registry/organizations/Organization-abc123.json"]
    assert (tmp_path / "registry" / "organizations" / "Organization-abc123.json").is_file()
