"""Metadata query DSL — filters, rootJunction, order, server-side paging.

Shows the full DHIS2 `/api/<resource>` query surface through the generated
typed accessor: multiple `filter=` params combined via `rootJunction`,
multi-clause `order=`, explicit `page` + `pageSize`, and the "dump it all"
variant (`paging=False`).

Usage:
    uv run python examples/client/metadata_filter_order_paging.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Walk through the filter / order / paging surface on dataElements + orgUnits."""
    async with open_client(profile_from_env()) as client:
        # 1. Single filter.
        only_penta = await client.resources.data_elements.list(
            filters=["name:like:Penta"],
            fields="id,name",
        )
        print(f"name:like:Penta -> {len(only_penta)} elements")

        # 2. Multi-filter with OR junction (default is AND).
        penta_or_measles = await client.resources.data_elements.list(
            filters=["name:like:Penta", "code:eq:DE_MEASLES"],
            root_junction="OR",
            fields="id,name,code",
        )
        print(f"name:like:Penta OR code:eq:DE_MEASLES -> {len(penta_or_measles)} elements")

        # 3. Ordered + paged (server-side).
        sorted_ous = await client.resources.organisation_units.list(
            order=["level:asc", "name:asc"],
            page_size=5,
            page=2,
            fields="id,name,level",
        )
        print("\npage 2, 5/page, order=level:asc,name:asc:")
        for ou in sorted_ous:
            print(f"  level={ou.level}  id={ou.id}  name={ou.name}")

        # 4. paging=False — every row in one response. Use `list_raw` when you
        # want the `pager` metadata alongside the rows.
        all_des = await client.resources.data_elements.list(
            paging=False,
            fields=":identifiable",
        )
        print(f"\npaging=False, fields=:identifiable -> {len(all_des)} data elements (single request)")

        # 5. list_raw gives the envelope too.
        envelope = await client.resources.organisation_units.list_raw(
            page_size=3,
            page=1,
            fields="id,name",
        )
        pager = envelope.get("pager") or {}
        print(f"\npager: page={pager.get('page')}/{pager.get('pageCount')}  total={pager.get('total')}")


if __name__ == "__main__":
    run_example(main)
