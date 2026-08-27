"""What DHIS2 said about a submission after `d2w fhir forward` drained the queue.

A receipt has three states, and only the facade's own listing can tell you which one a receipt is
in. Kept is not imported: a receipt sits in `received` from the moment the facade answered 201
until a drain moves it, and a drain moves it to `forwarded` when DHIS2 took the payload or to
`rejected` when DHIS2 refused it, writing what DHIS2 said beside it either way. Nothing about a
receipt disappears at any point - it stays readable in every state, because expiring the id a
client was handed at capture time would break that client on a schedule nothing told it about.

`GET /facade/spool` is a plain JSON listing, not a FHIR search, and that is a decision rather than an
oversight. The receipts themselves are `GET /QuestionnaireResponse` and always have been. What that
search cannot carry is the *envelope*: which state the receipt is in, what the facade had to warn
about, and the DHIS2 import counts or error rows the forwarder left beside it. None of those are
elements of a QuestionnaireResponse, and bending a DHIS2 import summary into FHIR would spread one
record across a resource, a tag nobody publishes, and a second operation.

Usage:
    d2w fhir forward --import             # in the project directory, to give the states meaning
    uv run python examples/fhir/client/read_receipt_verdict.py
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from _fixture import served_facade

FHIR_JSON = "application/fhir+json"


def verdict(row: dict[str, Any]) -> str:
    """One line saying what became of one receipt, in the words its state earns."""
    imported = row.get("imported")
    rejection = row.get("rejection")
    if imported is not None:
        return (
            f"DHIS2 took it: created {imported['created']}, updated {imported['updated']}, "
            f"ignored {imported['ignored']}"
        )
    if rejection is not None:
        reasons = "; ".join(
            f"[{issue.get('error_code') or 'no code'}] {issue.get('message')}" for issue in rejection["issues"][:3]
        )
        return f"DHIS2 refused it: {rejection.get('message') or rejection.get('status')} - {reasons}"
    return "not yet sent to DHIS2"


async def main() -> None:
    """Read the queue's verdict on every receipt, then read one receipt back in whatever state it is in."""
    async with httpx.AsyncClient(base_url=served_facade(), timeout=30.0) as client:
        listing = (
            (await client.get("/facade/spool", params={"_count": 50}, headers={"Accept": "application/json"}))
            .raise_for_status()
            .json()
        )
        counts = listing["counts"]
        print(f"{listing['total']} receipt(s) in this project's queue")
        print(f"  {counts['received']} not yet sent to DHIS2")
        print(f"  {counts['forwarded']} accepted by DHIS2")
        print(f"  {counts['rejected']} refused by DHIS2")
        print(f"  {counts['malformed']} unreadable - files that do not parse as a receipt at all")

        for row in listing["responses"]:
            where = row["organisation_unit"] or row["tracked_entity"] or "-"
            print(f"\n{row['response_id']}  {row['lifecycle']}")
            print(f"  {row['form_kind']} form {row['questionnaire_id']}, {row['answer_count']} value(s) at {where}")
            print(f"  period {row['period'] or '-'}, received {row['received_at']}")
            for warning in row["warnings"]:
                print(f"  noted at capture: {warning}")
            print(f"  {verdict(row)}")

        if not listing["responses"]:
            print("\nnothing captured yet - post a submission first")
            return

        # A receipt is readable in every state. This one may have been drained since it was
        # captured; the id it was handed at capture time still answers, and still answers with the
        # submission as it arrived rather than with anything DHIS2 now holds.
        first = listing["responses"][0]
        receipt = (
            (await client.get(f"/QuestionnaireResponse/{first['response_id']}", headers={"Accept": FHIR_JSON}))
            .raise_for_status()
            .json()
        )
        print(f"\nGET /QuestionnaireResponse/{receipt['id']} while it is `{first['lifecycle']}`: 200")
        print(f"  it still reads as the submission that was sent, answering {receipt['questionnaire']}")


if __name__ == "__main__":
    asyncio.run(main())
