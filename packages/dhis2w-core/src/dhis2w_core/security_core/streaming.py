"""Crash-safe streaming writer for audit runs: JSONL spine, live Markdown, resume.

A run writes to one folder. `manifest.json` records the run identity. `report.jsonl`
is the spine: one `CheckResult` per line, flushed and fsynced as each check finishes,
so a dropped connection never loses completed work. The Markdown report is streamed
live the same way; the other formats are rendered from the full report at finalize.
`load_prior` reads the spine back so an interrupted run can resume or be re-rendered.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from dhis2w_core.security_core.report.base import ReportRenderer, StreamingRenderer
from dhis2w_core.security_core.report.model import AuditReport, CheckResult, RunManifest

MANIFEST_FILENAME = "manifest.json"
SPINE_FILENAME = "report.jsonl"


def _fsync(handle: TextIO) -> None:
    """Flush a text handle and force it to disk so a crash keeps finished work."""
    handle.flush()
    os.fsync(handle.fileno())


class ReportWriter:
    """Streams an audit run to a folder: manifest, JSONL spine, live Markdown, finalized formats."""

    def __init__(
        self,
        folder: Path,
        manifest: RunManifest,
        *,
        streaming_renderer: StreamingRenderer,
        finalize_renderers: Sequence[ReportRenderer] = (),
        resume: bool = False,
    ) -> None:
        """Open `folder` for writing; append rather than truncate when `resume` is set."""
        self._folder = folder
        self._streaming = streaming_renderer
        self._finalize = list(finalize_renderers)
        folder.mkdir(parents=True, exist_ok=True)
        spine_path = folder / SPINE_FILENAME
        markdown_path = folder / f"report.{streaming_renderer.suffix}"
        if not resume and spine_path.exists():
            raise FileExistsError(f"{spine_path} already exists; pass resume=True or use a fresh folder")
        self._write_manifest(manifest)
        if resume:
            self._spine = spine_path.open("a", encoding="utf-8")
            self._markdown = markdown_path.open("a", encoding="utf-8")
        else:
            self._spine = spine_path.open("w", encoding="utf-8")
            self._markdown = markdown_path.open("w", encoding="utf-8")
            self._markdown.write(streaming_renderer.header(manifest))
            _fsync(self._markdown)

    def write_result(self, result: CheckResult) -> None:
        """Append one result to the JSONL spine and the live Markdown, fsyncing both."""
        self._spine.write(result.model_dump_json() + "\n")
        _fsync(self._spine)
        self._markdown.write(self._streaming.section(result))
        _fsync(self._markdown)

    def finalize(self, report: AuditReport) -> None:
        """Write the Markdown footer, render the remaining formats, and mark the run complete.

        Closing the open handles is the caller's job (use the writer as a
        context manager or call `close`), so a finalize that raises mid-render
        never leaks the spine. The `completed=True` manifest write is the last
        durable step, so a crash before it leaves the run resumable.
        """
        self._markdown.write(self._streaming.footer(report.summary))
        _fsync(self._markdown)
        for renderer in self._finalize:
            path = self._folder / f"report.{renderer.suffix}"
            with path.open("w", encoding="utf-8") as handle:
                handle.write(renderer.render(report))
                _fsync(handle)
        self._write_manifest(report.manifest)

    def close(self) -> None:
        """Close the open spine and Markdown handles; safe to call more than once."""
        if not self._markdown.closed:
            self._markdown.close()
        if not self._spine.closed:
            self._spine.close()

    def __enter__(self) -> ReportWriter:
        """Enter the writer's context, returning the writer itself."""
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Close the open handles when the context exits."""
        self.close()

    def _write_manifest(self, manifest: RunManifest) -> None:
        """Write `manifest.json`, overwriting any prior copy, and fsync it."""
        path = self._folder / MANIFEST_FILENAME
        with path.open("w", encoding="utf-8") as handle:
            handle.write(manifest.model_dump_json(indent=2))
            _fsync(handle)

    @classmethod
    def load_prior(cls, folder: Path) -> tuple[RunManifest | None, list[CheckResult]]:
        """Read an existing run's manifest and completed results for resume or re-render."""
        manifest: RunManifest | None = None
        manifest_path = folder / MANIFEST_FILENAME
        if manifest_path.exists():
            manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        results: list[CheckResult] = []
        spine_path = folder / SPINE_FILENAME
        if spine_path.exists():
            for line in spine_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped:
                    results.append(CheckResult.model_validate_json(stripped))
        return manifest, results
