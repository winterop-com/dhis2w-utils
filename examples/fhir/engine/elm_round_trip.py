"""Compile CQL to ELM, read the ELM back, and check both give the same answers.

ELM is CQL after compilation: the same logic as a JSON tree, with every literal typed and every
reference resolved. It exists so that the language a human writes and the artifact a machine runs are
two different things - a measure is authored once in CQL, published as ELM, and executed by whichever
implementation the receiving system happens to run.

That makes ELM the interchange format, and it cuts both ways here:

* `ELMSerializer` turns CQL source into ELM JSON, so a library written against this engine can be
  handed to another implementation.
* `ELMEvaluator` loads ELM JSON and runs it, so a library compiled elsewhere runs here without ever
  being parsed as CQL.

This example does both in one pass and compares the answers, which is the check that matters: the
round trip is only worth anything if the numbers survive it.

Usage:
    uv run python examples/fhir/engine/elm_round_trip.py

Needs no DHIS2, no server, and no project: the library and its data are inline.
"""

from __future__ import annotations

import json
from typing import Any

from _bundle import clinic_bundle
from dhis2w_fhir_engine import CQLEvaluator, ELMEvaluator, ELMSerializer
from dhis2w_fhir_engine.r4 import BundleDataSource
from pydantic import BaseModel

LIBRARY_SOURCE = """
library RoundTrip version '1.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1'

codesystem SNOMED: 'http://snomed.info/sct'

define "Doses Expected": 4
define "Doses Per Child": 2
define "Total Doses": "Doses Expected" * "Doses Per Child"
define "Enough Doses": "Doses Expected" >= 3
define "Programme": 'Child Programme'
define "Dose Numbers": { 1, 2, 3 }
define "Label": 'doses expected: ' + ToString("Doses Expected")
define "Nothing Recorded": null
define "Is Nothing Recorded": "Nothing Recorded" is null
"""

#: The definitions compared across the two evaluators.
COMPARED_DEFINITIONS = (
    "Doses Expected",
    "Total Doses",
    "Enough Doses",
    "Programme",
    "Dose Numbers",
    "Label",
    "Is Nothing Recorded",
)


class RoundTripComparison(BaseModel):
    """One definition's answer from the CQL evaluator and from the ELM evaluator."""

    definition: str
    from_cql: str
    from_elm: str

    @property
    def agrees(self) -> bool:
        """Whether both evaluators said the same thing."""
        return self.from_cql == self.from_elm

    def rendered(self) -> str:
        """The line as it prints: the definition, both answers, and whether they matched."""
        verdict = "same" if self.agrees else "DIFFERENT"
        return f"  {self.definition:24} {self.from_cql:24} {self.from_elm:24} {verdict}"


def _library_section_names(elm: dict[str, Any], section: str) -> list[str]:
    """The `localIdentifier` or `name` of every entry in one `def`-wrapped ELM library section."""
    entries = elm["library"].get(section, {}).get("def", [])
    return [entry.get("localIdentifier") or entry.get("name") or entry.get("id", "?") for entry in entries]


def main() -> None:
    """Compile one library to ELM, run it from both sides, and compare every answer."""
    data_source = BundleDataSource(clinic_bundle())

    cql_evaluator = CQLEvaluator(data_source=data_source)
    cql_evaluator.compile(LIBRARY_SOURCE)

    # serialize_library_json compiles the CQL and writes standard ELM JSON - the artifact you would
    # publish, or hand to another CQL implementation.
    elm_json = ELMSerializer().serialize_library_json(LIBRARY_SOURCE)
    elm = json.loads(elm_json)

    identifier = elm["library"]["identifier"]
    print(f"CQL source -> ELM JSON: {len(elm_json)} characters")
    print(f"  identifier   {identifier['id']} version {identifier['version']}")
    print(f"  schema       {elm['library']['schemaIdentifier']['id']} {elm['library']['schemaIdentifier']['version']}")
    print(f"  usings       {_library_section_names(elm, 'usings')}")
    print(f"  includes     {_library_section_names(elm, 'includes')}")
    print(f"  codeSystems  {_library_section_names(elm, 'codeSystems')}")
    print(f"  statements   {[entry['name'] for entry in elm['library']['statements']['def']]}")
    print()

    # The ELM evaluator never sees the CQL. It reads the JSON the serializer wrote and runs that.
    elm_evaluator = ELMEvaluator(data_source=data_source)
    elm_evaluator.load(elm_json)

    print(f"definition               {'from CQL':24} {'from ELM':24} verdict")
    comparisons = [
        RoundTripComparison(
            definition=name,
            from_cql=str(cql_evaluator.evaluate_definition(name)),
            from_elm=str(elm_evaluator.evaluate_definition(name)),
        )
        for name in COMPARED_DEFINITIONS
    ]
    for comparison in comparisons:
        print(comparison.rendered())

    print()
    if not all(comparison.agrees for comparison in comparisons):
        raise SystemExit("the round trip changed an answer - that is a defect, not a rounding difference")
    print("Every answer survived the round trip, which is what makes ELM an interchange format")
    print("rather than a debugging dump: publish the ELM, and the logic travels with it.")


if __name__ == "__main__":
    main()
