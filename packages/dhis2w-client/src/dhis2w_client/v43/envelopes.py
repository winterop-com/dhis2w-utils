"""DHIS2 WebMessageResponse + ImportReport envelopes (shim over generated/v43/oas).

The raw shapes come from `/api/openapi.json#/components/schemas/{WebMessage,
ObjectReport, ImportReport, TypeReport, Stats, ErrorReport, ImportConflict,
ImportCount}` — see `dhis2w_client.generated.v43.oas`. This module re-exports
those classes under their domain names and adds the helper methods
(`created_uid`, `task_ref`, `object_report`, `import_count`, `import_report`,
`conflicts`, `conflict_rows`, `rejected_indexes`) on `WebMessageResponse`
that callers rely on.

Every POST/PUT/DELETE/PATCH through `/api/*` returns a `WebMessageResponse`.
Its `response` field carries an endpoint-specific payload; the helper methods
project it into the right typed shape (`ObjectReport` for CRUD, `ImportReport`
for `/api/metadata`, `ImportCount` for `/api/dataValueSets`, etc.).

DHIS2 uses TWO different error shapes depending on the endpoint:

- `/api/dataValueSets` + `/api/tracker` return `response.conflicts[]` — a
  flat list of `ImportConflict` rows. `conflicts()` returns these verbatim.
- `/api/metadata` returns `response.typeReports[*].objectReports[*].errorReports[*]`
  — a three-level tree tagging each error with the owning resource type +
  UID. `conflicts()` misses these entirely (they're not under
  `response.conflicts`).

`conflict_rows()` normalises both shapes into a uniform `ConflictRow` list so
CLI renderers can show a single Rich table regardless of the endpoint.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_client.generated.v43.oas import (
    ErrorReport,
    ImportConflict,
    ImportCount,
    ImportReport,
    ObjectReport,
    Stats,
    TypeReport,
    WebMessage,
)

# Conflict keeps the local name callers use for per-row rejection; OpenAPI
# names the wire schema `ImportConflict`. Alias so the public API is stable.
Conflict = ImportConflict


class ConflictRow(BaseModel):
    """Normalised conflict row — uniform across `/api/metadata` and `/api/dataValueSets`.

    `response.conflicts[]` (data-value / tracker) and
    `response.typeReports[*].objectReports[*].errorReports[*]` (metadata)
    both flatten to this shape via `WebMessageResponse.conflict_rows()`,
    so CLI renderers can print one Rich table regardless of the source.
    """

    model_config = ConfigDict(frozen=True)

    resource: str | None = None
    """Resource type — `"DataElement"` / `"OrganisationUnit"` etc., stripped
    from DHIS2's fully-qualified `klass` strings.
    """

    uid: str | None = None
    """UID of the owning object (if DHIS2 surfaced one)."""

    property: str | None = None
    """Property that tripped the error — `"name"`, `"categoryCombo"`, etc."""

    value: str | None = None
    """Offending value, or rich context DHIS2 tucked on `value` / `objects`."""

    error_code: str | None = None
    """DHIS2 error code — `E4003`, `E5003`, etc. Stable across versions."""

    message: str | None = None
    """Human-readable error message DHIS2 rendered (includes args substituted)."""

    indexes: list[int] | None = None
    """Payload-array indexes the conflict applies to (data-value / tracker imports)."""


class WebMessageResponse(WebMessage):
    """DHIS2 write-response envelope with typed helper accessors.

    Inherits every wire field from `WebMessage` (`httpStatus`, `httpStatusCode`,
    `status`, `code`, `message`, `devMessage`, `errorCode`, `response`) and adds
    helper methods that project the endpoint-specific `response` dict into the
    right typed shape.
    """

    @property
    def created_uid(self) -> str | None:
        """Pull `response.uid` when the inner envelope is an ObjectReport.

        DHIS2's ObjectReport names the created identifier `uid` (not `id`) —
        see BUGS.md #4f. This property hides the defensive lookup.
        """
        if self.response is None:
            return None
        uid = self.response.get("uid") or self.response.get("id")
        return str(uid) if uid else None

    def task_ref(self) -> tuple[str, str] | None:
        """Return `(job_type, task_uid)` when DHIS2 returned a job-kickoff envelope.

        Every `/api/*/async` or `/api/resourceTables/analytics`-style endpoint
        returns a `JobConfigurationWebMessageResponse` with `response.jobType`
        and `response.id`. Callers that want to watch the job to completion
        feed this tuple to `maintenance.service.watch_task`.
        """
        if self.response is None:
            return None
        job_type = self.response.get("jobType")
        task_uid = self.response.get("id")
        if isinstance(job_type, str) and isinstance(task_uid, str):
            return job_type, task_uid
        return None

    def notifier_endpoint(self) -> str | None:
        """Return `response.relativeNotifierEndpoint` when DHIS2 returned a job-kickoff envelope.

        A job-scheduling endpoint (`/api/resourceTables/analytics`, an async
        import) sets `response.relativeNotifierEndpoint` to the
        `/api/system/tasks/{jobType}/{id}` path its notifications stream from.
        `task_ref()` gives the same `(job_type, task_uid)` as a tuple; this
        returns the ready-made path when a caller wants it verbatim.
        """
        if self.response is None:
            return None
        endpoint = self.response.get("relativeNotifierEndpoint")
        return str(endpoint) if isinstance(endpoint, str) else None

    def object_report(self) -> ObjectReport | None:
        """Validate `response` as an `ObjectReport` — useful after single-object CRUD."""
        return ObjectReport.model_validate(self.response) if self.response else None

    def import_count(self) -> ImportCount | None:
        """Validate `response` (or `response.importCount`) as an `ImportCount`.

        DHIS2 uses two shapes for the counts: some endpoints inline them at
        `response.imported` / `response.updated` / ...; others nest them under
        `response.importCount = {...}`. Both reach the same parsed model.
        """
        if not self.response:
            return None
        nested = self.response.get("importCount")
        if isinstance(nested, dict):
            return ImportCount.model_validate(nested)
        return ImportCount.model_validate(self.response)

    def import_report(self) -> ImportReport | None:
        """Validate `response` as an `ImportReport` — useful after metadata bulk imports."""
        return ImportReport.model_validate(self.response) if self.response else None

    def conflicts(self) -> list[Conflict]:
        """Pull `response.conflicts[]` — per-row rejections from a data-value or tracker import.

        Does NOT surface metadata-import errors (those live under
        `response.typeReports[*].objectReports[*].errorReports[*]` instead).
        Use `conflict_rows()` for a uniform view across both shapes.
        """
        if not self.response:
            return []
        raw = self.response.get("conflicts") or []
        if not isinstance(raw, list):
            return []
        return [Conflict.model_validate(item) for item in raw]

    def conflict_rows(self) -> list[ConflictRow]:
        """Return every error / conflict on the envelope, normalised to `ConflictRow`.

        Walks both DHIS2 shapes and merges:

        - Flat `response.conflicts[]` (data-value / tracker imports) — each
          entry becomes one row with `property` + `value` + `error_code` +
          `indexes` populated.
        - Nested `response.typeReports[*].objectReports[*].errorReports[*]`
          (metadata imports) — each `ErrorReport` becomes one row with
          `resource` (from the owning `TypeReport.klass`), `uid` (from the
          `ObjectReport`), `property` (`errorProperty`), `error_code`, and
          `message` all set.

        Empty list on a clean response. The flat list is stable across the
        two input shapes so CLI renderers can print one Rich table.
        """
        return [*self._flat_conflict_rows(), *self._metadata_error_rows()]

    def _flat_conflict_rows(self) -> list[ConflictRow]:
        """Surface `response.conflicts[]` — the data-value / tracker shape."""
        if not self.response:
            return []
        raw = self.response.get("conflicts") or []
        if not isinstance(raw, list):
            return []
        rows: list[ConflictRow] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            rows.append(
                ConflictRow(
                    resource=_strip_klass(item.get("object") if isinstance(item.get("object"), str) else None),
                    uid=None,
                    property=item.get("property") if isinstance(item.get("property"), str) else None,
                    value=item.get("value") if isinstance(item.get("value"), str) else None,
                    error_code=item.get("errorCode") if isinstance(item.get("errorCode"), str) else None,
                    message=None,
                    indexes=item.get("indexes") if isinstance(item.get("indexes"), list) else None,
                ),
            )
        return rows

    def _metadata_error_rows(self) -> list[ConflictRow]:
        """Walk `response.typeReports[*].objectReports[*].errorReports[*]` — metadata shape."""
        if not self.response:
            return []
        type_reports = self.response.get("typeReports") or []
        if not isinstance(type_reports, list):
            return []
        rows: list[ConflictRow] = []
        for type_report in type_reports:
            if not isinstance(type_report, dict):
                continue
            resource = _strip_klass(type_report.get("klass") if isinstance(type_report.get("klass"), str) else None)
            for object_report in type_report.get("objectReports") or []:
                if not isinstance(object_report, dict):
                    continue
                uid = object_report.get("uid") if isinstance(object_report.get("uid"), str) else None
                for error_report in object_report.get("errorReports") or []:
                    if not isinstance(error_report, dict):
                        continue
                    rows.append(
                        ConflictRow(
                            resource=resource,
                            uid=uid,
                            property=error_report.get("errorProperty")
                            if isinstance(error_report.get("errorProperty"), str)
                            else None,
                            value=_best_error_value(error_report),
                            error_code=error_report.get("errorCode")
                            if isinstance(error_report.get("errorCode"), str)
                            else None,
                            message=error_report.get("message")
                            if isinstance(error_report.get("message"), str)
                            else None,
                            indexes=None,
                        ),
                    )
        return rows

    def rejected_indexes(self) -> list[int]:
        """Pull `response.rejectedIndexes[]` — payload-array indexes DHIS2 refused to import."""
        if not self.response:
            return []
        raw = self.response.get("rejectedIndexes") or []
        if not isinstance(raw, list):
            return []
        return [int(idx) for idx in raw if isinstance(idx, int)]


# Re-bound types for the static checker. `Any` kept so callers importing it
# from here (historical pattern) still work.
_ = Any


def _strip_klass(klass: str | None) -> str | None:
    """Pull the bare resource name from a Jackson fully-qualified klass string.

    `"org.hisp.dhis.dataelement.DataElement"` -> `"DataElement"`. Returns
    the input unchanged when it isn't a dotted path, and `None` through.
    """
    if klass is None:
        return None
    return klass.rsplit(".", 1)[-1] if "." in klass else klass


def _best_error_value(error_report: dict[str, Any]) -> str | None:
    """Pick a sensible `value` column for a metadata `ErrorReport`.

    DHIS2's ErrorReport carries several fields that could render as the
    "offending value". Priority order:
      1. `value` — present when DHIS2 tucked a full JSON-ish Object reference.
      2. `errorProperties` — typed args array DHIS2 substitutes into `message`;
         the first arg is usually the offending value (`"bjDvmb4bfuf"`,
         `"INVALID_VALUE"`, etc.).
      3. `args` — older alias for `errorProperties`.
      4. None when nothing is available.
    """
    value = error_report.get("value")
    if isinstance(value, str) and value:
        return value
    for key in ("errorProperties", "args"):
        extras = error_report.get(key)
        if isinstance(extras, list) and extras:
            first = extras[0]
            if isinstance(first, (str, int, float, bool)):
                return str(first)
    return None


__all__ = [
    "Conflict",
    "ConflictRow",
    "ErrorReport",
    "ImportCount",
    "ImportReport",
    "ObjectReport",
    "Stats",
    "TypeReport",
    "WebMessageResponse",
]
