"""Answer a question whose DHIS2 data element uses an option set: find the published list, send a code.

A DHIS2 option set is a closed list - "Exclusive, Replacement, Mixed" - and a data element bound to
one accepts nothing else. FHIR splits that single DHIS2 object in two, and the split is the thing
worth learning:

* a **CodeSystem** holds the concepts. Each has a `code` and a `display`, and the code is what
  identifies the option. By default the concept code is the DHIS2 option **UID**, and the DHIS2
  option **code** rides beside it as a `dhis2-code` concept property - so the pair is always
  recoverable, whichever spelling the instance keys its data on.
* a **ValueSet** binds a question to that CodeSystem. `Questionnaire.item.answerValueSet` names the
  ValueSet, never the CodeSystem, so answering means one dereference: read the ValueSet, follow
  `compose.include[].system` to the CodeSystem, and read the concepts from there.

An answer is then a `Coding` naming both halves: `system` is the CodeSystem's canonical and `code`
is one of its published concept codes. Free text is not an answer to a coded question - a `choice`
item is answered `valueCoding` and on nothing else - and a `valueCoding` carrying a code the list
does not publish is refused just as firmly, because a code the guide never defined names no option.

What DHIS2 finally stores is neither of the two things a client sends: it is the option's own DHIS2
code, which the translator resolves the concept back to. So the answer travels as a guide concept
and lands as a DHIS2 option code, and this example prints both ends of that.

Usage:
    uv run python examples/fhir/client/answer_coded_question.py

Reads whichever coded question the example fixture's forms publish first.

How a consumer gets DHIS2 identifiers back from a concept is at
docs/fhir/401-terminology-and-conceptmaps.md.
"""

from __future__ import annotations

import httpx
from _fixture import conversion_context, served_facade
from _runner import run_example
from dhis2w_fhir.conversion import answer_wire_value
from dhis2w_fhir.r4 import (
    CodeSystem,
    Coding,
    FhirBase,
    Questionnaire,
    QuestionnaireItem,
    QuestionnaireResponseAnswer,
    ValueSet,
)
from pydantic import BaseModel

FHIR_JSON = "application/fhir+json"

#: The concept property carrying the DHIS2 option code when the concept code is the DHIS2 option UID.
OPTION_CODE_PROPERTY = "dhis2-code"

#: A code no generated guide publishes, which is what a client sending its own vocabulary would send.
UNPUBLISHED_CODE = "PARTIAL_BREASTFEEDING"


class CodedQuestion(BaseModel):
    """One published question whose answers are constrained to an option set, and the form asking it."""

    form_id: str
    form_title: str
    link_id: str
    text: str
    value_set: str


def _coded_questions(items: list[QuestionnaireItem] | None, form: Questionnaire) -> list[CodedQuestion]:
    """Every question of one form's tree whose answers are bound to a published option list."""
    found: list[CodedQuestion] = []
    for item in items or []:
        if item.answerValueSet:
            found.append(
                CodedQuestion(
                    form_id=form.id or "-",
                    form_title=form.title or "-",
                    link_id=item.linkId or "-",
                    text=item.text or "-",
                    value_set=item.answerValueSet,
                )
            )
        found.extend(_coded_questions(item.item, form))
    return found


async def _find_by_url[T: FhirBase](
    client: httpx.AsyncClient, model: type[T], resource_type: str, url: str
) -> T | None:
    """Find one published terminology resource by its canonical, which is how a client resolves a binding."""
    bundle = (await client.get(f"/{resource_type}", params={"url": url})).raise_for_status().json()
    entries = bundle.get("entry", [])
    return model.model_validate(entries[0]["resource"]) if entries else None


async def main() -> None:
    """Resolve one coded question's published option list, then answer it right and two ways wrong."""
    async with httpx.AsyncClient(base_url=served_facade(), headers={"Accept": FHIR_JSON}, timeout=30.0) as client:
        bundle = (await client.get("/Questionnaire", params={"_count": 100})).raise_for_status().json()
        questions = [
            question
            for entry in bundle.get("entry", [])
            for form in [Questionnaire.model_validate(entry["resource"])]
            for question in _coded_questions(form.item, form)
        ]
        if not questions:
            print("no published form binds a question to an option set, so there is nothing to answer here")
            return
        question = questions[0]
        print(f"{question.text} ({question.link_id}) on {question.form_title}")
        print(f"  answers are bound to {question.value_set}")

        # The question names a ValueSet; the concepts live in the CodeSystem that ValueSet composes.
        value_set = await _find_by_url(client, ValueSet, "ValueSet", question.value_set)
        includes = (value_set.compose.include if value_set and value_set.compose else None) or []
        system = includes[0].system if includes else None
        if system is None:
            print("  that ValueSet composes no CodeSystem this server publishes")
            return
        code_system = await _find_by_url(client, CodeSystem, "CodeSystem", system)
        if code_system is None:
            print(f"  {system} is not published here, so no answer to this question can be checked")
            return

    print(f"  which composes {system}")
    print(f"  {code_system.description}")
    for concept in code_system.concept or []:
        dhis2_code = next(
            (prop.valueString for prop in concept.property or [] if prop.code == OPTION_CODE_PROPERTY), "-"
        )
        print(f"    {concept.code:14} {concept.display:24} DHIS2 option code {dhis2_code}")

    context = conversion_context()
    specification = next(
        (
            form.questions[question.link_id]
            for form in context.forms.values()
            if form.canonical.endswith(f"/Questionnaire/{question.form_id}") and question.link_id in form.questions
        ),
        None,
    )
    if specification is None:
        print("  the translation context does not carry that form, so no answer can be translated here")
        return

    print()
    published = (code_system.concept or [])[0]
    right = QuestionnaireResponseAnswer(valueCoding=Coding(system=system, code=published.code))
    landed = answer_wire_value(specification, [right], context)
    print(f"answered {published.code} ({published.display}): DHIS2 stores the data value {landed.value!r}")
    for note in landed.notes:
        print(f"  note: {note.category} - {note.message}")

    unpublished = QuestionnaireResponseAnswer(valueCoding=Coding(system=system, code=UNPUBLISHED_CODE))
    for refusal in answer_wire_value(specification, [unpublished], context).refusals:
        print(f"answered {UNPUBLISHED_CODE}: {refusal.category} - {refusal.reason}")

    free_text = QuestionnaireResponseAnswer(valueString=published.display)
    for refusal in answer_wire_value(specification, [free_text], context).refusals:
        print(f"answered as free text: {refusal.category} - {refusal.reason}")


if __name__ == "__main__":
    run_example(main)
