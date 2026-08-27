"""Ask a running facade to evaluate an expression - one FHIRPath call and one CQL call, over plain HTTP.

`POST /facade/evaluate` is the facade's own endpoint, not FHIR: it answers `application/json` with typed
results and real diagnostics, because a parse error's line and column have nowhere to go in a
`Parameters` resource. So this needs httpx and a served project, and nothing else - no dhis2w
package, no DHIS2, no engine install of your own.

Two calls, which are the two shapes:

1. **FHIRPath over a resource you post.** `context.kind = "inline"` carries the resource in the
   request, so the expression is checked against exactly the document you have in front of you.
2. **CQL over the guide's own data.** A library whose `[Patient]` retrieve reads the Bundle posted as
   the context, answering one row per define it declares.

A third call is here on purpose: an expression that does not parse. It answers 200 with the line and
the column the parser stopped on, never a 500 - which is the whole reason this endpoint is worth
calling from a script rather than guessing at an expression in a text editor.

Usage:
    d2w fhir serve --port 8123          # in the project directory, in another shell
    uv run python examples/fhir/client/evaluate_via_facade.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on the
example project and stops it at exit - which is what lets this run unattended.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import httpx
from _fixture import served_facade

#: A resource with nothing to do with DHIS2. The evaluator takes any FHIR JSON, which is what makes
#: an example like this runnable against any served guide.
PATIENT: dict[str, Any] = {
    "resourceType": "Patient",
    "id": "example",
    "active": True,
    "birthDate": "1815-12-10",
    "name": [{"given": ["Ada", "Byron"], "family": "Lovelace"}],
}

#: The same person plus one condition, as the collection Bundle a CQL retrieve reads through.
BUNDLE: dict[str, Any] = {
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [
        {"resource": PATIENT},
        {"resource": {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/example"}}},
    ],
}

LIBRARY = """
library Example version '1.0'
using FHIR version '4.0.1'

define People: [Patient]
define HasCondition: exists [Condition]
define Greeting: 'hello'
"""


async def main() -> None:
    """Evaluate one FHIRPath expression, one CQL library, and one expression that will not parse."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        print(f"evaluating against {base_url}")

        # 1. FHIRPath over a resource carried in the request itself.
        answered = await evaluate(
            client,
            {
                "language": "fhirpath",
                "source": "Patient.name.given",
                "context": {"kind": "inline", "resource": PATIENT},
            },
        )
        for row in answered["results"]:
            print(f"  fhirpath {row['name']}: {len(row['values'])} match(es) - {row['values']}")

        # 2. CQL over a Bundle. Every define the library declares answers a row, in declaration order;
        #    `[Patient]` and `[Condition]` read through the Bundle posted as the context.
        answered = await evaluate(
            client,
            {"language": "cql", "source": LIBRARY, "context": {"kind": "inline", "resource": BUNDLE}},
        )
        print(f"  cql library declares: {', '.join(answered['definitions'])}")
        for row in answered["results"]:
            if row["refusal"] is not None:
                print(f"  cql {row['name']}: refused - {row['refusal']}")
                continue
            print(f"  cql {row['name']}: {row['values']}")

        # 3. An expression that will not parse. 200, with the position the parser stopped on - which
        #    is what a caller acts on, and what a 500 would have thrown away.
        answered = await evaluate(
            client,
            {
                "language": "fhirpath",
                "source": "Patient.name..given",
                "context": {"kind": "inline", "resource": PATIENT},
            },
        )
        for diagnostic in answered["diagnostics"]:
            place = f"line {diagnostic['line']}, column {diagnostic['column']}"
            print(f"  {diagnostic['kind']} error at {place}: {diagnostic['message'].splitlines()[0]}")


async def evaluate(client: httpx.AsyncClient, request: dict[str, Any]) -> dict[str, Any]:
    """One `POST /facade/evaluate`, raising only when the facade refused the request itself.

    A bad expression is not a refusal: it answers 200 with its diagnostics. What raises here is a
    request this facade cannot serve at all - a stored resource it does not hold, a register it does
    not publish - which arrives as an OperationOutcome with a 4xx status.
    """
    answered = await client.post("/facade/evaluate", json=request)
    if answered.status_code != 200:
        print(f"  refused: {answered.text[:300]}")
        answered.raise_for_status()
    body: dict[str, Any] = answered.json()
    return body


if __name__ == "__main__":
    asyncio.run(main())
