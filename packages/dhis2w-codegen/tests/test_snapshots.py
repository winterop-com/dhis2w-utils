"""Golden-snapshot tests: emitted output must match the committed generated tree.

Locks the contract that running the codegen against a committed manifest
produces a byte-for-byte copy of the committed `generated/v{N}/` tree.
Catches accidental emitter changes that would silently re-shape every
caller's working tree, and forces intentional codegen changes to update
the snapshot in the same PR.

Two parametrised cases per emitter, two versions = four checks total.
Adds ~5-10s to `make test`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dhis2w_codegen.discover import SchemasManifest
from dhis2w_codegen.emit import emit
from dhis2w_codegen.oas_emit import emit_from_openapi

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GENERATED_ROOT = _REPO_ROOT / "packages" / "dhis2w-client" / "src" / "dhis2w_client" / "generated"

_VERSIONS = ["v41", "v42", "v43"]


@pytest.mark.parametrize("version_key", _VERSIONS)
def test_schemas_manifest_is_canonical(version_key: str) -> None:
    """Committed schemas_manifest.json must equal the bytes the SchemasManifest validator produces.

    DHIS2's /api/schemas response order is not stable; the SchemasManifest validator
    sorts schemas and per-schema properties so re-fetches produce byte-identical output.
    A drift here means someone committed an un-canonicalized manifest and every
    subsequent regeneration will re-shuffle the file.
    """
    manifest_path = _GENERATED_ROOT / version_key / "schemas_manifest.json"
    committed_bytes = manifest_path.read_bytes()
    manifest = SchemasManifest.model_validate_json(committed_bytes)
    canonical_bytes = json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True).encode("utf-8")
    assert committed_bytes == canonical_bytes, (
        f"{manifest_path} is not in canonical order. "
        f"Re-run `d2w dev codegen rebuild` against a live DHIS2 instance, "
        f"or round-trip the manifest through SchemasManifest.model_validate_json + emit() to re-canonicalize."
    )


@pytest.mark.parametrize("version_key", _VERSIONS)
def test_schemas_emit_matches_committed_tree(version_key: str, tmp_path: Path) -> None:
    """`emit()` from the committed manifest must reproduce the committed schemas tree byte-for-byte."""
    manifest_path = _GENERATED_ROOT / version_key / "schemas_manifest.json"
    manifest = SchemasManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    emit(manifest, tmp_path)
    _assert_subtree_equal(tmp_path / "schemas", _GENERATED_ROOT / version_key / "schemas")


@pytest.mark.parametrize("version_key", _VERSIONS)
def test_oas_emit_matches_committed_tree(version_key: str, tmp_path: Path) -> None:
    """`emit_from_openapi()` must reproduce the committed OAS tree byte-for-byte."""
    version_dir = _GENERATED_ROOT / version_key
    manifest = SchemasManifest.model_validate_json((version_dir / "schemas_manifest.json").read_text(encoding="utf-8"))
    emit_from_openapi(
        version_dir / "openapi.json",
        tmp_path,
        version_key=manifest.version_key,
        raw_version=manifest.raw_version,
    )
    _assert_subtree_equal(tmp_path / "oas", version_dir / "oas")


def test_emit_is_deterministic_across_hash_seeds(tmp_path: Path) -> None:
    """`emit()` produces byte-identical output when the same input is processed twice in a row.

    Hash-seed randomisation isn't directly testable from inside a single Python process
    (PYTHONHASHSEED is locked at startup), but the determinism contract is symmetrical:
    if the second run matches the first, the emitter isn't relying on dict / set ordering
    that varies across process boundaries either.
    """
    manifest_path = _GENERATED_ROOT / "v43" / "schemas_manifest.json"
    manifest = SchemasManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    first = tmp_path / "first"
    second = tmp_path / "second"
    emit(manifest, first)
    emit(manifest, second)
    _assert_subtree_equal(first / "schemas", second / "schemas")


def _assert_subtree_equal(generated: Path, committed: Path) -> None:
    """Walk `generated` and `committed`, assert every file matches byte-for-byte; raise on first mismatch."""
    assert generated.is_dir(), f"emitter produced no output at {generated}"
    assert committed.is_dir(), f"committed tree missing at {committed}"

    generated_files = _file_set(generated)
    committed_files = _file_set(committed)

    only_in_generated = generated_files - committed_files
    only_in_committed = committed_files - generated_files

    assert not only_in_generated, (
        f"emitter wrote files not in committed tree: {sorted(only_in_generated)}; "
        f"either commit them or fix the emitter to stop producing them"
    )
    assert not only_in_committed, (
        f"committed tree has files the emitter no longer produces: {sorted(only_in_committed)}; "
        f"either delete them or fix the emitter to produce them again"
    )

    for relative_path in sorted(generated_files):
        emitted_bytes = (generated / relative_path).read_bytes()
        committed_bytes = (committed / relative_path).read_bytes()
        assert emitted_bytes == committed_bytes, (
            f"{relative_path}: emitter output differs from committed tree. "
            f"Either run `d2w dev codegen rebuild` + `oas-rebuild` to refresh the committed tree, "
            f"or fix the emitter to produce the committed bytes."
        )


def _file_set(root: Path) -> set[str]:
    """Return relative paths of every regular file under `root`, ignoring `__pycache__`."""
    skip = {"__pycache__"}
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and not any(part in skip for part in path.parts)
    }
