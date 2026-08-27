"""Read the contract off the server, then satisfy it - `OperationDefinition/serve-evaluate` and `$evaluate`.

A FHIR operation is discoverable rather than documented elsewhere. `/metadata` names it, an
`OperationDefinition` states its parameters and their cardinalities, and a client that can read both
can call the operation without ever being told about it out of band. This walks that chain end to
end against a running facade: find the operation, read its definition, build a request the definition
describes, and read the `Parameters` that comes back.

Three things the definition tells you that a hand-written note would have to repeat:

1. **What is required.** `language` and `source` are 1..1; `expression` and `context` are 0..1. A
   request missing a required parameter is refused before anything is evaluated.
2. **How a context is named.** `context` has no value of its own - it is parts, and which parts
   apply depends on the `kind` part. That is the whole of what an expression may reach.
3. **Where the answer's shape is stated.** `return` is 1..1 `Parameters`, which is why a define is a
   parameter, several values are `part` entries, and a refusal rides an `OperationOutcome`.

The parameter names here are camelCase - `resourceType`, `resourceId`, `expression` - because that is
what an operation's `Parameters` spells them as. `POST /facade/evaluate` takes the same three contexts under
this project's own snake_case names; `examples/fhir/client/evaluate_via_facade.py` is that endpoint,
and `examples/fhir/client/evaluate_as_parameters.py` reads the four rules of the answer shape.

Usage:
    d2w fhir serve --port 8123          # in the project directory, in another shell
    uv run python examples/fhir/client/evaluate_operation_contract.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on the
example project and stops it at exit - which is what lets this run unattended.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
from _fixture import aggregate_form_id, served_facade
from _runner import run_example

#: The id the operation's definition is served under, at the server's own base.
OPERATION_DEFINITION_ID = "serve-evaluate"

#: A small library whose defines answer three different value shapes, so the `Parameters` answer has
#: three different spellings to show: a string, a whole number, and a collection of several values.
LIBRARY = """
library FormReview version '1.0'
using FHIR version '4.0.1'

define "Form Title": [Questionnaire] Q return Q.title
define "Section Count": [Questionnaire] Q return Count(Q.item)
define "Section Names": flatten ([Questionnaire] Q return (Q.item) I return I.text)
"""


async def main() -> None:
    """Find the operation, read its definition, call it over a stored form, and read the Parameters back."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()
    form_id = aggregate_form_id()
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        print(f"evaluating against {base_url}")

        # 1. The conformance document names the operation and points at its definition. Nothing here
        #    is guessed: the canonical url comes off the server, and the read below follows it.
        metadata = (await client.get("/metadata")).raise_for_status().json()
        print()
        print("what /metadata declares at the service base:")
        for operation in metadata["rest"][0].get("operation", []):
            print(f"  ${operation['name']}  ->  {operation['definition']}")

        # 2. The definition itself, served like any other resource of the guide.
        definition = (await client.get(f"/OperationDefinition/{OPERATION_DEFINITION_ID}")).raise_for_status().json()
        print()
        print(f"OperationDefinition/{definition['id']}: {definition['title']}")
        print(f"  code ${definition['code']}, kind {definition['kind']}, system-level {definition['system']}")
        for parameter in definition["parameter"]:
            print(f"  {parameter['use']:3} {parameter['name']:11} {cardinality(parameter)} {parameter.get('type', '')}")
            for part in parameter.get("part", []):
                print(f"        part {part['name']:16} {cardinality(part)} {part.get('type', '')}")

        # 3. A request built to that contract: the two required parameters, and a context naming one
        #    resource this server already holds.
        print()
        print(f"calling $evaluate over the stored Questionnaire/{form_id}")
        answered = await evaluate(
            client,
            {
                "resourceType": "Parameters",
                "parameter": [
                    {"name": "language", "valueCode": "cql"},
                    {"name": "source", "valueString": LIBRARY},
                    {
                        "name": "context",
                        "part": [
                            {"name": "kind", "valueCode": "stored"},
                            {"name": "resourceType", "valueCode": "Questionnaire"},
                            {"name": "resourceId", "valueString": form_id},
                        ],
                    },
                ],
            },
        )
        print(f"  the answer is a {answered['resourceType']} of {len(answered.get('parameter', []))} parameter(s)")
        for parameter in answered.get("parameter", []):
            print(f"  {parameter['name']}: {said(parameter)}")

        # 4. The optional `expression` parameter narrows the same library to one define. The library
        #    is unchanged - what changes is how much of it the answer carries.
        print()
        print("the same library with expression = 'Section Count'")
        answered = await evaluate(
            client,
            {
                "resourceType": "Parameters",
                "parameter": [
                    {"name": "language", "valueCode": "cql"},
                    {"name": "source", "valueString": LIBRARY},
                    {"name": "expression", "valueString": "Section Count"},
                    {
                        "name": "context",
                        "part": [
                            {"name": "kind", "valueCode": "stored"},
                            {"name": "resourceType", "valueCode": "Questionnaire"},
                            {"name": "resourceId", "valueString": form_id},
                        ],
                    },
                ],
            },
        )
        for parameter in answered.get("parameter", []):
            print(f"  {parameter['name']}: {said(parameter)}")


def cardinality(parameter: dict[str, Any]) -> str:
    """One parameter's `min..max` as FHIR writes it, which is what says required from optional."""
    return f"{parameter.get('min', 0)}..{parameter.get('max', '*')}"


def said(parameter: dict[str, Any]) -> str:
    """One answered parameter as a line to read: the value, the resource, the parts, or the refusal."""
    for part in parameter.get("part", []):
        resource = part.get("resource", {})
        if resource.get("resourceType") == "OperationOutcome":
            return f"refused - {resource['issue'][0]['diagnostics']}"
    if "resource" in parameter:
        resource = parameter["resource"]
        return f"{resource['resourceType']}/{resource.get('id', '?')}"
    for key, value in parameter.items():
        if key.startswith("value"):
            return f"{value!r} ({key})"
    parts = parameter.get("part", [])
    return f"{len(parts)} part(s): " + ", ".join(said(part) for part in parts)


async def evaluate(client: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
    """One `POST /$evaluate`, raising only when the facade refused the request itself.

    A bad expression is not a refusal: it answers 200 with an `outcome` parameter carrying the line
    and column the parser stopped on. What raises here is a request this facade cannot serve at all -
    a stored resource it does not hold, a language it does not evaluate.
    """
    answered = await client.post("/$evaluate", json=body, headers={"Content-Type": "application/fhir+json"})
    if answered.status_code != 200:
        print(f"  refused: {answered.text[:300]}")
        answered.raise_for_status()
    parameters: dict[str, Any] = answered.json()
    return parameters


if __name__ == "__main__":
    run_example(main)
