"""CategoryOptionCombo read access — `Dhis2Client.category_option_combos`.

CategoryOptionCombos are the cells of the disaggregation matrix. DHIS2
generates and owns them — every CategoryCombo's options cross-product
materialises here on save, and aggregate data values key on the
resulting UIDs. Callers do not author CategoryOptionCombos directly;
they edit the parent CategoryCombo + its Categories' option lists and
DHIS2 regenerates the matrix.

This accessor is read-only: list / get / list-for-combo. For write
flows (creating combos, adding categories, polling the matrix
regeneration), reach for `Dhis2Client.category_combos`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_client.generated.v42.schemas import CategoryOptionCombo
from dhis2w_client.v42._collection import parse_collection

if TYPE_CHECKING:
    from dhis2w_client.v42.client import Dhis2Client

_COC_FIELDS: str = "id,name,code,categoryCombo[id,name],categoryOptions[id,name]"

_LIST_FOR_COMBO_PAGE_SIZE: int = 1000
"""Page size for `list_for_combo`'s pager walk — one request covers most combos."""


class CategoryOptionCombosAccessor:
    """`Dhis2Client.category_option_combos` — read-only access to the materialised matrix."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def list_all(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> list[CategoryOptionCombo]:
        """Page through every CategoryOptionCombo across every CategoryCombo."""
        raw = await self._client.get_raw(
            "/api/categoryOptionCombos",
            params={
                "fields": _COC_FIELDS,
                "page": str(page),
                "pageSize": str(page_size),
            },
        )
        return parse_collection(raw, "categoryOptionCombos", CategoryOptionCombo)

    async def get(self, uid: str) -> CategoryOptionCombo:
        """Fetch one CategoryOptionCombo by UID."""
        return await self._client.get(
            f"/api/categoryOptionCombos/{uid}", model=CategoryOptionCombo, params={"fields": _COC_FIELDS}
        )

    async def list_for_combo(self, combo_uid: str) -> list[CategoryOptionCombo]:
        """List every CategoryOptionCombo materialised by one CategoryCombo.

        Follows the pager envelope until exhausted, so large combos (a
        cross-product past `_LIST_FOR_COMBO_PAGE_SIZE` cells) come back
        complete rather than truncated at the first page.
        """
        combos: list[CategoryOptionCombo] = []
        page = 1
        while True:
            raw = await self._client.get_raw(
                "/api/categoryOptionCombos",
                params={
                    "fields": _COC_FIELDS,
                    "filter": f"categoryCombo.id:eq:{combo_uid}",
                    "page": str(page),
                    "pageSize": str(_LIST_FOR_COMBO_PAGE_SIZE),
                },
            )
            rows = parse_collection(raw, "categoryOptionCombos", CategoryOptionCombo)
            combos.extend(rows)
            pager = raw.get("pager")
            if isinstance(pager, dict) and "pageCount" in pager:
                if page >= int(pager["pageCount"] or 1):
                    break
            elif len(rows) < _LIST_FOR_COMBO_PAGE_SIZE:
                # No pager envelope — a short (or empty) page means we're done.
                break
            page += 1
        return combos


__all__ = [
    "CategoryOptionCombo",
    "CategoryOptionCombosAccessor",
]
