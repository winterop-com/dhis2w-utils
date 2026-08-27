"""Publish a library as ELM and run it on the facade - the compiled artifact answering as the source did.

CQL is what a person writes; ELM is what a machine runs. A measure is authored once in CQL,
compiled, and published as ELM JSON, and any implementation that reads ELM can execute it without
ever parsing the language it was written in. That is what makes ELM the interchange format, and it
is why the facade takes `language: "elm"` alongside `language: "cql"`.

This runs the same library both ways against the same stored resource and compares them define by
define. The compile happens here, in the caller's own process, with `ELMSerializer` from
`dhis2w_fhir_engine` - so the only thing that crosses the wire is JSON, and the facade never sees the
CQL at all. `examples/fhir/engine/elm_round_trip.py` does the same comparison with no server in the
picture; this one is the served half of that story.

The ELM is parsed by the facade before the engine is handed it, and that is deliberate rather than
incidental: `ELMEvaluator.load` would open a string that names a file on disk, and a parsed object
names nothing. A `source` of `/etc/passwd` is JSON that will not parse.

WHAT THE ROUND TRIP DOES NOT CARRY YET is printed at the end rather than left out quietly. The
compared set below must agree exactly - this file exits 1 if it ever stops agreeing, because a
compiled library answering differently from its source is a defect and not a rounding difference.
The gaps are stated separately, each one demonstrated by the run rather than remembered from a note.

Usage:
    d2w fhir serve --port 8123          # in the project directory, in another shell
    uv run python examples/fhir/client/evaluate_compiled_library.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on the
example project and stops it at exit - which is what lets this run unattended.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx
from _fixture import aggregate_form_id, served_facade
from _runner import run_example
from dhis2w_fhir_engine import ELMSerializer

#: The library both runs evaluate, reaching past literals into retrieves, projections, a where
#: clause, counting, existence, string building, and a `case` - the constructs a published measure
#: is actually made of.
LIBRARY = """
library FormReview version '1.0'
using FHIR version '4.0.1'

define "Form Title": [Questionnaire] Q return Q.title
define "Form Name": [Questionnaire] Q return Q.name
define "Form Status": [Questionnaire] Q return Q.status
define "Reports At": [Questionnaire] Q return Q.subjectType
define "Section Count": [Questionnaire] Q return Count(Q.item)
define "Section Ids": [Questionnaire] Q return (Q.item) I return I.linkId
define "Is Draft": exists ([Questionnaire] Q where Q.status = 'draft')
define "Forms Seen": Count([Questionnaire])
define "Any Form": exists [Questionnaire]
define "Doses Expected": 4
define "Label": 'sections counted: ' + ToString(2)
define "Band": case when 2 >= 2 then 'has sections' else 'flat' end
"""

#: A second library, compiled and run the same way, holding only constructs the round trip drops.
#:
#: It is here so the gaps below are demonstrated by this run rather than asserted from memory. Every
#: define in it answers from CQL and answers differently from ELM, and that is the whole point of it.
GAP_LIBRARY = """
library Gaps version '1.0'
using FHIR version '4.0.1'

define "Flattened": flatten ([Questionnaire] Q return (Q.item) I return I.text)
define "First Title": First([Questionnaire] Q return Q.title)
define "Last Section": Last(flatten ([Questionnaire] Q return (Q.item) I return I.text))
define function "Shouted"(word String): word + '!'
define "Via A Function": "Shouted"('Child Health')
"""

#: What each gap is, in the words a caller needs to hear before publishing a library as ELM.
GAP_REASONS: dict[str, str] = {
    "Flattened": "flatten() is not applied - the compiled library answers the nested collection",
    "First Title": "First() answers nothing at all, whatever it is given",
    "Last Section": "Last() answers nothing at all, for the same reason",
    "Via A Function": "a `define function` call answers nothing - only its declaration survives",
}


async def main() -> None:
    """Compile one library to ELM, run source and compiled form over the same stored resource, compare."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()
    form_id = aggregate_form_id()
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        print(f"evaluating against {base_url}")
        print(f"both runs read the stored Questionnaire/{form_id} - same resource, same engine, two languages")

        # The compile is local. What the facade receives is ELM JSON and a context; it never parses
        # a line of CQL for this call, which is exactly the position a receiving system is in.
        elm_json = ELMSerializer().serialize_library_json(LIBRARY)
        library = json.loads(elm_json)["library"]
        print()
        print(f"CQL source -> ELM JSON: {len(elm_json)} characters")
        print(f"  identifier   {library['identifier']['id']} version {library['identifier']['version']}")
        print(f"  schema       {library['schemaIdentifier']['id']} {library['schemaIdentifier']['version']}")
        print(f"  statements   {[statement['name'] for statement in library['statements']['def']]}")

        from_cql = await evaluate(client, "cql", LIBRARY, form_id)
        from_elm = await evaluate(client, "elm", elm_json, form_id)

        print()
        print(f"  {'define':16} {'from CQL':40} {'from ELM':40} verdict")
        disagreed = []
        for name in from_cql["definitions"]:
            said_by_cql = answered(from_cql, name)
            said_by_elm = answered(from_elm, name)
            agrees = said_by_cql == said_by_elm
            if not agrees:
                disagreed.append(name)
            print(
                f"  {name:16} {rendered(said_by_cql):40} {rendered(said_by_elm):40} {'same' if agrees else 'DIFFERENT'}"
            )

        print()
        if disagreed:
            raise SystemExit(f"the round trip changed an answer for {disagreed} - that is a defect, not a difference")
        print("Every answer above survived the round trip, over a resource the server holds rather than")
        print("one this file made up. Publish the ELM and the logic travels with it.")

        # The same two runs over the library of constructs that do not survive. Nothing here is
        # remembered: each line is one comparison this run just made.
        gap_elm_json = ELMSerializer().serialize_library_json(GAP_LIBRARY)
        gap_from_cql = await evaluate(client, "cql", GAP_LIBRARY, form_id)
        gap_from_elm = await evaluate(client, "elm", gap_elm_json, form_id)
        print()
        print("What the round trip does not carry yet, demonstrated rather than quietly left out:")
        for name in gap_from_cql["definitions"]:
            said_by_cql = answered(gap_from_cql, name)
            said_by_elm = answered(gap_from_elm, name)
            if said_by_cql == said_by_elm:
                print(f"  - {name}: this run agreed, so the gap below has closed - update this example")
                continue
            print(f"  - {GAP_REASONS.get(name, name)}")
            print(f"      CQL said {rendered(said_by_cql)}, ELM said {rendered(said_by_elm)}")


async def evaluate(client: httpx.AsyncClient, language: str, source: str, resource_id: str) -> dict[str, Any]:
    """One library in one language over one resource the served guide already holds."""
    answered_by = await client.post(
        "/facade/evaluate",
        json={
            "language": language,
            "source": source,
            "context": {"kind": "stored", "resource_type": "Questionnaire", "resource_id": resource_id},
        },
    )
    if answered_by.status_code != 200:
        print(f"  refused: {answered_by.text[:300]}")
        answered_by.raise_for_status()
    body: dict[str, Any] = answered_by.json()
    for diagnostic in body["diagnostics"]:
        print(f"  {language} {diagnostic['kind']} error: {diagnostic['message'].splitlines()[0]}")
    return body


def answered(outcome: dict[str, Any], name: str) -> list[Any]:
    """What one named define answered in one run, as the collection every result is."""
    for row in outcome["results"]:
        if row["name"] == name:
            return list(row["values"])
    return []


def rendered(values: list[Any]) -> str:
    """One collection as a short line, so two of them fit side by side and stay comparable."""
    if not values:
        return "(nothing)"
    text = ", ".join(str(value) for value in values)
    return text if len(text) <= 38 else f"{text[:35]}..."


if __name__ == "__main__":
    run_example(main)
