"""Ask a running facade's `$evaluate` operation for an evaluation, and read the `Parameters` it answers.

`POST [base]/$evaluate` is the FHIR-native sibling of `POST /facade/evaluate`. Same three languages, same
three contexts, same engine - the difference is the answer: a `Parameters` resource with one
parameter per define, named by the define, which a FHIR client reads without learning a shape this
project invented. `/facade/evaluate` answers this project's own JSON and is what the capture UI reads;
`examples/fhir/client/evaluate_via_facade.py` is that endpoint.

What this file shows is how to read the answer, which is four rules and no more:

1. **One value rides the parameter itself** - `valueString`, `valueBoolean`, `valueInteger`,
   `valueDecimal`, or `resource` where the define answered a whole FHIR resource.
2. **Several values ride one `part` apiece**, each named `value`, because a parameter states one
   value and a collection is several.
3. **A define that refused carries an `OperationOutcome` part**, so the library's other defines
   still answer.
4. **A define that matched nothing carries no parameter at all** - FHIR has no empty collection.

The input is a `Parameters` resource too, which is what an operation takes: `language` and `source`
are required, `expression` names one define, and `context` names the one resource the expression may
reach.

Usage:
    d2w fhir serve --port 8123          # in the project directory, in another shell
    uv run python examples/fhir/client/evaluate_as_parameters.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on the
example project and stops it at exit - which is what lets this run unattended.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
from _fixture import served_facade
from _runner import run_example

#: A resource with nothing to do with DHIS2. The evaluator takes any FHIR JSON, which is what makes
#: an example like this runnable against any served guide.
PATIENT: dict[str, Any] = {
    "resourceType": "Patient",
    "id": "example",
    "active": True,
    "birthDate": "1815-12-10",
    "name": [{"given": ["Ada", "Byron"], "family": "Lovelace"}],
}

#: A library whose last define refuses on purpose, which is what makes the OperationOutcome part
#: visible: `Message(..., 'Error', ...)` is CQL's own way of stopping one define and only that one.
LIBRARY = """
library Example version '1.0'
using FHIR version '4.0.1'

define Person: First([Patient])
define Given: (Person.name) N return N.given
define IsActive: Person.active
define Unmapped: Message('x', true, 'no-mapping', 'Error', 'nothing maps this question')
"""


async def main() -> None:
    """Run one CQL library and one FHIRPath expression through `$evaluate`, and read the answers."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        print(f"evaluating against {base_url}")

        # The operation is declared in the conformance document, at the server-level slot: its URL is
        # the service base's, because what it runs over is whatever the request names as its context.
        metadata = (await client.get("/metadata")).raise_for_status().json()
        declared = [operation["name"] for operation in metadata["rest"][0].get("operation", [])]
        print(f"  /metadata declares at the service base: {', '.join(declared) or '(none)'}")

        # 1. A CQL library over a resource carried in the request. Every define the library declares
        #    answers a parameter of its own name, in declaration order.
        answered = await evaluate(client, ask("cql", LIBRARY, context=inline(PATIENT)))
        for parameter in answered.get("parameter", []):
            print(f"  {parameter['name']}: {said(parameter)}")

        # 2. One FHIRPath expression. It has no define name, so its parameter is named `expression` -
        #    and two given names are two `part` entries rather than one value that lost its shape.
        answered = await evaluate(client, ask("fhirpath", "Patient.name.given", context=inline(PATIENT)))
        for parameter in answered.get("parameter", []):
            print(f"  {parameter['name']}: {said(parameter)}")

        # 3. An expression that matches nothing. FHIR has no empty collection, so the answer carries
        #    no parameter at all - `POST /facade/evaluate` is where "matched nothing" stays a stated row.
        answered = await evaluate(client, ask("fhirpath", "Patient.telecom.value", context=inline(PATIENT)))
        print(f"  an expression that matched nothing: {len(answered.get('parameter', []))} parameter(s)")


def ask(language: str, source: str, *, context: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One `$evaluate` input as the Parameters resource the operation takes."""
    parameter: list[dict[str, Any]] = [
        {"name": "language", "valueCode": language},
        {"name": "source", "valueString": source},
    ]
    if context is not None:
        parameter.append({"name": "context", "part": context})
    return {"resourceType": "Parameters", "parameter": parameter}


def inline(resource: dict[str, Any]) -> list[dict[str, Any]]:
    """The `context` parts naming a resource carried in the request itself.

    The other two kinds are `stored` - `resourceType` and `resourceId`, one resource of the served
    guide - and `registered`, one tracked entity read from the DHIS2 instance a live facade holds
    open. There is no fourth kind: an expression reaches the context and nothing else.
    """
    return [{"name": "kind", "valueCode": "inline"}, {"name": "resource", "resource": resource}]


def said(parameter: dict[str, Any]) -> str:
    """One answered parameter as a line to read: the value, the resource, the parts, or the refusal."""
    refusal = refused(parameter)
    if refusal is not None:
        return f"refused - {refusal}"
    if "resource" in parameter:
        resource = parameter["resource"]
        return f"{resource['resourceType']}/{resource.get('id', '?')}"
    for key, value in parameter.items():
        if key.startswith("value"):
            return f"{value!r} ({key})"
    return ", ".join(said(part) for part in parameter.get("part", []))


def refused(parameter: dict[str, Any]) -> str | None:
    """Why this define answered nothing, where one of its parts is the OperationOutcome saying so."""
    for part in parameter.get("part", []):
        resource = part.get("resource", {})
        if resource.get("resourceType") == "OperationOutcome":
            return str(resource["issue"][0]["diagnostics"])
    return None


async def evaluate(client: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
    """One `POST /$evaluate`, raising only when the facade refused the request itself.

    A bad expression is not a refusal: it answers 200 with an `outcome` parameter carrying the line
    and column the parser stopped on. What raises here is a request this facade cannot serve at all -
    a stored resource it does not hold, a language it does not evaluate - which arrives as an
    OperationOutcome with a 4xx status.
    """
    answered = await client.post("/$evaluate", json=body, headers={"Content-Type": "application/fhir+json"})
    if answered.status_code != 200:
        print(f"  refused: {answered.text[:300]}")
        answered.raise_for_status()
    parameters: dict[str, Any] = answered.json()
    return parameters


if __name__ == "__main__":
    run_example(main)
