"""Outlier detection + tracked-entity analytics — typed responses via the service layer.

Both endpoints return the Grid envelope (`Grid`) — headers
list + row arrays. Outlier detection adds statistical columns to each row
(`value`, `mean`, `stdDev`, `absDev`, `zScore`). Tracked-entity analytics
returns TE attributes per row.

Usage:
    uv run python examples/client/analytics_outlier_tracked_entities.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.profile import profile_from_env

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_core.v42.plugins.analytics import service


async def main() -> None:
    """Run one outlier query and one tracked-entity query against the default profile."""
    profile = profile_from_env()

    # 1. Outlier detection — narrow to Kambia, last 12 months.
    outliers = await service.query_outlier_detection(
        profile,
        data_sets=["BfMAe6Itzgt"],
        org_units=["PMa2VCrupOd"],
        periods="LAST_12_MONTHS",
        algorithm="Z_SCORE",
        threshold=2.0,
        max_results=5,
    )
    columns = [h.name for h in outliers.headers or []]
    print(f"outliers: {outliers.height} anomalies, columns={columns[:5]}...")
    # Map each row to a named dict for inspection.
    for row in (outliers.rows or [])[:3]:
        labelled = dict(zip(columns, row, strict=False))
        print(
            f"  {labelled.get('dxname', labelled.get('dx'))} / "
            f"{labelled.get('pe')} / {labelled.get('ouname', labelled.get('ou'))} "
            f"value={labelled.get('value')} zScore={labelled.get('zscore')}"
        )

    # 2. Tracked-entity analytics — list Person entities under Sierra Leone (descendants).
    response = await service.query_tracked_entities(
        profile,
        tracked_entity_type="nEenWmSyUEp",  # Person (Play) TET — Sierra Leone seed
        dimensions=["ou:ImspTQPwCqd"],
        ou_mode="DESCENDANTS",
        page_size=3,
        asc=["created"],
    )
    print(f"\ntracked entities: {response.height} rows × {response.width} columns")
    for row in (response.rows or [])[:3]:
        print(f"  {row}")


if __name__ == "__main__":
    run_example(main)
