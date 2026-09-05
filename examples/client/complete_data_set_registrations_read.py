"""Read which forms are reported complete: `client.complete_data_set_registrations.export`.

DHIS2 keeps completeness separately from values. A registration says the
report for one data set, period, organisation unit, and attribute option
combination is finished, and who said so. This accessor reads those claims back
from `GET /api/completeDataSetRegistrations` as the same typed envelope the
write side posts.

Selects by a date range under the Sierra Leone root with `children=True`, so
the answer covers every facility below it.

Usage:
    uv run python examples/client/complete_data_set_registrations_read.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

DATA_SET_UID = "BfMAe6Itzgt"  # Child Health
ORG_UNIT_UID = "ImspTQPwCqd"  # Sierra Leone root


async def main() -> None:
    """List the completeness registrations filed for one data set over the last year."""
    today = datetime.now(tz=UTC).date()
    start_date = (today - timedelta(days=365)).isoformat()

    async with open_client(profile_from_env()) as client:
        envelope = await client.complete_data_set_registrations.export(
            data_set=DATA_SET_UID,
            org_unit=ORG_UNIT_UID,
            children=True,
            start_date=start_date,
            end_date=today.isoformat(),
        )
        registrations = envelope.completeDataSetRegistrations
        print(f"--- {len(registrations)} registrations for {DATA_SET_UID} since {start_date} ---")
        for registration in registrations[:5]:
            print(
                f"  {registration.period}  {registration.organisationUnit}  "
                f"completed {registration.date} by {registration.storedBy}"
            )


if __name__ == "__main__":
    run_example(main)
