"""Validate a bundle without committing it — `client.metadata.dry_run`.

`importMode=VALIDATE` runs DHIS2's full preheat and validation pipeline over a
cross-resource bundle, returns the same `WebMessage` envelope a real import
would produce, and writes nothing. That makes it the gate to put in front of a
write: ask what the bundle would do, read the answer, then commit or fix.

An accepted bundle answers with the envelope: `import_report()`, its `stats`, and
what the run would have created. A refused one is a 409, so it arrives as a
`Dhis2ApiError` — and `error.web_message` parses the same envelope back out of
the error body, conflicts and all.

Usage:
    uv run python examples/client/metadata_dry_run.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import Dhis2ApiError, generate_uid

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.enums import AggregationType, DataElementDomain, ValueType
from dhis2w_client.generated.v42.schemas.data_element import DataElement
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Dry-run a bundle DHIS2 accepts, then one it refuses, and read the verdict off each."""
    async with open_client(profile_from_env()) as client:
        default_cc = await client.system.default_category_combo_uid()

        valid = [
            DataElement(
                id=generate_uid(),
                name=f"dry-run-demo {i}",
                shortName=f"drd-{i}",
                aggregationType=AggregationType.SUM,
                domainType=DataElementDomain.AGGREGATE,
                valueType=ValueType.NUMBER,
                categoryCombo={"id": default_cc},  # type: ignore[arg-type]
            )
            for i in range(3)
        ]

        print("--- a bundle DHIS2 accepts")
        envelope = await client.metadata.dry_run({"dataElements": valid})
        report = envelope.import_report()
        stats = report.stats if report else None
        print(f"  status={envelope.status}  would-create={stats.created if stats else '?'}")

        # Nothing was written, so those three names are still free — which is what
        # lets the next bundle reuse one of them to earn a refusal.
        print("\n--- a bundle DHIS2 refuses (two elements claim one name)")
        clashing = [element.model_copy(update={"id": generate_uid()}) for element in valid[:2]]
        clashing[1].name = clashing[0].name
        clashing[1].shortName = clashing[0].shortName
        try:
            await client.metadata.dry_run({"dataElements": clashing})
        except Dhis2ApiError as error:
            print(f"  refused with HTTP {error.status_code}")
            refusal = error.web_message
            report = refusal.import_report() if refusal else None
            stats = report.stats if report else None
            print(f"  status={refusal.status if refusal else '?'}  ignored={stats.ignored if stats else '?'}")
            # `conflict_rows()` is the uniform view: metadata refusals live under
            # `typeReports[*].objectReports[*].errorReports[*]`, where a data-value
            # import puts them in a flat `conflicts[]`. This reads both.
            for row in (refusal.conflict_rows() if refusal else [])[:3]:
                print(f"  refused {row.resource}/{row.uid} on {row.property} [{row.error_code}]")
        else:
            print("  this instance accepted the clash")


if __name__ == "__main__":
    run_example(main)
