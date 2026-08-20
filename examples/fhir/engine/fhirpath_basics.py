"""Navigate one FHIR resource with FHIRPath: paths, filters, functions, and a yes-or-no answer.

FHIRPath is the expression language FHIR uses to point at parts of a resource. Every expression
answers with a *collection* - never a bare value - so a path that matches nothing answers with an
empty collection rather than an error, and a path that matches one thing answers with a list of one.
That single rule explains most of what looks surprising below.

A path walks elements by name. `where(...)` keeps the entries a condition holds for. Functions like
`first()`, `count()`, and `exists()` reshape the collection. `evaluate_boolean` is the shorthand for
"did that come back as a single true?", which is what a rule engine actually wants to ask.

`evaluate` hands back FHIR primitives in a wrapper that keeps the element's extensions attached, so
`unwrap_primitives` is what turns them into the plain Python strings and numbers you print.

Usage:
    uv run python examples/fhir/engine/fhirpath_basics.py

Needs no DHIS2, no server, and no project: the resource is inline.
"""

from __future__ import annotations

from _bundle import CLINIC_REGISTER_IDENTIFIER_SYSTEM, one_patient
from dhis2w_fhir_engine import FHIRPathEvaluator, unwrap_primitives
from pydantic import BaseModel

#: Each row is one expression and the sentence that says why anyone would write it.
EXPRESSIONS: tuple[tuple[str, str], ...] = (
    ("Patient.name.family", "walk the path: a name's family name"),
    ("Patient.name.given", "an element that repeats answers with every entry"),
    ("Patient.name.given.first()", "first() takes one entry out of a collection"),
    ("Patient.identifier.value", "both identifiers, in the order the resource lists them"),
    (
        f"Patient.identifier.where(system = '{CLINIC_REGISTER_IDENTIFIER_SYSTEM}').value",
        "where() keeps only the identifier issued by one system",
    ),
    ("Patient.identifier.count()", "count() reduces a collection to its size"),
    ("Patient.name.exists()", "exists() asks whether anything matched at all"),
    ("Patient.deceased.exists()", "an element the resource never carries: empty, not an error"),
    ("Patient.name.select(given.first() & ' ' & family)", "select() builds a new value per entry"),
    ("Patient.birthDate < @2024-01-01", "a date literal, compared with the element"),
)


class ExpressionAnswer(BaseModel):
    """One expression, the collection it answered with, and why the expression was written."""

    expression: str
    purpose: str
    answer: list[object]

    def rendered(self) -> str:
        """The line as it prints: expression, answer, then the reason in the margin."""
        return f"  {self.expression:72}  {self.answer!s:26}  {self.purpose}"


def main() -> None:
    """Evaluate every expression against one Patient and print what each collection came back as."""
    patient = one_patient()
    evaluator = FHIRPathEvaluator()

    print(f"Patient/{patient['id']} - {patient['name'][0]['given'][0]} {patient['name'][0]['family']}")
    print(f"born {patient['birthDate']}, {len(patient['identifier'])} identifier(s)")
    print()

    for expression, purpose in EXPRESSIONS:
        # unwrap_primitives strips the extension-carrying wrapper off FHIR primitives, leaving the
        # plain Python value. Skip it and you print the wrapper's repr instead of the string.
        answer = ExpressionAnswer(
            expression=expression,
            purpose=purpose,
            answer=unwrap_primitives(evaluator.evaluate(expression, patient)),
        )
        print(answer.rendered())

    print()
    # evaluate_boolean is the question a decision rule asks: one entry, and that entry is true.
    active = evaluator.evaluate_boolean("Patient.active", patient)
    female = evaluator.evaluate_boolean("Patient.gender = 'female'", patient)
    print(f"evaluate_boolean('Patient.active')            -> {active}")
    print(f"evaluate_boolean(\"Patient.gender = 'female'\") -> {female}")
    print()
    print("Every answer above is a collection. An empty one means the path matched nothing,")
    print("which is FHIRPath's way of saying 'this resource does not carry that' - not a failure.")


if __name__ == "__main__":
    main()
