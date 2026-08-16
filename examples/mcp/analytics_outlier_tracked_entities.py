"""Outlier detection + tracked-entity analytics via MCP tools.

Usage:
    uv run python examples/mcp/analytics_outlier_tracked_entities.py
"""

from __future__ import annotations

import asyncio

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def main() -> None:
    """Drive `analytics_outlier_detection` + `analytics_tracked_entities_query`."""
    async with Client(build_server()) as client:
        outliers = await client.call_tool(
            "analytics_outlier_detection",
            {
                "data_sets": ["BfMAe6Itzgt"],
                "org_units": ["PMa2VCrupOd"],
                "periods": "LAST_12_MONTHS",
                "algorithm": "Z_SCORE",
                "threshold": 2.0,
                "max_results": 5,
            },
        )
        payload = outliers.structured_content or {}
        meta = payload.get("metadata", {})
        print(f"outliers: algo={meta.get('algorithm')} count={meta.get('count')}")

        response = await client.call_tool(
            "analytics_tracked_entities_query",
            {
                "tracked_entity_type": "nEenWmSyUEp",
                "dimensions": ["ou:ImspTQPwCqd"],
                "ou_mode": "DESCENDANTS",
                "page_size": 3,
                "asc": ["created"],
            },
        )
        body = response.structured_content or {}
        print(f"tracked entities: {body.get('height')} rows x {body.get('width')} columns")


if __name__ == "__main__":
    asyncio.run(main())
