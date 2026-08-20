"""Score a clinical quality measure: populations in, a FHIR MeasureReport out.

A quality measure is a fraction with the numerator and the denominator both written as logic. The
denominator is who should have had the thing done; the numerator is who did. Everything the standard
adds on top is about being precise on who is in which:

* **Initial population** - everyone the measure looks at before any narrowing.
* **Denominator** - who the measure holds to account.
* **Denominator exclusion** - people removed from the denominator outright.
* **Numerator** - the ones who met it.
* **Numerator exclusion** - people removed from the numerator, but left in the denominator.

`MeasureEvaluator` finds each of those by the conventional CQL definition name, so a library that
spells `define "Numerator"` needs no wiring at all. The scoring says what the counts mean:
*proportion* divides the numerator by the denominator and reports the fraction, while *cohort*
reports the membership and no fraction - a count of who qualified is the whole answer. Both are run
below over the same library, so the difference is the score line and nothing else.

The report that comes out is a typed model, and `to_fhir()` renders it as a FHIR R4 MeasureReport -
the resource an aggregator or a dashboard expects.

Usage:
    uv run python examples/fhir/engine/measure_report.py

Needs no DHIS2, no server, and no project: the cohort is inline.
"""

from __future__ import annotations

import json

from _bundle import PATIENTS, clinic_bundle
from dhis2w_fhir_engine.r4 import BundleDataSource, MeasureEvaluator, MeasureScoring, PopulationType
from pydantic import BaseModel

MEASURE_SOURCE = """
library MeaslesCoverage version '1.0'
using FHIR version '4.0.1'

context Patient

define "Initial Population":
    true

define "Denominator":
    "Initial Population"

define "Denominator Exclusion":
    Patient.gender = 'unknown'

define "Numerator":
    exists [Immunization]
"""

#: The populations this measure declares, in the order a reader wants them narrated.
REPORTED_POPULATIONS = (
    PopulationType.INITIAL_POPULATION,
    PopulationType.DENOMINATOR,
    PopulationType.DENOMINATOR_EXCLUSION,
    PopulationType.NUMERATOR,
)


class PopulationLine(BaseModel):
    """One population's count and the people the evaluator put in it."""

    population: str
    count: int
    patient_identifiers: list[str]

    def rendered(self) -> str:
        """The line as it prints: the population, its count, then who is in it."""
        members = ", ".join(self.patient_identifiers) if self.patient_identifiers else "-"
        return f"  {self.population:22} {self.count:2}   {members}"


def main() -> None:
    """Load one measure, score it over the whole cohort, and render the FHIR MeasureReport."""
    data_source = BundleDataSource(clinic_bundle())

    evaluator = MeasureEvaluator(data_source=data_source)
    evaluator.set_scoring(MeasureScoring.PROPORTION)
    # load_measure compiles the library and reads its population definitions off the conventional
    # names. Nothing else declares which define is the numerator.
    evaluator.load_measure(MEASURE_SOURCE)

    report = evaluator.evaluate_population(PATIENTS, data_source=data_source)
    group = report.groups[0]

    print(f"measure {report.measure_id}, scored as a {MeasureScoring.PROPORTION.value}")
    print(f"{len(report.patient_results)} people evaluated, one at a time under `context Patient`")
    print()
    print("population              n   who")
    for population in REPORTED_POPULATIONS:
        count = group.populations[population.value]
        print(
            PopulationLine(
                population=population.value,
                count=count.count,
                patient_identifiers=list(count.patients),
            ).rendered()
        )

    print()
    numerator = group.populations[PopulationType.NUMERATOR.value].count
    denominator = group.populations[PopulationType.DENOMINATOR.value].count
    print(f"measure score = numerator / denominator = {numerator} / {denominator} = {group.measure_score}")
    print()

    print("per person, as the evaluator decided it:")
    for result in report.patient_results:
        memberships = [name for name, member in result.populations.items() if member]
        print(f"  {result.patient_id:10} {', '.join(memberships)}")

    print()
    fhir_report = report.to_fhir()
    populations = {
        entry["code"]["coding"][0]["code"]: entry["count"] for entry in fhir_report["group"][0]["population"]
    }
    print(f"to_fhir() -> a {fhir_report['resourceType']}, status {fhir_report['status']}, type {fhir_report['type']}")
    print(f"  measure   {fhir_report['measure']}")
    print(f"  counts    {json.dumps(populations)}")
    print(f"  score     {fhir_report['group'][0]['measureScore']['value']}")
    print()

    # The same library under cohort scoring: the memberships are identical, and there is no fraction
    # to report, because a cohort measure's answer is who qualified rather than what share did.
    cohort_evaluator = MeasureEvaluator(data_source=data_source)
    cohort_evaluator.set_scoring(MeasureScoring.COHORT)
    cohort_evaluator.load_measure(MEASURE_SOURCE)
    cohort_group = cohort_evaluator.evaluate_population(PATIENTS, data_source=data_source).groups[0]
    cohort_counts = {name: count.count for name, count in cohort_group.populations.items()}
    print(f"the same library scored as a {MeasureScoring.COHORT.value}:")
    print(f"  counts    {json.dumps(cohort_counts)}")
    print(f"  score     {cohort_group.measure_score}   (a cohort reports membership, not a fraction)")
    print()
    print("The MeasureReport is the deliverable: the logic stays in the library, the answer travels as FHIR.")


if __name__ == "__main__":
    main()
