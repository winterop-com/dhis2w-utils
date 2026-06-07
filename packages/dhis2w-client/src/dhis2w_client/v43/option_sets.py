"""Integration-grade helpers for DHIS2 OptionSets + Options.

Generic CRUD for option sets + individual options is covered by
`client.resources.option_sets` and `client.resources.options` (generated).
This accessor adds the workflow primitives external integrations
typically reach for:

- Resolve an OptionSet by its business **code** (external systems tend
  to know "VACCINE_TYPE", not the DHIS2 UID).
- Walk a set's options in sort order without the array-of-references
  hoop.
- Pinpoint a single option by code or display name without pulling the
  whole set into memory.
- **Idempotent bulk sync** — given a list of `(code, name)` pairs, add
  the new ones, update names on existing codes, optionally remove
  options missing from the spec. The canonical ETL pattern for
  keeping a DHIS2 controlled vocabulary in step with an external
  source of truth.

DHIS2 stores `sortOrder` as a 0-indexed integer matching array
position; the upsert helper writes it the same way, so round-tripping
through the server stays stable.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from dhis2w_client.generated.v43.common import Reference
from dhis2w_client.generated.v43.schemas import Option, OptionSet
from dhis2w_client.v43._collection import parse_collection
from dhis2w_client.v43.uids import generate_uid

if TYPE_CHECKING:
    from dhis2w_client.v43.client import Dhis2Client


class OptionSpec(BaseModel):
    """One option in a `upsert_options` spec — identified by business code."""

    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    sort_order: int | None = None


class UpsertReport(BaseModel):
    """Summary of an `upsert_options` run — codes grouped by the action taken."""

    model_config = ConfigDict(frozen=True)

    option_set_uid: str
    added: list[str]
    updated: list[str]
    removed: list[str]
    skipped: list[str]
    dry_run: bool


class OptionSetsAccessor:
    """`Dhis2Client.option_sets` — integration helpers over /api/optionSets + /api/options."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client — reuses its auth + HTTP pool for every request."""
        self._client = client

    async def list_all(self, *, page: int = 1, page_size: int = 50, include_options: bool = False) -> list[OptionSet]:
        """Page through OptionSets. `include_options=True` resolves each set's options inline."""
        fields = (
            "id,code,name,description,valueType,version,options[id,code,name,sortOrder]"
            if include_options
            else "id,code,name,valueType"
        )
        raw = await self._client.get_raw(
            "/api/optionSets",
            params={"fields": fields, "page": str(page), "pageSize": str(page_size)},
        )
        return parse_collection(raw, "optionSets", OptionSet)

    async def get_by_code(self, code: str, *, include_options: bool = True) -> OptionSet | None:
        """Fetch an OptionSet by its business code; return None if no match.

        External integrations routinely know a set by a stable code (e.g.
        `VACCINE_TYPE`) rather than the DHIS2 UID. `include_options=True`
        (default) pulls every option inline (id + code + name + sortOrder).
        Set `False` when you only need metadata for an existence check.
        """
        fields = (
            "id,code,name,description,valueType,version,options[id,code,name,sortOrder]"
            if include_options
            else "id,code,name,valueType"
        )
        raw = await self._client.get_raw(
            "/api/optionSets",
            params={"filter": f"code:eq:{code}", "fields": fields, "paging": "false"},
        )
        matches = raw.get("optionSets")
        if not isinstance(matches, list) or not matches:
            return None
        first = matches[0]
        if not isinstance(first, dict):
            return None
        return OptionSet.model_validate(first)

    async def list_options(self, option_set_uid: str) -> list[Option]:
        """Return every option in a set, ordered by `sortOrder` (ascending).

        Streams `/api/options?filter=optionSet.id:eq:{uid}` with paging off,
        so a set with 10,000 options still returns in one call. DHIS2
        enforces a practical ceiling on option-set size — if you're
        hitting it, use the generated accessor with explicit paging.
        Fields include `attributeValues` so `upsert_options` can preserve
        them when updating an option's name or sort order.
        """
        raw = await self._client.get_raw(
            "/api/options",
            params={
                "filter": f"optionSet.id:eq:{option_set_uid}",
                "fields": "id,code,name,sortOrder,optionSet[id],attributeValues[value,attribute[id]]",
                "order": "sortOrder:asc",
                "paging": "false",
            },
        )
        return parse_collection(raw, "options", Option)

    async def find_option(
        self,
        option_set_uid: str,
        *,
        option_code: str | None = None,
        option_name: str | None = None,
    ) -> Option | None:
        """Locate one option in a set by code or display name; None if not found.

        Exactly one of `option_code` / `option_name` must be provided.
        Filters run server-side — cheap for big sets. `option_code`
        matches via `:eq:` (exact); `option_name` uses `:eq:` too since
        display names are already unique within a set.
        """
        if (option_code is None) == (option_name is None):
            raise ValueError("find_option requires exactly one of `option_code` / `option_name`")
        property_filter = f"code:eq:{option_code}" if option_code is not None else f"name:eq:{option_name}"
        raw = await self._client.get_raw(
            "/api/options",
            params={
                "filter": [f"optionSet.id:eq:{option_set_uid}", property_filter],
                "fields": "id,code,name,sortOrder,optionSet[id]",
                "paging": "false",
            },
        )
        rows = raw.get("options")
        if not isinstance(rows, list) or not rows:
            return None
        first = rows[0]
        if not isinstance(first, dict):
            return None
        return Option.model_validate(first)

    async def upsert_options(
        self,
        option_set_uid: str,
        spec: Sequence[OptionSpec],
        *,
        remove_missing: bool = False,
        dry_run: bool = False,
    ) -> UpsertReport:
        """Reconcile the set's options against `spec`; return the diff as a typed report.

        For each entry in `spec`:

        - Code not in the current set → **ADD** (mints a UID, creates).
        - Code in the current set but name or sort order differs → **UPDATE**.
        - Code in the current set and fully matches → **SKIP** (no-op).

        If `remove_missing=True`, any current option whose code isn't in
        `spec` is **REMOVED**. Defaults off — the safer posture for
        ETL pipelines where the spec is a partial refresh rather than a
        full-catalogue replacement.

        `sort_order` on each `OptionSpec` is optional; missing values are
        filled in with the spec-list index (0-based, matching DHIS2's
        internal convention). Callers driving a reorder can pin explicit
        values.

        `dry_run=True` computes the report without writing anything.
        Useful for previewing the effect in CI pipelines.
        """
        duplicates = self._duplicate_codes(spec)
        if duplicates:
            raise ValueError(f"upsert spec has duplicate codes: {sorted(duplicates)}")

        current_options = await self.list_options(option_set_uid)
        current_by_code = {opt.code: opt for opt in current_options if opt.code is not None}
        spec_by_code = {entry.code: entry for entry in spec}

        added: list[str] = []
        updated: list[str] = []
        skipped: list[str] = []
        to_create: list[Option] = []
        to_update: list[Option] = []

        for index, entry in enumerate(spec):
            existing = current_by_code.get(entry.code)
            desired_sort_order = entry.sort_order if entry.sort_order is not None else index
            if existing is None:
                to_create.append(
                    Option(
                        id=generate_uid(),
                        code=entry.code,
                        name=entry.name,
                        sortOrder=desired_sort_order,
                        optionSet=Reference(id=option_set_uid),
                    ),
                )
                added.append(entry.code)
                continue
            if existing.name == entry.name and existing.sortOrder == desired_sort_order:
                skipped.append(entry.code)
                continue
            existing_id = existing.id
            if existing_id is None:
                # Defensive — the generated model types id as `str | None` but
                # every option fetched from DHIS2 carries one.
                skipped.append(entry.code)
                continue
            # Preserve attributeValues from the current option. A full POST on
            # `/api/metadata?importStrategy=CREATE_AND_UPDATE` replaces the
            # object wholesale; if we don't include the existing attribute
            # values, DHIS2 silently drops them. `list_options` above pulls
            # them in the fields selector specifically for this merge.
            attribute_values = getattr(existing, "attributeValues", None)
            update_kwargs: dict[str, Any] = {
                "id": existing_id,
                "code": entry.code,
                "name": entry.name,
                "sortOrder": desired_sort_order,
                "optionSet": Reference(id=option_set_uid),
            }
            if attribute_values:
                update_kwargs["attributeValues"] = attribute_values
            to_update.append(Option(**update_kwargs))
            updated.append(entry.code)

        removed: list[str] = []
        to_remove_uids: list[str] = []
        if remove_missing:
            for existing in current_options:
                if existing.code is None or existing.id is None:
                    continue
                if existing.code in spec_by_code:
                    continue
                to_remove_uids.append(existing.id)
                removed.append(existing.code)

        if not dry_run:
            bulk_writes = to_create + to_update
            if bulk_writes:
                await self._client.resources.options.save_bulk(bulk_writes)
            if to_remove_uids:
                # `DELETE /api/options/{uid}` returns 200 but leaves the option
                # in place on DHIS2 v42 — options are collection-owned by their
                # OptionSet and need the metadata-bundle DELETE path to actually
                # disappear. Documented in BUGS.md alongside the matching
                # `/api/metadata?importStrategy=DELETE` workaround.
                await self._client.metadata.delete_bulk("options", to_remove_uids)

        return UpsertReport(
            option_set_uid=option_set_uid,
            added=added,
            updated=updated,
            removed=removed,
            skipped=skipped,
            dry_run=dry_run,
        )

    @staticmethod
    def _duplicate_codes(spec: Sequence[OptionSpec]) -> set[str]:
        """Return codes that appear more than once in `spec` — callers must not pass these."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for entry in spec:
            if entry.code in seen:
                duplicates.add(entry.code)
            seen.add(entry.code)
        return duplicates

    # -----------------------------------------------------------------------
    # Attribute-value helpers — option-specific delegators
    #
    # Cross-resource helpers live on `client.attribute_values`; these methods
    # are thin, Option-typed convenience wrappers around the generic accessor
    # for the integration flow that started this whole thread (SNOMED /
    # LOINC / ICD-10 mapping on OptionSet members).
    # -----------------------------------------------------------------------

    async def get_option_attribute_value(
        self,
        option_uid: str,
        attribute_code_or_uid: str,
    ) -> str | None:
        """Read one attribute value off an Option; None if the attribute isn't set."""
        return await self._client.attribute_values.get_value(
            "options",
            option_uid,
            attribute_code_or_uid,
        )

    async def set_option_attribute_value(
        self,
        option_uid: str,
        attribute_code_or_uid: str,
        value: str,
    ) -> None:
        """Set / replace one attribute value on an Option (read-merge-write)."""
        await self._client.attribute_values.set_value(
            "options",
            option_uid,
            attribute_code_or_uid,
            value,
        )

    async def find_option_by_attribute(
        self,
        option_set_uid: str,
        attribute_code_or_uid: str,
        value: str,
    ) -> Option | None:
        """Reverse lookup — find the Option in a set whose attribute matches a value.

        Thin wrapper over `client.attribute_values.find_one_uid_by_value(...)`
        that scopes the query to one OptionSet (`extra_filters` narrows the
        search) and returns a typed `Option` model. On miss returns None.
        """
        matched_uid = await self._client.attribute_values.find_one_uid_by_value(
            "options",
            attribute_code_or_uid,
            value,
            extra_filters=[f"optionSet.id:eq:{option_set_uid}"],
        )
        if matched_uid is None:
            return None
        raw = await self._client.get_raw(
            f"/api/options/{matched_uid}",
            params={"fields": "id,code,name,sortOrder,optionSet[id],attributeValues[value,attribute[id]]"},
        )
        return Option.model_validate(raw)


__all__ = [
    "OptionSetsAccessor",
    "OptionSpec",
    "UpsertReport",
]
