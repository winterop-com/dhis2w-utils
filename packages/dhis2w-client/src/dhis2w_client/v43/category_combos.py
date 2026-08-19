"""CategoryCombo authoring — `Dhis2Client.category_combos`.

A `CategoryCombo` is the disaggregation grid: an ordered list of
`Category`s whose cross-product of options materialises (server-side)
as the `CategoryOptionCombo` set that data values key on. Aggregate
data elements + data sets reference a CategoryCombo to declare what
their disaggregation looks like.

This module covers the CategoryCombo layer. The Category leaf ships in
`dhis2w_client.categories`; the auto-generated `CategoryOptionCombo`
matrix is exposed read-only in `dhis2w_client.category_option_combos`.

Server-side matrix generation: when a CategoryCombo is created or its
`categories` list changes, DHIS2 regenerates the CategoryOptionCombo
set in the background. The `wait_for_coc_generation` helper polls
`/api/categoryCombos/{uid}/categoryOptionCombos` until the expected
count lands — cold-start regen on a large combo can take tens of
seconds, especially under arm64 emulation of the linux/amd64 image.

Note on the wire field name: `/api/schemas/categoryCombo` reports
`fieldName='categories'` (correct English) on both v42 and v43. v42
also accepted the misspelled alias `categorys`, but v43 dropped the
alias and now silently ignores unknown fields, so writes need the
correct spelling. The generated `CategoryCombo` model uses
`categories`, and this accessor's payloads + field selectors do too.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from dhis2w_client.generated.v43.schemas import CategoryCombo
from dhis2w_client.v43._collection import parse_collection
from dhis2w_client.v43.envelopes import WebMessageResponse

if TYPE_CHECKING:
    from dhis2w_client.v43.client import Dhis2Client

_CATEGORY_COMBO_FIELDS: str = (
    "id,name,code,dataDimensionType,skipTotal,default,"
    "categories[id,name,categoryOptions[id,name]],"
    "categoryOptionCombos[id,name]"
)


class CategoryCombosAccessor:
    """`Dhis2Client.category_combos` — CRUD + ordered category membership + matrix-poll helper."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def list_all(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> list[CategoryCombo]:
        """Page through CategoryCombos with categories + COCs resolved inline."""
        raw = await self._client.get_raw(
            "/api/categoryCombos",
            params={
                "fields": _CATEGORY_COMBO_FIELDS,
                "page": str(page),
                "pageSize": str(page_size),
            },
        )
        return parse_collection(raw, "categoryCombos", CategoryCombo)

    async def get(self, uid: str) -> CategoryCombo:
        """Fetch one CategoryCombo by UID."""
        return await self._client.get(
            f"/api/categoryCombos/{uid}", model=CategoryCombo, params={"fields": _CATEGORY_COMBO_FIELDS}
        )

    async def create(
        self,
        *,
        name: str,
        categories: list[str],
        code: str | None = None,
        data_dimension_type: str = "DISAGGREGATION",
        skip_total: bool = False,
        uid: str | None = None,
    ) -> CategoryCombo:
        """Create a CategoryCombo with an ordered list of Category UIDs.

        `data_dimension_type` is `DISAGGREGATION` (the default — combos
        that participate in the data-value matrix) or `ATTRIBUTE` (combos
        used for attribute-option-combo metadata). `skip_total=True`
        omits the "total" CategoryOptionCombo aggregation row in
        downstream tables.

        DHIS2 regenerates the `CategoryOptionCombo` matrix server-side
        on save — call `wait_for_coc_generation(uid, expected_count)`
        after a large combo create to block until the matrix lands.
        """
        if not categories:
            raise ValueError("CategoryCombo requires at least one category UID")
        payload: dict[str, Any] = {
            "name": name,
            "dataDimensionType": data_dimension_type,
            "skipTotal": skip_total,
            "categories": [{"id": cat_uid} for cat_uid in categories],
        }
        if code:
            payload["code"] = code
        if uid:
            payload["id"] = uid
        envelope = await self._client.post("/api/categoryCombos", payload, model=WebMessageResponse)
        created_uid = envelope.created_uid or uid
        if not created_uid:
            raise RuntimeError("category-combo create did not return a uid")
        return await self.get(created_uid)

    async def update(self, combo: CategoryCombo) -> CategoryCombo:
        """PUT an edited CategoryCombo back. `combo.id` must be set."""
        if not combo.id:
            raise ValueError("update requires combo.id to be set")
        body = combo.model_dump(by_alias=True, exclude_none=True, mode="json")
        await self._client.put_raw(f"/api/categoryCombos/{combo.id}", body=body)
        return await self.get(combo.id)

    async def rename(
        self,
        uid: str,
        *,
        name: str | None = None,
        code: str | None = None,
    ) -> CategoryCombo:
        """Partial-update the label fields — read, mutate, PUT."""
        if name is None and code is None:
            raise ValueError("rename requires at least one of name / code")
        current = await self.get(uid)
        if name is not None:
            current.name = name
        if code is not None:
            current.code = code
        return await self.update(current)

    async def add_category(self, uid: str, category_uid: str) -> None:
        """Append a Category to this combo's ordered membership.

        DHIS2 preserves insertion order on the `categories` array — the
        order drives the CategoryOptionCombo matrix shape. Re-ordering
        requires a full PUT via `update(combo)` with the desired list.
        """
        await self._client.resources.category_combos.add_collection_item(uid, "categories", category_uid)

    async def remove_category(self, uid: str, category_uid: str) -> None:
        """Remove a Category from this combo's membership."""
        await self._client.resources.category_combos.remove_collection_item(uid, "categories", category_uid)

    async def wait_for_coc_generation(
        self,
        uid: str,
        *,
        expected_count: int,
        timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 1.0,
    ) -> int:
        """Block until the CategoryOptionCombo matrix reaches `expected_count`.

        DHIS2 regenerates the COC matrix in the background on every
        CategoryCombo save, so this method polls
        `client.category_option_combos.list_for_combo(uid)` until the
        count matches `expected_count`. On cold-start or under arm64
        emulation a large combo's regen can take tens of seconds.

        Raises `TimeoutError` when `timeout_seconds` elapses without
        reaching the expected count. Returns the final count.
        """
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            current = len(await self._client.category_option_combos.list_for_combo(uid))
            if current >= expected_count:
                return current
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(
                    f"category-combo {uid}: expected {expected_count} categoryOptionCombos, "
                    f"have {current} after {timeout_seconds:.0f}s",
                )
            await asyncio.sleep(poll_interval_seconds)

    async def delete(self, uid: str) -> None:
        """Delete a CategoryCombo — DHIS2 rejects the default combo + combos in use."""
        if not uid:
            raise ValueError("delete requires a non-empty uid")
        await self._client.resources.category_combos.delete(uid)


__all__ = [
    "CategoryCombo",
    "CategoryCombosAccessor",
]
