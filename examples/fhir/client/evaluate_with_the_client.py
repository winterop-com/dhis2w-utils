"""Ask a facade a FHIRPath question with `FacadeClient` - an inline document, a stored one, and a typo.

`evaluate_via_facade.py` next door posts the same request over plain httpx, which is worth reading
for what the wire carries. This is the typed path: the two contexts are models, the answer is an
`EvaluationOutcome`, and nothing here spells a JSON key.

The two contexts are the two places a document can be:

- **`InlineResourceContext.over(...)`** carries the document in the request. `over` takes a typed R4
  model or a parsed document, so a caller holding either is one call from an evaluation - which is
  what makes it the way to check a draft before anybody submits it.
- **`StoredResourceContext`** names a resource the facade already holds, by type and id. Nothing is
  posted; the expression runs over exactly what a read of that address would have answered.

A third, `RegisteredEntityContext`, evaluates over one tracked entity read live out of DHIS2 -
`evaluate_registered_person.py` is that story.

**A bad expression is an answer, not a refusal.** A source that will not parse comes back as a 200
carrying the line and column the parser stopped on, so `evaluate` returns an outcome rather than
raising. `FacadeError` is reserved for a request the facade cannot serve at all.

Usage:
    uv run python examples/fhir/client/evaluate_with_the_client.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on the
example project and stops it at exit - which is what lets this run unattended.
"""

from __future__ import annotations

import os
import sys

from _fixture import aggregate_form_id, served_facade
from _runner import run_example
from dhis2w_fhir import (
    EvaluationLanguage,
    EvaluationOutcome,
    FacadeClient,
    InlineResourceContext,
    StoredResourceContext,
)

#: Makes the generated draft byte-reproducible, so two runs evaluate over the same answers.
SEED = 20260

#: What to ask of the draft carried in the request - one line each about the document itself.
INLINE_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("QuestionnaireResponse.questionnaire", "which published form this draft answers"),
    ("QuestionnaireResponse.status", "how far along it is - a capture is submitted as completed"),
    ("QuestionnaireResponse.descendants().answer.count()", "how many answers it carries, at any depth"),
    (
        "QuestionnaireResponse.descendants().where(answer.exists()).linkId.first()",
        "the first cell answered - {dataElement}.{categoryOptionCombo}, the identity DHIS2 files it under",
    ),
)

#: What to ask of the form the facade already holds - one line each about the DHIS2 data set behind it.
STORED_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("Questionnaire.title", "the DHIS2 data set's own name, carried through unchanged"),
    ("Questionnaire.item.text", "the sections, which are the data set's own section names"),
    ("Questionnaire.item.item.item.count()", "the answerable cells - one per category combination"),
)

#: An expression with a bracket nobody closed, which is what a person typing into a box produces.
UNPARSEABLE = "Questionnaire.item.where(text = 'Anaemia'"


async def main() -> None:
    """Evaluate over a draft in the request, over a form on the server, and over an expression that will not parse."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()
    form_id = aggregate_form_id()

    async with FacadeClient(base_url) as facade:
        print(f"evaluating against {facade.base_url}")

        # INLINE. The draft has never been submitted and the facade will never hold it - the whole
        # document travels with the question, and the expression is checked against exactly it.
        # `over` also takes a parsed document, for a caller who has JSON rather than a model.
        draft = await facade.generate(form_id, seed=SEED)
        inline = InlineResourceContext.over(draft)
        print(f"\ninline context: a draft of {form_id}, carried in the request and stored nowhere")
        for expression, why in INLINE_QUESTIONS:
            outcome = await facade.evaluate(EvaluationLanguage.FHIRPATH, expression, context=inline)
            print(f"  {expression}")
            print(f"    {said(outcome)}")
            print(f"    {why}")

        # STORED. The document is already on the server, so the request carries the question and the
        # address and nothing else. This is what turns a served guide into something interrogable.
        stored = StoredResourceContext(resource_type="Questionnaire", resource_id=form_id)
        print(f"\nstored context: Questionnaire/{form_id}, read off the server rather than posted")
        for expression, why in STORED_QUESTIONS:
            outcome = await facade.evaluate(EvaluationLanguage.FHIRPATH, expression, context=stored)
            print(f"  {expression}")
            print(f"    {said(outcome)}")
            print(f"    {why}")

        # A TYPO. No exception: the outcome carries the diagnostic, with the position the parser
        # stopped at, which is what an editor underlines.
        outcome = await facade.evaluate(EvaluationLanguage.FHIRPATH, UNPARSEABLE, context=stored)
        print(f"\nan expression that will not parse: {UNPARSEABLE}")
        print(f"  {said(outcome)}")
        print("  answered, not raised - `evaluate` raises only when the facade cannot serve the request at all")


def said(outcome: EvaluationOutcome) -> str:
    """One outcome as a line to read: the collection it answered, or the diagnostic that stopped it."""
    for diagnostic in outcome.diagnostics:
        where = f" at line {diagnostic.line}, column {diagnostic.column}" if diagnostic.line is not None else ""
        return f"{diagnostic.kind} error{where}: {diagnostic.message.splitlines()[0]}"
    values = outcome.results[0].values if outcome.results else ()
    if not values:
        return "matched nothing - the document does not say"
    if len(values) == 1:
        return f"{values[0]!r}"
    return f"{list(values)}"


if __name__ == "__main__":
    run_example(main)
