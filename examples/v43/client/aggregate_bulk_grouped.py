"""Bulk dataValueSets push grouped by dataset — forward-compat across v41/v42/v43.

Demonstrates `client.data_values.import_grouped_by_dataset(values, ...)`
— required on v43 for any DataElement that belongs to multiple
DataSets (BUGS.md #35). v41/v42 also accept the explicit envelope
shape, so callers can write the same code on all three majors.

On v43 this is necessary: bare `/api/dataValueSets` POSTs that mix
values whose DEs belong to multiple DataSets get rejected with
`409 E8002 Data set detection failed` (BUGS.md #35). v41 + v42
silently auto-target one of the matching DataSets, but they ALSO
accept the explicit envelope — so this code path works unchanged
when the target upgrades.

This file lives in `examples/v43/client/` and runs against a v41
stack; identical code lives in `examples/v42/client/` and
`examples/v43/client/` (only the version-pinned `dhis2w_client.v{N}`
import differs).

Usage:
    uv run python examples/v43/client/aggregate_bulk_grouped.py

Requires: a stack with at least one DataSet that has both
DataElements + OrganisationUnits attached (the seeded Sierra Leone
fixture qualifies).
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client.v43 import DataValue
from dhis2w_core.profile import profile_from_env
from dhis2w_core.v43.client_context import open_client
from pydantic import BaseModel


class _RefById(BaseModel):
    """Typed view of `{id: ...}` envelopes — `DataSet.organisationUnits` is `list[Any]` in the generated model."""

    id: str


async def main() -> None:
    """Build 3 typed DataValues and push them grouped by DataSet (v43 — necessary, not optional)."""
    async with open_client(profile_from_env()) as client:
        # Walk DataSets and pick the first one whose categoryCombo is default —
        # v43 enforces `E8023 Data set not usable with attribute option combo`
        # when the posted attributeOptionCombo doesn't match the DataSet's CC,
        # so the default AOC below (`HllvX50cXC0`) only works for default-CC
        # DataSets. v41/v42 silently accepted any AOC. (BUGS.md #41)
        # DataSet.categoryCombo[id,isDefault] is filtered client-side rather
        # than server-side via `categoryCombo.isDefault:eq:true` because v41
        # rejects that filter shape with 400.
        ds_rows = await client.resources.data_sets.list(
            fields="id,periodType,categoryCombo[id,isDefault],dataSetElements[dataElement[id,categoryCombo[id]]],organisationUnits[id]",
            # v41 rejects `:!empty` with `E1003 "!empty" is not a valid operator`;
            # `:gt:0` (count > 0) is the cross-version-compatible shape.
            filters=["dataSetElements:gt:0", "organisationUnits:gt:0"],
            page_size=50,
        )
        ds = next(
            (
                row
                for row in ds_rows
                if row.categoryCombo and (row.categoryCombo.model_extra or {}).get("isDefault") is True
            ),
            None,
        )
        if ds is None:
            print("no default-CC DataSet with DEs + OUs — skipping bulk demo")
            return
        de_uid: str | None = None
        de_cc_id: str | None = None
        for dse in ds.dataSetElements or []:
            if not dse.dataElement or not dse.dataElement.id:
                continue
            de_uid = dse.dataElement.id
            cc_ref = (dse.dataElement.model_extra or {}).get("categoryCombo") or {}
            de_cc_id = cc_ref.get("id") if isinstance(cc_ref, dict) else None
            break
        ou_uid = _RefById.model_validate(ds.organisationUnits[0]).id if ds.organisationUnits else None
        if not de_uid or not ou_uid:
            print("first DataSet missing dataElement or orgUnit ref — skipping bulk demo")
            return

        # v43 also enforces `E8024 Data set + data element not usable with
        # category option combo` when the posted COC doesn't match the DE's
        # categoryCombo. So look up the DE's CC's first COC instead of
        # hardcoding the default — works on v41/v42 (any valid COC for the
        # DE's CC is accepted) and on v43 (matches the strict check).
        coc_uid = "HllvX50cXC0"
        if de_cc_id:
            cc_detail = await client.resources.category_combos.get(de_cc_id, fields="categoryOptionCombos[id]")
            for coc in cc_detail.categoryOptionCombos or []:
                first_id = _RefById.model_validate(coc).id
                if first_id:
                    coc_uid = first_id
                    break
        # Pick three distinct periods so each DataValue lands on its own key —
        # v43 rejects multiple values targeting the same data-value key in
        # one batch with `E8128 Value #N all affect the same data value`.
        periods = ["210701", "210702", "210703"] if str(ds.periodType) == "Monthly" else ["2107", "2108", "2109"]

        # Build typed DataValues — same shape across v41/v42/v43.
        values = [
            DataValue(
                dataElement=de_uid,
                period=period,
                orgUnit=ou_uid,
                categoryOptionCombo=coc_uid,
                attributeOptionCombo="HllvX50cXC0",
                value=str(value),
            )
            for period, value in zip(periods, (10, 20, 30), strict=True)
        ]

        # The grouped push pre-fetches DE→DataSet membership and chunks
        # by DataSet. Works on v41 + v42 + v43.
        responses = await client.data_values.import_grouped_by_dataset(values, chunk_size=10, force=True)
        for i, resp in enumerate(responses):
            count = resp.import_count()
            if count is not None:
                print(f"  chunk {i}: imported={count.imported} updated={count.updated} ignored={count.ignored}")
            else:
                print(f"  chunk {i}: {resp.status} (no import_count in envelope)")


if __name__ == "__main__":
    run_example(main)
