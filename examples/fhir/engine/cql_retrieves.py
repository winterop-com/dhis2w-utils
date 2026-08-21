"""Read data from CQL with a retrieve: `[Patient]`, `[Immunization]`, and what a context narrows.

A retrieve is CQL's only way to reach data. `[Immunization]` means "every Immunization the data
source holds", and it is deliberately not a query language: the filtering vocabulary is small, and
everything else is done by CQL expressions over what came back.

What a retrieve reaches is decided entirely by the data source handed to the evaluator.
`BundleDataSource` indexes one Bundle by resource type; `PatientBundleDataSource` does the same for a
Bundle that is about one person. Neither is a network call - retrieves answer out of memory.

The other half of a retrieve is the *context*. Under `context Patient` the engine evaluates the
library once per person, and a retrieve inside it sees only that person's resources - which the
engine works out by following each resource type's patient reference element, a fact it reads off the
FHIR version binding rather than knowing itself.

Usage:
    uv run python examples/fhir/engine/cql_retrieves.py

Needs no DHIS2, no server, and no project: the Bundle is inline.
"""

from __future__ import annotations

from typing import Any

from _bundle import PATIENTS, clinic_bundle
from dhis2w_fhir_engine import CQLEvaluator
from dhis2w_fhir_engine.r4 import BundleDataSource
from pydantic import BaseModel

UNSCOPED_LIBRARY = """
library Retrieves version '1.0'
using FHIR version '4.0.1'

define "Every Child": [Patient]
define "Every Dose": [Immunization]
define "Every Weight": [Observation]
define "Dose Count": Count([Immunization])
define "Children With A Dose":
    [Immunization] I return I.patient.reference
"""

PER_PERSON_LIBRARY = """
library PerPerson version '1.0'
using FHIR version '4.0.1'
context Patient

define "Doses For This Child": [Immunization]
define "Weights For This Child": [Observation]
define "Vaccinated": exists [Immunization]
"""


class PersonRetrieveResult(BaseModel):
    """What the per-person library said about one child."""

    patient_identifier: str
    dose_count: int
    weight_count: int
    vaccinated: bool

    def rendered(self) -> str:
        """The line as it prints: the child, then what the retrieves inside their context reached."""
        verdict = "vaccinated" if self.vaccinated else "no dose recorded"
        return f"  {self.patient_identifier:10} {self.dose_count} dose(s), {self.weight_count} weight(s)  {verdict}"


def _identifiers(resources: list[dict[str, Any]]) -> list[str]:
    """The `id` of every resource a retrieve returned."""
    return [resource["id"] for resource in resources]


def main() -> None:
    """Run unscoped retrieves over the whole Bundle, then the same retrieves once per child."""
    data_source = BundleDataSource(clinic_bundle())

    unscoped = CQLEvaluator(data_source=data_source)
    unscoped.compile(UNSCOPED_LIBRARY)

    print("retrieves with no context - everything the data source holds of that type:")
    print(f"  [Patient]       -> {_identifiers(unscoped.evaluate_definition('Every Child'))}")
    print(f"  [Immunization]  -> {_identifiers(unscoped.evaluate_definition('Every Dose'))}")
    print(f"  [Observation]   -> {_identifiers(unscoped.evaluate_definition('Every Weight'))}")
    print(f"  Count([Immunization]) -> {unscoped.evaluate_definition('Dose Count')}")
    # Four doses, three children: `return` is CQL's distinct-by-default qualifier, so the repeated
    # reference collapses without a `distinct` around it. `return all` is what keeps duplicates.
    print(f"  children reached by a dose -> {unscoped.evaluate_definition('Children With A Dose')}")
    print()

    per_person = CQLEvaluator(data_source=data_source)
    per_person.compile(PER_PERSON_LIBRARY)

    print("the same retrieves under `context Patient` - one evaluation per child:")
    for patient in PATIENTS:
        # The context resource names whose evaluation this is. Every retrieve inside it is filtered
        # to that person, by the reference element the FHIR version binding states for the type -
        # Immunization.patient, Observation.subject.
        result = PersonRetrieveResult(
            patient_identifier=patient["id"],
            dose_count=len(per_person.evaluate_definition("Doses For This Child", resource=patient)),
            weight_count=len(per_person.evaluate_definition("Weights For This Child", resource=patient)),
            vaccinated=bool(per_person.evaluate_definition("Vaccinated", resource=patient)),
        )
        print(result.rendered())

    print()
    print("Same library, same data source, different subject - a retrieve reads whatever the context is.")
    print("That is the whole mechanism a quality measure is built on.")


if __name__ == "__main__":
    main()
