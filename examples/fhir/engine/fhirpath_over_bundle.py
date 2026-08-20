"""Ask a whole Bundle a question with FHIRPath: pick a type out of it, filter it, and count.

A Bundle is the shape a FHIR server hands back a set of resources in, and it is what
`d2w fhir serve --live` builds out of a DHIS2 cohort. Every resource sits under `entry.resource`,
mixed together and in no particular order, so the first move of any expression over a Bundle is to
say which type you meant.

`ofType(Patient)` is that move. `where(...)` narrows further, and because a path keeps walking
whatever the previous step produced, one expression reaches from the Bundle down to a field on the
resources it selected - which is how a count of vaccinated children ends up as a single line.

Usage:
    uv run python examples/fhir/engine/fhirpath_over_bundle.py

Needs no DHIS2, no server, and no project: the Bundle is inline.
"""

from __future__ import annotations

from _bundle import MEASLES_VACCINE_CODE, clinic_bundle
from dhis2w_fhir_engine import FHIRPathEvaluator, unwrap_primitives
from pydantic import BaseModel

#: Each row is one expression over the whole Bundle and the question it stands in for.
BUNDLE_EXPRESSIONS: tuple[tuple[str, str], ...] = (
    ("Bundle.entry.resource.count()", "how many resources is this Bundle carrying?"),
    ("Bundle.entry.resource.ofType(Patient).id", "which children are in it?"),
    ("Bundle.entry.resource.ofType(Patient).count()", "how many children?"),
    ("Bundle.entry.resource.ofType(Immunization).count()", "how many doses were recorded?"),
    (
        f"Bundle.entry.resource.ofType(Immunization).where(vaccineCode.coding.code = '{MEASLES_VACCINE_CODE}').count()",
        "how many of those doses were measles doses?",
    ),
    (
        f"Bundle.entry.resource.ofType(Immunization)"
        f".where(vaccineCode.coding.code = '{MEASLES_VACCINE_CODE}').patient.reference",
        "which children did the measles doses go to?",
    ),
    (
        "Bundle.entry.resource.ofType(Observation).valueQuantity.value",
        "every weight recorded, in the unit the Observation states",
    ),
    (
        "Bundle.entry.resource.ofType(Patient).where(gender = 'female').name.family",
        "the family names of the girls",
    ),
    (
        "Bundle.entry.resource.ofType(Patient).where(birthDate > @2023-06-01).id",
        "the children born after a cut-off date",
    ),
)


class BundleAnswer(BaseModel):
    """One expression over the Bundle, the question behind it, and the collection it answered with."""

    question: str
    expression: str
    answer: list[object]


def main() -> None:
    """Run every Bundle expression and print the question, the answer, and the expression that got it."""
    bundle = clinic_bundle()
    evaluator = FHIRPathEvaluator()

    print(f"a {bundle['type']} Bundle of {len(bundle['entry'])} entries - patients, doses, weights, one organisation")
    print()

    for expression, question in BUNDLE_EXPRESSIONS:
        answer = BundleAnswer(
            question=question,
            expression=expression,
            answer=unwrap_primitives(evaluator.evaluate(expression, bundle)),
        )
        print(f"{answer.question}")
        print(f"  {answer.expression}")
        print(f"  -> {answer.answer}")
        print()

    # The same expression is what a rule engine runs: one question, one boolean, no parsing of JSON
    # in Python at all.
    everyone_named = evaluator.evaluate_boolean(
        "Bundle.entry.resource.ofType(Patient).all(name.exists())",
        bundle,
    )
    print(f"every child in the Bundle has a name: {everyone_named}")
    print("ofType() is what makes a Bundle answerable: without it a path walks resources of every type at once.")


if __name__ == "__main__":
    main()
